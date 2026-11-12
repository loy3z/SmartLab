"""A change that outlives its original booking must reserve room for both sessions."""
from dataclasses import replace
from datetime import timedelta

from django.test import SimpleTestCase

from booking.domain import BookingStatus
from booking.tests.test_sprint3 import Sprint3Fixture


class ChangeQuotaReviewTests(Sprint3Fixture, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.service.min_advance_days = 7
        self.service.max_advance_days = 28
        # Leave enough time for the original booking to begin while its change waits.
        self.room = replace(self.room, pending_hold_minutes=20160)
        self.repo.save_resource(self.room)

    def change_at_full_allowance(self, waitlisted=False, fill_remaining=True):
        old = self.approved(days=8, hour=8, minutes=180)
        for day in (9, 10):
            self.approved(days=day, hour=8, minutes=180)
        blocker = self.approved(self.other, days=11, hour=8, minutes=180) if waitlisted else None
        change, _ = self.service.request_time_change(self.student, old.id, *self.at(11, 8, 180))
        if fill_remaining:
            self.approved(days=12, hour=8, minutes=180)
        return old, change, blocker

    def test_change_can_be_approved_at_the_limit_while_old_booking_is_still_future(self):
        old, change, _ = self.change_at_full_allowance()
        approved = self.service.review_booking(self.admin, change.id, "APPROVED")
        self.assertEqual(approved.status, BookingStatus.APPROVED)
        self.assertEqual(self.repo.get_booking(old.id).status, BookingStatus.CANCELLED)
        self.assertEqual(self.service.week_hours(self.student.id, self.today + timedelta(days=8))["used_hours"], 12)

    def test_manual_approval_rechecks_quota_when_old_booking_has_started(self):
        old, change, _ = self.change_at_full_allowance()
        self.now = old.start + timedelta(minutes=1)
        self.refused("WEEKLY_LIMIT_REACHED", self.service.review_booking, self.admin, change.id, "APPROVED")
        self.assertEqual(self.repo.get_booking(change.id).status, BookingStatus.PENDING_APPROVAL)
        self.assertEqual(self.repo.get_booking(old.id).status, BookingStatus.APPROVED)

    def test_automatic_approval_rejects_an_over_limit_change_after_old_booking_started(self):
        old, change, _ = self.change_at_full_allowance()
        deadline = old.start + timedelta(minutes=15)
        self.repo.save_booking(replace(change, review_due_at=deadline, hold_until=deadline))
        self.now = deadline
        self.service.process_due_requests()
        decided = self.repo.get_booking(change.id)
        self.assertEqual((decided.status, decided.reason_code),
                         (BookingStatus.REJECTED, "AUTO_REJECTED_BOOKING_RULES"))
        self.assertEqual(self.repo.get_booking(old.id).status, BookingStatus.APPROVED)
        self.assertEqual(self.service.week_hours(self.student.id, self.today + timedelta(days=8))["used_hours"], 12)

    def test_waitlist_does_not_promote_an_over_limit_change_after_old_booking_started(self):
        old, change, blocker = self.change_at_full_allowance(waitlisted=True)
        self.assertEqual(change.status, BookingStatus.WAITLISTED)
        self.now = old.start + timedelta(minutes=1)
        self.service.cancel_booking(self.other, blocker.id)
        decided = self.repo.get_booking(change.id)
        self.assertEqual((decided.status, decided.reason_code),
                         (BookingStatus.REJECTED, "WEEKLY_LIMIT_REACHED"))
        self.assertEqual(self.repo.get_booking(old.id).status, BookingStatus.APPROVED)
        self.assertEqual(self.service.week_hours(self.student.id, self.today + timedelta(days=8))["used_hours"], 12)

    def test_started_old_booking_and_later_change_can_both_be_kept_within_allowance(self):
        old, change, _ = self.change_at_full_allowance(fill_remaining=False)
        self.now = old.start + timedelta(minutes=1)
        approved = self.service.review_booking(self.admin, change.id, "APPROVED")
        self.assertEqual(approved.status, BookingStatus.APPROVED)
        self.assertEqual(self.repo.get_booking(old.id).status, BookingStatus.APPROVED)
        self.assertEqual(self.service.week_hours(self.student.id, self.today + timedelta(days=8))["used_hours"], 12)
