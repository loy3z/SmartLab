"""Run once or schedule this command; memory demo must use the server endpoint."""
from django.core.management.base import BaseCommand, CommandError

from booking.repository import MemoryRepository
from booking.runtime import get_service


class Command(BaseCommand):
    help = "Process due Outlook jobs using a shared durable repository."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 100:
            raise CommandError("Use --limit between 1 and 100.")
        service = get_service()
        if isinstance(service.repo, MemoryRepository):
            raise CommandError("Memory data is process-local. Use POST /api/v1/admin/outlook/process/ in the running demo server.")
        if not service.calendar_sync.enabled:
            raise CommandError("Enable OUTLOOK_ENABLED first.")
        records = service.calendar_sync.process_pending(options["limit"])
        self.stdout.write(f"Processed {len(records)} Outlook jobs.")
