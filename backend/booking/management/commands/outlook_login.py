"""Sign in once with your own Microsoft account (device code); the backend then renews access by itself.

Needs OUTLOOK_PUBLIC_CLIENT_ID (a public-client app registration, no secret). The refresh token is written to
OUTLOOK_REFRESH_TOKEN_FILE (default .local/outlook-refresh-token, ignored by Git) and is never printed.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from booking.outlook import OutlookError, finish_device_login, save_refresh_token, start_device_login


class Command(BaseCommand):
    help = "Sign in to Outlook with a device code so the calendar sync renews its own access."

    def handle(self, *args, **options):
        if not settings.OUTLOOK_PUBLIC_CLIENT_ID:
            raise CommandError("Set OUTLOOK_PUBLIC_CLIENT_ID to the Application (client) ID of your app registration.")
        if not settings.OUTLOOK_REFRESH_TOKEN_FILE:
            raise CommandError("Set OUTLOOK_REFRESH_TOKEN_FILE to a private path (outside Git) first.")
        if settings.OUTLOOK_ACCESS_TOKEN:
            raise CommandError("Unset OUTLOOK_ACCESS_TOKEN: it would be used instead of this sign-in.")
        try:
            started = start_device_login(settings.OUTLOOK_PUBLIC_CLIENT_ID, settings.OUTLOOK_AUTHORITY)
            # The user code is short-lived and only lets *you* finish signing in; it is not a credential.
            self.stdout.write(f"Open {started['verification_uri']} and enter the code {started['user_code']}.")
            self.stdout.write("Sign in with your own Microsoft account and accept Calendars.ReadWrite. Waiting...")
            result = finish_device_login(settings.OUTLOOK_PUBLIC_CLIENT_ID, settings.OUTLOOK_AUTHORITY,
                                         started["device_code"], started.get("interval", 5), started.get("expires_in", 900))
        except OutlookError as exc:
            raise CommandError(f"Sign-in did not finish: {exc.code}.") from None
        except KeyboardInterrupt:
            raise CommandError("Sign-in cancelled; nothing was saved.") from None
        save_refresh_token(settings.OUTLOOK_REFRESH_TOKEN_FILE, settings.OUTLOOK_PUBLIC_CLIENT_ID, result["refresh_token"])
        self.stdout.write("Signed in. Access now renews automatically; run manage.py outlook_live_check to test it.")
