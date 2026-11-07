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

2026-11-07 (client, Week 8): the person asks to extend a booking in progress and a Manager decides
(``extend_booking``, ``review_extension``); a Manager's own extension applies at once.
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
        """2026-11-07 (client, Week 8): finish a booking in progress later.

        The person the booking is for asks for a later end (by dragging it on the page). It waits for a Manager, as when
        they emailed the Manager, who checked that nobody had booked the time after. A Manager extending a booking
        applies it at once. Checked now and again when a Manager approves: the booking is approved and in progress, the
        new end fits the resource's opening hours, longest booking and time steps, and the time after is free (it is
        not held while the request waits). Asking again replaces the requested end.
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
            self._check_extension(source, end)
            if manager:
                return self._apply_extension(actor, source, end)
            requested = replace(source, extension_end=end, updated_at=now)
            self._save_booking(requested)
            self._audit(actor.id, "EXTENSION_REQUESTED", "booking", source.id, current_end=source.end.isoformat(), requested_end=end.isoformat())
            self._notify_managers("EXTENSION_REQUESTED", "Extension requested",
                                  f"{actor.display_name} ({actor.zid}) asks to finish {self._booking_label(source)} later, "
                                  f"at {self.describe_moment(end, source)}.", source, link="/manager/home", except_ids={actor.id})
            return requested

    def review_extension(self, actor, booking_id, decision, reason="", *, expected_end=None):
        """Manager: approve (the end moves, if the time after is still free) or reject (with a reason) a waiting request."""
        self.require_manager(actor)
        if decision not in ("APPROVED", "REJECTED"):
            raise DomainError("VALIDATION_ERROR", "Choose APPROVED or REJECTED.")
        if decision == "REJECTED" and not reason.strip():
            raise DomainError("REASON_REQUIRED", "A rejection reason is required.")
        self.process_due_requests()
        source = self.booking_for(actor, booking_id)
        with self.repo.atomic(resource_ids=[source.resource_id], student_ids=[source.student_id]):
            source = self.booking_for(actor, booking_id)
            if source.extension_end is None or source.status != BookingStatus.APPROVED:
                raise DomainError("NO_EXTENSION_REQUEST", "This booking has no extension request waiting.", 409)
            # Sprint 3: decide the time the Manager saw, not a replacement submitted while the page was open.
            if expected_end is not None and source.extension_end != expected_end:
                raise DomainError("EXTENSION_CHANGED", "The requested end changed. Refresh the page before deciding.", 409)
            if decision == "REJECTED":
                rejected = replace(source, extension_end=None, updated_at=self.now())
                self._save_booking(rejected)
                self._audit(actor.id, "EXTENSION_REJECTED", "booking", source.id, reason=reason.strip())
                self._notify(source.student_id, "EXTENSION_REJECTED", "Extension not approved",
                             f"Your request to finish {self._booking_label(source)} later was not approved. Reason: {reason.strip()}", source)
                return rejected
            if source.extension_end <= self.now():
                raise DomainError("EXTENSION_EXPIRED", "The requested end has already passed.", 409)
            self._check_extension(source, source.extension_end)
            return self._apply_extension(actor, source, source.extension_end)

    def _check_extension(self, booking, end):
        """The booking with its new end still fits the resource, and nobody has booked or is holding the time after."""
        resource = self.resource(booking.resource_id)
        error = (self._account_violation(booking.student_id) or self._resource_violation(resource)
                 or self._period_violation(resource, booking.start, end, allow_long_booking=True, started=True))
        if error:
            raise error
        if self._overlaps(booking.resource_id, booking.end, end, booking.id):
            raise DomainError("BOOKING_CONFLICT", "Someone has already booked or is holding the time after this booking.", 409)

    def _apply_extension(self, actor, booking, end):
        extended = replace(booking, end=end, extension_end=None, updated_at=self.now(), revision=booking.revision + 1)
        self._save_booking(extended)
        self._audit(actor.id, "BOOKING_EXTENDED", "booking", booking.id, old_end=booking.end.isoformat(), new_end=end.isoformat())
        if actor.id != booking.student_id:
            self._notify(booking.student_id, "EXTENSION_APPROVED", "Booking extended",
                         f"{self._booking_label(extended)} now ends at {self.describe_moment(end, extended)}.", extended)
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
