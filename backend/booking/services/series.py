"""Sprint 3: Weekly series made by staff (Admin or Manager), for themselves or for someone else.

Staff choose the weekdays, start time, length and first/last date (at most BookingRules.max_series_weeks). A
preview shows every date and whether it can be booked; dates with a problem are skipped by choice, never queued.
The series may reach past the normal "at most N days ahead" window, but every other rule applies to each date:
the minimum advance days, opening hours, length, the person's induction (valid on that date) and conflicts.
Because staff create it, every kept date is approved at once (no review). Series bookings do not count towards
the weekly limit, but check-in applies. Each date is an ordinary booking with series_id, so cancelling one date,
rescheduling it, Outlook and the calendar link work as for any booking.
"""
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from ..domain import Booking, BookingSeries, BookingStatus
from ..errors import DomainError
from .base import ACTIVE_REQUEST_STATUSES
from ..test_console import booking_rules_bypassed, test_period_violation


class SeriesMixin:
    def _series_plan(self, actor, resource_id, weekdays, start_time, duration_minutes, first_date, last_date,
                     on_behalf_of_zid=None):
        """Validate the pattern and check every date. Returns (resource, person, [occurrence dict])."""
        self.require_staff(actor)
        person = self._beneficiary(actor, on_behalf_of_zid)
        error = self.frozen_violation(self.repo.get_principal(person.id) or person)
        if error and not booking_rules_bypassed(actor, person.id):
            raise error
        resource = self.resource(resource_id)
        days = sorted({int(item) for item in weekdays})
        if not days or any(item < 1 or item > 7 for item in days):
            raise DomainError("VALIDATION_ERROR", "Choose at least one weekday (1 = Monday ... 7 = Sunday).")
        if not isinstance(first_date, date) or not isinstance(last_date, date) or last_date < first_date:
            raise DomainError("VALIDATION_ERROR", "The last date must be on or after the first date.")
        weeks = 52 if booking_rules_bypassed(actor, person.id) else self.rules().max_series_weeks
        if (last_date - first_date).days >= weeks * 7:
            raise DomainError("SERIES_TOO_LONG", f"A weekly series can cover at most {weeks} weeks.", 400, {"max_weeks": weeks})
        if not isinstance(start_time, time):
            raise DomainError("VALIDATION_ERROR", "Choose a start time.")
        zone = ZoneInfo(resource.timezone)
        earliest, _ = self.booking_window(resource)
        occurrences = []
        day = first_date
        while day <= last_date:
            if day.isoweekday() in days:
                start = datetime.combine(day, start_time, zone).astimezone(UTC)
                end = start + timedelta(minutes=duration_minutes)
                occurrences.append(self._series_check(actor, person, resource, day, start, end, earliest))
            day += timedelta(days=1)
        if not occurrences:
            raise DomainError("SERIES_EMPTY", "No date in this range falls on the chosen weekdays.")
        return resource, person, days, occurrences

    def _series_check(self, actor, person, resource, day, start, end, earliest):
        # Sprint 3 (1.17.0): written the same way as in _series_plan and create_series (the actor's own series only).
        bypass = booking_rules_bypassed(actor, person.id)
        error = test_period_violation(self, resource, start, end) if bypass else self._period_violation(resource, start, end)
        if error is None and day < earliest and not bypass:
            error = DomainError("BOOKING_TOO_SOON", f"Bookings must be made at least {self.min_advance_days} days in advance.")
        if not bypass:
            error = error or self.rule_violation(person.id, resource, start, end)
        if error is None and self._student_overlap(person.id, resource.id, start, end):
            error = DomainError("DUPLICATE_BOOKING", "This person already has a request for this resource at this time.")
        if error is None and self._overlaps(resource.id, start, end):
            error = DomainError("BOOKING_CONFLICT", "This time is already booked or held.")
        return {"date": day.isoformat(), "start": start, "end": end, "available": error is None,
                "reason_code": error.code if error else None, "message": error.message if error else None}

    def preview_series(self, actor, resource_id, weekdays, start_time, duration_minutes, first_date, last_date,
                       on_behalf_of_zid=None):
        self.process_due_requests()
        resource, person, days, occurrences = self._series_plan(actor, resource_id, weekdays, start_time, duration_minutes,
                                                                first_date, last_date, on_behalf_of_zid)
        return {"resource_id": resource.id, "booking_for": {"id": person.id, "zid": person.zid,
                                                            "display_name": person.display_name, "role": person.role.value},
                "weekdays": days, "occurrences": occurrences,
                "available_count": sum(1 for item in occurrences if item["available"])}

    def create_series(self, actor, resource_id, weekdays, start_time, duration_minutes, first_date, last_date, purpose,
                      on_behalf_of_zid=None, skip_dates=()):
        """Create the kept dates as approved bookings. A date with a problem must be listed in skip_dates."""
        self.process_due_requests()
        purpose = (purpose or "").strip()
        if not purpose or len(purpose) > 1000:
            raise DomainError("VALIDATION_ERROR", "A booking purpose of up to 1000 characters is required.")
        person = self._beneficiary(actor, on_behalf_of_zid)
        skip = {item.isoformat() if isinstance(item, date) else str(item) for item in skip_dates}
        with self.repo.atomic(resource_ids=[str(resource_id)], student_ids=[person.id]):
            resource, person, days, occurrences = self._series_plan(actor, resource_id, weekdays, start_time, duration_minutes,
                                                                    first_date, last_date, on_behalf_of_zid)
            kept = [item for item in occurrences if item["date"] not in skip]
            problems = [item for item in kept if not item["available"]]
            if problems:
                raise DomainError("SERIES_CONFLICT", "Some dates cannot be booked any more: check the dates again.", 409,
                                  {"dates": [{"date": item["date"], "reason_code": item["reason_code"]} for item in problems]})
            if not kept:
                raise DomainError("SERIES_EMPTY", "Keep at least one date.")
            now = self.now()
            series = BookingSeries(str(uuid4()), person.id, actor.id, resource.id, ",".join(str(item) for item in days),
                                   start_time, duration_minutes, first_date, last_date, purpose, now)
            self.repo.save_series(series)
            bookings = []
            for item in kept:
                booking = Booking(str(uuid4()), person.id, resource.id, item["start"], item["end"], purpose, now,
                                  BookingStatus.APPROVED, "SERIES_CREATED_BY_STAFF", reviewed_by=actor.id, reviewed_at=now,
                                  updated_at=now, created_by=actor.id, series_id=series.id,
                                  attendance="NOT_TRACKED" if booking_rules_bypassed(actor, person.id) else None)
                self._save_booking(booking)
                self._audit(actor.id, "BOOKING_CREATED", "booking", booking.id, status=booking.status.value,
                            reason_code=booking.reason_code, series_id=series.id,
                            booked_for=person.id if person.id != actor.id else None)
                bookings.append(booking)
            self._audit(actor.id, "BOOKING_SERIES_CREATED", "series", series.id, resource_id=resource.id, booked_for=person.id,
                        dates=[item["date"] for item in kept], skipped=sorted(skip))
            dates = f"{len(bookings)} date(s) from {kept[0]['date']} to {kept[-1]['date']}, {start_time:%H:%M} ({duration_minutes / 60:g} h)"
            if person.id != actor.id:
                self._notify(person.id, "SERIES_CREATED_FOR_YOU", "Weekly booking made for you",
                             f"{actor.display_name} booked {resource.name} for you on {dates}. All dates are approved.")
            else:  # Sprint 3: confirmation of the staff member's own series
                self._notify(person.id, "SERIES_CREATED", "Weekly booking confirmed",
                             f"You booked {resource.name} on {dates}. All dates are approved.")
            return series, bookings

    def series_detail(self, actor, series_id):
        series = self.repo.get_series(str(series_id))
        if series is None or (not actor.is_staff and series.student_id != actor.id):
            raise DomainError("NOT_FOUND", "Series not found.", 404)
        bookings = sorted((item for item in self.repo.list_bookings(student_id=series.student_id)
                           if item.series_id == series.id), key=lambda item: item.start)
        return series, bookings

    def cancel_series(self, actor, series_id):
        """Staff cancel every future date of a series that is still active (past dates stay as history)."""
        self.require_staff(actor)
        series, bookings = self.series_detail(actor, series_id)
        cancelled = []
        for booking in bookings:
            if booking.status in ACTIVE_REQUEST_STATUSES and booking.start > self.now():
                cancelled.append(self.cancel_booking(actor, booking.id))
        if cancelled:
            self._audit(actor.id, "BOOKING_SERIES_CANCELLED", "series", series.id, cancelled=[item.id for item in cancelled])
        return series, cancelled
