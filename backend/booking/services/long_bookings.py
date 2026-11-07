"""Separate requests to exceed only the normal single-booking duration, approved manually by a Manager."""
import re
from dataclasses import replace
from datetime import UTC
from uuid import UUID, uuid4, uuid5

from ..domain import Booking, BookingStatus
from ..errors import DomainError
from .base import HEAD_STATUSES, UNDECIDED_STATUSES


class LongBookingsMixin:
    def create_long_booking(self, actor, resource_id, start, end, purpose, long_booking_reason,
                            idempotency_key=None, on_behalf_of_zid=None):
        self.require_booking_user(actor)
        self.process_due_requests()
        purpose = (purpose or "").strip()
        reason = (long_booking_reason or "").strip()
        if not purpose or len(purpose) > 1000:
            raise DomainError("VALIDATION_ERROR", "A booking purpose of up to 1000 characters is required.")
        if not reason or len(reason) > 1000:
            raise DomainError("LONG_BOOKING_REASON_REQUIRED", "Explain why a longer booking is needed (up to 1000 characters).")
        if start.tzinfo is None or start.utcoffset() is None or end.tzinfo is None or end.utcoffset() is None:
            raise DomainError("INVALID_TIME", "Start and end require UTC offsets.")
        start, end = start.astimezone(UTC), end.astimezone(UTC)
        beneficiary = self._beneficiary(actor, on_behalf_of_zid)
        resource_id = str(resource_id)
        if idempotency_key:
            if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", idempotency_key):
                raise DomainError("INVALID_IDEMPOTENCY_KEY", "Use up to 128 letters, digits, dots, underscores, colons or hyphens.")
            booking_id = str(uuid5(UUID("3797490d-6aa7-4bf0-b004-aa50ffab4adc"), f"{actor.id}:{idempotency_key}"))
        else:
            booking_id = str(uuid4())
        with self.repo.atomic(resource_ids=[resource_id], student_ids=[beneficiary.id]):
            existing = self.repo.get_booking(booking_id)
            if existing:
                if ((existing.resource_id, existing.start, existing.end, existing.purpose, existing.student_id,
                     existing.long_booking, existing.long_booking_reason, existing.additional_hours)
                        != (resource_id, start, end, purpose, beneficiary.id, True, reason, False)):
                    raise DomainError("IDEMPOTENCY_CONFLICT", "This Idempotency-Key was already used with different booking details.", 409)
                return existing, False
            resource = self.resource(resource_id)
            error = self.rule_violation(beneficiary.id, resource, start, end, check_window=True, allow_long_booking=True)
            if error:
                raise error
            normal_maximum = self._normal_booking_limit(resource)[2]
            if (end - start).total_seconds() / 60 <= normal_maximum:
                raise DomainError("LONG_BOOKING_NOT_NEEDED", "This duration fits the normal limit; submit a normal booking request.",
                                  400, {"normal_max_booking_minutes": normal_maximum})
            self._reject_duplicate_request(beneficiary.id, resource_id, start, end)
            error = (self._weekly_limit_violation(beneficiary.id, resource, start, end)
                     or self._future_booking_limit_violation(beneficiary.id))
            if error:
                raise error
            conflicts = self._overlaps(resource_id, start, end)
            now = self.now()
            deadline = None if conflicts else self._review_deadline(resource, start)
            status = BookingStatus.WAITLISTED if conflicts else BookingStatus.PENDING_APPROVAL
            booking = Booking(booking_id, beneficiary.id, resource_id, start, end, purpose, now, status,
                              "LONG_BOOKING_WAITLISTED" if conflicts else "LONG_BOOKING_AWAITING_MANAGER",
                              review_due_at=deadline, hold_until=deadline, updated_at=now, created_by=actor.id,
                              long_booking=True, long_booking_reason=reason)
            self._save_booking(booking)
            self._audit(actor.id, "LONG_BOOKING_REQUESTED", "booking", booking.id, reason=reason, booked_for=beneficiary.id,
                        requested_start=start.isoformat(), requested_end=end.isoformat(), status=status.value,
                        review_due_at=deadline.isoformat() if deadline else None)
            self._created_notices(actor, beneficiary, booking)
            self._notify_long_booking_managers(booking)
            return booking, True

    def _notify_long_booking_managers(self, booking):
        state = "is queued behind an earlier booking or request" if booking.status == BookingStatus.WAITLISTED else (
            f"needs a Manager decision by {self.describe_moment(booking.review_due_at, booking)}; it expires without approval")
        self._notify_managers("LONG_BOOKING_REQUEST", "Longer-booking request to decide",
                              f"{self._booking_label(booking)} {state}. Reason: {booking.long_booking_reason}", booking,
                              link="/admin/bookings", except_ids={booking.student_id, booking.created_by})

    def review_long_booking(self, actor, booking_id, decision, reason=""):
        self.require_manager(actor)
        self.process_due_requests()
        if decision not in ("APPROVED", "REJECTED"):
            raise DomainError("VALIDATION_ERROR", "Choose APPROVED or REJECTED.")
        if decision == "REJECTED" and not reason.strip():
            raise DomainError("REASON_REQUIRED", "A rejection reason is required.")
        source = self.booking_for(actor, booking_id)
        with self.repo.atomic(resource_ids=[source.resource_id], student_ids=[source.student_id]):
            source = self.booking_for(actor, booking_id)
            if not source.long_booking:
                raise DomainError("REQUEST_NOT_REVIEWABLE", "This is not a longer-booking request.", 409)
            if decision == "APPROVED" and source.status == BookingStatus.WAITLISTED:
                raise DomainError("REQUEST_WAITLISTED", "This request is queued behind an earlier booking or request.", 409)
            reviewable = HEAD_STATUSES if decision == "APPROVED" else UNDECIDED_STATUSES
            if source.status not in reviewable or source.start <= self.now():
                raise DomainError("REQUEST_NOT_REVIEWABLE", "Only a pending or waitlisted longer-booking request can be reviewed.", 409)
            if source.status in HEAD_STATUSES and (source.review_due_at is None or source.review_due_at <= self.now()):
                raise DomainError("REQUEST_NOT_REVIEWABLE", "The longer-booking review deadline has passed.", 409)
            if source.student_id == actor.id or source.created_by == actor.id:
                raise DomainError("SELF_REVIEW_FORBIDDEN", "You cannot review a request that is for you or that you created.", 403)
            if decision == "APPROVED":
                resource = self.resource(source.resource_id)
                error = (self.rule_violation(source.student_id, resource, source.start, source.end, allow_long_booking=True)
                         or self._weekly_limit_violation(source.student_id, resource, source.start, source.end, source.id)
                         or self._future_booking_limit_violation(source.student_id, source.id))
                if error:
                    raise error
                blockers = self._overlaps(source.resource_id, source.start, source.end, source.id)
                if any(item.status == BookingStatus.APPROVED for item in blockers):
                    raise DomainError("BOOKING_CONFLICT", "This period is already occupied by an approved booking.", 409)
                if blockers:
                    raise DomainError("BOOKING_HOLD_CONFLICT", "This period is temporarily held by an earlier pending request.", 409)
            revised = replace(source, status=BookingStatus(decision), reason_code=f"LONG_BOOKING_{decision}",
                              reviewed_by=actor.id, reviewed_at=self.now(), decision_reason=reason.strip() or None,
                              updated_at=self.now())
            self._save_booking(revised)
            self._audit(actor.id, f"LONG_BOOKING_{decision}", "booking", source.id, reason=reason.strip(),
                        long_booking_reason=source.long_booking_reason, requested_start=source.start.isoformat(),
                        requested_end=source.end.isoformat())
            if decision == "REJECTED":
                self._promote_waitlist(source.resource_id)
            return revised
