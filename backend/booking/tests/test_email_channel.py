"""Sprint 3: email notifications (booking.email_channel) and manage.py send_test_email.

Django's test runner swaps in the in-memory email backend, so nothing leaves the machine: sent emails appear in
django.core.mail.outbox.
"""
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings

from booking.notification_channels import reset_channels
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
                mock.patch("booking.email_channel.send_mail", side_effect=OSError("no network")), \
                self.assertLogs("booking.email_channel", "ERROR") as logged:
            reset_channels()
            response = self.create_booking()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn("no network", "\n".join(logged.output))


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
