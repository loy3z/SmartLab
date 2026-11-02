"""Longer bookings waive only the ordinary single-booking cap and always require a Manager's decision."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, time, timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, override_settings

from booking.domain import Booking, BookingStatus, Principal, Role
from booking.errors import DomainError
from booking.test_console import TEST_ACCOUNT_ID, test_identity as make_test_identity
from booking.tests.test_services import BookingFixtureMixin


class LongBookingTests(BookingFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.service._override_rule(min_advance_days=7, max_advance_days=28)
        self.manager = Principal(str(uuid4()), "z9888888", "Manager", Role.MANAGER, "manager@example.test")
        self.manager2 = Principal(str(uuid4()), "z9777777", "Other manager", Role.MANAGER, "manager2@example.test")
        for person in (self.manager, self.manager2):
            self.repo.save_principal(person)
        for person in (self.student, self.other, self.admin, self.manager):
            self.qualification(person)
        self.zone = ZoneInfo(self.room.timezone)
        self.today = self.now.astimezone(self.zone).date()

    def at(self, days=8, hour=10, minutes=240):
        start = datetime.combine(self.today + timedelta(days=days), time(hour), self.zone)
        return start, start + timedelta(minutes=minutes)

    def long(self, actor=None, days=8, hour=10, minutes=240, **kwargs):
        start, end = self.at(days, hour, minutes)
        return self.service.create_long_booking(actor or self.student, self.room.id, start, end, "Research",
                                                "A continuous experiment needs a longer session", **kwargs)[0]

    def refused(self, code, call, *args, **kwargs):
        with self.assertRaises(DomainError) as denied:
            call(*args, **kwargs)
        self.assertEqual(denied.exception.code, code)
        return denied.exception

    def test_request_reserves_capacity_until_manager_deadline_and_never_auto_approves(self):
        booking = self.long()
        self.assertEqual(booking.status, BookingStatus.PENDING_APPROVAL)
        self.assertEqual((booking.review_due_at, booking.hold_until), (self.now + timedelta(days=1),) * 2)
        self.assertTrue(booking.blocks_resource_at(self.now))
        self.now = booking.review_due_at - timedelta(microseconds=1)
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.PENDING_APPROVAL)
        self.now += timedelta(microseconds=1)
        self.service.process_due_requests()
        expired = self.repo.get_booking(booking.id)
        self.assertEqual((expired.status, expired.reason_code), (BookingStatus.EXPIRED, "LONG_BOOKING_REVIEW_EXPIRED"))
        self.assertFalse(expired.blocks_resource_at(self.now))
        self.refused("REQUEST_NOT_REVIEWABLE", self.service.review_booking, self.manager, booking.id, "APPROVED")
        self.assertTrue(any(item.kind == "BOOKING_EXPIRED" for item in self.repo.list_notifications(self.student.id)))

    def test_raising_normal_duration_limit_does_not_allow_automatic_approval_of_an_existing_long_request(self):
        booking = self.long()
        self.service._override_rule(max_slots_per_booking=10)
        self.now = booking.review_due_at
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.EXPIRED)

    def test_review_deadline_is_rechecked_after_waiting_for_the_write_lock(self):
        booking = self.long()
        self.now = booking.review_due_at - timedelta(microseconds=1)
        atomic = self.repo.atomic

        @contextmanager
        def delayed_lock(*args, **kwargs):
            with atomic(*args, **kwargs):
                self.now = booking.review_due_at
                yield

        with patch.object(self.repo, "atomic", side_effect=delayed_lock):
            self.refused("REQUEST_NOT_REVIEWABLE", self.service.review_long_booking, self.manager, booking.id, "APPROVED")
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.EXPIRED)

    def test_only_manager_can_approve_or_reject_and_self_review_is_forbidden(self):
        booking = self.long()
        for decision in ("APPROVED", "REJECTED"):
            self.refused("FORBIDDEN", self.service.review_booking, self.admin, booking.id, decision, "Reason")
        own = self.long(self.manager, days=9)
        self.refused("SELF_REVIEW_FORBIDDEN", self.service.review_booking, self.manager, own.id, "APPROVED")
        delegated = self.long(self.manager, days=10, on_behalf_of_zid=self.other.zid)
        self.refused("SELF_REVIEW_FORBIDDEN", self.service.review_booking, self.manager, delegated.id, "REJECTED", "Reason")
        self.assertEqual(self.service.review_booking(self.manager2, delegated.id, "APPROVED").status, BookingStatus.APPROVED)
        self.refused("REASON_REQUIRED", self.service.review_long_booking, self.manager, booking.id, "REJECTED")
        self.refused("VALIDATION_ERROR", self.service.review_long_booking, self.manager, booking.id, "CANCELLED")

    def test_manager_decision_keeps_exact_scope_and_reason_in_audit(self):
        booking = self.long()
        approved = self.service.review_booking(self.manager, booking.id, "APPROVED", "Continuous run justified")
        self.assertEqual((approved.status, approved.start, approved.end), (BookingStatus.APPROVED, booking.start, booking.end))
        audit = next(item for item in self.repo.list_audit() if item.action == "LONG_BOOKING_APPROVED")
        self.assertEqual((audit.details["requested_start"], audit.details["requested_end"]),
                         (booking.start.isoformat(), booking.end.isoformat()))
        self.assertEqual(audit.details["long_booking_reason"], booking.long_booking_reason)

    def test_long_and_normal_requests_share_fifo_and_expiry_promotes_the_next_request(self):
        start, end = self.at(minutes=60)
        first = self.service.create_booking(self.other, self.room.id, start, end, "Earlier ordinary booking")[0]
        self.now += timedelta(seconds=1)
        second = self.long()
        self.now += timedelta(seconds=1)
        third = self.long(self.admin)
        self.assertEqual((second.status, third.status), (BookingStatus.WAITLISTED, BookingStatus.WAITLISTED))
        self.assertIsNone(second.review_due_at)
        self.refused("REQUEST_WAITLISTED", self.service.review_booking, self.manager, second.id, "APPROVED")
        self.service.cancel_booking(self.other, first.id)
        promoted = self.repo.get_booking(second.id)
        self.assertEqual((promoted.status, promoted.long_booking), (BookingStatus.PENDING_APPROVAL, True))
        self.assertEqual(promoted.review_due_at, self.now + timedelta(days=1))
        self.assertEqual(self.repo.get_booking(third.id).status, BookingStatus.WAITLISTED)
        notices = [item for item in self.repo.list_notifications(self.manager.id)
                   if item.kind == "LONG_BOOKING_REQUEST" and item.booking_id == second.id]
        self.assertEqual(len(notices), 2)  # Submission and the point at which it can be reviewed.
        self.now = promoted.review_due_at
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(second.id).status, BookingStatus.EXPIRED)
        next_booking = self.repo.get_booking(third.id)
        self.assertEqual((next_booking.status, next_booking.review_due_at),
                         (BookingStatus.PENDING_APPROVAL, self.now + timedelta(days=1)))

    def test_rejection_releases_hold_and_waitlisted_request_can_be_rejected(self):
        first = self.long()
        queued = self.long(self.other)
        self.assertEqual(self.service.review_booking(self.manager, queued.id, "REJECTED", "Not needed").status,
                         BookingStatus.REJECTED)
        queued = self.long(self.other)
        self.service.review_booking(self.manager, first.id, "REJECTED", "Use a shorter session")
        self.assertEqual(self.repo.get_booking(queued.id).status, BookingStatus.PENDING_APPROVAL)

    def test_all_long_requests_count_toward_normal_twelve_hour_weekly_allowance(self):
        for day in (7, 8, 9):
            self.long(days=day)
        start, end = self.at(10, minutes=30)
        self.refused("WEEKLY_LIMIT_REACHED", self.service.create_booking, self.student, self.room.id, start, end, "Extra base slot")
        self.refused("WEEKLY_LIMIT_REACHED", self.long, days=10)
        self.assertEqual(self.long(days=14).status, BookingStatus.PENDING_APPROVAL)  # A separate local week.

    def test_weekly_and_future_quotas_are_rechecked_at_approval_without_double_counting(self):
        first = self.long()
        self.service._override_rule(max_slots_per_week=6)
        self.refused("WEEKLY_LIMIT_REACHED", self.service.review_booking, self.manager, first.id, "APPROVED")
        self.service._override_rule(max_slots_per_week=24)
        second = self.long(days=9)
        self.service._override_rule(max_active_future_bookings=1)
        self.refused("FUTURE_BOOKING_LIMIT_REACHED", self.service.review_booking, self.manager, first.id, "APPROVED")
        self.service.cancel_booking(self.student, second.id)
        self.assertEqual(self.service.review_booking(self.manager, first.id, "APPROVED").status, BookingStatus.APPROVED)

    def test_no_more_than_eight_future_bookings_including_long_requests(self):
        for day in (7, 8, 9, 14, 15, 16, 21, 22):
            self.long(days=day)
        self.refused("FUTURE_BOOKING_LIMIT_REACHED", self.long, days=23)

    def test_longer_than_normal_but_not_resource_maximum_and_other_period_rules_remain(self):
        self.refused("LONG_BOOKING_NOT_NEEDED", self.long, minutes=180)
        self.assertEqual(self.long(minutes=210).status, BookingStatus.PENDING_APPROVAL)
        self.refused("DURATION_LIMIT", self.long, days=9, minutes=540)
        self.refused("OUTSIDE_OPENING_HOURS", self.long, days=9, hour=19)
        self.refused("INVALID_SLOT_COUNT", self.long, days=9, minutes=255)
        self.repo.save_resource(replace(self.room, max_booking_minutes=240))
        self.refused("DURATION_LIMIT", self.long, days=9, minutes=270)

    def test_minimum_seven_and_maximum_twenty_eight_days_apply(self):
        self.refused("BOOKING_TOO_SOON", self.long, days=6)
        self.assertEqual(self.long(days=7).status, BookingStatus.PENDING_APPROVAL)
        self.assertEqual(self.long(days=28).status, BookingStatus.PENDING_APPROVAL)
        self.refused("BOOKING_TOO_FAR_AHEAD", self.long, days=29)

    def test_qualification_freeze_and_resource_limit_are_rechecked_before_manager_approval(self):
        booking = self.long()
        self.repo.save_principal(replace(self.student, frozen_until=self.now + timedelta(days=3)))
        self.refused("ACCOUNT_FROZEN", self.service.review_booking, self.manager, booking.id, "APPROVED")
        self.repo.save_principal(self.student)
        self.repo.save_resource(replace(self.room, max_booking_minutes=180))
        self.refused("DURATION_LIMIT", self.service.review_booking, self.manager, booking.id, "APPROVED")
        self.repo.save_resource(self.room)
        submission = self.repo.list_submissions(student_id=self.student.id)[0]
        self.repo.save_submission(replace(submission, valid_until=booking.end - timedelta(minutes=1)))
        self.refused("QUALIFICATION_REQUIRED", self.service.review_booking, self.manager, booking.id, "APPROVED")

    def test_waitlist_promotion_uses_resource_cap_not_normal_cap(self):
        first = self.long(self.other)
        queued = self.long()
        self.service.cancel_booking(self.other, first.id)
        self.assertEqual(self.repo.get_booking(queued.id).status, BookingStatus.PENDING_APPROVAL)
        self.assertEqual(self.service.review_booking(self.manager, queued.id, "APPROVED").status, BookingStatus.APPROVED)

    def test_availability_exposes_technical_limit_but_allows_small_timeline_query_cells(self):
        day = self.today + timedelta(days=8)
        normal = self.service.availability(self.student, self.room.id, day)
        longer = self.service.availability(self.student, self.room.id, day, duration_minutes=30, long_booking=True)
        self.assertEqual((normal["max_booking_minutes"], longer["normal_max_booking_minutes"]), (180, 180))
        self.assertEqual((longer["min_booking_minutes"], longer["max_booking_minutes"]), (210, 480))
        self.assertTrue(longer["long_booking"])
        self.assertTrue(any(item["available"] for item in longer["slots"]))
        self.assertEqual((longer["min_advance_days"], longer["max_advance_days"]), (7, 28))
        self.refused("INVALID_DURATION", self.service.availability, self.student, self.room.id, day, duration_minutes=240)
        self.refused("VALIDATION_ERROR", self.service.availability, self.student, self.room.id, day,
                     long_booking=True, additional_hours=True)
        self.refused("VALIDATION_ERROR", self.service.availability, self.student, self.room.id, day,
                     long_booking=True, urgent=True)
        self.repo.save_resource(replace(self.room, slot_minutes=60, max_booking_minutes=480))
        self.service._override_rule(max_slots_per_booking=5)
        longer = self.service.availability(self.student, self.room.id, day, duration_minutes=60, long_booking=True)
        self.assertEqual((longer["normal_max_booking_minutes"], longer["min_booking_minutes"]), (150, 180))
        self.repo.save_resource(replace(self.room, max_booking_minutes=120))
        longer = self.service.availability(self.student, self.room.id, day, long_booking=True)
        self.assertFalse(longer["can_request"])

    def test_ordinary_additional_and_recurring_paths_do_not_gain_long_booking_exemption(self):
        start, end = self.at()
        self.refused("DURATION_LIMIT", self.service.create_booking, self.student, self.room.id, start, end, "Normal")
        self.refused("DURATION_LIMIT", self.service.create_additional_hours_booking, self.student, self.room.id,
                     start, end, "Extra", "Additional allowance")
        day = start.astimezone(self.zone).date()
        preview = self.service.preview_series(self.admin, self.room.id, [day.isoweekday()], time(10), 240, day, day,
                                              on_behalf_of_zid=self.student.zid)
        self.assertEqual(preview["occurrences"][0]["reason_code"], "DURATION_LIMIT")

    def test_idempotency_covers_reason_and_prevents_cross_endpoint_replay(self):
        start, end = self.at()
        args = (self.student, self.room.id, start, end, "Research", "Long experiment")
        first, created = self.service.create_long_booking(*args, idempotency_key="long-key")
        again, repeated = self.service.create_long_booking(*args, idempotency_key="long-key")
        self.assertEqual((created, repeated, first.id), (True, False, again.id))
        self.refused("IDEMPOTENCY_CONFLICT", self.service.create_long_booking, *args[:-1], "Different reason", idempotency_key="long-key")
        self.refused("IDEMPOTENCY_CONFLICT", self.service.create_booking, self.student, self.room.id, start, end,
                     "Research", idempotency_key="long-key")
        self.refused("IDEMPOTENCY_CONFLICT", self.service.create_additional_hours_booking,
                     self.student, self.room.id, start, end, "Research", "Spare capacity", idempotency_key="long-key")
        start, end = self.at(9, minutes=60)
        self.service.create_booking(self.student, self.room.id, start, end, "Normal", idempotency_key="normal-key")
        self.refused("IDEMPOTENCY_CONFLICT", self.service.create_long_booking, self.student, self.room.id, start, end,
                     "Normal", "Long request", idempotency_key="normal-key")

    def test_exact_scope_cannot_be_changed_through_ordinary_change_or_manager_reschedule(self):
        booking = self.long()
        self.service.review_booking(self.manager, booking.id, "APPROVED")
        start, end = self.at(9)
        self.refused("LONG_BOOKING_NEW_REQUEST_REQUIRED", self.service.request_time_change, self.student, booking.id, start, end)
        self.refused("LONG_BOOKING_NEW_REQUEST_REQUIRED", self.service.reschedule_booking, self.manager, booking.id, start, end)

    def test_notifications_and_overview_identify_manager_review(self):
        booking = self.long()
        overview = self.service.staff_overview(self.manager)
        self.assertEqual((overview["pending_bookings"], overview["long_booking_requests"]), (0, 1))
        self.assertTrue(overview["can_decide_long_bookings"])
        self.assertFalse(self.service.staff_overview(self.admin)["can_decide_long_bookings"])
        self.assertTrue(any(item.kind == "LONG_BOOKING_REQUEST" for item in self.repo.list_notifications(self.manager.id)))
        notice = next(item for item in self.repo.list_notifications(self.student.id) if item.kind == "BOOKING_SUBMITTED")
        self.assertNotIn("system decides", notice.body)
        self.assertIn("expires", notice.body)

    @override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, ENABLE_TEST_CONSOLE=True)
    def test_explicit_test_console_does_not_auto_approve_or_expand_long_booking_limits(self):
        principal = replace(self.student, id=TEST_ACCOUNT_ID, zid="1")
        self.repo.save_principal(principal)
        self.qualification(principal)
        actor = make_test_identity(principal, "STUDENT", True)
        self.assertEqual(self.long(actor).status, BookingStatus.PENDING_APPROVAL)
        self.refused("BOOKING_TOO_SOON", self.long, actor, days=1)
        self.refused("BOOKING_TOO_FAR_AHEAD", self.long, actor, days=29)
        self.refused("DURATION_LIMIT", self.long, actor, days=9, minutes=540)

    def test_concurrent_manager_approval_happens_once(self):
        booking = self.long()
        barrier = Barrier(2)

        def decide(actor):
            barrier.wait()
            try:
                return self.service.review_booking(actor, booking.id, "APPROVED").status
            except DomainError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(decide, (self.manager, self.manager2)))
        self.assertCountEqual(results, [BookingStatus.APPROVED, "REQUEST_NOT_REVIEWABLE"])
        self.assertEqual(sum(item.kind == "BOOKING_APPROVED" for item in self.repo.list_notifications(self.student.id)), 1)
