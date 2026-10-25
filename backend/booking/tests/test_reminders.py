"""Sprint 3: reminders in the bell (booking coming up, induction expiring soon) and expired-request notices."""

from datetime import timedelta

from django.test import SimpleTestCase

from booking.domain import BookingStatus
from booking.tests.test_sprint3 import Sprint3Fixture


class ReminderTests(Sprint3Fixture, SimpleTestCase):
    def test_booking_reminder_is_sent_once_the_day_before(self):
        booking = self.approved(self.student, days=3)
        self.service.process_due_requests()
        self.assertEqual(self.notices(self.student, "BOOKING_REMINDER"), [])   # still more than 24 hours away
        self.now = booking.start - timedelta(hours=23)
        self.service.process_due_requests()
        self.service.process_due_requests()
        reminders = self.notices(self.student, "BOOKING_REMINDER")
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0].booking_id, booking.id)
        self.assertIn("I'm here", reminders[0].body)
        self.assertIn("09:45 and 10:30", reminders[0].body)                 # the check-in window, local time

    def test_no_reminder_for_requests_that_are_not_approved(self):
        booking = self.approved(self.student, days=3)
        queued = self.request(self.other, days=3)                               # same time: waitlisted
        self.now = booking.start - timedelta(hours=2)
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(queued.id).status, BookingStatus.WAITLISTED)
        self.assertEqual(self.notices(self.other, "BOOKING_REMINDER"), [])
        self.assertEqual(len(self.notices(self.student, "BOOKING_REMINDER")), 1)

    def test_induction_expiry_reminder_is_sent_once(self):
        submission = self.qualification(self.other, valid_until=self.now + timedelta(days=20))
        self.service.process_due_requests()
        self.assertEqual(self.notices(self.other, "INDUCTION_EXPIRING"), [])
        self.now += timedelta(days=7)                                          # 13 days left
        self.service.process_due_requests()
        self.service.process_due_requests()
        reminders = self.notices(self.other, "INDUCTION_EXPIRING")
        self.assertEqual(len(reminders), 1)
        self.assertIn("13 day(s)", reminders[0].body)
        self.assertEqual(reminders[0].link, f"/induction?requirement={submission.requirement_id}&submission={submission.id}")

    def test_waitlisted_request_that_never_got_a_place_is_noticed(self):
        self.approved(self.student, days=3)
        queued = self.request(self.other, days=3)
        self.assertEqual(queued.status, BookingStatus.WAITLISTED)
        self.now = queued.start + timedelta(minutes=1)
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(queued.id).status, BookingStatus.EXPIRED)
        notice = self.notices(self.other, "BOOKING_EXPIRED")[0]
        self.assertIn("no place opened up in time", notice.body)
