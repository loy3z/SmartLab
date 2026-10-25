"""Sprint 3: check the email settings by sending one test email.

    python manage.py send_test_email --to your.own@address

Uses the same settings as the email channel (EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, ...), but always
sends to the --to address, whatever EMAIL_MODE says. Prints the settings in use (never the password) and Gmail's
error message if sending fails, for example a wrong app password.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

from booking.email_channel import email_mode


class Command(BaseCommand):
    help = "Send one test email with the configured SMTP settings."

    def add_arguments(self, parser):
        parser.add_argument("--to", required=True, help="address to send the test email to (use your own)")

    def handle(self, *args, **options):
        address = options["to"].strip()
        if "@" not in address:
            raise CommandError("--to must be an email address.")
        self.stdout.write(f"Server: {settings.EMAIL_HOST}:{settings.EMAIL_PORT} (TLS {'on' if settings.EMAIL_USE_TLS else 'off'})")
        self.stdout.write(f"Sign in as: {settings.EMAIL_HOST_USER or '(EMAIL_HOST_USER is empty)'}; "
                          f"password {'set' if settings.EMAIL_HOST_PASSWORD else 'NOT set'}")
        self.stdout.write(f"From: {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"Email channel: {'on' if settings.EMAIL_ENABLED else 'off'} (EMAIL_ENABLED); "
                          f"EMAIL_MODE={email_mode()}")
        body = ("This is a test email from SmartLab.\n\n"
                "If you can read this, the system mailbox works. Booking emails are sent only when EMAIL_ENABLED=true, "
                "and EMAIL_MODE decides who receives them.\n\n"
                f"Web app: {settings.SITE_URL}")
        try:
            send_mail("SmartLab: test email", body, settings.DEFAULT_FROM_EMAIL, [address], fail_silently=False)
        except Exception as exc:
            raise CommandError(f"Sending failed: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Sent to {address}. Check the inbox (and the spam folder)."))
