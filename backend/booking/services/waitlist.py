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
        if booking.additional_hours:
            return BookingStatus.REJECTED, "ADDITIONAL_HOURS_NEEDS_MANAGER", "Additional hours require a Manager's decision."
        if booking.long_booking:
            return BookingStatus.EXPIRED, "LONG_BOOKING_REVIEW_EXPIRED", "No Manager approved the longer booking before its review deadline."
        resource = self.repo.get_resource(booking.resource_id)
        error = self.rule_violation(booking.student_id, resource, booking.start, booking.end)
        if error:
            return (BookingStatus.REJECTED, _AUTO_REJECT_CODES.get(error.code, "AUTO_REJECTED_BOOKING_RULES"),
                    error.message)
        if any(item.status == BookingStatus.APPROVED for item in self._overlaps(booking.resource_id, booking.start, booking.end, booking.id, booking.replaces_id)):
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
        queue = sorted((item for item in self.repo.list_bookings(resource_id=str(resource_id), statuses=[BookingStatus.WAITLISTED])
                        if item.status == BookingStatus.WAITLISTED and not item.additional_hours), key=lambda item: (item.created_at, item.id))
        changed = []
        for booking in queue:
            now = self.now()
            extra = {}
            if booking.start <= now:
                status, reason, action = BookingStatus.EXPIRED, "START_TIME_PASSED", "BOOKING_TIME_PROCESSED"
            else:
                # A closed resource keeps its queue until it reopens.
                if resource is None or not resource.bookable or self._overlaps(booking.resource_id, booking.start, booking.end, booking.id, booking.replaces_id):
                    continue
                error = self.rule_violation(booking.student_id, resource, booking.start, booking.end,
                                            allow_long_booking=booking.long_booking)
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
            if revised.long_booking and revised.status == BookingStatus.PENDING_APPROVAL:
                self._notify_long_booking_managers(revised)
            changed.append(revised)
        if changed:
            ids = _promoted_ids.get()
            if ids is None:
                ids = []
                _promoted_ids.set(ids)
            ids.extend(item.id for item in changed)
        return changed

    @staticmethod
    def _due_for_processing(booking, now):
        """Whether time processing would change this undecided request: its start has passed, or its review window has ended."""
        return booking.start <= now or (not booking.additional_hours and booking.status in HEAD_STATUSES and booking.review_due_at is not None
                                        and booking.review_due_at <= now)

    def process_due_requests(self):
        """Idempotent time processing; called from queries and actions (or a future scheduler).

        - An undecided request whose start time has passed expires.
        - A pending request whose review window has ended without an Admin decision is decided by the
          system: approved if it still follows the rules, otherwise rejected.
        Freed time is then offered to the waitlist. Finally, approved bookings whose check-in time has passed
        without a check-in are marked as missed (see attendance.py).
        """
        changed, released = [], set()
        # 2026-10-29 (load test S1): read only undecided requests that may be due, not every booking ever made
        # (5000 past bookings made each API request about 0.8 s slower). The exact checks below are unchanged.
        for candidate in self.repo.list_bookings(statuses=UNDECIDED_STATUSES, due_by=self.now()):
            # Every API request runs this, so a request that is not due yet is skipped before taking any lock
            # (2026-10-27, performance P5: 200 waiting requests added about 0.5 s to each API request).
            # The same check is repeated under the lock below.
            if candidate.status not in UNDECIDED_STATUSES or not self._due_for_processing(candidate, self.now()):
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
                    action = ("BOOKING_AUTO_APPROVED" if status == BookingStatus.APPROVED else
                              "BOOKING_TIME_PROCESSED" if status == BookingStatus.EXPIRED else "BOOKING_AUTO_REJECTED")
                    extra = {"reviewed_by": "SYSTEM", "reviewed_at": now, "decision_reason": note}
                    if status in (BookingStatus.REJECTED, BookingStatus.EXPIRED):
                        released.add(current.resource_id)
                else:
                    continue
                updated = replace(current, status=status, reason_code=reason, updated_at=now, **extra)
                self._save_booking(updated)
                self._audit("SYSTEM", action, "booking", updated.id, status=status.value, reason_code=reason)
                changed.append(updated)
        for resource_id in sorted(released):
            if any(item.status == BookingStatus.WAITLISTED
                   for item in self.repo.list_bookings(resource_id=resource_id, statuses=[BookingStatus.WAITLISTED])):
                with self.repo.atomic(resource_ids=[resource_id]):
                    changed.extend(self._promote_waitlist(resource_id))
        if any(item.status == BookingStatus.APPROVED for item in changed):
            ids = _promoted_ids.get()
            if ids is None:
                ids = []
                _promoted_ids.set(ids)
            ids.extend(item.id for item in changed if item.status == BookingStatus.APPROVED)
        # Sprint 3 check-in: approved bookings whose check-in time passed without one count as missed.
        self._process_attendance()
        # Sprint 3: reminders (booking tomorrow, induction expiring soon); each is sent once.
        self._send_reminders()
        return changed
