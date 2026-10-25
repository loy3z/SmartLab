"""Shared state and helpers every part of the service uses: clock, rules, role checks, audit, resource lookup."""
from contextvars import ContextVar
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from ..domain import AuditRecord, BookingStatus, Role
from ..errors import DomainError
from ..rules import BookingRules, StaticRulesProvider
from ..test_console import TEST_ACCOUNT_ID

# Requests that hold first place for their slot (blocking others while hold_until is in the future).
# Only PENDING_APPROVAL is created now; WAITING_QUALIFICATION stays for stored records of the earlier flow.
HEAD_STATUSES = (BookingStatus.WAITING_QUALIFICATION, BookingStatus.PENDING_APPROVAL)
# Requests that are still undecided, including those queued on the waitlist.
UNDECIDED_STATUSES = HEAD_STATUSES + (BookingStatus.WAITLISTED,)
# A student cannot create another request for the same resource while one of
# these records overlaps the requested period. Terminal records do not prevent
# the student from booking the resource again.
ACTIVE_REQUEST_STATUSES = UNDECIDED_STATUSES + (BookingStatus.APPROVED,)

# Bookings changed by automatic waitlist promotion during the current request, so the
# HTTP layer can push newly approved ones to Outlook. One list per thread/request context.
_promoted_ids = ContextVar("booking_promoted_ids", default=None)

# Automatic decisions name the rule that failed. Codes from the shared rule check map to these.
_AUTO_REJECT_CODES = {
    "ACCOUNT_INACTIVE": "AUTO_REJECTED_ACCOUNT_INACTIVE",
    "RESOURCE_UNAVAILABLE": "AUTO_REJECTED_RESOURCE_UNAVAILABLE",
    "RESOURCE_POLICY_NOT_CONFIGURED": "AUTO_REJECTED_QUALIFICATION",
    "QUALIFICATION_REQUIRED": "AUTO_REJECTED_QUALIFICATION",
}


class ServiceBase:
    def __init__(self, repo, storage, clock=None, calendar_sync=None, rules=None,
                 qualification_validity_days=None, min_advance_days=None, max_advance_days=None):
        """rules: a RulesProvider (see rules.py) or a BookingRules value.

        The three keyword numbers are a shortcut for tests and scripts: they build fixed rules.
        """
        self.repo, self.storage = repo, storage
        self.clock = clock or (lambda: datetime.now(UTC))
        self.calendar_sync = calendar_sync
        if rules is None or isinstance(rules, BookingRules):
            base = rules or BookingRules()
            overrides = {name: value for name, value in (
                ("qualification_validity_days", qualification_validity_days),
                ("min_advance_days", min_advance_days), ("max_advance_days", max_advance_days)) if value is not None}
            rules = StaticRulesProvider(replace(base, **overrides))
        self.rules_provider = rules
        self.rules()  # fail fast on invalid values

    def rules(self) -> BookingRules:
        """Current booking rules (read on every check, so a changed provider value applies at once)."""
        return self.rules_provider.current()

    def _override_rule(self, **values):
        """Pin a rule to a fixed value (scripts and tests); production reads them from the rules provider."""
        self.rules_provider = StaticRulesProvider(replace(self.rules(), **values))

    min_advance_days = property(lambda self: self.rules().min_advance_days,
                                lambda self, value: self._override_rule(min_advance_days=value))

    max_advance_days = property(lambda self: self.rules().max_advance_days,
                                lambda self, value: self._override_rule(max_advance_days=value))

    qualification_validity_days = property(lambda self: self.rules().qualification_validity_days,
                                           lambda self, value: self._override_rule(qualification_validity_days=value))

    def take_promoted_ids(self):
        """Return and clear booking IDs changed by waitlist promotion in this request context."""
        ids = _promoted_ids.get() or []
        _promoted_ids.set(None)
        return ids

    def _save_booking(self, booking):
        previous = self.repo.get_booking(booking.id)
        self.repo.save_booking(booking)
        if self.calendar_sync and booking.student_id != TEST_ACCOUNT_ID:
            self.calendar_sync.schedule(booking)
        self._booking_changed(previous, booking)  # Sprint 3: notifications
        self._apply_time_change(previous, booking)  # Sprint 3 (1.16.0): approved change request replaces the old booking

    def _remember_changed(self, bookings):
        """Sprint 3: bookings changed as a side effect of this request (promotion, freeze), so the HTTP layer syncs Outlook."""
        ids = _promoted_ids.get()
        if ids is None:
            ids = []
            _promoted_ids.set(ids)
        ids.extend(item.id for item in bookings if item.id not in ids)

    def now(self):
        current = self.clock()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("The service clock must be timezone aware.")
        return current.astimezone(UTC)

    def require_student(self, actor):
        if not actor.active or actor.role != Role.STUDENT:
            raise DomainError("FORBIDDEN", "This action requires an active student account.", 403)

    def require_booking_user(self, actor):
        """Any active account books and uploads induction evidence: Admins and Managers follow
        the same eligibility, induction, opening-hours and conflict rules as students."""
        if not actor.active:
            raise DomainError("FORBIDDEN", "This action requires an active account.", 403)

    def require_staff(self, actor):
        """Admin and Manager: reviews, queues, audit. A Manager has every Admin permission."""
        if not actor.active or actor.role not in (Role.ADMIN, Role.MANAGER):
            raise DomainError("FORBIDDEN", "This action requires an Admin or Manager account.", 403)

    def require_manager(self, actor):
        """Manager only: booking policies and the staff/user list (roles are nominated by the lab owner)."""
        if not actor.active or actor.role != Role.MANAGER:
            raise DomainError("FORBIDDEN", "This action requires an active Manager account.", 403)

    def _audit(self, actor_id, action, kind, entity_id, **details):
        self.repo.append_audit(AuditRecord(str(uuid4()), actor_id, action, kind, entity_id, self.now(), details))

    def resource(self, resource_id):
        resource = self.repo.get_resource(str(resource_id))
        if resource is None:
            raise DomainError("NOT_FOUND", "Resource not found.", 404)
        return resource
