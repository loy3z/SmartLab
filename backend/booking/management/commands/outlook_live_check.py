"""Real Microsoft Graph test against your own calendar (run on your computer after signing in).

Does what the booking system does, against the real calendar: creates one temporary event without attendees,
reads it back, moves it as a Manager's reschedule would, reads it back again and deletes it as a cancellation
would. Nothing is invited and the event is removed at the end (also when a step fails).
"""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.module_loading import import_string

from booking.outlook import OutlookError, event_differences


@dataclass(frozen=True)
class _Booking:
    id: str
    start: datetime
    end: datetime
    urgent: bool = False


@dataclass(frozen=True)
class _Person:
    id: str
    display_name: str
    university_email: str


@dataclass(frozen=True)
class _Resource:
    id: str
    name: str
    location: str


class Command(BaseCommand):
    help = "Run create / read / reschedule / cancel against the configured Outlook calendar."

    def handle(self, *args, **options):
        provider = import_string(settings.OUTLOOK_PROVIDER_FACTORY)()
        if not provider.configured:
            raise CommandError("Outlook is not configured: run outlook_login (or outlook_token) first.")
        provider.invite_mode = "none"  # never invite anyone from this check
        start = (datetime.now(UTC) + timedelta(days=3)).replace(hour=3, minute=0, second=0, microsecond=0)
        booking = _Booking(str(uuid4()), start, start + timedelta(minutes=30))
        person = _Person(str(uuid4()), "SmartLab live check", "live-check@example.invalid")
        resource = _Resource(str(uuid4()), "Live check (safe to delete)", "SmartLab test")
        path = provider.target_path()
        event_id = None
        failures = 0

        def step(name, ok, detail=""):
            nonlocal failures
            failures += not ok
            self.stdout.write(f"{'PASS' if ok else 'FAIL'}  {name}{('  - ' + detail) if detail else ''}")
            return ok

        try:
            self.stdout.write(f"Mode: {provider.mode}. Calendar: {path}")
            details = provider.check_connection()
            step("1 connect and read the calendar", True, details.get("calendar_name") or "")
            event = provider.create_event(booking, person, resource, path, transaction_id=booking.id)
            event_id = event.id
            step("2 create a temporary event", bool(event_id), start.strftime("%Y-%m-%d %H:%M UTC"))
            expected = provider.expected_snapshot(booking, person, resource)
            found = event_differences(expected, provider.get_event(path, event_id))
            step("3 read it back: matches the booking", not found, ", ".join(found))
            moved = _Booking(booking.id, booking.start + timedelta(hours=2), booking.end + timedelta(hours=2))
            provider.update_event(moved, person, resource, path, event_id)
            found = event_differences(provider.expected_snapshot(moved, person, resource), provider.get_event(path, event_id))
            step("4 reschedule moves the same event", not found, ", ".join(found) or moved.start.strftime("%H:%M UTC"))
            provider.delete_event(path, event_id)
            try:
                snapshot = provider.get_event(path, event_id)
                step("5 cancellation removes the event", snapshot.cancelled, "event still readable")
            except OutlookError as exc:
                step("5 cancellation removes the event", exc.code == "GRAPH_HTTP_404", exc.code)
            event_id = None
        except OutlookError as exc:
            step("Microsoft Graph call", False, exc.code)
        finally:
            if event_id:
                try:
                    provider.delete_event(path, event_id)
                    self.stdout.write("Temporary event removed.")
                except OutlookError as exc:
                    self.stdout.write(f"Could not remove the temporary event ({exc.code}); delete "
                                      f"'SmartLab booking: {resource.name}' in Outlook by hand.")
        if failures:
            raise CommandError(f"{failures} step(s) failed.")
        self.stdout.write("All live Outlook checks passed.")
