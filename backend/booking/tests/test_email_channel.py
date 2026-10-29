"""Sprint 3: email notifications (booking.email_channel) and manage.py send_test_email.

Django's test runner swaps in the in-memory email backend, so nothing leaves the machine: sent emails appear in
django.core.mail.outbox.
"""
import threading
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.mail.backends import locmem
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings

from booking import notification_channels
from booking.domain import Principal, Role
from booking.notification_channels import deliver_new_notifications, reset_channels
from booking.runtime import fixed_id
from booking.test_console import TEST_ACCOUNT_ID
from booking.tests.test_api import BookingAPIFixtureMixin

EMAIL_ON = dict(NOTIFICATION_CHANNELS=["booking.email_channel.EmailChannel"], SITE_URL="https://smartlab.example",
                DEFAULT_FROM_EMAIL="SmartLab <system@example.com>")


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class EmailChannelTests(BookingAPIFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        reset_channels()
        mail.outbox = []
        self.addCleanup(reset_channels)

    def run_booking_flow(self, day_offset=3, **email_settings):
        """z1000001 asks for a room, then an Admin approves it. Returns the emails sent (from this flow only)."""
        mail.outbox = []
        with override_settings(**EMAIL_ON, **email_settings):
            reset_channels()
            response = self.create_booking(payload=self.payload(day_offset=day_offset))
            self.assertEqual(response.status_code, 201, response.data)
            booking = response.data
            self.admin.post(f"/api/v1/admin/bookings/{booking['id']}/review/", {"decision": "APPROVED"}, format="json")
            self.assertTrue(notification_channels.wait_for_deliveries(5))  # emails are sent in the background
        return mail.outbox

    def test_allowlist_sends_confirmation_and_decision_with_subject_and_link(self):
        sent = self.run_booking_flow(EMAIL_MODE="allowlist", EMAIL_ALLOWED_RECIPIENTS=["Z1000001@ad.unsw.edu.au"])
        self.assertEqual([item.to for item in sent], [["z1000001@ad.unsw.edu.au"]] * 2)
        received, approved = sent
        self.assertTrue(received.subject.startswith(f"SmartLab: Request received – {self.room['name']}, "))
        self.assertRegex(received.subject, r"\d{2}:\d{2}–\d{2}:\d{2}$")
        self.assertIn("not confirmed until it is approved", received.body)
        self.assertTrue(approved.subject.startswith("SmartLab: Booking approved – "))
        self.assertIn("Open SmartLab: https://smartlab.example/#/bookings", approved.body)
        self.assertEqual(approved.from_email, "SmartLab <system@example.com>")
        self.assertNotIn("Demo redirect", approved.body)

    def test_allowlist_skips_everyone_else(self):
        self.assertEqual(self.run_booking_flow(EMAIL_MODE="allowlist", EMAIL_ALLOWED_RECIPIENTS=["me@example.com"]), [])

    def test_redirect_sends_everything_to_one_address_and_says_who_it_was_for(self):
        sent = self.run_booking_flow(EMAIL_MODE="redirect", EMAIL_REDIRECT_TO="me@example.com")
        self.assertEqual([item.to for item in sent], [["me@example.com"]] * 2)
        self.assertIn("meant for z1000001 <z1000001@ad.unsw.edu.au>", sent[0].body)

    def test_none_and_unknown_modes_send_nothing_and_all_sends_to_the_person(self):
        self.assertEqual(self.run_booking_flow(3, EMAIL_MODE="none"), [])
        self.assertEqual(self.run_booking_flow(4, EMAIL_MODE="everyone"), [])
        self.assertEqual([item.to for item in self.run_booking_flow(5, EMAIL_MODE="all")], [["z1000001@ad.unsw.edu.au"]] * 2)

    def test_only_listed_kinds_are_emailed(self):
        sent = self.run_booking_flow(EMAIL_MODE="all", EMAIL_NOTIFICATION_KINDS=["BOOKING_APPROVED"])
        self.assertEqual([item.subject.split(" – ")[0] for item in sent], ["SmartLab: Booking approved"])

    def test_a_failing_mail_server_does_not_undo_the_booking(self):
        with override_settings(**EMAIL_ON, EMAIL_MODE="all"), \
                mock.patch.object(locmem.EmailBackend, "send_messages", side_effect=OSError("no network")), \
                self.assertLogs("booking.email_channel", "ERROR") as logged:
            reset_channels()
            response = self.create_booking()
            notification_channels.wait_for_deliveries(5)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn("no network", "\n".join(logged.output))

    # 2026-10-27 (performance P1–P3): Gmail takes about 1.9 s to connect, so emails go out on a background thread.

    def test_the_response_does_not_wait_for_the_mail_server(self):
        release, sent = threading.Event(), threading.Event()
        real_send = locmem.EmailBackend.send_messages

        def slow_send(backend, messages):  # a mail server that answers only when the test says so
            release.wait(5)
            count = real_send(backend, messages)
            sent.set()
            return count

        with override_settings(**EMAIL_ON, EMAIL_MODE="all"), mock.patch.object(locmem.EmailBackend, "send_messages", slow_send):
            reset_channels()
            response = self.create_booking(payload=self.payload())
            self.assertEqual(response.status_code, 201, response.data)
            self.assertFalse(sent.is_set(), "the response waited for the mail server")
            release.set()
            self.assertTrue(notification_channels.wait_for_deliveries(5))
        self.assertEqual([item.to for item in mail.outbox], [["z1000001@ad.unsw.edu.au"]])

    def test_emails_waiting_together_share_one_connection(self):
        created = []
        real_init = locmem.EmailBackend.__init__

        def counting_init(backend, *args, **kwargs):
            created.append(backend)
            real_init(backend, *args, **kwargs)

        with override_settings(**EMAIL_ON, EMAIL_MODE="all"), mock.patch.object(locmem.EmailBackend, "__init__", counting_init):
            reset_channels()
            self.service.take_new_notification_ids()
            for title in ["Booking approved", "Booking rescheduled"]:
                self.service._notify(fixed_id(501), "BOOKING_APPROVED", title, "Details")
            deliver_new_notifications(self.service)
            self.assertTrue(notification_channels.wait_for_deliveries(5))
        self.assertEqual([item.subject for item in mail.outbox], ["SmartLab: Booking approved", "SmartLab: Booking rescheduled"])
        self.assertEqual(len(created), 1)

    def test_each_sent_email_is_logged_with_its_notification_and_recipient_domain(self):
        with self.assertLogs("booking.email_channel", "INFO") as logged:
            self.run_booking_flow(EMAIL_MODE="all")
        lines = [line for line in logged.output if "Email sent for notification" in line]
        self.assertEqual(len(lines), 2, logged.output)
        self.assertRegex(lines[0], r"to @ad\.unsw\.edu\.au: waited \d+ ms, sent in \d+ ms$")
        self.assertNotIn("z1000001", "\n".join(lines))  # the log names the domain only

    def test_a_mail_server_that_cannot_be_reached_is_logged_and_later_emails_still_go(self):
        with override_settings(**EMAIL_ON, EMAIL_MODE="all"), \
                mock.patch.object(locmem.EmailBackend, "open", side_effect=[OSError("connection refused"), None]), \
                self.assertLogs("booking.email_channel", "INFO") as logged:
            reset_channels()
            self.service.take_new_notification_ids()
            for title in ["First", "Second"]:
                self.service._notify(fixed_id(501), "BOOKING_APPROVED", title, "Details")
                deliver_new_notifications(self.service)
                self.assertTrue(notification_channels.wait_for_deliveries(5))
        self.assertIn("connection refused", "\n".join(logged.output))
        self.assertEqual([item.subject for item in mail.outbox], ["SmartLab: Second"])

    def test_failed_email_is_persisted_and_retried_after_backoff(self):
        with override_settings(**EMAIL_ON, EMAIL_MODE="all"):
            reset_channels()
            self.service.take_new_notification_ids()
            notification = self.service._notify(fixed_id(501), "BOOKING_APPROVED", "Retry me", "Details")
            pending = self.service.repo.get_email_delivery(notification.id)
            self.assertEqual((pending.status, pending.attempts), ("PENDING", 0))

            with mock.patch.object(locmem.EmailBackend, "send_messages", side_effect=OSError("temporary outage")):
                self.service.email_delivery.process_pending(10)
            retry = self.service.repo.get_email_delivery(notification.id)
            self.assertEqual((retry.status, retry.attempts), ("RETRY", 1))
            self.assertIn("temporary outage", retry.last_error)
            self.assertIsNotNone(retry.next_attempt_at)

            self.service.email_delivery.clock = lambda: retry.next_attempt_at + timedelta(seconds=1)
            self.service.email_delivery.process_pending(10)
            sent = self.service.repo.get_email_delivery(notification.id)
            self.assertEqual((sent.status, sent.attempts), ("SENT", 2))
            self.assertIsNotNone(sent.sent_at)

    def test_email_outbox_rolls_back_with_the_notification(self):
        before = len(self.service.repo.list_email_deliveries())
        with override_settings(**EMAIL_ON, EMAIL_MODE="all"), self.assertRaises(RuntimeError):
            with self.service.repo.atomic(student_ids=[fixed_id(501)]):
                self.service._notify(fixed_id(501), "BOOKING_APPROVED", "Rolled back", "Details")
                raise RuntimeError("cancel transaction")
        self.assertEqual(len(self.service.repo.list_email_deliveries()), before)

    def test_test_console_account_never_enters_the_external_email_queue(self):
        self.service.repo.save_principal(Principal(
            TEST_ACCOUNT_ID, "1", "Test account 1", Role.STUDENT, "test-account@invalid.example"))
        with override_settings(**EMAIL_ON, EMAIL_MODE="all"):
            notification = self.service._notify(
                TEST_ACCOUNT_ID, "BOOKING_APPROVED", "Test notice", "Do not deliver externally.")
        self.assertIsNone(self.service.repo.get_email_delivery(notification.id))

    def test_expired_worker_lease_can_be_recovered(self):
        with override_settings(**EMAIL_ON, EMAIL_MODE="all"):
            self.service.take_new_notification_ids()
            notification = self.service._notify(fixed_id(501), "BOOKING_APPROVED", "Recover me", "Details")
            now = self.service.email_delivery.now()
            first = self.service.repo.claim_email_deliveries(now, 1, "worker-a", now + timedelta(minutes=5))[0]
            self.assertEqual((first.status, first.attempts), ("IN_PROGRESS", 1))
            self.assertEqual(self.service.repo.claim_email_deliveries(now, 1, "worker-b", now + timedelta(minutes=5)), [])
            recovered = self.service.repo.claim_email_deliveries(
                now + timedelta(minutes=6), 1, "worker-b", now + timedelta(minutes=11))[0]
            self.assertEqual((recovered.notification_id, recovered.worker_id, recovered.attempts),
                             (notification.id, "worker-b", 2))

    def test_maximum_attempts_moves_email_to_terminal_failure(self):
        with override_settings(**EMAIL_ON, EMAIL_MODE="all", EMAIL_MAX_ATTEMPTS=1):
            self.service.take_new_notification_ids()
            notification = self.service._notify(fixed_id(501), "BOOKING_APPROVED", "Fail once", "Details")
            with mock.patch.object(locmem.EmailBackend, "send_messages", side_effect=OSError("permanent failure")):
                self.service.email_delivery.process_pending(10)
            failed = self.service.repo.get_email_delivery(notification.id)
            self.assertEqual((failed.status, failed.attempts, failed.next_attempt_at), ("FAILED", 1, None))


class SendTestEmailCommandTests(SimpleTestCase):
    def test_sends_one_email_and_prints_settings_without_the_password(self):
        mail.outbox = []
        out = StringIO()
        with override_settings(EMAIL_HOST_USER="system@example.com", EMAIL_HOST_PASSWORD="abcdabcdabcdabcd"):
            call_command("send_test_email", "--to", "me@example.com", stdout=out)
        self.assertEqual([item.to for item in mail.outbox], [["me@example.com"]])
        self.assertEqual(mail.outbox[0].subject, "SmartLab: test email")
        self.assertIn("password set", out.getvalue())
        self.assertNotIn("abcdabcd", out.getvalue())

    def test_bad_address_and_send_failure(self):
        with self.assertRaises(CommandError):
            call_command("send_test_email", "--to", "not-an-address", stdout=StringIO())
        with mock.patch("booking.management.commands.send_test_email.send_mail", side_effect=OSError("535 bad password")), \
                self.assertRaisesMessage(CommandError, "535 bad password"):
            call_command("send_test_email", "--to", "me@example.com", stdout=StringIO())
