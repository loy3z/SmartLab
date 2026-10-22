"""Time-based processing: expiry, automatic decisions when a review window ends, and waitlist promotion."""
from dataclasses import replace

from ..domain import BookingStatus
from .base import HEAD_STATUSES, UNDECIDED_STATUSES, _AUTO_REJECT_CODES, _promoted_ids


class WaitlistMixin:
    def _auto_decision(self, booking):
        """What the system decides when the review window ends without an Admin decision.

        Approve only if every rule still holds (the same check an Admin approval uses) and no approved
        booking overlaps; otherwise reject with the rule that failed.
        """
        resource = self.repo.get_resource(booking.resource_id)
        error = self.rule_violation(booking.student_id, resource, booking.start, booking.end)
        if error:
            return (BookingStatus.REJECTED, _AUTO_REJECT_CODES.get(error.code, "AUTO_REJECTED_BOOKING_RULES"),
                    error.message)
        if any(item.status == BookingStatus.APPROVED for item in self._overlaps(booking.resource_id, booking.start, booking.end, booking.id)):
            return BookingStatus.REJECTED, "AUTO_REJECTED_CONFLICT", "The time is already taken by an approved booking."
        return BookingStatus.APPROVED, "AUTO_APPROVED_AFTER_REVIEW_WINDOW", None

    def _promote_waitlist(self, resource_id):
        """Offer freed time to waitlisted requests in submission order (strict FIFO).

        Call inside a transaction that holds the resource lock, after anything that may free a slot:
        cancellation, rejection, expiry, rescheduling or reopening a resource. A request is promoted only
        when no approved booking or pending request overlaps it. It then becomes pending again with a
        fresh review window (an Admin decides, or the system does when the window ends); a request whose
        requester no longer has a valid induction is rejected instead. Earlier requests are always
        considered first.
        """
        resource = self.repo.get_resource(str(resource_id))
        queue = sorted((item for item in self.repo.list_bookings(resource_id=str(resource_id))
                        if item.status == BookingStatus.WAITLISTED), key=lambda item: (item.created_at, item.id))
        changed = []
        for booking in queue:
            now = self.now()
            extra = {}
            if booking.start <= now:
                status, reason, action = BookingStatus.EXPIRED, "START_TIME_PASSED", "BOOKING_TIME_PROCESSED"
            else:
                # A closed resource keeps its queue until it reopens.
                if resource is None or not resource.bookable or self._overlaps(booking.resource_id, booking.start, booking.end, booking.id):
                    continue
                error = self.rule_violation(booking.student_id, resource, booking.start, booking.end)
                if error is None:
                    deadline = self._review_deadline(resource, booking.start)
                    status, reason, action = BookingStatus.PENDING_APPROVAL, "PROMOTED_FROM_WAITLIST", "BOOKING_PROMOTED"
                    extra = {"hold_until": deadline, "review_due_at": deadline}
                else:
                    status, reason, action = BookingStatus.REJECTED, error.code, "BOOKING_REJECTED"
                    extra = {"reviewed_by": "SYSTEM", "reviewed_at": now, "decision_reason": error.message}
            revised = replace(booking, status=status, reason_code=reason, updated_at=now, **extra)
            self._save_booking(revised)
            self._audit("SYSTEM", action, "booking", revised.id, status=status.value, reason_code=reason,
                        hold_until=revised.hold_until.isoformat() if status in HEAD_STATUSES else None)
            changed.append(revised)
        if changed:
            ids = _promoted_ids.get()
            if ids is None:
                ids = []
                _promoted_ids.set(ids)
            ids.extend(item.id for item in changed)
        return changed

    def process_due_requests(self):
        """Idempotent time processing; called from queries and actions (or a future scheduler).

        - An undecided request whose start time has passed expires.
        - A pending request whose review window has ended without an Admin decision is decided by the
          system: approved if it still follows the rules, otherwise rejected.
        Freed time is then offered to the waitlist.
        """
        changed, released = [], set()
        for candidate in self.repo.list_bookings():
            if candidate.status not in UNDECIDED_STATUSES:
                continue
            with self.repo.atomic(resource_ids=[candidate.resource_id], student_ids=[candidate.student_id]):
                current = self.repo.get_booking(candidate.id)
                if current.status not in UNDECIDED_STATUSES:
                    continue
                now = self.now()
                extra = {}
                if current.start <= now:
                    status, reason, action = BookingStatus.EXPIRED, "START_TIME_PASSED", "BOOKING_TIME_PROCESSED"
                    if current.status in HEAD_STATUSES:
                        released.add(current.resource_id)
                elif current.status in HEAD_STATUSES and current.review_due_at and current.review_due_at <= now:
                    status, reason, note = self._auto_decision(current)
                    action = "BOOKING_AUTO_APPROVED" if status == BookingStatus.APPROVED else "BOOKING_AUTO_REJECTED"
                    extra = {"reviewed_by": "SYSTEM", "reviewed_at": now, "decision_reason": note}
                    if status == BookingStatus.REJECTED:
                        released.add(current.resource_id)
                else:
                    continue
                updated = replace(current, status=status, reason_code=reason, updated_at=now, **extra)
                self._save_booking(updated)
                self._audit("SYSTEM", action, "booking", updated.id, status=status.value, reason_code=reason)
                changed.append(updated)
        for resource_id in sorted(released):
            if any(item.status == BookingStatus.WAITLISTED for item in self.repo.list_bookings(resource_id=resource_id)):
                with self.repo.atomic(resource_ids=[resource_id]):
                    changed.extend(self._promote_waitlist(resource_id))
        if any(item.status == BookingStatus.APPROVED for item in changed):
            ids = _promoted_ids.get()
            if ids is None:
                ids = []
                _promoted_ids.set(ids)
            ids.extend(item.id for item in changed if item.status == BookingStatus.APPROVED)
        return changed
