"""Run time-based booking work continuously in a durable deployment."""

import logging
import signal
from threading import Event
from time import monotonic

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from booking.repository import MemoryRepository
from booking.runtime import get_service


logger = logging.getLogger("booking.scheduler")


class Command(BaseCommand):
    help = ("Run due booking decisions, reminders, attendance checks, email delivery and Outlook retries "
            "at a fixed interval. PostgreSQL or another shared durable repository is required.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval-seconds",
            type=float,
            default=60,
            help="Seconds between scheduler cycle starts (default: 60).",
        )
        parser.add_argument(
            "--outlook-limit",
            type=int,
            default=10,
            help="Maximum Outlook jobs processed per run; use 0 to disable (default: 10).",
        )
        parser.add_argument(
            "--email-limit",
            type=int,
            default=50,
            help="Maximum email jobs processed per run; use 0 to disable (default: 50).",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run one cycle and exit. Useful for deployment smoke tests.",
        )

    def handle(self, *args, **options):
        interval = options["interval_seconds"]
        outlook_limit = options["outlook_limit"]
        email_limit = options["email_limit"]
        once = options["once"]
        if not 1 <= interval <= 3600:
            raise CommandError("Use --interval-seconds between 1 and 3600.")
        if not 0 <= outlook_limit <= 100:
            raise CommandError("Use --outlook-limit between 0 and 100.")
        if not 0 <= email_limit <= 500:
            raise CommandError("Use --email-limit between 0 and 500.")

        service = get_service()
        if isinstance(service.repo, MemoryRepository):
            raise CommandError(
                "The scheduler requires a shared durable repository. Configure PostgreSQL "
                "with REPOSITORY_FACTORY before starting it."
            )

        stop_requested = Event()
        previous_handlers = {}

        def request_stop(signum, _frame):
            self.stdout.write(f"Received signal {signum}; stopping after the current cycle.")
            stop_requested.set()

        if not once:
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, request_stop)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Scheduler started: interval={interval:g}s, email_limit={email_limit}, "
                    f"outlook_limit={outlook_limit}."
                )
            )

        try:
            while True:
                started_at = monotonic()
                try:
                    call_command(
                        "process_due",
                        email_limit=email_limit,
                        outlook_limit=outlook_limit,
                        stdout=self.stdout,
                        stderr=self.stderr,
                    )
                except Exception as exc:
                    logger.exception("Scheduled processing failed; the next cycle will retry.")
                    if once:
                        raise CommandError(f"Scheduled processing failed: {exc}") from exc
                    self.stderr.write(
                        self.style.ERROR(
                            f"Scheduled processing failed: {exc}. The next cycle will retry."
                        )
                    )

                if once:
                    return

                elapsed = monotonic() - started_at
                delay = max(0.0, interval - elapsed)
                if stop_requested.wait(delay):
                    return
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)
