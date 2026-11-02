"""HTTP boundaries for the separate, Manager-only single-duration exemption."""
from dataclasses import replace
from datetime import datetime, timedelta

from django.test import SimpleTestCase, override_settings

from booking.tests.test_api import BookingAPIFixtureMixin, NOW, SYDNEY


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class LongBookingAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.now = NOW
        self.service.clock = lambda: self.now
        self.service.min_advance_days, self.service.max_advance_days = 7, 28

    def long_payload(self, **overrides):
        return {**self.payload(day_offset=8, minutes=240),
                "long_booking_reason": "The continuous experiment needs four uninterrupted hours.", **overrides}

    def create_long(self, client=None, payload=None, key=None):
        return (client or self.verified).post(
            "/api/v1/bookings/long-bookings/", payload or self.long_payload(), format="json",
            **({"HTTP_IDEMPOTENCY_KEY": key} if key else {}))

    def review(self, booking_id, client=None, decision="APPROVED", **extra):
        return (client or self.manager).post(f"/api/v1/admin/bookings/{booking_id}/review/",
                                             {"decision": decision, **extra}, format="json")

    def test_separate_endpoint_rejects_unqualified_users_and_privilege_fields(self):
        self.assertEqual(self.create_long(self.client).status_code, 401)
        self.assertEqual(self.create_long(self.student).status_code, 403)
        for changes in ({"long_booking_reason": " "}, {"long_booking": True}, {"additional_hours": True},
                        {"urgent": True}, {"series_id": self.room["id"]}, {"reviewed_by": "SYSTEM"}):
            with self.subTest(changes=changes):
                denied = self.create_long(payload=self.long_payload(**changes))
                self.assertEqual(denied.status_code, 400, denied.data)
        normal = self.verified.post("/api/v1/bookings/", self.payload(day_offset=8, minutes=240), format="json")
        self.assertEqual((normal.status_code, normal.data["error"]["code"]), (400, "DURATION_LIMIT"))
        extra = self.verified.post("/api/v1/bookings/additional-hours/",
                                   {**self.payload(day_offset=8, minutes=240), "additional_hours_reason": "Spare capacity"},
                                   format="json")
        self.assertEqual((extra.status_code, extra.data["error"]["code"]), (400, "DURATION_LIMIT"))

    def test_idempotency_preserves_the_request_kind_and_justification(self):
        created = self.create_long(key="long-request")
        self.assertEqual(created.status_code, 201, created.data)
        booking = created.data
        self.assertTrue(booking["long_booking"])
        self.assertFalse(booking["additional_hours"])
        self.assertEqual(booking["long_booking_reason"], self.long_payload()["long_booking_reason"])
        self.assertEqual(booking["status"], "PENDING_APPROVAL")
        self.assertTrue(booking["hold_active"])
        replay = self.create_long(key="long-request")
        self.assertEqual((replay.status_code, replay.data["id"]), (200, booking["id"]))
        changed = self.create_long(payload=self.long_payload(long_booking_reason="Different experiment"), key="long-request")
        self.assertEqual((changed.status_code, changed.data["error"]["code"]), (409, "IDEMPOTENCY_CONFLICT"))
        for endpoint, body in (("", self.payload(day_offset=8, minutes=240)),
                               ("additional-hours/", {**self.payload(day_offset=8, minutes=240),
                                                      "additional_hours_reason": "Extra time"})):
            denied = self.verified.post(f"/api/v1/bookings/{endpoint}", body, format="json",
                                        HTTP_IDEMPOTENCY_KEY="long-request")
            self.assertEqual((denied.status_code, denied.data["error"]["code"]), (409, "IDEMPOTENCY_CONFLICT"))

    def test_only_manager_may_approve_or_reject_and_creator_cannot_review(self):
        created = self.create_long()
        self.assertEqual(created.status_code, 201, created.data)
        for client in (self.verified, self.admin):
            for decision in ("APPROVED", "REJECTED"):
                denied = self.review(created.data["id"], client, decision, reason="Review")
                self.assertEqual(denied.status_code, 403, denied.data)
        approved = self.review(created.data["id"])
        self.assertEqual((approved.status_code, approved.data["status"]), (200, "APPROVED"))
        self.assertIsNotNone(approved.data["reviewed_by"])
        on_behalf = self.create_long(self.manager, self.long_payload(**self.payload(day_offset=9, minutes=240),
                                                                   on_behalf_of_zid="z1000001"))
        self.assertEqual(on_behalf.status_code, 201, on_behalf.data)
        denied = self.review(on_behalf.data["id"], decision="REJECTED", reason="Own request")
        self.assertEqual((denied.status_code, denied.data["error"]["code"]), (403, "SELF_REVIEW_FORBIDDEN"))
        student_on_behalf = self.create_long(payload=self.long_payload(on_behalf_of_zid="z1000002"))
        self.assertEqual(student_on_behalf.status_code, 403, student_on_behalf.data)

    def test_unreviewed_request_expires_at_review_deadline_and_releases_capacity(self):
        created = self.create_long()
        self.assertEqual(created.status_code, 201, created.data)
        deadline = datetime.fromisoformat(created.data["review_due_at"].replace("Z", "+00:00"))
        self.now = deadline - timedelta(seconds=1)
        detail = self.verified.get(f"/api/v1/bookings/{created.data['id']}/")
        self.assertEqual(detail.data["status"], "PENDING_APPROVAL")
        self.now = deadline
        expired = self.verified.get(f"/api/v1/bookings/{created.data['id']}/")
        self.assertEqual(expired.data["status"], "EXPIRED")
        self.assertEqual(expired.data["reason_code"], "LONG_BOOKING_REVIEW_EXPIRED")
        self.assertFalse(expired.data["blocks_slot"])
        late = self.review(created.data["id"])
        self.assertEqual(late.status_code, 409, late.data)

    def test_availability_exposes_long_lengths_but_keeps_the_normal_date_window(self):
        path = f"/api/v1/resources/{self.room['id']}/availability/"
        today = NOW.astimezone(SYDNEY).date()
        query = {"date": (today + timedelta(days=8)).isoformat(), "long_booking": "true"}
        # The picker queries small timeline cells even though its final selected period must exceed the normal cap.
        available = self.verified.get(path, {**query, "duration_minutes": 30})
        self.assertEqual(available.status_code, 200, available.data)
        self.assertTrue(available.data["long_booking"])
        self.assertEqual(available.data["normal_max_booking_minutes"], 180)
        self.assertEqual(available.data["min_booking_minutes"], 210)
        self.assertEqual(available.data["max_booking_minutes"], self.room["max_booking_minutes"])
        self.assertEqual((available.data["min_advance_days"], available.data["max_advance_days"]), (7, 28))
        for other in ("urgent", "additional_hours"):
            denied = self.verified.get(path, {**query, other: "true"})
            self.assertEqual(denied.status_code, 400, denied.data)
        for day, code in ((6, "BOOKING_TOO_SOON"), (29, "BOOKING_TOO_FAR_AHEAD")):
            denied = self.create_long(payload=self.long_payload(**self.payload(day_offset=day, minutes=240)))
            self.assertEqual((denied.status_code, denied.data["error"]["code"]), (400, code))
        unnecessary = self.create_long(payload=self.long_payload(**self.payload(day_offset=8, minutes=180)))
        self.assertEqual((unnecessary.status_code, unnecessary.data["error"]["code"]), (400, "LONG_BOOKING_NOT_NEEDED"))
        resource = self.service.resource(self.room["id"])
        self.service.repo.save_resource(replace(resource, max_booking_minutes=210))
        too_long = self.create_long()
        self.assertEqual((too_long.status_code, too_long.data["error"]["code"]), (400, "DURATION_LIMIT"))

    def test_long_bookings_consume_weekly_allowance_and_cannot_be_moved(self):
        for day in (7, 8, 9):
            created = self.create_long(payload=self.long_payload(**self.payload(day_offset=day, minutes=240)))
            self.assertEqual(created.status_code, 201, created.data)
        denied = self.verified.post("/api/v1/bookings/", self.payload(day_offset=10), format="json")
        self.assertEqual((denied.status_code, denied.data["error"]["code"]), (409, "WEEKLY_LIMIT_REACHED"))
        approved = self.review(created.data["id"])
        self.assertEqual(approved.status_code, 200, approved.data)
        new = self.payload(day_offset=10, minutes=240)
        for action, client in (("change", self.verified), ("reschedule", self.manager)):
            denied = client.post(f"/api/v1/bookings/{created.data['id']}/{action}/",
                                 {"start": new["start"], "end": new["end"]}, format="json")
            self.assertEqual((denied.status_code, denied.data["error"]["code"]),
                             (409, "LONG_BOOKING_NEW_REQUEST_REQUIRED"))

    def test_overview_separates_long_requests_and_schema_documents_endpoint(self):
        created = self.create_long()
        self.assertEqual(created.status_code, 201, created.data)
        for client, can_decide in ((self.admin, False), (self.manager, True)):
            overview = client.get("/api/v1/admin/overview/")
            self.assertEqual(overview.status_code, 200, overview.data)
            self.assertEqual(overview.data["long_booking_requests"], 1)
            self.assertEqual(overview.data["pending_bookings"], 0)
            self.assertEqual(overview.data["can_decide_long_bookings"], can_decide)
        schema = self.client.get("/api/schema/").json()
        self.assertIn("/api/v1/bookings/long-bookings/", schema["paths"])
