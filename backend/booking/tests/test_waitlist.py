"""Strict first-come-first-served waitlist with automatic promotion.

Scenario names follow the team discussion: A submits first (induction under review),
B next (induction under review), C later (already qualified), D last.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from booking.domain import BookingStatus, Principal, QualificationStatus, Role
from booking.exceptions import DomainError
from booking.runtime import reset_runtime
from booking.tests.test_api import NOW, PNG, BookingAPIFixtureMixin
from booking.tests.test_outlook import FakeCalendar
from booking.tests.test_services import BookingFixtureMixin

SYDNEY = ZoneInfo("Australia/Sydney")


class WaitlistServiceTests(BookingFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        # Manager-configured long hold: the first pending request keeps its place until decided.
        self.room = replace(self.room, pending_hold_minutes=20160)
        self.repo.save_resource(self.room)
        self.a = self.student
        self.b = self.other
        self.c = self.make_student("z3333333")
        self.d = self.make_student("z4444444")
        self.qual_a = self.qualification(self.a, status=QualificationStatus.PENDING)
        self.qual_b = self.qualification(self.b, status=QualificationStatus.PENDING)
        self.qualification(self.c)
        self.qualification(self.d)

    def make_student(self, zid):
        principal = Principal(str(uuid4()), zid, zid, Role.STUDENT, f"{zid}@ad.unsw.edu.au")
        self.repo.save_principal(principal)
        return principal

    def book(self, principal=None, **overrides):
        # Requests arrive one after another; queue order follows submission time.
        booking = super().book(principal, **overrides)
        self.now += timedelta(seconds=1)
        return booking

    def get(self, booking):
        return self.repo.get_booking(booking.id)

    def queue(self):
        """A, B, C, D request the same slot in that order."""
        return [self.book(person) for person in (self.a, self.b, self.c, self.d)]

    def test_first_request_holds_the_slot_and_everyone_else_queues_in_order(self):
        a, b, c, d = self.queue()
        self.assertEqual(a.status, BookingStatus.WAITING_QUALIFICATION)
        self.assertEqual(a.hold_until, a.start)
        self.assertEqual([x.status for x in (b, c, d)], [BookingStatus.WAITLISTED] * 3)
        # C is qualified but still cannot jump ahead of A.
        with self.assertRaises(DomainError) as denied:
            self.service.review_booking(self.admin, c.id, "APPROVED")
        self.assertEqual(denied.exception.code, "REQUEST_WAITLISTED")

    def test_first_place_is_kept_through_the_24_hour_escalation(self):
        a, b, c, _ = self.queue()
        self.now += timedelta(hours=25)
        self.service.process_due_requests()
        self.assertEqual(self.get(a).status, BookingStatus.PENDING_APPROVAL)
        self.assertTrue(self.get(a).hold_is_active(self.now))
        self.assertEqual([self.get(x).status for x in (b, c)], [BookingStatus.WAITLISTED] * 2)

    def test_when_first_is_verified_the_queue_stays_as_backup(self):
        a, b, c, d = self.queue()
        self.service.review_qualification(self.admin, self.qual_a.id, "VERIFIED")
        self.assertEqual(self.get(a).status, BookingStatus.APPROVED)
        self.assertEqual([self.get(x).status for x in (b, c, d)], [BookingStatus.WAITLISTED] * 3)

    def test_cancellation_promotes_the_next_request_even_if_a_later_one_is_qualified(self):
        a, b, c, _ = self.queue()
        self.service.cancel_booking(self.a, a.id)
        promoted = self.get(b)
        self.assertEqual((promoted.status, promoted.reason_code),
                         (BookingStatus.WAITING_QUALIFICATION, "PROMOTED_FROM_WAITLIST"))
        self.assertTrue(promoted.hold_is_active(self.now))
        self.assertEqual(self.get(c).status, BookingStatus.WAITLISTED)  # strict FIFO: C waits behind B

    def test_qualified_next_request_is_approved_automatically(self):
        a, b, c, d = self.queue()
        self.service.cancel_booking(self.a, a.id)
        self.service.cancel_booking(self.b, b.id)  # B (now first) withdraws
        self.assertEqual((self.get(c).status, self.get(c).reason_code), (BookingStatus.APPROVED, "PROMOTED_FROM_WAITLIST"))
        self.assertEqual(self.get(d).status, BookingStatus.WAITLISTED)

    def test_rejecting_the_first_induction_passes_the_slot_on(self):
        a, b, c, _ = self.queue()
        self.service.review_qualification(self.admin, self.qual_a.id, "REJECTED", "Wrong certificate")
        self.assertEqual(self.get(a).status, BookingStatus.REJECTED)
        self.assertIn(self.get(b).status, (BookingStatus.WAITING_QUALIFICATION, BookingStatus.PENDING_APPROVAL))
        self.assertEqual(self.get(c).status, BookingStatus.WAITLISTED)

    def test_admin_can_reject_a_waitlisted_request_without_affecting_order(self):
        a, b, c, d = self.queue()
        self.service.review_booking(self.admin, c.id, "REJECTED", "Duplicate request")
        self.assertEqual(self.get(c).status, BookingStatus.REJECTED)
        self.service.cancel_booking(self.a, a.id)
        self.assertEqual(self.get(b).status, BookingStatus.WAITING_QUALIFICATION)
        self.assertEqual(self.get(d).status, BookingStatus.WAITLISTED)

    def test_promotion_skips_requests_without_a_current_qualification(self):
        a, b, c, _ = self.queue()
        self.now += timedelta(seconds=1)
        self.qualification(self.b, status=QualificationStatus.REJECTED)  # recorded directly
        self.service.cancel_booking(self.a, a.id)
        self.assertEqual((self.get(b).status, self.get(b).reason_code), (BookingStatus.REJECTED, "QUALIFICATION_REQUIRED"))
        self.assertEqual(self.get(c).status, BookingStatus.APPROVED)

    def test_waitlisted_requests_expire_at_start(self):
        a, b, c, _ = self.queue()
        self.now = a.start
        self.service.process_due_requests()
        self.assertEqual({self.get(x).status for x in (a, b, c)}, {BookingStatus.EXPIRED})

    def test_freed_time_goes_to_the_earliest_request_that_fits(self):
        self.qualification(self.a)  # A qualified: approved 10:00-11:00
        first = self.book(self.a)
        long_one = self.book(self.c, end=self.end + timedelta(hours=1))   # 10:00-12:00, waits
        short_one = self.book(self.d)                                      # 10:00-11:00, waits behind C
        self.service.cancel_booking(self.a, first.id)
        self.assertEqual(self.get(long_one).status, BookingStatus.APPROVED)
        self.assertEqual(self.get(short_one).status, BookingStatus.WAITLISTED)

    def test_rescheduling_frees_the_old_slot_for_the_queue(self):
        self.qualification(self.a)
        first = self.book(self.a)
        waiting = self.book(self.c)
        self.service.reschedule_booking(self.a, first.id, self.start + timedelta(hours=3), self.end + timedelta(hours=3))
        self.assertEqual(self.get(waiting).status, BookingStatus.APPROVED)

    def test_promotions_are_audited_and_reported_for_calendar_sync(self):
        a, b, _, _ = self.queue()
        self.service.take_promoted_ids()
        self.service.cancel_booking(self.a, a.id)
        self.assertEqual(self.service.take_promoted_ids(), [b.id])
        self.assertEqual(self.service.take_promoted_ids(), [])
        record = [item for item in self.repo.list_audit() if item.entity_id == b.id][-1]
        self.assertEqual((record.action, record.actor_id), ("BOOKING_PROMOTED", "SYSTEM"))



class DefaultThirtyMinuteHoldTests(BookingFixtureMixin, SimpleTestCase):
    """The agreed workflow with the default 30-minute hold (A under review, B qualified)."""

    def setUp(self):
        super().setUp()
        self.qual_a = self.qualification(self.student, status=QualificationStatus.PENDING)
        self.qualification(self.other)

    def test_qualified_b_waits_while_a_holds_then_gets_the_slot_when_the_hold_ends(self):
        a = self.book(self.student)                       # 10:00, hold until 10:30
        self.now += timedelta(minutes=10)
        b = self.book(self.other)                         # 10:10, A still holds
        self.assertEqual(b.status, BookingStatus.WAITLISTED)
        with self.assertRaises(DomainError):
            self.service.review_booking(self.admin, b.id, "APPROVED")
        self.now = a.hold_until                           # 10:30
        self.service.process_due_requests()
        self.assertEqual((self.repo.get_booking(a.id).status, self.repo.get_booking(a.id).reason_code),
                         (BookingStatus.WAITLISTED, "HOLD_EXPIRED"))
        self.assertEqual(self.repo.get_booking(b.id).status, BookingStatus.APPROVED)

    def test_qualified_b_after_the_hold_is_approved_and_a_waits_until_b_cancels(self):
        a = self.book(self.student)                       # 10:00
        self.now = a.hold_until + timedelta(minutes=10)   # 10:40
        b = self.book(self.other)
        self.assertEqual(b.status, BookingStatus.APPROVED)
        self.assertEqual(self.repo.get_booking(a.id).status, BookingStatus.WAITLISTED)
        self.service.review_qualification(self.admin, self.qual_a.id, "VERIFIED")
        self.assertEqual(self.repo.get_booking(a.id).status, BookingStatus.WAITLISTED)  # qualified, still queued
        self.service.cancel_booking(self.other, b.id)
        self.assertEqual((self.repo.get_booking(a.id).status, self.repo.get_booking(a.id).reason_code),
                         (BookingStatus.APPROVED, "PROMOTED_FROM_WAITLIST"))

    def test_a_is_approved_on_verification_if_nobody_took_the_slot(self):
        a = self.book(self.student)
        self.now = a.hold_until + timedelta(hours=2)
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(a.id).status, BookingStatus.WAITLISTED)
        self.service.review_qualification(self.admin, self.qual_a.id, "VERIFIED")
        self.assertEqual(self.repo.get_booking(a.id).status, BookingStatus.APPROVED)

    def test_a_does_not_get_a_second_hold_while_still_under_review(self):
        a = self.book(self.student)
        self.now = a.hold_until
        self.service.process_due_requests()
        current = self.repo.get_booking(a.id)
        self.assertEqual(current.status, BookingStatus.WAITLISTED)
        self.assertFalse(current.blocks_resource_at(self.now))
        self.assertEqual(self.repo.list_blocking_bookings(self.room.id, self.start, self.end, self.now), [])

    def test_a_still_waiting_does_not_block_the_next_newcomer_under_review(self):
        third = Principal(str(uuid4()), "z5555555", "Third", Role.STUDENT, "z5555555@ad.unsw.edu.au")
        self.repo.save_principal(third)
        self.qualification(third, status=QualificationStatus.PENDING)
        a = self.book(self.student)
        self.now = a.hold_until + timedelta(minutes=1)
        c = self.book(third)
        self.assertEqual(c.status, BookingStatus.WAITING_QUALIFICATION)  # C gets its own 30-minute hold
        self.assertTrue(c.hold_is_active(self.now))


class BookingLimitTests(BookingFixtureMixin, SimpleTestCase):
    def test_bookings_can_start_at_most_seven_days_ahead(self):
        self.qualification()
        today = self.now.astimezone(SYDNEY).date()
        last = datetime.combine(today + timedelta(days=7), datetime.min.time(), SYDNEY).replace(hour=19)
        self.assertEqual(self.book(start=last, end=last + timedelta(hours=1)).status, BookingStatus.APPROVED)
        too_far = last + timedelta(hours=13)  # 08:00 on day 8
        with self.assertRaises(DomainError) as denied:
            self.book(start=too_far, end=too_far + timedelta(hours=1))
        self.assertEqual(denied.exception.code, "BOOKING_TOO_FAR_AHEAD")
        self.assertEqual(denied.exception.details["latest_date"], (today + timedelta(days=7)).isoformat())

    def test_reschedule_respects_the_horizon(self):
        self.qualification()
        booking = self.book()
        far = self.start + timedelta(days=8)
        with self.assertRaises(DomainError) as denied:
            self.service.reschedule_booking(self.student, booking.id, far, far + timedelta(hours=1))
        self.assertEqual(denied.exception.code, "BOOKING_TOO_FAR_AHEAD")

    def test_student_under_review_may_hold_only_one_undecided_request(self):
        self.qualification(status=QualificationStatus.PENDING)
        first = self.book()
        with self.assertRaises(DomainError) as denied:
            self.book(start=self.start + timedelta(hours=2), end=self.end + timedelta(hours=2))
        self.assertEqual(denied.exception.code, "PENDING_REQUEST_LIMIT")
        self.assertEqual(denied.exception.details["pending_booking_ids"], [first.id])
        self.service.cancel_booking(self.student, first.id)
        self.assertEqual(self.book(start=self.start + timedelta(hours=2), end=self.end + timedelta(hours=2)).status,
                         BookingStatus.WAITING_QUALIFICATION)

    def test_qualified_students_are_not_limited(self):
        self.qualification()
        for hour in (0, 2, 4):
            self.assertEqual(self.book(start=self.start + timedelta(hours=hour),
                                       end=self.end + timedelta(hours=hour)).status, BookingStatus.APPROVED)


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class WaitlistAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def test_positions_dashboard_counts_and_admin_queue(self):
        first = self.create_booking().data
        self.submit()
        reviewed = self.admin.post(f"/api/v1/admin/qualifications/{self.items(self.admin.get('/api/v1/admin/qualifications/'))[0]['id']}/review/",
                                   {"decision": "VERIFIED"}, format="json")
        self.assertEqual(reviewed.status_code, 200, reviewed.data)
        second = self.create_booking(self.student).data
        self.assertEqual((first["status"], second["status"], second["waitlist_position"]), ("APPROVED", "WAITLISTED", 1))
        self.assertIsNone(first["waitlist_position"])
        self.assertEqual(self.student.get("/api/v1/dashboard/").data["counts"]["WAITLISTED"], 1)
        queue = self.items(self.admin.get("/api/v1/admin/bookings/", {"status": "WAITLISTED"}))
        self.assertEqual([item["id"] for item in queue], [second["id"]])

    def test_errors_for_horizon_and_pending_limit(self):
        far = self.create_booking(payload=self.payload(day_offset=9))
        self.assert_error(far, 400)
        self.assertEqual(far.data["error"]["code"], "BOOKING_TOO_FAR_AHEAD")
        self.submit()
        self.assertEqual(self.create_booking(self.student).status_code, 201)
        limited = self.create_booking(self.student, self.payload(hour=14))
        self.assert_error(limited, 409)
        self.assertEqual(limited.data["error"]["code"], "PENDING_REQUEST_LIMIT")


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True,
                   OUTLOOK_ENABLED=True, OUTLOOK_SYNC_ON_WRITE=True)
class WaitlistOutlookTests(SimpleTestCase):
    def setUp(self):
        self.service = reset_runtime()
        self.service.clock = lambda: NOW
        self.service.min_advance_days, self.service.max_advance_days = 0, 7  # workflow tests book a few days ahead; see test_booking_window.py
        self.provider = FakeCalendar()
        self.service.calendar_sync.provider = self.provider
        for item in self.service.repo.list_submissions():
            self.service.repo.save_submission(replace(item, valid_until=None))

    def login(self, zid):
        client = APIClient()
        result = client.post("/api/v1/auth/demo-login/", {"zid": zid}, format="json")
        client.credentials(HTTP_AUTHORIZATION="Bearer " + result.data["access_token"])
        return client

    def test_promoted_approval_is_pushed_to_outlook_in_the_same_request(self):
        verified, newcomer, admin = self.login("z1000001"), self.login("z1000002"), self.login("z9000001")
        room = next(item for item in self.service.repo.list_resources() if item.name == "Lab Room 1")
        upload = newcomer.post("/api/v1/qualifications/", {
            "requirement_id": room.required_qualification_id, "title": "Induction",
            "file": SimpleUploadedFile("induction.png", PNG, content_type="image/png")}, format="multipart")
        admin.post(f"/api/v1/admin/qualifications/{upload.data['id']}/review/", {"decision": "VERIFIED"}, format="json")
        start = (NOW.astimezone(SYDNEY) + timedelta(days=3)).replace(hour=12, minute=0)
        payload = {"resource_id": room.id, "start": start.isoformat(),
                   "end": (start + timedelta(hours=1)).isoformat(), "purpose": "Practical"}
        first = verified.post("/api/v1/bookings/", payload, format="json").data
        waiting = newcomer.post("/api/v1/bookings/", payload, format="json").data
        self.assertEqual(waiting["status"], "WAITLISTED")
        verified.post(f"/api/v1/bookings/{first['id']}/cancel/", {}, format="json")
        promoted = newcomer.get(f"/api/v1/bookings/{waiting['id']}/").data
        self.assertEqual(promoted["status"], "APPROVED")
        self.assertEqual(promoted["outlook_sync"]["status"], "SYNCED")
        self.assertEqual([call[0] for call in self.provider.creates], [first["id"], waiting["id"]])
