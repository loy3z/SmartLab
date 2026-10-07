"""Local-only helper: read a delegated Graph token without putting it in history."""
import getpass
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Save a temporary delegated Graph token for the local Outlook demo."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("This token-file helper is only available with DEBUG=true.")
        if settings.OUTLOOK_ACCESS_TOKEN:
            raise CommandError("Unset OUTLOOK_ACCESS_TOKEN before using the token-file helper.")
        expected = settings.BASE_DIR / ".local" / "outlook-token"
        if not settings.OUTLOOK_TOKEN_FILE or Path(settings.OUTLOOK_TOKEN_FILE).resolve() != expected.resolve():
            raise CommandError("Use the default ignored .local/outlook-token path for this helper.")
        try:
            token = getpass.getpass("Paste the Graph access token (hidden), then press Enter: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise CommandError("Token entry cancelled; no token was saved.") from None
        if not token or "\n" in token or "\r" in token:
            raise CommandError("The token must be a single non-empty line.")
        expected.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(expected, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(token)
        self.stdout.write("Local token saved. Its expiry and permissions will be checked by Microsoft Graph.")
