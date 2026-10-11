"""Client requirements: temporary holds protect pending requests, not confirmations."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

from django.test import SimpleTestCase, override_settings
from django.utils.dateparse import parse_datetime

from booking.domain import BookingStatus, Principal, QualificationStatus, Role
from booking.errors import DomainError
from booking.tests.test_api import BookingAPIFixtureMixin, NOW, SYDNEY
from booking.tests.test_services import BookingFixtureMixin


class PendingHoldWorkflowTests(BookingFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.manager = Principal(str(uuid4()), "z8888888", "Lab manager", Role.MANAGER, "z8888888@ad.unsw.edu.au")
        self.repo.save_principal(self.manager)
        self.qualification(status=QualificationStatus.PENDING)

    def test_later_qualified_student_cannot_bypass_an_active_pending_hold(self):
        earlier = self.book()
        self.qualification(self.other)
        later = self.book(self.other)
        self.assertEqual(earlier.status, BookingStatus.WAITING_QUALIFICATION)
        self.assertEqual(earlier.hold_until, self.now + timedelta(minutes=30))
        self.assertEqual(later.status, BookingStatus.WAITLISTED)
        self.assertEqual(later.reason_code, "TEMPORARY_HOLD_CONFLICT")
        self.assertIsNone(later.hold_until)
        with self.assertRaises(DomainError) as rejected:
            self.service.review_booking(self.admin, later.id, "APPROVED")
        self.assertEqual(rejected.exception.code, "REQUEST_WAITLISTED")
        self.assertTrue(self.repo.get_booking(earlier.id).hold_is_active(self.now))

    def test_exact_hold_expiry_releases_slot_without_expiring_the_request(self):
        earlier = self.book()
        self.now = earlier.hold_until - timedelta(microseconds=1)
        self.assertTrue(earlier.blocks_resource_at(self.now))
        self.now = earlier.hold_until
        self.service.process_due_requests()
        current = self.repo.get_booking(earlier.id)
        self.assertEqual((current.status, current.reason_code), (BookingStatus.WAITLISTED, "HOLD_EXPIRED"))
        self.assertEqual(current.hold_until, earlier.hold_until)
        self.assertFalse(current.blocks_resource_at(self.now))
        self.qualification(self.other)
        self.assertEqual(self.book(self.other).status, BookingStatus.APPROVED)

    def test_holder_can_be_approved_without_conflicting_with_own_hold(self):
        submission = self.repo.list_submissions(student_id=self.student.id)[0]
        pending = self.book()
        self.service.review_qualification(self.admin, submission.id, "VERIFIED")
        approved = self.repo.get_booking(pending.id)
        self.assertEqual(approved.status, BookingStatus.APPROVED)
        self.assertFalse(approved.hold_is_active(self.now))
        self.assertTrue(approved.blocks_resource_at(self.now))

    def test_reads_and_idempotent_retries_do_not_renew_hold(self):
        pending = self.book(idempotency_key="pending-double-click")
        self.now += timedelta(minutes=20)
        self.service.availability(self.student, self.room.id, self.start.date())
        self.assertEqual(self.book(idempotency_key="pending-double-click").hold_until, pending.hold_until)
        self.now = pending.hold_until
        self.service.process_due_requests()
        current = self.repo.get_booking(pending.id)
        self.assertEqual(current.status, BookingStatus.WAITLISTED)
        self.assertEqual(current.hold_until, pending.hold_until)

    def test_escalation_does_not_renew_a_long_hold(self):
        self.service.set_pending_hold_minutes(self.manager, self.room.id, 20160)
        pending = self.book()
        self.now += timedelta(hours=24)
        self.service.process_due_requests()
        current = self.repo.get_booking(pending.id)
        self.assertEqual(current.status, BookingStatus.PENDING_APPROVAL)
        self.assertEqual(current.hold_until, pending.hold_until)
        self.assertTrue(current.hold_is_active(self.now))

    def test_cancellation_immediately_releases_a_pending_hold(self):
        pending = self.book()
        cancelled = self.service.cancel_booking(self.student, pending.id)
        self.assertFalse(cancelled.blocks_resource_at(self.now))
        self.qualification(self.other)
        self.assertEqual(self.book(self.other).status, BookingStatus.APPROVED)

    def test_rejection_immediately_releases_a_pending_hold(self):
        self.service.wait_hours = 96
        pending = self.book()
        self.assertEqual(pending.status, BookingStatus.PENDING_APPROVAL)
        rejected = self.service.review_booking(self.admin, pending.id, "REJECTED", "Not suitable")
        self.assertFalse(rejected.blocks_resource_at(self.now))
        self.qualification(self.other)
        self.assertEqual(self.book(self.other).status, BookingStatus.APPROVED)

    def test_hold_is_capped_at_start_and_unapproved_request_expires_at_start(self):
        self.service.set_pending_hold_minutes(self.manager, self.room.id, 10080)
        pending = self.book()
        self.assertEqual(pending.hold_until, pending.start)
        self.now = pending.start
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(pending.id).status, BookingStatus.EXPIRED)
        self.assertEqual(self.repo.list_blocking_bookings(self.room.id, self.start, self.end, self.now), [])

    def test_manager_policy_changes_only_apply_to_new_holds(self):
        self.service.unverified_pending_limit = 2
        first = self.book()
        self.service.set_pending_hold_minutes(self.manager, self.room.id, 90)
        second = self.book(start=self.end, end=self.end + timedelta(hours=1))
        self.assertEqual(first.hold_until, self.now + timedelta(minutes=30))
        self.assertEqual(second.hold_until, self.now + timedelta(minutes=90))
        self.assertEqual(self.repo.get_booking(first.id).hold_until, first.hold_until)

    def test_policy_cannot_be_changed_by_student_admin_or_inactive_manager(self):
        for actor in (self.student, self.admin, replace(self.manager, active=False)):
            with self.subTest(role=actor.role), self.assertRaises(DomainError) as denied:
                self.service.set_pending_hold_minutes(actor, self.room.id, 90)
            self.assertEqual(denied.exception.status, 403)
        for value in (0, -1, 20161, True, "30"):
            with self.subTest(value=value), self.assertRaises(DomainError):
                self.service.set_pending_hold_minutes(self.manager, self.room.id, value)

    def test_parallel_pending_requests_create_only_one_active_hold(self):
        self.qualification(self.other, status=QualificationStatus.PENDING)
        barrier = Barrier(2)
        def request(principal):
            barrier.wait(timeout=5)
            return self.book(principal)
        with ThreadPoolExecutor(max_workers=2) as pool:
            records = list(pool.map(request, (self.student, self.other)))
        self.assertEqual(sum(item.hold_is_active(self.now) for item in records), 1)
        self.assertCountEqual([item.status for item in records], [BookingStatus.WAITING_QUALIFICATION, BookingStatus.WAITLISTED])

    def test_adjacent_periods_and_other_resources_do_not_conflict_with_hold(self):
        self.book()
        self.qualification(self.other)
        adjacent = self.book(self.other, start=self.end, end=self.end + timedelta(hours=1))
        other_resource = replace(self.room, id=str(uuid4()))
        self.repo.save_resource(other_resource)
        independent = self.book(self.other, resource_id=other_resource.id)
        self.assertEqual(adjacent.status, BookingStatus.APPROVED)
        self.assertEqual(independent.status, BookingStatus.APPROVED)

    def test_request_can_still_be_approved_after_hold_expires_if_slot_is_free(self):
        pending = self.book()
        self.now = pending.hold_until
        submission = self.repo.list_submissions(student_id=self.student.id)[0]
        self.service.review_qualification(self.admin, submission.id, "VERIFIED")
        self.assertEqual(self.repo.get_booking(pending.id).status, BookingStatus.APPROVED)


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True, OUTLOOK_ENABLED=False)
class PendingHoldAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def waiting(self):
        self.submit()
        result = self.create_booking(self.student)
        self.assertEqual(result.status_code, 201)
        return result.data

    def slots(self, client):
        day = parse_datetime(self.payload()["start"]).astimezone(SYDNEY).date().isoformat()
        response = client.get(f"/api/v1/resources/{self.room['id']}/availability/", {"date": day, "duration_minutes": 60})
        self.assertEqual(response.status_code, 200)
        expected = parse_datetime(self.payload()["start"])
        return next(item for item in response.data["slots"] if parse_datetime(item["start"]) == expected)

    def test_availability_distinguishes_private_pending_holds_from_confirmations(self):
        waiting = self.waiting()
        other_view = self.slots(self.verified)
        own_view = self.slots(self.student)
        self.assertFalse(other_view["available"])
        self.assertEqual(other_view["reason_code"], "TEMPORARILY_HELD")
        self.assertEqual(other_view["hold_until"], waiting["hold_until"])
        self.assertFalse(other_view["held_by_me"])
        self.assertTrue(own_view["held_by_me"])
        self.assertFalse(other_view["requested_by_me"])
        self.assertTrue(own_view["requested_by_me"])
        self.assertNotIn("student_id", other_view)
        self.assertNotIn("booking_id", other_view)
        self.assertEqual(waiting["outlook_sync"]["status"], "NOT_REQUIRED")

    def shorten_hold(self, minutes=30):
        endpoint = f"/api/v1/admin/resources/{self.room['id']}/booking-policy/"
        self.assertEqual(self.manager.patch(endpoint, {"pending_hold_minutes": minutes}, format="json").status_code, 200)

    def test_default_hold_is_30_minutes(self):
        waiting = self.waiting()
        self.assertEqual(parse_datetime(waiting["hold_until"]), NOW + timedelta(minutes=30))

    def test_hold_expiry_changes_availability_and_dashboard_without_expiring_request(self):
        self.shorten_hold()
        waiting = self.waiting()
        self.service.clock = lambda: parse_datetime(waiting["hold_until"])
        slot = self.slots(self.verified)
        self.assertTrue(slot["available"])
        self.assertIsNone(slot["hold_until"])
        current = self.student.get("/api/v1/dashboard/").data["bookings"][0]
        self.assertEqual((current["status"], current["reason_code"]), ("WAITLISTED", "HOLD_EXPIRED"))
        self.assertFalse(current["hold_active"])
        self.assertFalse(current["blocks_slot"])

    def test_waitlisted_request_cannot_be_force_approved_and_is_promoted_when_a_short_hold_ends(self):
        self.shorten_hold()
        waiting = self.waiting()
        later = self.create_booking().data
        self.assertEqual((later["status"], later["waitlist_position"]), ("WAITLISTED", 1))
        endpoint = f"/api/v1/admin/bookings/{later['id']}/review/"
        denied = self.admin.post(endpoint, {"decision": "APPROVED"}, format="json")
        self.assertEqual(denied.status_code, 409)
        self.assertEqual(denied.data["error"]["code"], "REQUEST_WAITLISTED")
        self.service.clock = lambda: parse_datetime(waiting["hold_until"])
        promoted = self.verified.get(f"/api/v1/bookings/{later['id']}/").data
        self.assertEqual((promoted["status"], promoted["reason_code"]), ("APPROVED", "PROMOTED_FROM_WAITLIST"))
        self.assertTrue(promoted["blocks_slot"])
        self.assertIsNone(promoted["waitlist_position"])

    def test_client_cannot_choose_hold_deadline_or_identity(self):
        for key, value in (("hold_until", "2099-01-01T00:00:00Z"), ("hold_active", False), ("student_id", str(uuid4()))):
            payload = self.payload()
            payload[key] = value
            self.assertEqual(self.create_booking(payload=payload).status_code, 400)

    def test_manager_policy_interface_and_read_only_admin_access(self):
        endpoint = f"/api/v1/admin/resources/{self.room['id']}/booking-policy/"
        self.assertEqual(self.admin.get(endpoint).data["pending_hold_minutes"], 30)
        for client in (self.student, self.admin):
            self.assertEqual(client.patch(endpoint, {"pending_hold_minutes": 90}, format="json").status_code, 403)
        changed = self.manager.patch(endpoint, {"pending_hold_minutes": 90}, format="json")
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.manager.get(endpoint).data["pending_hold_minutes"], 90)
        waiting = self.waiting()
        self.assertEqual(parse_datetime(waiting["hold_until"]), NOW + timedelta(minutes=90))
        for data in ({"pending_hold_minutes": 0}, {"pending_hold_minutes": 20161}, {"pending_hold_minutes": 60, "role": "MANAGER"}):
            self.assertEqual(self.manager.patch(endpoint, data, format="json").status_code, 400)

    def test_identity_includes_required_university_email_but_is_separate_from_eligibility(self):
        me = self.student.get("/api/v1/auth/me/")
        self.assertEqual(me.data["university_email"], "z1000002@ad.unsw.edu.au")
        for email in (None, "not-an-email"):
            data = {"zid": "z3000001", "display_name": "Student"}
            if email is not None:
                data["university_email"] = email
            response = self.client.post("/api/v1/auth/demo-register/", data, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertIn("university_email", response.data["error"]["details"])
        self.assertEqual(self.create_booking(self.student).status_code, 403)

    def test_qualification_is_resource_specific_not_a_global_login_flag(self):
        resources = self.items(self.verified.get("/api/v1/resources/"))
        advanced = next(item for item in resources if item["name"] == "Lab Room 2")
        self.assertNotEqual(advanced["required_qualification_id"], self.room["required_qualification_id"])
        denied = self.create_booking(payload=self.payload(advanced))
        self.assertEqual(denied.status_code, 403)
        submission = self.submit(self.verified, requirement_id=advanced["required_qualification_id"])
        reviewed = self.admin.post(f"/api/v1/admin/qualifications/{submission['id']}/review/", {"decision": "VERIFIED"}, format="json")
        self.assertEqual(reviewed.status_code, 200)
        self.assertEqual(self.create_booking(payload=self.payload(advanced)).data["status"], "APPROVED")
