"""End-to-end API workflows with in-memory data and a deterministic clock."""

import base64
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from booking.domain import QualificationStatus
from booking.authentication import issue_demo_token
from booking.runtime import get_service, reset_runtime


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII="
)
NOW = datetime(2026, 10, 5, 0, tzinfo=timezone.utc)
SYDNEY = ZoneInfo("Australia/Sydney")


class BookingAPIFixtureMixin:
    def setUp(self):
        reset_runtime()
        self.service = get_service()
        self.service.clock = lambda: NOW
        self.service.min_advance_days, self.service.max_advance_days = 0, 7  # workflow tests book a few days ahead; see test_booking_window.py
        self.client = APIClient()
        self.verified = self.login("z1000001")
        self.student = self.login("z1000002")
        self.admin = self.login("z9000001")
        self.manager = self.login("z9000002")
        resources = self.items(self.verified.get("/api/v1/resources/"))
        self.room = next(item for item in resources if item["kind"] == "ROOM")
        self.equipment = next(item for item in resources if item["kind"] == "EQUIPMENT")
        self.requirement_id = self.room["required_qualification_id"]
        # Keep these tests independent of when the demo seed was created.
        for submission in self.service.repo.list_submissions():
            if submission.status == QualificationStatus.VERIFIED:
                self.service.repo.save_submission(replace(submission, valid_until=None))

    def login(self, zid):
        client = APIClient()
        staff = next((item for item in get_service().repo.list_principals() if item.zid == zid and item.is_staff), None)
        if staff is not None:
            # Staff sign in with a password on the staff page (see test_staff_sign_in.py); skip the slow hash here.
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_demo_token(staff)}")
            return client
        response = client.post("/api/v1/auth/demo-login/", {"zid": zid}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access_token']}")
        return client

    def items(self, response):
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        self.assertIn("count", response.data)
        self.assertEqual(response.data["count"], len(response.data["results"]))
        return response.data["results"]

    def payload(self, resource=None, day_offset=3, hour=10, minutes=60):
        start = (NOW.astimezone(SYDNEY) + timedelta(days=day_offset)).replace(
            hour=hour, minute=0, second=0, microsecond=0
        )
        return {
            "resource_id": (resource or self.room)["id"],
            "start": start.isoformat(),
            "end": (start + timedelta(minutes=minutes)).isoformat(),
            "purpose": "Sprint 1 practical session",
        }

    def submit(self, client=None, **overrides):
        data = {
            "requirement_id": self.requirement_id,
            "title": "Laboratory induction",
            "notes": "Training completed; please verify the attached certificate.",
            "file": SimpleUploadedFile("induction.png", PNG, content_type="image/png"),
        }
        data.update(overrides)
        response = (client or self.student).post("/api/v1/qualifications/", data, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def approve(self, booking, client=None):
        """Admin approval of a pending request (every new request starts as PENDING_APPROVAL)."""
        booking_id = booking["id"] if isinstance(booking, dict) else booking.data["id"]
        response = (client or self.admin).post(f"/api/v1/admin/bookings/{booking_id}/review/", {"decision": "APPROVED"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def create_approved(self, client=None, payload=None):
        response = self.create_booking(client, payload)
        self.assertEqual(response.status_code, 201, response.data)
        return self.approve(response)

    def verify_student(self, client=None):
        """Upload and verify an induction for z1000002 (or the given client), so they may book."""
        submission = self.submit(client)
        reviewed = self.admin.post(f"/api/v1/admin/qualifications/{submission['id']}/review/", {"decision": "VERIFIED"}, format="json")
        self.assertEqual(reviewed.status_code, 200, reviewed.data)
        return submission

    def create_booking(self, client=None, payload=None, **headers):
        return (client or self.verified).post(
            "/api/v1/bookings/", payload or self.payload(), format="json", **headers
        )

    def assert_error(self, response, status):
        self.assertEqual(response.status_code, status, getattr(response, "data", None))
        self.assertIn("error", response.data)
        self.assertIn("code", response.data["error"])
        self.assertIn("message", response.data["error"])

@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class BookingAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def test_invalid_resource_identifier_has_a_json_error_for_the_frontend(self):
        response = self.verified.get("/api/v1/resources/not-a-uuid/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")

    def test_missing_resource_policy_cannot_bypass_the_induction_gate(self):
        resource = self.service.repo.get_resource(self.room["id"])
        self.service.repo.save_resource(replace(resource, required_qualification_id=None))
        response = self.create_booking(client=self.student)
        self.assert_error(response, 409)
        self.assertEqual(response.data["error"]["code"], "RESOURCE_POLICY_NOT_CONFIGURED")
        self.assertEqual(self.service.repo.list_bookings(), [])

    def test_demo_registration_does_not_accept_privileged_role(self):
        response = self.client.post(
            "/api/v1/auth/demo-register/",
            {"zid": "z2000001", "display_name": "Demo student", "university_email": "z2000001@ad.unsw.edu.au", "role": "ADMIN"},
            format="json",
        )
        self.assert_error(response, 400)
        valid = self.client.post(
            "/api/v1/auth/demo-register/",
            {"zid": "z2000001", "display_name": "Demo student", "university_email": "z2000001@ad.unsw.edu.au"}, format="json",
        )
        self.assertEqual(valid.status_code, 201, valid.data)
        self.assertEqual(valid.data["user"]["role"], "STUDENT")
        self.assertEqual(valid.data["user"]["university_email"], "z2000001@ad.unsw.edu.au")

    def test_demo_auth_is_hidden_when_debug_or_demo_flag_is_disabled(self):
        for flags in ({"DEBUG": False}, {"ENABLE_DEMO_AUTH": False}):
            with self.subTest(flags=flags), override_settings(**flags):
                response = self.client.post(
                    "/api/v1/auth/demo-login/", {"zid": "z1000001"}, format="json"
                )
                self.assertEqual(response.status_code, 404)
                response = self.client.post(
                    "/api/v1/auth/demo-register/",
                    {"zid": "z2000002", "display_name": "Demo student", "university_email": "z2000002@ad.unsw.edu.au"}, format="json",
                )
                self.assertEqual(response.status_code, 404)
                self.assertEqual(self.verified.get("/api/v1/auth/me/").status_code, 401)

    def test_client_identity_headers_and_invalid_bearer_do_not_authenticate(self):
        response = self.client.get(
            "/api/v1/admin/bookings/", HTTP_X_USER_ROLE="ADMIN", HTTP_X_USER_ZID="z9000001"
        )
        self.assert_error(response, 401)
        response = self.client.get(
            "/api/v1/auth/me/", HTTP_AUTHORIZATION="Bearer invented-token"
        )
        self.assert_error(response, 401)

    def test_student_without_induction_can_log_in_but_cannot_request_booking(self):
        self.assertEqual(self.student.get("/api/v1/auth/me/").status_code, 200)
        self.assert_error(self.create_booking(self.student), 403)
        self.assertEqual(self.items(self.student.get("/api/v1/bookings/")), [])

    def test_pending_request_holds_slot_against_later_requests(self):
        self.verify_student()
        waiting = self.create_booking(self.student)
        self.assertEqual(waiting.status_code, 201, waiting.data)
        self.assertEqual(waiting.data["status"], "PENDING_APPROVAL")
        self.assertIsNotNone(waiting.data["review_due_at"])
        self.assertTrue(waiting.data["hold_active"])
        self.assertTrue(waiting.data["blocks_slot"])
        later = self.create_booking(self.verified)
        self.assertEqual(later.status_code, 201, later.data)
        self.assertEqual(later.data["status"], "WAITLISTED")
        self.assertEqual(later.data["reason_code"], "TEMPORARY_HOLD_CONFLICT")
        self.assertEqual(later.data["waitlist_position"], 1)
        self.assertIsNone(later.data["hold_until"])

    def test_verified_student_can_book_room_and_equipment_and_view_own_dashboard(self):
        for resource in (self.room, self.equipment):
            with self.subTest(kind=resource["kind"]):
                response = self.create_booking(payload=self.payload(resource))
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(response.data["status"], "PENDING_APPROVAL")
                self.assertEqual(self.approve(response)["status"], "APPROVED")
        self.assertEqual(len(self.items(self.verified.get("/api/v1/bookings/"))), 2)
        self.assertEqual(self.verified.get("/api/v1/dashboard/").status_code, 200)

    def test_induction_under_review_blocks_requests_until_it_is_verified(self):
        submission = self.submit()
        self.assert_error(self.create_booking(self.student), 403)
        review = self.admin.post(f"/api/v1/admin/qualifications/{submission['id']}/review/", {"decision": "VERIFIED"}, format="json")
        self.assertEqual(review.status_code, 200, review.data)
        self.assertEqual(review.data["updated_bookings"], [])
        self.assertEqual(self.create_booking(self.student).data["status"], "PENDING_APPROVAL")

    def test_conflict_is_waitlisted_and_promoted_to_pending_after_cancellation(self):
        first = self.create_approved()
        self.verify_student()
        conflict = self.create_booking(self.student)
        self.assertEqual(conflict.status_code, 201, conflict.data)
        self.assertEqual((conflict.data["status"], conflict.data["reason_code"]), ("WAITLISTED", "TIME_CONFLICT"))
        rejected_approval = self.admin.post(f"/api/v1/admin/bookings/{conflict.data['id']}/review/", {"decision": "APPROVED"}, format="json")
        self.assert_error(rejected_approval, 409)
        cancelled = self.verified.post(f"/api/v1/bookings/{first['id']}/cancel/", {}, format="json")
        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        promoted = self.student.get(f"/api/v1/bookings/{conflict.data['id']}/")
        self.assertEqual((promoted.data["status"], promoted.data["reason_code"]), ("PENDING_APPROVAL", "PROMOTED_FROM_WAITLIST"))
        self.assertEqual(self.approve(promoted.data)["status"], "APPROVED")

    def test_same_student_cannot_request_overlapping_time_for_same_resource_twice(self):
        first = self.create_booking(payload=self.payload(hour=10))
        self.assertEqual(first.status_code, 201, first.data)

        exact = self.create_booking(payload=self.payload(hour=10))
        self.assert_error(exact, 409)
        self.assertEqual(exact.data["error"]["code"], "DUPLICATE_BOOKING")
        self.assertEqual(exact.data["error"]["details"]["booking_id"], first.data["id"])

        overlapping = self.payload(hour=10)
        start = datetime.fromisoformat(overlapping["start"]) + timedelta(minutes=30)
        overlapping["start"] = start.isoformat()
        overlapping["end"] = (start + timedelta(hours=1)).isoformat()
        overlap = self.create_booking(payload=overlapping)
        self.assert_error(overlap, 409)
        self.assertEqual(overlap.data["error"]["code"], "DUPLICATE_BOOKING")
        self.assertEqual(len(self.items(self.verified.get("/api/v1/bookings/"))), 1)

    def test_cancelled_request_does_not_prevent_booking_same_time_again(self):
        first = self.create_booking()
        cancelled = self.verified.post(
            f"/api/v1/bookings/{first.data['id']}/cancel/", {}, format="json",
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        replacement = self.create_booking()
        self.assertEqual(replacement.status_code, 201, replacement.data)
        self.assertEqual(replacement.data["status"], "PENDING_APPROVAL")

    def test_review_window_end_approves_through_process_due(self):
        waiting = self.create_booking().data
        self.service.clock = lambda: NOW + timedelta(hours=23, minutes=59)
        self.admin.post("/api/v1/admin/process-due/", {}, format="json")
        self.assertEqual(self.verified.get(f"/api/v1/bookings/{waiting['id']}/").data["status"], "PENDING_APPROVAL")
        self.service.clock = lambda: NOW + timedelta(hours=24)
        processed = self.admin.post("/api/v1/admin/process-due/", {}, format="json")
        self.assertEqual(processed.status_code, 200, processed.data)
        self.assertEqual(self.verified.get(f"/api/v1/bookings/{waiting['id']}/").data["status"], "APPROVED")

    def test_unresolved_booking_expires_at_start_time(self):
        payload = self.payload(day_offset=0, hour=15)
        response = self.create_booking(self.verified, payload)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["review_due_at"], response.data["start"])  # window capped at the start
        self.service.clock = lambda: datetime.fromisoformat(payload["start"])
        self.admin.post("/api/v1/admin/process-due/", {}, format="json")
        detail = self.verified.get(f"/api/v1/bookings/{response.data['id']}/")
        self.assertEqual(detail.data["status"], "EXPIRED")

    def test_approved_booking_is_private_and_only_its_owner_can_cancel(self):
        booking = self.create_approved()
        self.assertEqual(self.items(self.student.get("/api/v1/bookings/")), [])
        self.assert_error(self.student.get(f"/api/v1/bookings/{booking['id']}/"), 404)
        self.assert_error(
            self.student.post(f"/api/v1/bookings/{booking['id']}/cancel/", {}, format="json"), 404
        )
        detail = self.verified.get(f"/api/v1/bookings/{booking['id']}/")
        self.assertEqual(detail.data["status"], "APPROVED")

    def test_owner_can_reschedule_an_approved_booking_but_not_into_a_conflict(self):
        booking = self.create_approved()
        occupied = self.create_approved(payload=self.payload(day_offset=4, hour=14))
        conflict = self.verified.post(f"/api/v1/bookings/{booking['id']}/reschedule/", {
            "start": occupied["start"], "end": occupied["end"],
        }, format="json")
        self.assert_error(conflict, 409)
        self.assertEqual(conflict.data["error"]["code"], "DUPLICATE_BOOKING")
        self.verify_student()
        held = self.create_booking(self.student, self.payload(day_offset=6, hour=14)).data
        self.assertTrue(held["hold_active"])
        held_conflict = self.verified.post(f"/api/v1/bookings/{booking['id']}/reschedule/", {
            "start": held["start"], "end": held["end"],
        }, format="json")
        self.assert_error(held_conflict, 409)
        self.assertEqual(held_conflict.data["error"]["code"], "BOOKING_HOLD_CONFLICT")
        self.assertEqual(held_conflict.data["error"]["details"]["hold_until"], held["hold_until"])
        new_period = self.payload(day_offset=5, hour=15)
        moved = self.verified.post(f"/api/v1/bookings/{booking['id']}/reschedule/", {
            "start": new_period["start"], "end": new_period["end"],
        }, format="json")
        self.assertEqual(moved.status_code, 200, moved.data)
        self.assertEqual(moved.data["start"], datetime.fromisoformat(new_period["start"]).astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))
        self.assertEqual(moved.data["revision"], 2)
        self.assertTrue(any(item.action == "BOOKING_RESCHEDULED" and item.entity_id == booking["id"]
                            for item in self.service.repo.list_audit()))
        self.assert_error(self.student.post(f"/api/v1/bookings/{booking['id']}/reschedule/", {
            "start": new_period["start"], "end": new_period["end"],
        }, format="json"), 404)

    def test_student_cannot_use_admin_endpoints(self):
        for endpoint in ("bookings", "qualifications"):
            with self.subTest(endpoint=endpoint):
                self.assert_error(self.student.get(f"/api/v1/admin/{endpoint}/"), 403)
        self.assert_error(
            self.student.post("/api/v1/admin/process-due/", {}, format="json"), 403
        )

    def test_manager_can_review_induction_and_repeated_review_is_rejected(self):
        submission = self.submit()
        listed = self.manager.get("/api/v1/admin/qualifications/")
        self.assertEqual(listed.status_code, 200)
        row = next(item for item in listed.data["results"] if item["id"] == submission["id"])
        self.assertEqual(set(row["student"]), {"id", "zid", "display_name", "university_email"})
        self.assertEqual(row["student"]["id"], submission["student_id"])
        url = f"/api/v1/admin/qualifications/{submission['id']}/review/"
        reviewed = self.manager.post(url, {"decision": "VERIFIED"}, format="json")
        self.assertEqual(reviewed.status_code, 200, reviewed.data)
        self.assertEqual(reviewed.data["submission"]["status"], "VERIFIED")
        self.assert_error(self.admin.post(url, {"decision": "VERIFIED"}, format="json"), 409)

    def test_induction_attachment_is_private_and_real_content_is_preserved(self):
        submission = self.submit()
        url = f"/api/v1/qualifications/{submission['id']}/file/"
        for client in (self.student, self.admin):
            with self.subTest(client=client):
                response = client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b"".join(response.streaming_content), PNG)
                self.assertEqual(response["Content-Type"], "image/png")
        self.assert_error(self.verified.get(url), 404)
        self.assert_error(self.client.get(url), 401)
        self.assertEqual(self.items(self.verified.get("/api/v1/qualifications/"))[0]["status"], "VERIFIED")

    def test_spoofed_and_oversized_attachments_are_rejected(self):
        for content, content_type in (
            (b"this is not an image", "image/png"),
            (PNG + b"x" * (5 * 1024 * 1024), "image/png"),
        ):
            with self.subTest(size=len(content)):
                response = self.student.post(
                    "/api/v1/qualifications/",
                    {
                        "requirement_id": self.requirement_id, "title": "Induction",
                        "file": SimpleUploadedFile("proof.png", content, content_type=content_type),
                    }, format="multipart",
                )
                self.assert_error(response, 400)
        self.assertEqual(self.items(self.student.get("/api/v1/qualifications/")), [])

    def test_rejection_requires_reason_and_rejected_induction_blocks_new_request(self):
        submission = self.submit()
        url = f"/api/v1/admin/qualifications/{submission['id']}/review/"
        self.assert_error(self.admin.post(url, {"decision": "REJECTED"}, format="json"), 400)
        reviewed = self.admin.post(
            url, {"decision": "REJECTED", "reason": "Certificate does not cover this laboratory"},
            format="json",
        )
        self.assertEqual(reviewed.status_code, 200, reviewed.data)
        self.assertEqual(reviewed.data["submission"]["status"], "REJECTED")
        self.assert_error(self.create_booking(self.student), 403)

    def test_unknown_resource_invalid_range_and_naive_timestamp_are_rejected(self):
        invalids = [
            ({**self.payload(), "resource_id": str(uuid4())}, 404),
            ({**self.payload(), "end": self.payload()["start"]}, 400),
            ({**self.payload(), "start": "2026-10-08T10:00:00"}, 400),
            (self.payload(hour=7), 400),
        ]
        for payload, status in invalids:
            with self.subTest(payload=payload):
                self.assert_error(self.create_booking(payload=payload), status)

    def test_adjacent_bookings_are_allowed_and_utc_equivalent_times_conflict(self):
        first = self.create_booking(payload=self.payload(hour=10))
        self.assertEqual(first.data["status"], "PENDING_APPROVAL")
        adjacent = self.create_booking(payload=self.payload(hour=11))
        self.assertEqual(adjacent.data["status"], "PENDING_APPROVAL")
        payload = self.payload(hour=10)
        payload["start"] = datetime.fromisoformat(payload["start"]).astimezone(timezone.utc).isoformat()
        payload["end"] = datetime.fromisoformat(payload["end"]).astimezone(timezone.utc).isoformat()
        same_instant = self.create_booking(payload=payload)
        self.assert_error(same_instant, 409)
        self.assertEqual(same_instant.data["error"]["code"], "DUPLICATE_BOOKING")

    def test_idempotency_key_replays_original_and_rejects_changed_payload(self):
        first = self.create_booking(HTTP_IDEMPOTENCY_KEY="one-click")
        second = self.create_booking(HTTP_IDEMPOTENCY_KEY="one-click")
        self.assertIn(first.status_code, (200, 201), first.data)
        self.assertIn(second.status_code, (200, 201), second.data)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(len(self.items(self.verified.get("/api/v1/bookings/"))), 1)
        changed = self.create_booking(payload=self.payload(hour=12), HTTP_IDEMPOTENCY_KEY="one-click")
        self.assert_error(changed, 409)

    def test_availability_does_not_publish_other_students_booking_details(self):
        booking = self.create_approved()
        own_response = self.verified.get(
            f"/api/v1/resources/{self.room['id']}/availability/",
            {"date": "2026-10-08", "duration_minutes": 60},
        )
        response = self.student.get(
            f"/api/v1/resources/{self.room['id']}/availability/",
            {"date": "2026-10-08", "duration_minutes": 60},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("z1000001", str(response.data))
        self.assertNotIn("Sprint 1 practical session", str(response.data))
        self.assertFalse(response.data["can_request"])
        slots = {
            datetime.fromisoformat(item["start"]).astimezone(SYDNEY).time(): item
            for item in response.data["slots"]
        }
        self.assertFalse(slots[datetime(2026, 10, 8, 10).time()]["available"])
        self.assertEqual(slots[datetime(2026, 10, 8, 10).time()]["reason_code"], "BOOKED")
        self.assertFalse(slots[datetime(2026, 10, 8, 10).time()]["requested_by_me"])
        self.assertTrue(slots[datetime(2026, 10, 8, 11).time()]["available"])
        own_slots = {
            datetime.fromisoformat(item["start"]).astimezone(SYDNEY).time(): item
            for item in own_response.data["slots"]
        }
        self.assertTrue(own_slots[datetime(2026, 10, 8, 10).time()]["requested_by_me"])
        self.assertNotIn("booking_id", own_slots[datetime(2026, 10, 8, 10).time()])
        self.assertEqual(booking["status"], "APPROVED")

    @override_settings(AUTH_PROVIDER="booking.authentication.DisabledIdentityProvider")
    def test_unconfigured_sso_rejects_bearer_without_trusting_client_claims(self):
        response = self.client.get(
            "/api/v1/auth/me/", HTTP_AUTHORIZATION="Bearer z9000001",
            HTTP_X_USER_ROLE="ADMIN",
        )
        self.assert_error(response, 401)
        self.assertEqual(response.data["error"]["code"], "SSO_NOT_CONFIGURED")

    def test_openapi_document_is_available_without_authentication(self):
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["openapi"].startswith("3."))
        self.assertIn("/api/v1/bookings/", data["paths"])
