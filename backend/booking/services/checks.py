"""The one shared rule check used by create, approve, automatic decisions, waitlist promotion and reschedule (account
-> resource status -> time -> booking window -> induction and prerequisites), plus conflict lookups.
"""
from datetime import datetime, timedelta
from math import ceil, lcm
from zoneinfo import ZoneInfo

from ..domain import BookingStatus
from ..errors import DomainError
from .base import ACTIVE_REQUEST_STATUSES, UNDECIDED_STATUSES


class ChecksMixin:
    def _selection_step_minutes(self, resource):
        """Smallest selectable step that satisfies both resource and fair-use slots."""
        return lcm(resource.slot_minutes, self.rules().booking_slot_minutes)

    def _normal_booking_limit(self, resource):
        """Return (maximum slots, slot size, effective duration cap) for a normal request."""
        rules = self.rules()
        resource_slots = resource.max_booking_minutes // rules.booking_slot_minutes
        maximum_slots = min(rules.max_slots_per_booking, resource_slots)
        return maximum_slots, rules.booking_slot_minutes, maximum_slots * rules.booking_slot_minutes

    def _long_booking_limit(self, resource):
        """The resource's technical maximum, aligned to its selectable step; no normal duration exemption elsewhere."""
        slot_minutes = self.rules().booking_slot_minutes
        step = self._selection_step_minutes(resource)
        maximum = resource.max_booking_minutes // step * step
        return maximum // slot_minutes, slot_minutes, maximum

    def _overlaps(self, resource_id, start, end, exclude_id=None, also_exclude=None):
        """Bookings and active holds that block this period.

        also_exclude (Sprint 3, 1.16.0): one more booking to ignore. A change request passes the booking it replaces,
        so moving a booking by an hour is not blocked by its own old time.
        """
        found = self.repo.list_blocking_bookings(resource_id, start, end, self.now(), exclude_id)
        return [item for item in found if also_exclude is None or item.id != also_exclude]

    def _student_overlap(self, student_id, resource_id, start, end, exclude_id=None):
        """Return the student's earliest overlapping active request for this resource."""
        matches = [item for item in self.repo.list_bookings(student_id=student_id, resource_id=resource_id)
                   if item.id != exclude_id and item.status in ACTIVE_REQUEST_STATUSES
                   and start < item.end and item.start < end]
        return min(matches, key=lambda item: (item.created_at, item.id)) if matches else None

    def _reject_duplicate_request(self, student_id, resource_id, start, end, exclude_id=None):
        existing = self._student_overlap(student_id, resource_id, start, end, exclude_id)
        if existing:
            raise DomainError(
                "DUPLICATE_BOOKING",
                "You already have an active request for this resource during the selected time.",
                409,
                {"booking_id": existing.id, "status": existing.status.value,
                 "start": existing.start.isoformat().replace("+00:00", "Z"),
                 "end": existing.end.isoformat().replace("+00:00", "Z")},
            )

    def _resource_violation(self, resource):
        if resource is None or not resource.bookable:
            status = "MISSING" if resource is None else resource.status.value if resource.active else "INACTIVE"
            return DomainError("RESOURCE_UNAVAILABLE", "This resource is not accepting bookings right now.", 409,
                               {"resource_status": status, "status_reason": resource.status_reason if resource else None})
        return None

    def _require_bookable(self, resource):
        error = self._resource_violation(resource)
        if error:
            raise error

    def _period_violation(self, resource, start, end, allow_long_booking=False, started=False):
        """Time rules of one resource: future start, maximum length, one local day within opening hours, increments.

        started (2026-11-06): extending a booking in progress, so the start may already have passed.
        """
        if start.tzinfo is None or start.utcoffset() is None or end.tzinfo is None or end.utcoffset() is None:
            return DomainError("INVALID_TIME", "Start and end require UTC offsets.")
        if start >= end or (start <= self.now() and not started):
            return DomainError("INVALID_TIME", "Use a future start time and an end later than start.")
        duration = (end - start).total_seconds() / 60
        max_slots, slot_minutes, maximum = (self._long_booking_limit(resource) if allow_long_booking
                                            else self._normal_booking_limit(resource))
        if duration % slot_minutes:
            return DomainError(
                "INVALID_SLOT_COUNT",
                f"Booking length must use {slot_minutes}-minute increments.",
                400,
                {"slot_minutes": slot_minutes},
            )
        if duration > maximum:
            return DomainError(
                "DURATION_LIMIT",
                f"{'This resource permits bookings' if allow_long_booking else 'A normal booking may be'} up to {maximum / 60:g} h.",
                400,
                {"max_slots": max_slots, "slot_minutes": slot_minutes,
                 "resource_max_minutes": resource.max_booking_minutes},
            )
        local_start = start.astimezone(ZoneInfo(resource.timezone))
        local_end = end.astimezone(ZoneInfo(resource.timezone))
        if (local_start.date() != local_end.date() or local_start.time().replace(tzinfo=None) < resource.opening_time
                or local_end.time().replace(tzinfo=None) > resource.closing_time):
            return DomainError("OUTSIDE_OPENING_HOURS", "Book within one local day and the resource's opening hours.")
        opening = datetime.combine(local_start.date(), resource.opening_time, ZoneInfo(resource.timezone))
        offset = (local_start - opening).total_seconds() / 60
        step = self._selection_step_minutes(resource)
        if start.second or start.microsecond or end.second or end.microsecond or offset % step or duration % step:
            return DomainError("INVALID_TIME_INCREMENT", f"Use {step}-minute time increments.")
        return None

    def _validate_period(self, resource, start, end):
        self._require_bookable(resource)
        error = self._period_violation(resource, start, end)
        if error:
            raise error

    def _account_violation(self, student_id):
        person = self.repo.get_principal(str(student_id))
        if person is None or not person.active:
            return DomainError("ACCOUNT_INACTIVE", "The requester's account is no longer active for booking.", 409)
        return None

    def _qualification_violation(self, student_id, resource, end):
        eligibility, qualified = self.qualification_state(student_id, resource, end)
        if eligibility == "NOT_CONFIGURED":
            return DomainError("RESOURCE_POLICY_NOT_CONFIGURED",
                               "Configure an induction requirement for this resource before accepting requests.", 409)
        if not qualified:
            details = {"qualification_status": eligibility, "requirement_id": resource.required_qualification_id}
            missing = self.missing_prerequisite(student_id, resource.required_qualification_id, end)
            if missing:
                details.update(prerequisite_id=missing[0], prerequisite_status=missing[1])
            return DomainError("QUALIFICATION_REQUIRED",
                               f"A verified induction (and its prerequisites) valid for the whole booking is required (status {eligibility}).",
                               403, details)
        return None

    def rule_violation(self, student_id, resource, start, end, check_window=False, allow_long_booking=False):
        """The one place that decides whether a booking follows the rules (conflicts are checked separately).

        Used when a request is created, approved by an Admin, decided automatically, promoted from the
        waitlist and rescheduled, so all of them apply the same rules: the requester's account is active,
        the resource is open, the time fits the resource (future, opening hours, length, increments) and the
        requester's induction and its prerequisites are valid until the end. The booking window (how many
        days ahead) is checked only when a request is created or rescheduled (check_window=True): a request
        made on time does not become invalid while it waits for review. Returns a DomainError or None.
        """
        return (self._account_violation(student_id) or self._resource_violation(resource)
                or self._period_violation(resource, start, end, allow_long_booking=allow_long_booking)
                or (self._window_violation(resource, start) if check_window else None)
                or self._qualification_violation(student_id, resource, end))

    def booking_window(self, resource):
        """First and last local dates a new or rescheduled booking may start on (from the current rules)."""
        rules = self.rules()
        today = self.now().astimezone(ZoneInfo(resource.timezone)).date()
        return today + timedelta(days=rules.min_advance_days), today + timedelta(days=rules.max_advance_days)

    def _window_details(self, resource):
        rules = self.rules()
        earliest, latest = self.booking_window(resource)
        return {"earliest_date": earliest.isoformat(), "latest_date": latest.isoformat(),
                "min_advance_days": rules.min_advance_days, "max_advance_days": rules.max_advance_days}

    def _window_reason(self, resource, start):
        earliest, latest = self.booking_window(resource)
        day = start.astimezone(ZoneInfo(resource.timezone)).date()
        return "BOOKING_TOO_SOON" if day < earliest else "BOOKING_TOO_FAR_AHEAD" if day > latest else None

    def _window_violation(self, resource, start):
        reason = self._window_reason(resource, start)
        if reason == "BOOKING_TOO_SOON":
            return DomainError(reason, f"Bookings must be made at least {self.min_advance_days} days in advance.", 400,
                               self._window_details(resource))
        if reason == "BOOKING_TOO_FAR_AHEAD":
            return DomainError(reason, f"Bookings can start at most {self.max_advance_days} days ahead.", 400,
                               self._window_details(resource))
        return None

    def _validate_horizon(self, resource, start):
        error = self._window_violation(resource, start)
        if error:
            raise error

    def _duration_slots(self, start, end):
        """Quota slots occupied by a period; round legacy partial slots up conservatively."""
        minutes = (end - start).total_seconds() / 60
        return ceil(minutes / self.rules().booking_slot_minutes)

    def _weekly_limit_violation(self, student_id, resource, start, end, exclude_id=None, additional_slots=0):
        """Enforce the per-person slot allowance for the resource's local Monday-Sunday week.

        Ordinary pending, waitlisted, approved and staff-created series dates all count. Additional-hours
        allocations are separate and never consume this base allowance. ``additional_slots`` reserves earlier
        occurrences while a new series is being validated before it is saved.
        """
        rules = self.rules()
        limit = rules.max_slots_per_week
        zone = ZoneInfo(resource.timezone)
        day = start.astimezone(zone).date()
        week_start = day - timedelta(days=day.weekday())
        used = self._week_slots_used(student_id, zone, week_start, exclude_id)
        requested = self._duration_slots(start, end) + additional_slots
        if used + requested > limit:
            weekly_hours = limit * rules.booking_slot_minutes / 60
            return DomainError("WEEKLY_LIMIT_REACHED",
                               f"A person may book up to {weekly_hours:g} h in one week (Monday to Sunday).",
                               409,
                               {"limit_slots": limit, "used_slots": used,
                                "requested_slots": requested, "remaining_slots": max(0, limit - used),
                                "slot_minutes": rules.booking_slot_minutes,
                                "week_start": week_start.isoformat()})
        return None

    def _week_slots_used(self, student_id, zone, week_start, exclude_id=None):
        """Reserve each possible booking once per week (additional hours excluded).

        An undecided change and its approved future original are alternatives. In the same week, reserve the
        longer duration until the decision; a shorter change must not release hours that its withdrawal restores.
        Across weeks, each week keeps its own reservation until the original is actually cancelled. Once the
        original has started, approval keeps both bookings, so they must count separately.
        """
        week_end = week_start + timedelta(days=7)
        active = {item.id: item for item in self.repo.list_bookings(student_id=str(student_id))
                  if item.id != exclude_id and item.status in ACTIVE_REQUEST_STATUSES and not item.additional_hours}
        now = self.now()
        reserved = {}
        for item in active.values():
            if not week_start <= item.start.astimezone(zone).date() < week_end:
                continue
            original = active.get(item.replaces_id)
            replaces_future = (item.status in UNDECIDED_STATUSES and original is not None
                               and original.status == BookingStatus.APPROVED and original.start > now
                               and original.resource_id == item.resource_id)
            key = original.id if replaces_future else item.id
            reserved[key] = max(reserved.get(key, 0), self._duration_slots(item.start, item.end))
        return sum(reserved.values())

    def _change_approval_quota_violation(self, booking):
        """A late change approval keeps a started original: check the allowance for both before approving."""
        original = self.repo.get_booking(booking.replaces_id) if booking.replaces_id else None
        if original is None or original.status != BookingStatus.APPROVED or original.start > self.now():
            return None
        return self._weekly_limit_violation(booking.student_id, self.resource(booking.resource_id),
                                            booking.start, booking.end, exclude_id=booking.id)

    def week_hours(self, student_id, day=None):
        """Hours booked against the weekly allowance in the Sydney week of ``day`` (default: this week).

        Dashboard (2026-11-03) shows this week; the booking window (2026-11-10, U1) shows the week being booked.
        """
        rules = self.rules()
        zone = ZoneInfo("Australia/Sydney")
        day = day or self.now().astimezone(zone).date()
        week_start = day - timedelta(days=day.weekday())
        hours = lambda slots: slots * rules.booking_slot_minutes / 60  # noqa: E731
        return {"week_start": week_start.isoformat(), "used_hours": hours(self._week_slots_used(student_id, zone, week_start)),
                "limit_hours": hours(rules.max_slots_per_week)}

    def _future_booking_limit_violation(self, student_id, exclude_id=None, additional_count=0):
        """Enforce the per-person cap on active bookings that have not started yet.

        ``additional_count`` reserves earlier occurrences while a new series is
        being checked before any of its bookings are saved. A change request or
        reschedule excludes the booking it replaces, so changing time does not
        temporarily consume two places.
        """
        limit = self.rules().max_active_future_bookings
        now = self.now()
        active = [
            item
            for item in self.repo.list_bookings(student_id=str(student_id))
            if item.id != exclude_id
            and item.status in ACTIVE_REQUEST_STATUSES
            and item.start > now
        ]
        # An open change request represents the same future booking as the
        # approved record it will replace, so the pair consumes one place.
        replaced_ids = {item.replaces_id for item in active if item.replaces_id}
        used = sum(1 for item in active if item.id not in replaced_ids)
        requested = 1 + additional_count
        if used + requested > limit:
            return DomainError(
                "FUTURE_BOOKING_LIMIT_REACHED",
                f"A person may hold up to {limit} active future bookings at a time.",
                409,
                {
                    "limit": limit,
                    "used": used,
                    "requested": requested,
                    "remaining": max(0, limit - used),
                },
            )
        return None

    def _review_deadline(self, resource, start):
        """End of the Admin review window: pending_hold_minutes from now, but never after the booking starts."""
        return min(start, self.now() + timedelta(minutes=resource.pending_hold_minutes))

    def _require_eligible(self, actor_id, resource, end):
        """Only someone whose induction (and its prerequisites) is verified and valid at the end may request it."""
        error = self._qualification_violation(actor_id, resource, end)
        if error:
            raise error
