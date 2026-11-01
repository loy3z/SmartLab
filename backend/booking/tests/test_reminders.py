"""Sprint 3: reminders in the bell (booking coming up, induction expiring soon) and expired-request notices."""

from datetime import timedelta
import threading
from unittest.mock import patch

from django.db import connections
from django.test import SimpleTestCase, override_settings

from booking.domain import BookingStatus
from booking.tests.test_sprint3 import Sprint3Fixture


# Sprint 3 (2026-11-01): force two processors past the bulk de-duplication read before either saves.
def concurrent_reminder_check(test, service, person, kind, process):
    from booking.email_channel import EmailDeliveryService
    barrier, errors = threading.Barrier(2), []
    notify = service._notify

    def synchronized_notify(*args, **kwargs):
        barrier.wait(timeout=10)
        return notify(*args, **kwargs)

    def run():
        try:
            process()
        except Exception as error:
            errors.append(error)
        finally:
            connections.close_all()

    with override_settings(NOTIFICATION_CHANNELS=["booking.email_channel.EmailChannel"], EMAIL_MODE="all",
                           EMAIL_NOTIFICATION_KINDS=[kind], EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
        service.email_delivery = EmailDeliveryService(service, clock=service.now)
        with patch.object(service, "_notify", synchronized_notify):
            threads = [threading.Thread(target=run) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)
            test.assertFalse(any(thread.is_alive() for thread in threads))
        test.assertEqual(errors, [])
        notices = [item for item in service.repo.list_notifications(person.id) if item.kind == kind]
        deliveries = [item for item in service.repo.list_email_deliveries()
                      if item.notification_id in {notice.id for notice in notices}]
        test.assertEqual((len(notices), len(deliveries)), (1, 1))


class ReminderTests(Sprint3Fixture, SimpleTestCase):
    def test_concurrent_booking_reminders_create_one_notification_and_email(self):
        booking = self.approved(self.student, days=3)
        self.now = booking.start - timedelta(hours=23)
        concurrent_reminder_check(self, self.service, self.student, "BOOKING_REMINDER", self.service._booking_reminders)

    def test_concurrent_induction_reminders_create_one_notification_and_email(self):
        self.qualification(self.other, valid_until=self.now + timedelta(days=10))
        concurrent_reminder_check(self, self.service, self.other, "INDUCTION_EXPIRING", self.service._induction_reminders)

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
