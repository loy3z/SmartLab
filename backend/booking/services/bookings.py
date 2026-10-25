"""Booking requests: create (incl. on behalf and urgent), review, cancel and Manager reschedule."""
import re
from dataclasses import replace
from datetime import UTC
from uuid import UUID, uuid4, uuid5

from ..domain import Booking, BookingStatus, Role
from ..errors import DomainError
from .base import HEAD_STATUSES, UNDECIDED_STATUSES
from ..test_console import booking_rules_bypassed, create_test_booking, test_period_violation


class BookingsMixin:
    def create_booking(self, actor, resource_id, start, end, purpose, idempotency_key=None,
                       on_behalf_of_zid=None, urgent=False, urgent_reason=None, replaces=None):
        """Every request starts as pending (never confirmed straight away).

        Free time: PENDING_APPROVAL, holding the slot until an Admin decides or the review window
        (resource.pending_hold_minutes, default 24 hours) ends, when the system approves it if it still
        follows the rules and rejects it otherwise. Taken or held time: WAITLISTED in submission order.

        Anyone with an active account may book for themselves; an Admin or Manager may also book for
        someone else (on_behalf_of_zid). The booking belongs to that person (``student_id``, whose induction
        is checked) and records who created it (``created_by``) for accountability.

        Urgent request: a start sooner than the minimum advance window, with a reason. It
        skips only that window; induction, opening hours, length and conflicts still apply, the time must
        be free (no waitlist), and only a Manager can approve it (never automatic). Undecided, it expires
        at its start time.

        replaces (Sprint 3, 1.16.0): the approved booking a change request moves (see changes.py). Its own old time
        does not count as a clash, a duplicate or an extra booking in the week.
        """
        self.require_booking_user(actor)
        self.process_due_requests()
        resource_id = str(resource_id)
        if not purpose.strip() or len(purpose) > 1000:
            raise DomainError("VALIDATION_ERROR", "A booking purpose of up to 1000 characters is required.")
        if urgent and replaces is not None:  # Sprint 3 (1.16.0)
            raise DomainError("VALIDATION_ERROR", "A change request uses the normal booking window; it cannot be urgent.")
        urgent_reason = (urgent_reason or "").strip()
        if urgent and (not urgent_reason or len(urgent_reason) > 500):
            raise DomainError("URGENT_REASON_REQUIRED", "Explain why the request is urgent (up to 500 characters).")
        beneficiary = self._beneficiary(actor, on_behalf_of_zid)
        bypass = booking_rules_bypassed(actor, beneficiary.id)
        frozen = self.frozen_violation(  # Sprint 3: booking freeze
            self.repo.get_principal(beneficiary.id) or beneficiary)
        if start.tzinfo is None or start.utcoffset() is None or end.tzinfo is None or end.utcoffset() is None:
            raise DomainError("INVALID_TIME", "Start and end require UTC offsets.")
        start, end = start.astimezone(UTC), end.astimezone(UTC)
        if idempotency_key:
            if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", idempotency_key):
                raise DomainError("INVALID_IDEMPOTENCY_KEY", "Use up to 128 letters, digits, dots, underscores, colons or hyphens.")
            booking_id = str(uuid5(UUID("3797490d-6aa7-4bf0-b004-aa50ffab4adc"), f"{actor.id}:{idempotency_key}"))
        else:
            booking_id = str(uuid4())
        with self.repo.atomic(resource_ids=[resource_id], student_ids=[beneficiary.id]):
            existing = self.repo.get_booking(booking_id)
            if existing:
                if ((existing.resource_id, existing.start, existing.end, existing.purpose, existing.student_id, existing.urgent)
                        != (resource_id, start, end, purpose.strip(), beneficiary.id, bool(urgent))):
                    raise DomainError("IDEMPOTENCY_CONFLICT", "This Idempotency-Key was already used with different booking details.", 409)
                return existing, False
            resource = self.resource(resource_id)
            if bypass:
                return create_test_booking(self, actor, resource, booking_id, start, end, purpose,
                                           urgent, urgent_reason, replaces)
            if frozen:
                raise frozen
            self._validate_period(resource, start, end)
            if urgent:
                window = self._window_reason(resource, start)
                if window == "BOOKING_TOO_FAR_AHEAD":
                    self._validate_horizon(resource, start)
                if window is None:
                    raise DomainError("URGENT_NOT_NEEDED", "This time is inside the normal booking window: send a normal request.",
                                      400, self._window_details(resource))
            else:
                self._validate_horizon(resource, start)
            replaced_id = replaces.id if replaces else None  # Sprint 3 (1.16.0): change request
            self._reject_duplicate_request(beneficiary.id, resource_id, start, end, replaced_id)
            error = (self.rule_violation(beneficiary.id, resource, start, end, check_window=not urgent)
                     or self._weekly_limit_violation(beneficiary.id, resource, start, replaced_id))  # Sprint 3: weekly limit
            if error:
                raise error
            now = self.now()
            conflicts = self._overlaps(resource_id, start, end, also_exclude=replaced_id)
            on_behalf = beneficiary.id != actor.id
            if urgent:
                if conflicts:
                    raise DomainError("BOOKING_CONFLICT", "An urgent request needs free time: this period is already booked or held.", 409)
                booking = Booking(booking_id, beneficiary.id, resource_id, start, end, purpose.strip(), now,
                                  BookingStatus.PENDING_APPROVAL, "URGENT_AWAITING_MANAGER", review_due_at=None,
                                  updated_at=now, hold_until=start, created_by=actor.id, urgent=True,
                                  urgent_reason=urgent_reason)
                self._save_booking(booking)
                self._audit(actor.id, "BOOKING_CREATED", "booking", booking.id, status=booking.status.value,
                            reason_code=booking.reason_code, hold_until=start.isoformat(), urgent=True,
                            urgent_reason=urgent_reason, booked_for=beneficiary.id if on_behalf else None)
                self._created_notices(actor, beneficiary, booking)
                self._notify_managers("URGENT_REQUEST", "Urgent request to decide",
                                      f"{beneficiary.display_name} ({beneficiary.zid}) asks for {self._booking_label(booking)}. "
                                      f"Reason: {urgent_reason}", booking, link="/admin/bookings",
                                      except_ids={actor.id, beneficiary.id})
                return booking, True
            if conflicts:
                # Strict FIFO: someone earlier holds or owns this time, so queue behind them.
                status = BookingStatus.WAITLISTED
                reason = "TIME_CONFLICT" if any(item.status == BookingStatus.APPROVED for item in conflicts) else "TEMPORARY_HOLD_CONFLICT"
                deadline = None
            else:
                status, reason = BookingStatus.PENDING_APPROVAL, "AWAITING_REVIEW"
                deadline = self._review_deadline(resource, start)
            booking = Booking(booking_id, beneficiary.id, resource_id, start, end, purpose.strip(), now, status, reason,
                              review_due_at=deadline, updated_at=now, hold_until=deadline, created_by=actor.id,
                              replaces_id=replaced_id)
            self._save_booking(booking)
            self._audit(actor.id, "BOOKING_CREATED", "booking", booking.id, status=status.value, reason_code=reason,
                        hold_until=deadline.isoformat() if deadline else None,
                        booked_for=beneficiary.id if on_behalf else None, replaces=replaced_id)
            self._created_notices(actor, beneficiary, booking)
            return booking, True

    def _created_notices(self, actor, beneficiary, booking):
        """Sprint 3: confirm a new request to the person it is for (also emailed when email is on)."""
        if booking.status == BookingStatus.WAITLISTED:
            state = "is on the waitlist: it moves up when the time frees"
        elif booking.urgent:
            state = "is waiting for a Manager (urgent request)"
        else:
            state = f"is waiting for review; if nobody decides by {self.describe_moment(booking.review_due_at, booking)}, the system decides by the rules"
        if booking.replaces_id:  # Sprint 3 (1.16.0): change request
            old = self.repo.get_booking(booking.replaces_id)
            self._notify(beneficiary.id, "CHANGE_REQUESTED", "Change request received",
                         f"We received your request to move your booking to {self._booking_label(booking)}. It {state}. "
                         f"Your current booking ({self.describe_time(old) if old else 'the old time'}) stays until the new time is approved.",
                         booking)
            return
        if beneficiary.id != actor.id:
            self._notify(beneficiary.id, "BOOKING_CREATED_FOR_YOU", "Booking made for you",
                         f"{actor.display_name} booked {self._booking_label(booking)} for you. It {state}.", booking)
        else:
            self._notify(beneficiary.id, "BOOKING_SUBMITTED", "Request received",
                         f"We received your request for {self._booking_label(booking)}. It {state}. "
                         "It is not confirmed until it is approved.", booking)

    def booking_for(self, actor, booking_id):
        booking = self.repo.get_booking(str(booking_id))
        if booking is None or (actor.role == Role.STUDENT and booking.student_id != actor.id):
            raise DomainError("NOT_FOUND", "Booking not found.", 404)
        return booking

    def review_booking(self, actor, booking_id, decision, reason=""):
        self.require_staff(actor)
        self.process_due_requests()
        if decision not in ("APPROVED", "REJECTED"):
            raise DomainError("VALIDATION_ERROR", "Choose APPROVED or REJECTED.")
        if decision == "REJECTED" and not reason.strip():
            raise DomainError("REASON_REQUIRED", "A rejection reason is required.")
        source = self.booking_for(actor, booking_id)
        with self.repo.atomic(resource_ids=[source.resource_id], student_ids=[source.student_id]):
            source = self.booking_for(actor, booking_id)
            if decision == "APPROVED" and source.status == BookingStatus.WAITLISTED:
                raise DomainError("REQUEST_WAITLISTED", "This request is queued behind an earlier booking or request.", 409)
            reviewable = HEAD_STATUSES if decision == "APPROVED" else UNDECIDED_STATUSES
            if source.status not in reviewable:
                raise DomainError("REQUEST_NOT_REVIEWABLE", "Only a pending or waitlisted request can be reviewed.", 409)
            if source.student_id == actor.id or source.created_by == actor.id:
                raise DomainError("SELF_REVIEW_FORBIDDEN", "You cannot review a request that is for you or that you created.", 403)
            if source.urgent and actor.role != Role.MANAGER:
                raise DomainError("URGENT_NEEDS_MANAGER", "Only a Manager can decide an urgent request.", 403)
            if decision == "APPROVED":
                resource = self.resource(source.resource_id)
                error = self.rule_violation(source.student_id, resource, source.start, source.end)
                if error and error.code == "QUALIFICATION_REQUIRED":
                    raise DomainError("QUALIFICATION_NOT_VERIFIED", "Verify current induction evidence covering the booking before approval.",
                                      409, error.details)
                if error:
                    raise error
                blockers = self._overlaps(source.resource_id, source.start, source.end, source.id, source.replaces_id)
                if any(item.status == BookingStatus.APPROVED for item in blockers):
                    raise DomainError("BOOKING_CONFLICT", "This period is still occupied by an approved booking.", 409)
                if blockers:
                    raise DomainError("BOOKING_HOLD_CONFLICT", "This period is temporarily held by an earlier pending request.", 409,
                                      {"hold_until": max(item.hold_until for item in blockers).isoformat().replace("+00:00", "Z")})
            revised = replace(source, status=BookingStatus(decision), reason_code=f"MANUALLY_{decision}", reviewed_by=actor.id,
                              reviewed_at=self.now(), decision_reason=reason.strip() or None, updated_at=self.now())
            self._save_booking(revised)
            self._audit(actor.id, f"BOOKING_{decision}", "booking", revised.id, reason=reason.strip())
            if decision == "REJECTED":
                self._promote_waitlist(revised.resource_id)
            return revised

    def cancel_booking(self, actor, booking_id):
        self.process_due_requests()
        source = self.booking_for(actor, booking_id)
        with self.repo.atomic(resource_ids=[source.resource_id], student_ids=[source.student_id]):
            source = self.booking_for(actor, booking_id)
            if source.status == BookingStatus.CANCELLED:
                return source
            if source.status in (BookingStatus.REJECTED, BookingStatus.EXPIRED) or source.start <= self.now():
                raise DomainError("REQUEST_NOT_CANCELLABLE", "Only future active requests can be cancelled.", 409)
            reason = "CANCELLED_BY_STAFF" if actor.role in (Role.ADMIN, Role.MANAGER) else "CANCELLED_BY_USER"
            revised = replace(source, status=BookingStatus.CANCELLED, reason_code=reason, updated_at=self.now())
            self._save_booking(revised)
            self._audit(actor.id, "BOOKING_CANCELLED", "booking", revised.id)
            self._promote_waitlist(revised.resource_id)
            return revised

    def reschedule_booking(self, actor, booking_id, start, end):
        """Manager only: move someone's approved future booking to another valid free time.

        Induction, opening hours, length, the latest booking date and conflicts still apply; the minimum
        advance window does not (a Manager may move a booking to an earlier date, as with an urgent request).
        """
        self.require_manager(actor)
        self.process_due_requests()
        source = self.booking_for(actor, booking_id)
        if start.tzinfo is None or start.utcoffset() is None or end.tzinfo is None or end.utcoffset() is None:
            raise DomainError("INVALID_TIME", "Start and end require UTC offsets.")
        start, end = start.astimezone(UTC), end.astimezone(UTC)
        with self.repo.atomic(resource_ids=[source.resource_id], student_ids=[source.student_id]):
            source = self.booking_for(actor, booking_id)
            if source.status != BookingStatus.APPROVED or source.start <= self.now():
                raise DomainError("REQUEST_NOT_RESCHEDULABLE", "Only a future approved booking can be rescheduled.", 409)
            resource = self.resource(source.resource_id)
            bypass = booking_rules_bypassed(actor, source.student_id)
            if not bypass:
                self._validate_period(resource, start, end)
                if self._window_reason(resource, start) == "BOOKING_TOO_FAR_AHEAD":
                    self._validate_horizon(resource, start)
            self._reject_duplicate_request(source.student_id, source.resource_id, start, end, source.id)
            error = test_period_violation(self, resource, start, end) if bypass else (
                self.rule_violation(source.student_id, resource, start, end) or (
                    None if source.series_id else self._weekly_limit_violation(source.student_id, resource, start, source.id)))
            if error and error.code == "QUALIFICATION_REQUIRED":
                raise DomainError("QUALIFICATION_NOT_VERIFIED", "A current qualification covering the new booking period is required.",
                                  409, error.details)
            if error:
                raise error
            blockers = self._overlaps(source.resource_id, start, end, source.id)
            if any(item.status == BookingStatus.APPROVED for item in blockers):
                raise DomainError("BOOKING_CONFLICT", "The requested new period is occupied by another approved booking.", 409)
            if blockers:
                raise DomainError(
                    "BOOKING_HOLD_CONFLICT",
                    "The requested new period is temporarily held by an earlier pending request.",
                    409,
                    {"hold_until": max(item.hold_until for item in blockers).isoformat().replace("+00:00", "Z")},
                )
            if (source.start, source.end) == (start, end):
                return source
            revised = replace(
                source,
                start=start,
                end=end,
                reason_code="RESCHEDULED_BY_MANAGER",
                updated_at=self.now(),
                revision=source.revision + 1,
            )
            self._save_booking(revised)
            self._audit(
                actor.id,
                "BOOKING_RESCHEDULED",
                "booking",
                revised.id,
                old_start=source.start.isoformat(),
                old_end=source.end.isoformat(),
                new_start=revised.start.isoformat(),
                new_end=revised.end.isoformat(),
                revision=revised.revision,
            )
            self._promote_waitlist(revised.resource_id)  # the old period may now be free
            return revised
