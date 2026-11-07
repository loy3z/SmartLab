"""Booking rules in one place, behind a small interface.

Every number the client may want to change later (how far ahead people may book, how long a verified
induction stays valid, the default admin review window for new resources, the weekly and future-booking limits, check-in
times and the longest weekly series) is read through a
RulesProvider instead of being written into the booking code.

* Today: SettingsRulesProvider reads environment variables (see config/settings.py and .env.example).
* Later: write a provider that reads the values from a database table edited on a Manager page,
  implement ``current()``, and point RULES_PROVIDER at it. No booking code needs to change.

Rules that belong to one resource (opening hours, slot length, maximum duration, review window,
required induction, status) stay on the Resource record itself.
"""

from dataclasses import dataclass
from typing import Protocol

from .domain import MAX_PENDING_HOLD_MINUTES


def _bounded_int(name, value, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high}.")
    return value


@dataclass(frozen=True)
class BookingRules:
    # A new or rescheduled booking must start between these many local calendar days from today.
    # The client maximum is four weeks, including every occurrence of a staff-created series.
    # Checked when a request is submitted or rescheduled, not again when it is approved.
    min_advance_days: int = 7
    max_advance_days: int = 28
    # A verified induction stays valid this many days after it is approved.
    qualification_validity_days: int = 120
    # Review window given to new resources (each resource can then have its own value).
    default_review_window_minutes: int = 1440
    # Fair-use unit confirmed by the client: one quota slot is 30 minutes. A normal
    # request may use at most six slots (three hours). A resource may still set a
    # shorter technical maximum; longer requests will use a separate Manager flow.
    booking_slot_minutes: int = 30
    max_slots_per_booking: int = 6
    # Fair-use allowance confirmed by the client. Pending, waitlisted and approved
    # bookings all consume these 30-minute slots in the local Monday-Sunday week.
    max_slots_per_week: int = 24
    # Pending, waitlisted and approved bookings whose start is still in the future
    # all count towards this per-person limit.
    max_active_future_bookings: int = 8
    # Managers may grant additional weekly hours only this close to the requested start.
    additional_hours_approval_window_hours: int = 48
    # "I'm here" check-in is open from this many minutes before the start to this many minutes after it
    # (never after the end). Not checking in by then is a missed booking (no-show).
    check_in_opens_minutes: int = 15
    check_in_closes_minutes: int = 30
    # Longest weekly series pattern; every kept date must also fit the booking window.
    max_series_weeks: int = 14
    # Sprint 3 reminders: this many hours before an approved booking, and days before a verified induction expires.
    reminder_hours_before: int = 24
    induction_reminder_days: int = 14

    def __post_init__(self):
        _bounded_int("min_advance_days", self.min_advance_days, 0, 365)
        _bounded_int("max_advance_days", self.max_advance_days, 1, 365)
        if self.min_advance_days > self.max_advance_days:
            raise ValueError("min_advance_days must not exceed max_advance_days.")
        _bounded_int("qualification_validity_days", self.qualification_validity_days, 1, 3650)
        _bounded_int("default_review_window_minutes", self.default_review_window_minutes, 1, MAX_PENDING_HOLD_MINUTES)
        _bounded_int("booking_slot_minutes", self.booking_slot_minutes, 1, 240)
        _bounded_int("max_slots_per_booking", self.max_slots_per_booking, 1, 100)
        _bounded_int("max_slots_per_week", self.max_slots_per_week, 1, 1000)
        _bounded_int("max_active_future_bookings", self.max_active_future_bookings, 1, 1000)
        _bounded_int("additional_hours_approval_window_hours", self.additional_hours_approval_window_hours, 1, 168)
        _bounded_int("check_in_opens_minutes", self.check_in_opens_minutes, 0, 240)
        _bounded_int("check_in_closes_minutes", self.check_in_closes_minutes, 1, 480)
        _bounded_int("max_series_weeks", self.max_series_weeks, 1, 52)
        _bounded_int("reminder_hours_before", self.reminder_hours_before, 1, 168)
        _bounded_int("induction_reminder_days", self.induction_reminder_days, 1, 90)


class RulesProvider(Protocol):
    def current(self) -> BookingRules:
        """The rules in force now. Called on every check, so a changed value applies to the next request."""


class StaticRulesProvider:
    """Fixed rules; used by tests and when the service is built directly."""

    def __init__(self, rules: BookingRules):
        self._rules = rules

    def current(self) -> BookingRules:
        return self._rules


class SettingsRulesProvider:
    """Reads the rule environment variables listed in config/settings.py and .env.example."""

    def current(self) -> BookingRules:
        from django.conf import settings
        return BookingRules(
            min_advance_days=settings.MIN_ADVANCE_DAYS,
            max_advance_days=settings.MAX_ADVANCE_DAYS,
            qualification_validity_days=settings.QUALIFICATION_VALIDITY_DAYS,
            default_review_window_minutes=settings.DEFAULT_PENDING_HOLD_MINUTES,
            booking_slot_minutes=settings.BOOKING_SLOT_MINUTES,
            max_slots_per_booking=settings.MAX_SLOTS_PER_BOOKING,
            max_slots_per_week=settings.MAX_SLOTS_PER_WEEK,
            max_active_future_bookings=settings.MAX_ACTIVE_FUTURE_BOOKINGS,
            additional_hours_approval_window_hours=settings.ADDITIONAL_HOURS_APPROVAL_WINDOW_HOURS,
            check_in_opens_minutes=settings.CHECK_IN_OPENS_MINUTES,
            check_in_closes_minutes=settings.CHECK_IN_CLOSES_MINUTES,
            max_series_weeks=settings.MAX_SERIES_WEEKS,
            reminder_hours_before=settings.REMINDER_HOURS_BEFORE,
            induction_reminder_days=settings.INDUCTION_REMINDER_DAYS,
        )
