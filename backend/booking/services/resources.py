"""Manager resource settings: review window, maintenance/closed status, and the bookings report."""
from dataclasses import replace

from ..domain import MAX_PENDING_HOLD_MINUTES, ResourceStatus
from ..errors import DomainError
from .base import ACTIVE_REQUEST_STATUSES


class ResourcesMixin:
    def set_pending_hold_minutes(self, actor, resource_id, minutes):
        return self.set_booking_policy(actor, resource_id, pending_hold_minutes=minutes)

    def set_booking_policy(self, actor, resource_id, pending_hold_minutes):
        """Manager only: how long a pending request waits for an Admin (holding its slot) before the system decides.

        Applies to requests that become pending afterwards; existing deadlines stay unchanged.
        """
        self.require_manager(actor)
        if isinstance(pending_hold_minutes, bool) or not isinstance(pending_hold_minutes, int) \
                or not 1 <= pending_hold_minutes <= MAX_PENDING_HOLD_MINUTES:
            raise DomainError("VALIDATION_ERROR", f"pending_hold_minutes must be an integer from 1 to {MAX_PENDING_HOLD_MINUTES}.")
        with self.repo.atomic(resource_ids=[str(resource_id)]):
            current = self.resource(resource_id)
            updated = replace(current, pending_hold_minutes=pending_hold_minutes)
            self.repo.save_resource(updated)
            self._audit(actor.id, "RESOURCE_BOOKING_POLICY_UPDATED", "resource", current.id,
                        previous_minutes=current.pending_hold_minutes, pending_hold_minutes=pending_hold_minutes)
            return updated

    def set_resource_status(self, actor, resource_id, status, reason=None):
        """Manager only: open a resource or take it out of service (MAINTENANCE / CLOSED).

        Only new requests, approvals and waitlist promotions are stopped; existing bookings are kept so the
        Manager can decide whether to cancel them (they are returned as affected_bookings). Reopening the
        resource offers freed time to its waitlist again.
        """
        self.require_manager(actor)
        if status not in ResourceStatus._value2member_map_:
            raise DomainError("VALIDATION_ERROR", "status must be AVAILABLE, MAINTENANCE or CLOSED.")
        reason = (reason or "").strip() or None
        if status != ResourceStatus.AVAILABLE.value and not reason:
            raise DomainError("REASON_REQUIRED", "Give a reason when taking a resource out of service.")
        with self.repo.atomic(resource_ids=[str(resource_id)]):
            current = self.resource(resource_id)
            updated = replace(current, status=ResourceStatus(status),
                              status_reason=None if status == ResourceStatus.AVAILABLE.value else reason)
            if updated != current:
                self.repo.save_resource(updated)
                self._audit(actor.id, "RESOURCE_STATUS_CHANGED", "resource", current.id,
                            previous_status=current.status.value, status=updated.status.value, reason=updated.status_reason)
                if updated.bookable:
                    self._promote_waitlist(updated.id)
            affected = sorted((item for item in self.repo.list_bookings(resource_id=updated.id)
                               if item.status in ACTIVE_REQUEST_STATUSES and item.end > self.now()),
                              key=lambda item: (item.start, item.id))
            return updated, affected

    def booking_report(self, actor, statuses=None, resource_id=None, student_id=None, since=None, until=None):
        """Admin/Manager: every booking matching the filters, ordered by start time (for lists, print and CSV)."""
        self.require_staff(actor)
        self.process_due_requests()
        records = [item for item in self.repo.list_bookings()
                   if (not statuses or item.status.value in statuses)
                   and (resource_id is None or item.resource_id == str(resource_id))
                   and (student_id is None or item.student_id == str(student_id))
                   and (since is None or item.end > since) and (until is None or item.start < until)]
        return sorted(records, key=lambda item: (item.start, item.id))
