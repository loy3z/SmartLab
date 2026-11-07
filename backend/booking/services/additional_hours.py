"""Separate, non-reserving requests for spare capacity, decided only by a Manager."""
import re
from dataclasses import replace
from datetime import UTC, timedelta
from uuid import UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

from ..domain import Booking, BookingStatus
from ..errors import DomainError


class AdditionalHoursMixin:
    def create_additional_hours_booking(self, actor, resource_id, start, end, purpose, additional_hours_reason,
                                        idempotency_key=None, on_behalf_of_zid=None, active_data_collection=False,
                                        data_collection_reason=None):
        """Request an extra allocation; neither hold a slot nor consume the ordinary weekly allowance."""
        self.require_booking_user(actor)
        self.process_due_requests()
        purpose = (purpose or "").strip()
        reason = (additional_hours_reason or "").strip()
        collection_reason = (data_collection_reason or "").strip()
        if not purpose or len(purpose) > 1000:
            raise DomainError("VALIDATION_ERROR", "A booking purpose of up to 1000 characters is required.")
        if not reason or len(reason) > 1000:
            raise DomainError("ADDITIONAL_HOURS_REASON_REQUIRED", "Explain the additional-hours request (up to 1000 characters).")
        if not isinstance(active_data_collection, bool):
            raise DomainError("VALIDATION_ERROR", "active_data_collection must be a boolean.")
        if active_data_collection and (not collection_reason or len(collection_reason) > 1000):
            raise DomainError("DATA_COLLECTION_REASON_REQUIRED", "Explain the active data collection (up to 1000 characters).")
        if not active_data_collection and collection_reason:
            raise DomainError("VALIDATION_ERROR", "Only an active-data-collection claim may include its supporting reason.")
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
                     existing.additional_hours, existing.additional_hours_reason, existing.active_data_collection,
                     existing.data_collection_reason, existing.long_booking)
                        != (resource_id, start, end, purpose, beneficiary.id, True, reason, active_data_collection,
                            collection_reason or None, False)):
                    raise DomainError("IDEMPOTENCY_CONFLICT", "This Idempotency-Key was already used with different booking details.", 409)
                return existing, False
            resource = self.resource(resource_id)
            error = self.rule_violation(beneficiary.id, resource, start, end)
            if error:
                raise error
            if self._window_reason(resource, start) == "BOOKING_TOO_FAR_AHEAD":
                self._validate_horizon(resource, start)
            self._reject_duplicate_request(beneficiary.id, resource_id, start, end)
            error = self._future_booking_limit_violation(beneficiary.id)
            if error:
                raise error
            now = self.now()
            booking = Booking(booking_id, beneficiary.id, resource_id, start, end, purpose, now,
                              BookingStatus.PENDING_APPROVAL, "ADDITIONAL_HOURS_AWAITING_MANAGER", updated_at=now,
                              created_by=actor.id, additional_hours=True, additional_hours_reason=reason,
                              active_data_collection=active_data_collection, data_collection_reason=collection_reason or None)
            self._save_booking(booking)
            self._audit(actor.id, "ADDITIONAL_HOURS_REQUESTED", "booking", booking.id,
                        booked_for=beneficiary.id, reason=reason, active_data_collection=active_data_collection,
                        data_collection_reason=collection_reason or None)
            self._created_notices(actor, beneficiary, booking)
            self._notify_managers("ADDITIONAL_HOURS_REQUEST", "Additional-hours request to decide",
                                  f"{beneficiary.display_name} ({beneficiary.zid}) requests {self._booking_label(booking)}. "
                                  f"Reason: {reason}. This request does not hold the time.", booking,
                                  link="/admin/bookings", except_ids={actor.id, beneficiary.id})
            return booking, True

    def _additional_hours_priority(self, booking, context=None):
        context = {} if context is None else context
        priorities = context.setdefault("priorities", {})
        if booking.id in priorities:
            return priorities[booking.id]
        resource = self.repo.get_resource(booking.resource_id)
        zone = ZoneInfo(resource.timezone if resource else "Australia/Sydney")
        day = booking.start.astimezone(zone).date()
        week_start = day - timedelta(days=day.weekday())
        week_end = week_start + timedelta(days=7)
        used = any(item.attendance == "CHECKED_IN" and item.start <= self.now()
                   and week_start <= item.start.astimezone(zone).date() < week_end
                   for item in self.repo.list_bookings(student_id=booking.student_id, statuses=[BookingStatus.APPROVED]))
        reasons = ([] if used else ["NO_USE_THIS_WEEK"]) + (["ACTIVE_DATA_COLLECTION"] if booking.active_data_collection else [])
        priorities[booking.id] = ("PRIORITY" if reasons else "STANDARD"), reasons
        return priorities[booking.id]

    def _additional_hours_approval_error(self, booking, context=None):
        context = {} if context is None else context
        errors = context.setdefault("approval_errors", {})
        if booking.id not in errors:
            errors[booking.id] = self._check_additional_hours_approval(booking)
        return errors[booking.id]

    def _check_additional_hours_approval(self, booking):
        """Business eligibility only; actor permissions, claim confirmation and queue order are separate."""
        if booking.status != BookingStatus.PENDING_APPROVAL:
            return DomainError("REQUEST_NOT_REVIEWABLE", "Only a pending additional-hours request can be approved.", 409)
        now = self.now()
        if booking.start <= now:
            return DomainError("REQUEST_NOT_REVIEWABLE", "The requested booking has already started.", 409)
        hours = self.rules().additional_hours_approval_window_hours
        opens = booking.start - timedelta(hours=hours)
        if now < opens:
            return DomainError("ADDITIONAL_HOURS_TOO_EARLY", f"Additional hours may only be approved within {hours} hours of the start.",
                               409, {"approval_opens_at": opens.isoformat().replace("+00:00", "Z"), "approval_window_hours": hours})
        resource = self.repo.get_resource(booking.resource_id)
        error = self.rule_violation(booking.student_id, resource, booking.start, booking.end)
        if error:
            return error
        if self._window_reason(resource, booking.start) == "BOOKING_TOO_FAR_AHEAD":
            return self._window_violation(resource, booking.start)
        error = self._future_booking_limit_violation(booking.student_id, exclude_id=booking.id)
        if error:
            return error
        blockers = self._overlaps(booking.resource_id, booking.start, booking.end, booking.id)
        if blockers:
            return DomainError("ADDITIONAL_HOURS_NO_CAPACITY", "Additional hours require unused time with no confirmed booking or active hold.", 409)
        return None

    def _additional_hours_queue(self, booking, context=None):
        """Eligible, overlapping requests only; claims provisionally receive priority until Manager review."""
        context = {} if context is None else context
        pending = context.setdefault("pending_by_resource", {})
        if booking.resource_id not in pending:
            pending[booking.resource_id] = [item for item in self.repo.list_bookings(
                resource_id=booking.resource_id, statuses=[BookingStatus.PENDING_APPROVAL]) if item.additional_hours]
        queue = [item for item in pending[booking.resource_id]
                 if item.start < booking.end and booking.start < item.end
                 and self._additional_hours_approval_error(item, context) is None]
        return sorted(queue, key=lambda item: (self._additional_hours_priority(item, context)[0] != "PRIORITY", item.created_at, item.id))

    def additional_hours_review(self, booking, context=None):
        """Optional response-local cache; approvals always call without one for fresh checks under the lock."""
        if not booking.additional_hours:
            return None
        context = {} if context is None else context
        hours = self.rules().additional_hours_approval_window_hours
        group, reasons = self._additional_hours_priority(booking, context)
        error = self._additional_hours_approval_error(booking, context)
        queue = self._additional_hours_queue(booking, context) if booking.status == BookingStatus.PENDING_APPROVAL else []
        position = next((index + 1 for index, item in enumerate(queue) if item.id == booking.id), None)
        if error is None and position != 1:
            error = DomainError("ADDITIONAL_HOURS_QUEUE_PRIORITY", "An earlier or higher-priority additional-hours request must be decided first.",
                                409, {"queue_position": position, "first_request_id": queue[0].id if queue else None})
        return {"approval_opens_at": booking.start - timedelta(hours=hours), "approval_window_hours": hours,
                "priority_group": group, "priority_reasons": reasons, "queue_position": position,
                "can_approve": error is None, "blocker_code": error.code if error else None,
                "blocker_message": error.message if error else None}

    def review_additional_hours_booking(self, actor, booking_id, decision, reason="", confirm_active_data_collection=False):
        self.require_manager(actor)
        self.process_due_requests()
        source = self.booking_for(actor, booking_id)
        with self.repo.atomic(resource_ids=[source.resource_id], student_ids=[source.student_id]):
            source = self.booking_for(actor, booking_id)
            if not source.additional_hours or source.status != BookingStatus.PENDING_APPROVAL or source.start <= self.now():
                raise DomainError("REQUEST_NOT_REVIEWABLE", "Only a pending additional-hours request can be reviewed.", 409)
            if source.student_id == actor.id or source.created_by == actor.id:
                raise DomainError("SELF_REVIEW_FORBIDDEN", "You cannot review a request that is for you or that you created.", 403)
            if decision not in ("APPROVED", "REJECTED"):
                raise DomainError("VALIDATION_ERROR", "Choose APPROVED or REJECTED.")
            if decision == "REJECTED" and not reason.strip():
                raise DomainError("REASON_REQUIRED", "A rejection reason is required.")
            if not isinstance(confirm_active_data_collection, bool):
                raise DomainError("VALIDATION_ERROR", "confirm_active_data_collection must be a boolean.")
            review = self.additional_hours_review(source)
            if decision == "APPROVED":
                if not review["can_approve"]:
                    raise DomainError(review["blocker_code"], review["blocker_message"], 409,
                                      {"approval_opens_at": review["approval_opens_at"].isoformat().replace("+00:00", "Z"),
                                       "queue_position": review["queue_position"]})
                if source.active_data_collection and not confirm_active_data_collection:
                    raise DomainError("DATA_COLLECTION_CONFIRMATION_REQUIRED", "Confirm the active-data-collection evidence before approval, or reject the request.", 400)
            now = self.now()
            revised = replace(source, status=BookingStatus(decision), reason_code=f"ADDITIONAL_HOURS_{decision}",
                              reviewed_by=actor.id, reviewed_at=now, decision_reason=reason.strip() or None, updated_at=now)
            self._save_booking(revised)
            self._audit(actor.id, f"ADDITIONAL_HOURS_{decision}", "booking", source.id, reason=reason.strip(),
                        priority_group=review["priority_group"], priority_reasons=review["priority_reasons"],
                        queue_position=review["queue_position"], approval_window_hours=review["approval_window_hours"],
                        active_data_collection_confirmed=bool(source.active_data_collection and confirm_active_data_collection),
                        requested_start=source.start.isoformat(), requested_end=source.end.isoformat())
            return revised
