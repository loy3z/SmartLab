"""Failure and edge scenarios with reproducible evidence for incorrect behaviour."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from smtplib import SMTPException
from threading import Barrier
from unittest import mock

from django.core import mail
from django.core.mail.backends import locmem
from django.test import SimpleTestCase, override_settings

from booking.domain import BookingStatus
from booking.email_channel import EmailDeliveryService
from booking.exceptions import DomainError
from booking.tests.test_api import BookingAPIFixtureMixin
from booking.tests.test_sprint3 import Sprint3Fixture


@override_settings(NOTIFICATION_CHANNELS=[])
class EdgeHuntWorkflowTests(Sprint3Fixture, SimpleTestCase):
    def test_parallel_duplicate_requests_without_a_key_leave_one_booking(self):
        barrier = Barrier(2)

        def submit(_):
            barrier.wait(timeout=5)
            try:
                return self.request().status.value
            except DomainError as error:
                return error.code, error.status

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))

        self.assertCountEqual(results, ["PENDING_APPROVAL", ("DUPLICATE_BOOKING", 409)])
        self.assertEqual(len(self.repo.list_bookings()), 1)

    def test_review_deadline_rejects_a_resource_put_under_maintenance(self):
        booking = self.request()
        self.service.set_resource_status(self.manager, self.room.id, "MAINTENANCE", "Water leak")
        self.now = booking.review_due_at
        changed = self.service.process_due_requests()

        self.assertEqual([(item.id, item.status, item.reason_code, item.reviewed_by) for item in changed],
                         [(booking.id, BookingStatus.REJECTED, "AUTO_REJECTED_RESOURCE_UNAVAILABLE", "SYSTEM")])
        self.assertTrue(changed[0].decision_reason)
        self.assertEqual(len(self.notices(self.student, "BOOKING_REJECTED")), 1)
        self.assertEqual(self.service.process_due_requests(), [])

    def test_archiving_after_cancellation_keeps_booking_and_induction_history(self):
        booking = self.approved()
        self.service.cancel_booking(self.student, booking.id)
        self.service.archive_resource(self.manager, self.room.id)

        retained = self.repo.get_booking(booking.id)
        self.assertEqual(retained.status, BookingStatus.CANCELLED)
        self.assertFalse(self.repo.get_resource(retained.resource_id).active)
        self.assertIsNotNone(self.repo.get_requirement(self.room.required_qualification_id))
        self.assertTrue(self.repo.list_submissions(student_id=retained.student_id))
        self.assertIn(booking.id, [item.id for item in self.service.booking_report(self.manager)])


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True,
                   NOTIFICATION_CHANNELS=[], OUTLOOK_ENABLED=False)
class EdgeHuntIntegrityAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def test_resource_and_referenced_induction_deletion_are_explicitly_unsupported(self):
        booking = self.create_approved()
        resource_id = booking["resource_id"]
        requirement_id = self.service.repo.get_resource(resource_id).required_qualification_id
        for url in (f"/api/v1/admin/resources/{resource_id}/",
                    f"/api/v1/admin/qualification-requirements/{requirement_id}/"):
            with self.subTest(url=url):
                response = self.manager.delete(url)
                self.assertEqual(response.status_code, 405, response.data)
        self.assertIsNotNone(self.service.repo.get_resource(resource_id))
        self.assertIsNotNone(self.service.repo.get_requirement(requirement_id))
        self.assertEqual(self.service.repo.get_booking(booking["id"]).status, BookingStatus.APPROVED)


@override_settings(NOTIFICATION_CHANNELS=["booking.email_channel.EmailChannel"], EMAIL_MODE="all",
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   EMAIL_MAX_ATTEMPTS=6, EMAIL_LEASE_SECONDS=300)
class EdgeHuntEmailTests(Sprint3Fixture, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.service.email_delivery = EmailDeliveryService(self.service, clock=lambda: self.now, worker_id="first")
        mail.outbox = []
        self.service.take_new_notification_ids()
        self.addCleanup(self.service.take_new_notification_ids)

    def test_failed_booking_email_keeps_the_booking_and_bell_notice(self):
        booking = self.request()
        notice, = self.notices(self.student, "BOOKING_SUBMITTED")
        with mock.patch.object(locmem.EmailBackend, "send_messages", side_effect=SMTPException("SMTP unavailable")), \
                self.assertLogs("booking.email_channel", "ERROR"):
            self.service.email_delivery.process_pending(10)

        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.PENDING_APPROVAL)
        notices, _ = self.service.list_notifications(self.student)
        self.assertIn(notice.id, [item.id for item in notices])
        self.assertEqual(self.repo.get_email_delivery(notice.id).status, "RETRY")

    def test_connection_failure_obeys_each_backoff_and_stops_after_maximum_attempts(self):
        notice = self.service._notify(self.student.id, "BOOKING_SUBMITTED", "Request received", "Details")
        with mock.patch.object(locmem.EmailBackend, "open", side_effect=ConnectionRefusedError("SMTP refused")) as connect, \
                self.assertLogs("booking.email_channel", "ERROR"):
            for attempt, delay in enumerate((60, 300, 900, 3600, 3600), start=1):
                attempted_at = self.now
                self.service.email_delivery.process_pending(10)
                delivery = self.repo.get_email_delivery(notice.id)
                self.assertEqual((delivery.status, delivery.attempts, delivery.next_attempt_at),
                                 ("RETRY", attempt, attempted_at + timedelta(seconds=delay)))
                self.now = delivery.next_attempt_at - timedelta(microseconds=1)
                self.assertEqual(self.service.email_delivery.process_pending(10), [])
                self.now = delivery.next_attempt_at
            self.service.email_delivery.process_pending(10)
            failed = self.repo.get_email_delivery(notice.id)
            self.assertEqual((failed.status, failed.attempts, failed.next_attempt_at), ("FAILED", 6, None))
            self.now += timedelta(days=1)
            self.assertEqual(self.service.email_delivery.process_pending(10), [])
            self.assertEqual(connect.call_count, 6)

    def test_successful_retry_is_not_sent_again_by_later_processing(self):
        notice = self.service._notify(self.student.id, "BOOKING_SUBMITTED", "Request received", "Details")
        with mock.patch.object(locmem.EmailBackend, "send_messages", side_effect=SMTPException("Try later")), \
                self.assertLogs("booking.email_channel", "ERROR"):
            self.service.email_delivery.process_pending(10)
        self.now = self.repo.get_email_delivery(notice.id).next_attempt_at
        self.service.email_delivery.process_pending(10)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.repo.get_email_delivery(notice.id).status, "SENT")
        self.now += timedelta(days=1)
        self.assertEqual(self.service.email_delivery.process_pending(10), [])
        self.assertEqual(len(mail.outbox), 1)

    @unittest.expectedFailure
    def test_expired_batch_worker_does_not_resend_an_email_recovered_by_another_worker(self):
        # Known limitation, kept on purpose (email is delivered at least once; only one mail worker runs):
        # a worker still sends its stale batch entries after another worker recovers and sends them.
        first = self.service._notify(self.student.id, "BOOKING_SUBMITTED", "First request", "Details")
        second = self.service._notify(self.student.id, "BOOKING_SUBMITTED", "Second request", "Details")
        self.now += timedelta(seconds=1)
        recovery = EmailDeliveryService(self.service, clock=lambda: self.now, worker_id="recovery")
        real_send = locmem.EmailBackend.send_messages
        real_save = self.repo.save_email_delivery
        recovered = []

        def slow_send(backend, messages):
            count = real_send(backend, messages)
            if messages[0].subject == "SmartLab: First request":
                # A slow first message can exhaust the lease of every later message in the batch.
                self.now += timedelta(seconds=301)
            return count

        def save_and_recover(delivery):
            real_save(delivery)
            if delivery.notification_id == first.id and delivery.status == "SENT" and not recovered:
                # Run the scheduler after the first send commits, before this worker reaches the next item.
                recovered.extend(recovery.process_pending(10))

        with mock.patch.object(locmem.EmailBackend, "send_messages", slow_send), \
                mock.patch.object(self.repo, "save_email_delivery", save_and_recover):
            self.service.email_delivery.process_pending(10)

        self.assertEqual([item.notification_id for item in recovered], [second.id])
        self.assertEqual(self.repo.get_email_delivery(second.id).status, "SENT")
        self.assertEqual([item.subject for item in mail.outbox].count("SmartLab: Second request"), 1)
