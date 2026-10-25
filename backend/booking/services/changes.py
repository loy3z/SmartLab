"""Sprint 3 (1.16.0): change requests — the person a booking is for asks to move it to another time.

How it works (agreed with Loy on 2026-10-25):

- Only an approved, future booking can be changed, and only by the person it is for. The new time is on the same
  resource and goes through the normal request rules (booking window, opening hours, length, induction, freeze,
  weekly limit). Urgent changes are not offered.
- The change is a new booking request whose ``replaces_id`` points at the old booking. Free time: it waits for
  review like any request. Taken or held time: it joins the waitlist (the page warns about this before sending).
- The old booking stays until the new time is approved (by an Admin, by the system when the review window ends, or
  after moving up the waitlist). At that moment the old booking is cancelled automatically and its time is offered
  to the waitlist. If the change is rejected, withdrawn or expires, the old booking simply stays.
- One open change request per booking at a time.

Managers can still move a booking directly (``reschedule_booking`` in bookings.py).
"""
from dataclasses import replace

from ..domain import BookingStatus
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
