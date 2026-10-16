"""Booking rules in one place, behind a small interface.

Every number the client may want to change later (how far ahead people may book, how long a verified
induction stays valid, the default admin review window for new resources) is read through a
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
    # Checked when a request is submitted or rescheduled, not again when it is approved.
    min_advance_days: int = 7
    max_advance_days: int = 30
    # A verified induction stays valid this many days after it is approved.
    qualification_validity_days: int = 120
    # Review window given to new resources (each resource can then have its own value).
    default_review_window_minutes: int = 1440

    def __post_init__(self):
        _bounded_int("min_advance_days", self.min_advance_days, 0, 365)
        _bounded_int("max_advance_days", self.max_advance_days, 1, 365)
        if self.min_advance_days > self.max_advance_days:
            raise ValueError("min_advance_days must not exceed max_advance_days.")
        _bounded_int("qualification_validity_days", self.qualification_validity_days, 1, 3650)
        _bounded_int("default_review_window_minutes", self.default_review_window_minutes, 1, MAX_PENDING_HOLD_MINUTES)


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
    """Reads MIN_ADVANCE_DAYS, MAX_ADVANCE_DAYS, QUALIFICATION_VALIDITY_DAYS and DEFAULT_PENDING_HOLD_MINUTES."""

    def current(self) -> BookingRules:
        from django.conf import settings
        return BookingRules(
            min_advance_days=settings.MIN_ADVANCE_DAYS,
            max_advance_days=settings.MAX_ADVANCE_DAYS,
            qualification_validity_days=settings.QUALIFICATION_VALIDITY_DAYS,
            default_review_window_minutes=settings.DEFAULT_PENDING_HOLD_MINUTES,
        )
