"""Booking policy independent of HTTP and the eventual database adapter."""
import re
import secrets
from contextvars import ContextVar
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5
from zoneinfo import ZoneInfo
from .domain import (MAX_PENDING_HOLD_MINUTES, AuditRecord, Booking, BookingStatus, Principal, QualificationSubmission,
                     QualificationStatus, ResourceKind, ResourceStatus, Role, StaffCredential)
from .errors import DomainError
from .rules import BookingRules, StaticRulesProvider

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


_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I, so codes are easy to read out


def new_invite_code():
    raw = "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_invite_code(code):
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


class BookingService:
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
        self.repo.save_booking(booking)
        if self.calendar_sync:
            self.calendar_sync.schedule(booking)

    def now(self):
        current = self.clock()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("The service clock must be timezone aware.")
        return current.astimezone(UTC)

    def require_student(self, actor):
        if not actor.active or actor.role != Role.STUDENT:
            raise DomainError("FORBIDDEN", "This action requires an active student account.", 403)

    def require_booking_user(self, actor):
        """Only students book and upload induction evidence. Admins and Managers are staff: they review and manage."""
        if not actor.active or actor.role != Role.STUDENT:
            raise DomainError("FORBIDDEN", "Only students can book resources or submit induction evidence.", 403)

    def require_staff(self, actor):
        """Admin and Manager: reviews, queues, audit. A Manager has every Admin permission."""
        if not actor.active or actor.role not in (Role.ADMIN, Role.MANAGER):
            raise DomainError("FORBIDDEN", "This action requires an Admin or Manager account.", 403)

    def require_manager(self, actor):
        """Manager only: booking policies and the staff/user list (roles are nominated by the lab owner)."""
        if not actor.active or actor.role != Role.MANAGER:
            raise DomainError("FORBIDDEN", "This action requires an active Manager account.", 403)

    def list_users(self, actor, role=None, active=None, query=None):
        self.require_manager(actor)
        query = (query or "").strip().casefold()
        users = [item for item in self.repo.list_principals()
                 if (role is None or item.role == Role(role)) and (active is None or item.active == active)
                 and (not query or query in f"{item.zid} {item.display_name} {item.university_email}".casefold())]
        return sorted(users, key=lambda item: (item.role.value, item.zid))

    def update_user(self, actor, user_id, role=None, active=None):
        """(De)activate an account. Roles are fixed when the account is created.

        Students, Admins and Managers are separate kinds of account (client, week 5): a student is never
        given a staff role (passing inductions proves lab eligibility, not employment), and Admin and Manager
        are different levels of staff that do not switch. Staff accounts come from Add staff (create_staff)
        or, later, from the university identity provider; to replace someone, add the new account and
        deactivate the old one. ``role`` is accepted only when it equals the current role.
        Deactivating a student rejects their undecided requests at once; approved bookings are kept for
        the Manager to review.
        """
        self.require_manager(actor)
        if role is None and active is None:
            raise DomainError("VALIDATION_ERROR", "Provide role and/or active.")
        user_id = str(user_id)
        if user_id == actor.id:
            raise DomainError("SELF_MODIFICATION_FORBIDDEN", "Managers cannot change their own role or status.", 403)
        managers = [item.id for item in self.repo.list_principals() if item.role == Role.MANAGER]
        with self.repo.atomic(student_ids=sorted(set(managers + [user_id]))):
            current = self.repo.get_principal(user_id)
            if current is None:
                raise DomainError("NOT_FOUND", "User not found.", 404)
            if role is not None and Role(role) != current.role:
                raise DomainError("ROLE_CHANGE_NOT_ALLOWED",
                                  "Roles are fixed when an account is created. Students, Admins and Managers are "
                                  "separate accounts: add a new staff account with Add staff and deactivate the "
                                  "old one if needed.", 409,
                                  {"zid": current.zid, "role": current.role.value})
            updated = replace(current, role=Role(role) if role is not None else current.role,
                              active=current.active if active is None else active)
            if updated == current:
                return current
            if not any(item.role == Role.MANAGER and item.active
                       for item in [updated] + [p for p in self.repo.list_principals() if p.id != user_id]):
                raise DomainError("LAST_MANAGER", "At least one active Manager must remain.", 409)
            self.repo.save_principal(updated)
            self._audit(actor.id, "USER_UPDATED", "principal", updated.id, zid=updated.zid,
                        previous_role=current.role.value, role=updated.role.value,
                        previous_active=current.active, active=updated.active)
        if current.active and not updated.active:
            self._reject_undecided_requests(updated.id, actor.id, "ACCOUNT_DEACTIVATED",
                                            "The account was deactivated.")
        return updated

    def _reject_undecided_requests(self, student_id, actor_id, reason_code, note):
        """Reject a person's undecided requests (pending and waitlisted) and pass the time on."""
        changed = []
        for booking in sorted(self.repo.list_bookings(student_id=student_id), key=lambda item: (item.created_at, item.id)):
            if booking.status not in UNDECIDED_STATUSES:
                continue
            with self.repo.atomic(resource_ids=[booking.resource_id], student_ids=[student_id]):
                current = self.repo.get_booking(booking.id)
                if current.status not in UNDECIDED_STATUSES:
                    continue
                revised = replace(current, status=BookingStatus.REJECTED, reason_code=reason_code, reviewed_by=actor_id,
                                  reviewed_at=self.now(), decision_reason=note, updated_at=self.now())
                self._save_booking(revised)
                self._audit(actor_id, "BOOKING_REJECTED", "booking", revised.id, reason=note, reason_code=reason_code)
                changed.append(revised)
                self._promote_waitlist(revised.resource_id)
        return changed

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

    def induction_summary(self, student_id):
        """Each induction requirement with this person's current status (NOT_SUBMITTED, PENDING, VERIFIED, REJECTED, EXPIRED)."""
        summary = []
        for requirement in sorted(self.repo.list_requirements(), key=lambda item: (item.name, item.id)):
            record = self.latest_submission(student_id, requirement.id)
            if record is None:
                status = "NOT_SUBMITTED"
            elif record.status == QualificationStatus.VERIFIED and record.valid_until is not None and record.valid_until <= self.now():
                status = "EXPIRED"
            else:
                status = record.status.value
            summary.append({"requirement_id": requirement.id, "name": requirement.name, "status": status,
                            "valid_until": record.valid_until if record and status == "VERIFIED" else None})
        return summary

    def create_staff(self, actor, zid, display_name, university_email, role=Role.MANAGER):
        """Manager only ("Add staff"): create an Admin or Manager account for a staff member.

        Staff are not promoted from student accounts. With university SSO, the identity provider would
        create these from its staff records instead; the role is still assigned here by a Manager.
        """
        self.require_manager(actor)
        role = Role(role)
        if role not in (Role.ADMIN, Role.MANAGER):
            raise DomainError("VALIDATION_ERROR", "Staff accounts are ADMIN or MANAGER.")
        zid = zid.strip().lower()
        if not re.fullmatch(r"z\d{7}", zid):
            raise DomainError("VALIDATION_ERROR", "zID must be 'z' followed by 7 digits.")
        display_name, university_email = display_name.strip(), university_email.strip()
        if not display_name:
            raise DomainError("VALIDATION_ERROR", "A display name is required.")
        with self.repo.atomic():
            existing = next((item for item in self.repo.list_principals() if item.zid == zid), None)
            if existing:
                raise DomainError("USER_EXISTS", "A user with this zID already exists.", 409, {"user_id": existing.id})
            try:
                created = Principal(str(uuid4()), zid, display_name, role, university_email)
            except ValueError as exc:
                raise DomainError("VALIDATION_ERROR", str(exc)) from exc
            self.repo.save_principal(created)
            # The new staff member activates the account on the staff sign-in page with this code.
            self.repo.save_credential(StaffCredential(created.id, invite_code=new_invite_code(), updated_at=self.now()))
            self._audit(actor.id, f"{role.value}_CREATED", "principal", created.id, zid=zid)
            return created

    # ----- Staff sign-in (students use university sign-in; staff use zID + password) -----

    def staff_access(self, user):
        """For the user list: whether a staff account is activated, and its invite code while it is not."""
        if not user.is_staff:
            return {"activation_status": None, "invite_code": None}
        credential = self.repo.get_credential(user.id)
        if credential and credential.activated:
            return {"activation_status": "ACTIVATED", "invite_code": None}
        return {"activation_status": "AWAITING_ACTIVATION", "invite_code": credential.invite_code if credential else None}

    def reset_staff_access(self, actor, user_id):
        """Manager only: clear a staff member's password and issue a new invite code (forgotten password,
        or a lost code). The role and history stay the same."""
        self.require_manager(actor)
        user_id = str(user_id)
        if user_id == actor.id:
            raise DomainError("SELF_MODIFICATION_FORBIDDEN", "Ask another Manager to reset your access.", 403)
        with self.repo.atomic(student_ids=[user_id]):
            user = self.repo.get_principal(user_id)
            if user is None:
                raise DomainError("NOT_FOUND", "User not found.", 404)
            if not user.is_staff:
                raise DomainError("STUDENT_USES_SSO", "Students sign in with university sign-in and have no password here.", 409)
            self.repo.save_credential(StaffCredential(user.id, invite_code=new_invite_code(), updated_at=self.now()))
            self._audit(actor.id, "STAFF_ACCESS_RESET", "principal", user.id, zid=user.zid)
        return user

    def _staff_by_zid(self, zid):
        zid = (zid or "").strip().lower()
        return next((item for item in self.repo.list_principals() if item.zid == zid), None)

    def activate_staff(self, zid, invite_code, password):
        """First staff sign-in: the invite code from the Manager plus a password the staff member chooses."""
        from django.contrib.auth.hashers import make_password
        if len(password or "") < 8:
            raise DomainError("VALIDATION_ERROR", "Choose a password of at least 8 characters.", 400, {"password": ["At least 8 characters."]})
        with self.repo.atomic():
            user = self._staff_by_zid(zid)
            credential = self.repo.get_credential(user.id) if user and user.is_staff else None
            if (credential is None or not credential.invite_code
                    or normalize_invite_code(credential.invite_code) != normalize_invite_code(invite_code)):
                raise DomainError("INVALID_INVITE_CODE", "The zID or invite code is not correct. Ask your Manager for a new code.", 400)
            if not user.active:
                raise DomainError("ACCOUNT_DEACTIVATED", "This account has been deactivated.", 403)
            self.repo.save_credential(StaffCredential(user.id, password_hash=make_password(password), updated_at=self.now()))
            self._audit(user.id, "STAFF_ACTIVATED", "principal", user.id, zid=user.zid)
        return user

    def staff_sign_in(self, zid, password):
        """Staff sign-in page. The role comes from the account, never from the page used."""
        from django.contrib.auth.hashers import check_password
        user = self._staff_by_zid(zid)
        if user is not None and not user.is_staff:
            raise DomainError("STUDENT_USES_SSO", "Students sign in with university sign-in on the main sign-in page.", 403)
        if user is None:
            raise DomainError("INVALID_CREDENTIALS", "The zID or password is not correct.", 401)
        if not user.active:
            raise DomainError("ACCOUNT_DEACTIVATED", "This account has been deactivated.", 403)
        credential = self.repo.get_credential(user.id)
        if credential is None or not credential.activated:
            raise DomainError("ACCOUNT_NOT_ACTIVATED", "Activate your account first with the invite code from your Manager.", 403)
        if not check_password(password or "", credential.password_hash):
            raise DomainError("INVALID_CREDENTIALS", "The zID or password is not correct.", 401)
        return user

    def create_manager(self, actor, zid, display_name, university_email):
        return self.create_staff(actor, zid, display_name, university_email, Role.MANAGER)

    def set_prerequisites(self, actor, requirement_id, prerequisite_ids):
        """Manager only: which inductions must be verified and current before this one (e.g. Advanced needs General).

        Stored with the requirement, so a policy change needs no code change. Cycles are refused.
        """
        self.require_manager(actor)
        requirement = self.repo.get_requirement(str(requirement_id))
        if requirement is None:
            raise DomainError("NOT_FOUND", "Qualification requirement not found.", 404)
        wanted = tuple(dict.fromkeys(str(item) for item in prerequisite_ids))
        for item in wanted:
            if self.repo.get_requirement(item) is None:
                raise DomainError("VALIDATION_ERROR", f"Unknown prerequisite {item}.")
        graph = {item.id: set(item.prerequisite_ids) for item in self.repo.list_requirements()}
        graph[requirement.id] = set(wanted)

        def reaches(start, target, seen):
            for nxt in graph.get(start, ()):
                if nxt == target or (nxt not in seen and (seen.add(nxt) or reaches(nxt, target, seen))):
                    return True
            return False

        if requirement.id in wanted or reaches(requirement.id, requirement.id, set()):
            raise DomainError("PREREQUISITE_CYCLE", "These prerequisites would form a loop.", 409)
        updated = replace(requirement, prerequisite_ids=wanted)
        with self.repo.atomic():
            self.repo.save_requirement(updated)
            self._audit(actor.id, "REQUIREMENT_PREREQUISITES_UPDATED", "requirement", requirement.id,
                        previous=list(requirement.prerequisite_ids), prerequisites=list(wanted))
        return updated

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

    def _audit(self, actor_id, action, kind, entity_id, **details):
        self.repo.append_audit(AuditRecord(str(uuid4()), actor_id, action, kind, entity_id, self.now(), details))

    def resource(self, resource_id):
        resource = self.repo.get_resource(str(resource_id))
        if resource is None:
            raise DomainError("NOT_FOUND", "Resource not found.", 404)
        return resource

    def latest_submission(self, student_id, requirement_id):
        records = self.repo.list_submissions(student_id=student_id, requirement_id=requirement_id)
        # Creation time is authoritative; retain insertion order for equal timestamps.
        return max(enumerate(records), key=lambda pair: (pair[1].submitted_at, pair[0]))[1] if records else None

    def _requirement_status(self, student_id, requirement_id, end=None):
        """NOT_SUBMITTED, PENDING, REJECTED, EXPIRED, EXPIRES_BEFORE_END or VERIFIED, from the latest submission."""
        record = self.latest_submission(student_id, requirement_id)
        if record is None:
            return "NOT_SUBMITTED"
        if record.status == QualificationStatus.VERIFIED:
            if record.valid_until is not None and record.valid_until <= self.now():
                return "EXPIRED"
            if end is not None and record.valid_until is not None and record.valid_until < end:
                return "EXPIRES_BEFORE_END"
            return "VERIFIED"
        return record.status.value

    def _prerequisite_chain(self, requirement_id):
        """Every prerequisite of a requirement, nearest first, following the chain (General before Advanced)."""
        chain, seen, pending = [], {str(requirement_id)}, [str(requirement_id)]
        while pending:
            requirement = self.repo.get_requirement(pending.pop(0))
            for item in (requirement.prerequisite_ids if requirement else ()):
                if item not in seen:
                    seen.add(item)
                    chain.append(item)
                    pending.append(item)
        return chain

    def missing_prerequisite(self, student_id, requirement_id, end=None):
        """(requirement_id, status) of the first prerequisite that is not verified and current, or None."""
        for item in self._prerequisite_chain(requirement_id):
            status = self._requirement_status(student_id, item, end)
            if status != "VERIFIED":
                return item, status
        return None

    def qualification_state(self, student_id, resource, end=None):
        """Single eligibility check used by create, approve, automatic decisions, waitlist promotion,
        reschedule and availability.

        The resource's required induction must be verified and valid until the booking ends, and so must
        every prerequisite of it (for example General Lab Induction for Advanced Lab Training). A missing
        prerequisite is reported as PREREQUISITE_REQUIRED. Eligibility comes only from the latest
        QualificationSubmission of each requirement; a future source (school records, Moodle) can be an
        adapter that saves VERIFIED submissions, and these rules need no change.
        """
        if not resource.required_qualification_id:
            return "NOT_CONFIGURED", False
        if self.missing_prerequisite(student_id, resource.required_qualification_id, end):
            return "PREREQUISITE_REQUIRED", False
        status = self._requirement_status(student_id, resource.required_qualification_id, end)
        return status, status == "VERIFIED"

    def _overlaps(self, resource_id, start, end, exclude_id=None):
        return self.repo.list_blocking_bookings(resource_id, start, end, self.now(), exclude_id)

    def _student_overlap(self, student_id, resource_id, start, end, exclude_id=None):
        """Return the student's earliest overlapping active request for this resource."""
        matches = [item for item in self.repo.list_bookings(student_id=student_id, resource_id=resource_id)
                   if item.id != exclude_id and item.status in ACTIVE_REQUEST_STATUSES
                   and start < item.end and item.start < end]
        return min(matches, key=lambda item: (item.created_at, item.id)) if matches else None

    def _reject_duplicate_request(self, student_id, resource_id, start, end, exclude_id=None):
        existing = self._student_overlap(student_id, resource_id, start, end, exclude_id)
        if existing:
            raise DomainError(
                "DUPLICATE_BOOKING",
                "You already have an active request for this resource during the selected time.",
                409,
                {"booking_id": existing.id, "status": existing.status.value,
                 "start": existing.start.isoformat().replace("+00:00", "Z"),
                 "end": existing.end.isoformat().replace("+00:00", "Z")},
            )

    def _resource_violation(self, resource):
        if resource is None or not resource.bookable:
            status = "MISSING" if resource is None else resource.status.value if resource.active else "INACTIVE"
            return DomainError("RESOURCE_UNAVAILABLE", "This resource is not accepting bookings right now.", 409,
                               {"resource_status": status, "status_reason": resource.status_reason if resource else None})
        return None

    def _require_bookable(self, resource):
        error = self._resource_violation(resource)
        if error:
            raise error

    def _period_violation(self, resource, start, end):
        """Time rules of one resource: future start, maximum length, one local day within opening hours, increments."""
        if start.tzinfo is None or start.utcoffset() is None or end.tzinfo is None or end.utcoffset() is None:
            return DomainError("INVALID_TIME", "Start and end require UTC offsets.")
        if start >= end or start <= self.now():
            return DomainError("INVALID_TIME", "Use a future start time and an end later than start.")
        duration = (end - start).total_seconds() / 60
        if duration > resource.max_booking_minutes:
            return DomainError("DURATION_LIMIT", "The booking exceeds this resource's maximum duration.")
        local_start = start.astimezone(ZoneInfo(resource.timezone))
        local_end = end.astimezone(ZoneInfo(resource.timezone))
        if (local_start.date() != local_end.date() or local_start.time().replace(tzinfo=None) < resource.opening_time
                or local_end.time().replace(tzinfo=None) > resource.closing_time):
            return DomainError("OUTSIDE_OPENING_HOURS", "Book within one local day and the resource's opening hours.")
        opening = datetime.combine(local_start.date(), resource.opening_time, ZoneInfo(resource.timezone))
        offset = (local_start - opening).total_seconds() / 60
        if start.second or start.microsecond or end.second or end.microsecond or offset % resource.slot_minutes or duration % resource.slot_minutes:
            return DomainError("INVALID_TIME_INCREMENT", f"Use {resource.slot_minutes}-minute time increments.")
        return None

    def _validate_period(self, resource, start, end):
        self._require_bookable(resource)
        error = self._period_violation(resource, start, end)
        if error:
            raise error

    def _account_violation(self, student_id):
        person = self.repo.get_principal(str(student_id))
        if person is None or not person.active or person.role != Role.STUDENT:
            return DomainError("ACCOUNT_INACTIVE", "The requester's account is no longer active for booking.", 409)
        return None

    def _qualification_violation(self, student_id, resource, end):
        eligibility, qualified = self.qualification_state(student_id, resource, end)
        if eligibility == "NOT_CONFIGURED":
            return DomainError("RESOURCE_POLICY_NOT_CONFIGURED",
                               "Configure an induction requirement for this resource before accepting requests.", 409)
        if not qualified:
            details = {"qualification_status": eligibility, "requirement_id": resource.required_qualification_id}
            missing = self.missing_prerequisite(student_id, resource.required_qualification_id, end)
            if missing:
                details.update(prerequisite_id=missing[0], prerequisite_status=missing[1])
            return DomainError("QUALIFICATION_REQUIRED",
                               f"A verified induction (and its prerequisites) valid for the whole booking is required (status {eligibility}).",
                               403, details)
        return None

    def rule_violation(self, student_id, resource, start, end, check_window=False):
        """The one place that decides whether a booking follows the rules (conflicts are checked separately).

        Used when a request is created, approved by an Admin, decided automatically, promoted from the
        waitlist and rescheduled, so all of them apply the same rules: the requester's account is active,
        the resource is open, the time fits the resource (future, opening hours, length, increments) and the
        requester's induction and its prerequisites are valid until the end. The booking window (how many
        days ahead) is checked only when a request is created or rescheduled (check_window=True): a request
        made on time does not become invalid while it waits for review. Returns a DomainError or None.
        """
        return (self._account_violation(student_id) or self._resource_violation(resource)
                or self._period_violation(resource, start, end)
                or (self._window_violation(resource, start) if check_window else None)
                or self._qualification_violation(student_id, resource, end))

    def booking_window(self, resource):
        """First and last local dates a new or rescheduled booking may start on (from the current rules)."""
        rules = self.rules()
        today = self.now().astimezone(ZoneInfo(resource.timezone)).date()
        return today + timedelta(days=rules.min_advance_days), today + timedelta(days=rules.max_advance_days)

    def _window_details(self, resource):
        rules = self.rules()
        earliest, latest = self.booking_window(resource)
        return {"earliest_date": earliest.isoformat(), "latest_date": latest.isoformat(),
                "min_advance_days": rules.min_advance_days, "max_advance_days": rules.max_advance_days}

    def _window_reason(self, resource, start):
        earliest, latest = self.booking_window(resource)
        day = start.astimezone(ZoneInfo(resource.timezone)).date()
        return "BOOKING_TOO_SOON" if day < earliest else "BOOKING_TOO_FAR_AHEAD" if day > latest else None

    def _window_violation(self, resource, start):
        reason = self._window_reason(resource, start)
        if reason == "BOOKING_TOO_SOON":
            return DomainError(reason, f"Bookings must be made at least {self.min_advance_days} days in advance.", 400,
                               self._window_details(resource))
        if reason == "BOOKING_TOO_FAR_AHEAD":
            return DomainError(reason, f"Bookings can start at most {self.max_advance_days} days ahead.", 400,
                               self._window_details(resource))
        return None

    def _validate_horizon(self, resource, start):
        error = self._window_violation(resource, start)
        if error:
            raise error

    def _review_deadline(self, resource, start):
        """End of the Admin review window: pending_hold_minutes from now, but never after the booking starts."""
        return min(start, self.now() + timedelta(minutes=resource.pending_hold_minutes))

    def _require_eligible(self, actor_id, resource, end):
        """Only someone whose induction (and its prerequisites) is verified and valid at the end may request it."""
        error = self._qualification_violation(actor_id, resource, end)
        if error:
            raise error

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

    def create_booking(self, actor, resource_id, start, end, purpose, idempotency_key=None):
        """Every request starts as pending (never confirmed straight away).

        Free time: PENDING_APPROVAL, holding the slot until an Admin decides or the review window
        (resource.pending_hold_minutes, default 24 hours) ends, when the system approves it if it still
        follows the rules and rejects it otherwise. Taken or held time: WAITLISTED in submission order.
        """
        self.require_booking_user(actor)
        self.process_due_requests()
        resource_id = str(resource_id)
        if not purpose.strip() or len(purpose) > 1000:
            raise DomainError("VALIDATION_ERROR", "A booking purpose of up to 1000 characters is required.")
        if start.tzinfo is None or start.utcoffset() is None or end.tzinfo is None or end.utcoffset() is None:
            raise DomainError("INVALID_TIME", "Start and end require UTC offsets.")
        start, end = start.astimezone(UTC), end.astimezone(UTC)
        if idempotency_key:
            if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", idempotency_key):
                raise DomainError("INVALID_IDEMPOTENCY_KEY", "Use up to 128 letters, digits, dots, underscores, colons or hyphens.")
            booking_id = str(uuid5(UUID("3797490d-6aa7-4bf0-b004-aa50ffab4adc"), f"{actor.id}:{idempotency_key}"))
        else:
            booking_id = str(uuid4())
        with self.repo.atomic(resource_ids=[resource_id], student_ids=[actor.id]):
            existing = self.repo.get_booking(booking_id)
            if existing:
                if (existing.resource_id, existing.start, existing.end, existing.purpose) != (resource_id, start, end, purpose.strip()):
                    raise DomainError("IDEMPOTENCY_CONFLICT", "This Idempotency-Key was already used with different booking details.", 409)
                return existing, False
            resource = self.resource(resource_id)
            self._validate_period(resource, start, end)
            self._validate_horizon(resource, start)
            self._reject_duplicate_request(actor.id, resource_id, start, end)
            error = self.rule_violation(actor.id, resource, start, end, check_window=True)
            if error:
                raise error
            now = self.now()
            conflicts = self._overlaps(resource_id, start, end)
            if conflicts:
                # Strict FIFO: someone earlier holds or owns this time, so queue behind them.
                status = BookingStatus.WAITLISTED
                reason = "TIME_CONFLICT" if any(item.status == BookingStatus.APPROVED for item in conflicts) else "TEMPORARY_HOLD_CONFLICT"
                deadline = None
            else:
                status, reason = BookingStatus.PENDING_APPROVAL, "AWAITING_REVIEW"
                deadline = self._review_deadline(resource, start)
            booking = Booking(booking_id, actor.id, resource_id, start, end, purpose.strip(), now, status, reason,
                              review_due_at=deadline, updated_at=now, hold_until=deadline)
            self._save_booking(booking)
            self._audit(actor.id, "BOOKING_CREATED", "booking", booking.id, status=status.value, reason_code=reason,
                        hold_until=deadline.isoformat() if deadline else None)
            return booking, True

    def booking_for(self, actor, booking_id):
        booking = self.repo.get_booking(str(booking_id))
        if booking is None or (actor.role == Role.STUDENT and booking.student_id != actor.id):
            raise DomainError("NOT_FOUND", "Booking not found.", 404)
        return booking

    def submission_for(self, actor, submission_id):
        submission = self.repo.get_submission(str(submission_id))
        if submission is None or (actor.role == Role.STUDENT and submission.student_id != actor.id):
            raise DomainError("NOT_FOUND", "Qualification submission not found.", 404)
        return submission

    def submit_qualification(self, actor, requirement_id, title, notes, data, filename, content_type):
        self.require_booking_user(actor)
        requirement_id = str(requirement_id)
        if not title.strip() or len(title) > 160 or len(notes) > 2000:
            raise DomainError("VALIDATION_ERROR", "Check the qualification title and notes.")
        if not data or len(data) > 5 * 1024 * 1024:
            raise DomainError("INVALID_FILE", "Evidence must contain data and be no larger than 5 MiB.")
        stored = None
        try:
            with self.repo.atomic(student_ids=[actor.id]):
                if not self.repo.get_requirement(requirement_id):
                    raise DomainError("NOT_FOUND", "Qualification requirement not found.", 404)
                latest = self.latest_submission(actor.id, requirement_id)
                if latest and latest.status == QualificationStatus.PENDING:
                    raise DomainError("QUALIFICATION_ALREADY_PENDING", "Your evidence is already waiting for review.", 409)
                if latest and latest.status == QualificationStatus.VERIFIED and (latest.valid_until is None or latest.valid_until > self.now()):
                    raise DomainError("QUALIFICATION_ALREADY_VERIFIED", "Your qualification is already current.", 409)
                self._require_prerequisites(actor.id, requirement_id)
                stored = self.storage.save(data, filename, content_type, actor.id)
                record = QualificationSubmission(str(uuid4()), actor.id, requirement_id, title.strip(), notes, stored.id, self.now())
                self.repo.save_submission(record)
                self._audit(actor.id, "QUALIFICATION_SUBMITTED", "qualification", record.id)
                return record
        except Exception:
            if stored:
                self.storage.delete(stored.id)
            raise

    def _require_prerequisites(self, student_id, requirement_id):
        """Evidence for a requirement is accepted and verified only after its prerequisites are verified and current."""
        missing = self.missing_prerequisite(student_id, requirement_id)
        if missing:
            prerequisite = self.repo.get_requirement(missing[0])
            raise DomainError("PREREQUISITE_REQUIRED",
                              f"{prerequisite.name if prerequisite else 'A prerequisite induction'} must be verified and current first.",
                              409, {"prerequisite_id": missing[0], "prerequisite_status": missing[1]})

    def qualification_expiry(self, verified_at):
        """Expiry for a qualification verified at ``verified_at`` (Sprint 1: fixed days).

        Replace this calculation if the client later adopts term end dates or
        per-requirement validity; manual review and any Moodle adapter should both use it.
        """
        return verified_at + timedelta(days=self.qualification_validity_days)

    def review_qualification(self, actor, submission_id, decision, reason=""):
        self.require_staff(actor)
        self.process_due_requests()
        if decision not in ("VERIFIED", "REJECTED"):
            raise DomainError("VALIDATION_ERROR", "Choose VERIFIED or REJECTED.")
        if decision == "REJECTED" and not reason.strip():
            raise DomainError("REASON_REQUIRED", "A rejection reason is required.")
        source = self.submission_for(actor, submission_id)
        resource_ids = sorted(item.id for item in self.repo.list_resources() if item.required_qualification_id == source.requirement_id)
        with self.repo.atomic(resource_ids=resource_ids, student_ids=[source.student_id]):
            source = self.submission_for(actor, submission_id)
            if source.status != QualificationStatus.PENDING:
                raise DomainError("ALREADY_REVIEWED", "This evidence has already been reviewed.", 409)
            if actor.id == source.student_id:
                raise DomainError("SELF_REVIEW_FORBIDDEN", "You cannot review your own evidence.", 403)
            if decision == "VERIFIED":
                self._require_prerequisites(source.student_id, source.requirement_id)
            reviewed_at = self.now()
            updated = replace(source, status=QualificationStatus(decision), reviewed_by=actor.id, reviewed_at=reviewed_at,
                              rejection_reason=reason.strip() if decision == "REJECTED" else None,
                              valid_until=self.qualification_expiry(reviewed_at) if decision == "VERIFIED" else None)
            self.repo.save_submission(updated)
            self._audit(actor.id, f"QUALIFICATION_{decision}", "qualification", updated.id, reason=reason.strip(),
                        valid_until=updated.valid_until.isoformat() if updated.valid_until else None)
            changed = []
            if decision == "REJECTED":
                # The latest evidence for this requirement is now rejected, so none of the person's undecided
                # requests that depend on it can be approved: reject them at once and pass the time on.
                for booking in sorted(self.repo.list_bookings(student_id=source.student_id), key=lambda item: (item.created_at, item.id)):
                    if booking.status not in UNDECIDED_STATUSES or booking.resource_id not in resource_ids:
                        continue
                    if booking.start <= self.now():
                        revised = replace(booking, status=BookingStatus.EXPIRED, reason_code="START_TIME_PASSED", updated_at=self.now())
                        self._audit("SYSTEM", "BOOKING_TIME_PROCESSED", "booking", revised.id, status="EXPIRED", reason_code="START_TIME_PASSED")
                    else:
                        revised = replace(booking, status=BookingStatus.REJECTED, reason_code="QUALIFICATION_REJECTED",
                                          reviewed_by=actor.id, reviewed_at=self.now(), decision_reason=reason.strip(),
                                          updated_at=self.now())
                        self._audit(actor.id, "BOOKING_REJECTED", "booking", revised.id, reason=reason.strip(),
                                    reason_code="QUALIFICATION_REJECTED", qualification_id=updated.id)
                    self._save_booking(revised)
                    changed.append(revised)
                for resource_id in sorted({item.resource_id for item in changed}):
                    self._promote_waitlist(resource_id)
            return updated, changed

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
            if source.student_id == actor.id:
                raise DomainError("SELF_REVIEW_FORBIDDEN", "You cannot approve your own request.", 403)
            if decision == "APPROVED":
                resource = self.resource(source.resource_id)
                error = self.rule_violation(source.student_id, resource, source.start, source.end)
                if error and error.code == "QUALIFICATION_REQUIRED":
                    raise DomainError("QUALIFICATION_NOT_VERIFIED", "Verify current induction evidence covering the booking before approval.",
                                      409, error.details)
                if error:
                    raise error
                blockers = self._overlaps(source.resource_id, source.start, source.end, source.id)
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
        """Move a student's confirmed future booking to another valid free slot."""
        self.require_booking_user(actor)
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
            self._validate_period(resource, start, end)
            self._validate_horizon(resource, start)
            self._reject_duplicate_request(actor.id, source.resource_id, start, end, source.id)
            error = self.rule_violation(source.student_id, resource, start, end, check_window=True)
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
                reason_code="RESCHEDULED_BY_USER",
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

    AUDIT_ENTITY_TYPES = ("booking", "qualification", "resource", "principal", "requirement")

    def audit_trail(self, actor, resource_id=None, student_id=None, entity_type=None, entity_id=None,
                    action=None, actor_id=None, since=None, until=None, limit=100, offset=0):
        """Admin/Manager view of requests, approvals, changes and cancellations, newest first.

        resource_id matches the resource's own records and those of its bookings; student_id
        matches records the student performed plus their bookings, submissions and account.
        Returns (total_matching, page). Filtering runs in memory over ``repo.list_audit()``;
        a database adapter may push these filters into an indexed query with the same results.
        """
        self.require_staff(actor)
        if entity_type is not None and entity_type not in self.AUDIT_ENTITY_TYPES:
            raise DomainError("VALIDATION_ERROR", "Unknown audit entity type.")
        for name, value in (("since", since), ("until", until)):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise DomainError("INVALID_TIME", f"{name} requires a UTC offset.")
        if since is not None and until is not None and since >= until:
            raise DomainError("INVALID_TIME", "since must be earlier than until.")
        if not 1 <= limit <= 500 or offset < 0:
            raise DomainError("VALIDATION_ERROR", "Use limit 1-500 and a non-negative offset.")
        resource_entities = student_entities = None
        if resource_id is not None:
            resource_id = str(resource_id)
            resource_entities = {("resource", resource_id)} | {
                ("booking", item.id) for item in self.repo.list_bookings(resource_id=resource_id)}
        if student_id is not None:
            student_id = str(student_id)
            student_entities = ({("principal", student_id)}
                                | {("booking", item.id) for item in self.repo.list_bookings(student_id=student_id)}
                                | {("qualification", item.id) for item in self.repo.list_submissions(student_id=student_id)})
        matches = []
        for index, record in enumerate(self.repo.list_audit()):
            key = (record.entity_type, record.entity_id)
            if resource_entities is not None and key not in resource_entities:
                continue
            if student_entities is not None and key not in student_entities and record.actor_id != student_id:
                continue
            if entity_type is not None and record.entity_type != entity_type:
                continue
            if entity_id is not None and record.entity_id != str(entity_id):
                continue
            if action is not None and record.action != action:
                continue
            if actor_id is not None and record.actor_id != str(actor_id):
                continue
            if since is not None and record.at < since:
                continue
            if until is not None and record.at >= until:
                continue
            matches.append((record.at, index, record))
        matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return len(matches), [record for _, _, record in matches[offset:offset + limit]]

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

    def availability(self, actor, resource_id, day, duration_minutes=30, exclude_booking_id=None):
        """exclude_booking_id: the caller's own booking being rescheduled, so its current time shows as free."""
        self.process_due_requests()
        resource = self.resource(resource_id)
        exclude = None
        if exclude_booking_id:
            excluded = self.booking_for(actor, exclude_booking_id)
            if excluded.resource_id != resource.id:
                raise DomainError("VALIDATION_ERROR", "exclude_booking_id must be a booking for this resource.")
            exclude = excluded.id
        if not resource.active:
            raise DomainError("RESOURCE_UNAVAILABLE", "The resource is inactive.", 409)
        if duration_minutes < 1 or duration_minutes > resource.max_booking_minutes or duration_minutes % resource.slot_minutes:
            raise DomainError("INVALID_DURATION", f"Use multiples of {resource.slot_minutes} minutes, up to {resource.max_booking_minutes}.")
        zone = ZoneInfo(resource.timezone)
        cursor = datetime.combine(day, resource.opening_time, zone).astimezone(UTC)
        closing = datetime.combine(day, resource.closing_time, zone).astimezone(UTC)
        eligibility, _ = self.qualification_state(actor.id, resource)
        own_requests = [item for item in self.repo.list_bookings(student_id=actor.id, resource_id=resource.id)
                        if item.status in ACTIVE_REQUEST_STATUSES and item.id != exclude]
        slots = []
        while cursor + timedelta(minutes=duration_minutes) <= closing:
            end = cursor + timedelta(minutes=duration_minutes)
            blockers = self._overlaps(resource.id, cursor, end, exclude)
            holds = [item for item in blockers if item.hold_is_active(self.now())]
            requested_by_me = any(cursor < item.end and item.start < end for item in own_requests)
            window = self._window_reason(resource, cursor)
            reason = ("START_TIME_PASSED" if cursor <= self.now() else
                      "RESOURCE_UNAVAILABLE" if not resource.bookable else
                      "TOO_SOON" if window == "BOOKING_TOO_SOON" else
                      "TOO_FAR_AHEAD" if window == "BOOKING_TOO_FAR_AHEAD" else
                      "BOOKED" if any(item.status == BookingStatus.APPROVED for item in blockers) else
                      "TEMPORARILY_HELD" if holds else None)
            slots.append({"start": cursor, "end": end, "available": reason is None, "reason_code": reason,
                          "hold_until": max(item.hold_until for item in holds) if reason == "TEMPORARILY_HELD" else None,
                          "held_by_me": bool(holds) and all(item.student_id == actor.id for item in holds)
                          if reason == "TEMPORARILY_HELD" else False,
                          "requested_by_me": requested_by_me})
            cursor += timedelta(minutes=resource.slot_minutes)
        return {"resource_id": resource.id, "date": day.isoformat(), "timezone": resource.timezone,
                "duration_minutes": duration_minutes, "slots": slots, **self._window_details(resource),
                "resource_status": resource.status.value, "status_reason": resource.status_reason,
                "review_window_minutes": resource.pending_hold_minutes,
                # Only students book; their induction (and its prerequisites) must be verified and current.
                "can_request": actor.role == Role.STUDENT and eligibility == "VERIFIED" and resource.bookable,
                "qualification_status": eligibility,
                "missing_prerequisite_id": (self.missing_prerequisite(actor.id, resource.required_qualification_id) or (None,))[0]
                if eligibility == "PREREQUISITE_REQUIRED" else None}
