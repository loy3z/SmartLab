"""Sprint 3 (1.16.0): change requests — the person a booking is for asks to move it to another time.

How it works (agreed with Loy on 2026-10-25):

- Only an approved, future booking can be changed, and only by the person it is for. The new time is on the same
  resource and goes through the normal request rules (booking window, opening hours, length, induction,
  weekly limit). Urgent changes are not offered.
- The change is a new booking request whose ``replaces_id`` points at the old booking. Free time: it waits for
  review like any request. Taken or held time: it joins the waitlist (the page warns about this before sending).
- The old booking stays until the new time is approved (by an Admin, by the system when the review window ends, or
  after moving up the waitlist). At that moment the old booking is cancelled automatically and its time is offered
  to the waitlist. If the change is rejected, withdrawn or expires, the old booking simply stays.
- One open change request per booking at a time.

Managers can still move a booking directly (``reschedule_booking`` in bookings.py).

2026-11-06 (client, Week 8): a booking in progress can be extended at once (``extend_booking``).
"""
from dataclasses import replace
from datetime import UTC

from ..domain import BookingStatus, Role
from ..errors import DomainError
from .base import UNDECIDED_STATUSES


class ChangesMixin:
    def request_time_change(self, actor, booking_id, start, end, idempotency_key=None):
        """Ask to move the actor's own approved booking to start–end. Returns (new request, created)."""
        self.require_booking_user(actor)
        self.process_due_requests()
        source = self.booking_for(actor, booking_id)
        if source.student_id != actor.id:
            raise DomainError("FORBIDDEN", "Only the person a booking is for can ask to change its time.", 403)
        if source.additional_hours:
            raise DomainError("ADDITIONAL_HOURS_NEW_REQUEST_REQUIRED",
                              "Additional hours are approved for one exact time. Cancel this booking and submit a new additional-hours request.", 409)
        if source.long_booking:
            raise DomainError("LONG_BOOKING_NEW_REQUEST_REQUIRED",
                              "A longer booking is approved for one exact time. Cancel this booking and submit a new longer-booking request.", 409)
        if source.status != BookingStatus.APPROVED or source.start <= self.now():
            raise DomainError("REQUEST_NOT_CHANGEABLE", "Only a future approved booking can be changed.", 409)
        if start.tzinfo is None or start.utcoffset() is None or end.tzinfo is None or end.utcoffset() is None:
            raise DomainError("INVALID_TIME", "Start and end require UTC offsets.")
        if (start, end) == (source.start, source.end):
            raise DomainError("VALIDATION_ERROR", "Choose a time different from the current booking.")
        open_change = self.open_change_for(source)
        if open_change:
            raise DomainError("CHANGE_ALREADY_REQUESTED",
                              "This booking already has a change request waiting. Withdraw it first to ask for another time.",
                              409, {"booking_id": open_change.id})
        return self.create_booking(actor, source.resource_id, start, end, source.purpose, idempotency_key,
                                   replaces=source)

    def extend_booking(self, actor, booking_id, end):
        """2026-11-06 (client, Week 8): stay longer when an experiment runs over and nobody has booked the time after.

        The person a booking is for, or a Manager, moves the end of an approved booking that is in progress. It applies
        at once (no request to review) when the extra time is free and the whole booking still fits the resource's
        opening hours and longest booking. For everyone but a Manager the normal limits apply too: the 3-hour booking,
        the weekly hours and an induction valid until the new end; when they do not allow it, a Manager can extend
        it. Managers are told about every extension, so they know the lab stays in use.
        """
        self.process_due_requests()
        source = self.booking_for(actor, booking_id)
        manager = actor.role == Role.MANAGER
        if source.student_id != actor.id and not manager:
            raise DomainError("FORBIDDEN", "Only the person a booking is for, or a Manager, can extend it.", 403)
        if source.additional_hours or source.long_booking:
            raise DomainError("EXTENSION_NOT_AVAILABLE", "This booking was approved for one exact time; ask a Manager to change it.", 409)
        if end.tzinfo is None or end.utcoffset() is None:
            raise DomainError("INVALID_TIME", "The new end requires a UTC offset.")
        end = end.astimezone(UTC)
        with self.repo.atomic(resource_ids=[source.resource_id], student_ids=[source.student_id]):
            source = self.booking_for(actor, booking_id)
            now = self.now()
            if source.status != BookingStatus.APPROVED or not source.start <= now < source.end:
                raise DomainError("EXTENSION_NOT_AVAILABLE", "Only an approved booking that is in progress can be extended.", 409)
            if end <= source.end:
                raise DomainError("VALIDATION_ERROR", "Choose an end later than the current end.")
            resource = self.resource(source.resource_id)
            error = (self._account_violation(source.student_id) or self._resource_violation(resource)
                     or self._period_violation(resource, source.start, end, allow_long_booking=manager, started=True))
            if not error and not manager:
                error = (self._qualification_violation(source.student_id, resource, end)
                         or self._weekly_limit_violation(source.student_id, resource, source.start, end, source.id))
            if error:
                raise error
            self._reject_duplicate_request(source.student_id, source.resource_id, source.end, end, source.id)
            if self._overlaps(source.resource_id, source.end, end, source.id):
                raise DomainError("BOOKING_CONFLICT", "Someone has already booked or is holding the time after this booking.", 409)
            extended = replace(source, end=end, updated_at=now, revision=source.revision + 1)
            self._save_booking(extended)
            self._audit(actor.id, "BOOKING_EXTENDED", "booking", extended.id,
                        old_end=source.end.isoformat(), new_end=end.isoformat())
            person = self.repo.get_principal(source.student_id)
            self._notify_managers("BOOKING_EXTENDED", "Booking extended",
                                  f"{person.display_name} ({person.zid}) now has {self._booking_label(extended)}.",
                                  extended, link="/admin/bookings", except_ids={actor.id})
            return extended

    def open_change_for(self, booking):
        """The undecided change request (pending or waitlisted) that would replace this booking, if any."""
        return next((item for item in self.repo.list_bookings(student_id=booking.student_id)
                     if item.replaces_id == booking.id and item.status in UNDECIDED_STATUSES), None)

    def _apply_time_change(self, previous, booking):
        """Called on every booking save (base.py ``_save_booking``): when a change request has just been approved,
        cancel the booking it replaces and offer that time to the waitlist.

        Skipped when the old booking is no longer approved (already cancelled) or has already started; the person
        then keeps both, and staff can cancel one.
        """
        if not booking.replaces_id or booking.status != BookingStatus.APPROVED:
            return
        if previous is not None and previous.status == BookingStatus.APPROVED:
            return
        old = self.repo.get_booking(booking.replaces_id)
        if old is None or old.status != BookingStatus.APPROVED or old.start <= self.now():
            return
        cancelled = replace(old, status=BookingStatus.CANCELLED, reason_code="REPLACED_BY_CHANGE", updated_at=self.now())
        self._save_booking(cancelled)
        self._audit("SYSTEM", "BOOKING_REPLACED", "booking", old.id, replaced_by=booking.id,
                    new_start=booking.start.isoformat(), new_end=booking.end.isoformat())
        self._remember_changed([cancelled])  # so the HTTP layer updates Outlook for the old booking too
        self._promote_waitlist(old.resource_id)
