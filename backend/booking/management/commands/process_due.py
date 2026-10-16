"""Decide due booking requests on a schedule (run every few minutes by cron or Windows Task Scheduler).

The website also does this whenever someone uses it; this command makes sure a request whose
24-hour review window ends at night is still decided on time. It is safe to run repeatedly or
from several machines: each decision happens in a locked transaction and is made only once.
"""
from django.core.management.base import BaseCommand, CommandError

from booking.repository import MemoryRepository
from booking.runtime import get_service


class Command(BaseCommand):
    help = "Approve or reject requests whose review window has ended, expire past requests and move the waitlist."

    def add_arguments(self, parser):
        parser.add_argument("--outlook-limit", type=int, default=10,
                            help="Also push up to this many due Outlook updates (0 to skip).")

    def handle(self, *args, **options):
        if not 0 <= options["outlook_limit"] <= 100:
            raise CommandError("Use --outlook-limit between 0 and 100.")
        service = get_service()
        if isinstance(service.repo, MemoryRepository):
            raise CommandError("Memory data is process-local. Use PostgreSQL (REPOSITORY_FACTORY), or "
                               "POST /api/v1/admin/process-due/ on the running demo server.")
        changed = service.process_due_requests()
        service.take_promoted_ids()
        self.stdout.write(f"Decided or expired {len(changed)} request(s).")
        sync = getattr(service, "calendar_sync", None)
        if options["outlook_limit"] and sync is not None and sync.enabled:
            records = sync.process_pending(options["outlook_limit"])
            self.stdout.write(f"Processed {len(records)} Outlook job(s).")
