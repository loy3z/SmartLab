"""Booking policy independent of HTTP and the eventual database adapter."""
import re
from contextvars import ContextVar
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5
from zoneinfo import ZoneInfo
from .domain import (MAX_PENDING_HOLD_MINUTES, AuditRecord, Booking, BookingStatus, Principal, QualificationSubmission,
                     QualificationStatus, ResourceStatus, Role)
from .errors import DomainError

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


def _bounded_int(name, value, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high}.")
    return value


class BookingService:
    def __init__(self, repo, storage, clock=None, calendar_sync=None, qualification_validity_days=120,
                 min_advance_days=7, max_advance_days=30):
        self.repo, self.storage = repo, storage
        self.clock = clock or (lambda: datetime.now(UTC))
        self.calendar_sync = calendar_sync
        # Sprint 1 fixed policy: a verified induction lasts one term (default 120 days from approval).
        # Configured by QUALIFICATION_VALIDITY_DAYS; reviewers cannot choose a different expiry.
        if isinstance(qualification_validity_days, bool) or not isinstance(qualification_validity_days, int) \
                or not 1 <= qualification_validity_days <= 3650:
            raise ValueError("qualification_validity_days must be an integer from 1 to 3650.")
        self.qualification_validity_days = qualification_validity_days
        # Team proposal (not client-confirmed): a booking must start between min_advance_days and
        # max_advance_days local calendar days from today (default: at least one week, at most 30 days ahead).
        self.min_advance_days = _bounded_int("min_advance_days", min_advance_days, 0, 365)
        self.max_advance_days = _bounded_int("max_advance_days", max_advance_days, 1, 365)
        if self.min_advance_days > self.max_advance_days:
            raise ValueError("min_advance_days must not exceed max_advance_days.")

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
        if not actor.active or actor.role not in (Role.STUDENT, Role.ADMIN):
            raise DomainError(
                "FORBIDDEN",
                "This action requires an active Student or Admin account.",
                403,
            )

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
        """Nominate a user's role or (de)activate the account. Takes effect on the user's next request."""
        self.require_manager(actor)
        if role is None and active is None:
            raise DomainError("VALIDATION_ERROR", "Provide role and/or active.")
        user_id = str(user_id)
        if user_id == actor.id:
            raise DomainError("SELF_MODIFICATION_FORBIDDEN", "Managers cannot change their own role or status.", 403)
        if role == Role.MANAGER.value:
            raise DomainError("MANAGER_ROLE_NOT_ASSIGNABLE",
                              "Managers are created only with Add manager, not by changing a role.", 403)
        managers = [item.id for item in self.repo.list_principals() if item.role == Role.MANAGER]
        with self.repo.atomic(student_ids=sorted(set(managers + [user_id]))):
            current = self.repo.get_principal(user_id)
            if current is None:
                raise DomainError("NOT_FOUND", "User not found.", 404)
            if role is not None and current.role == Role.MANAGER and role != Role.MANAGER.value:
                raise DomainError("MANAGER_ROLE_NOT_ASSIGNABLE",
                                  "A Manager's role cannot be changed here; deactivate the account instead.", 403)
            if role == Role.ADMIN.value and current.role == Role.STUDENT:
                inductions = self.induction_summary(current.id)
                missing = [item for item in inductions if item["status"] != "VERIFIED"]
                if missing:
                    raise DomainError("INDUCTION_REQUIRED_FOR_ADMIN",
                                      f"{current.display_name} ({current.zid}) must pass every induction before becoming an administrator.",
                                      409, {"zid": current.zid, "display_name": current.display_name, "missing_inductions": missing})
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
            return updated

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

    def create_manager(self, actor, zid, display_name, university_email):
        """Manager only ("Add manager"): the only way to create a Manager. Students and admins come from
        existing accounts; their role is changed with update_user. No induction is required for a Manager."""
        self.require_manager(actor)
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
                created = Principal(str(uuid4()), zid, display_name, Role.MANAGER, university_email)
            except ValueError as exc:
                raise DomainError("VALIDATION_ERROR", str(exc)) from exc
            self.repo.save_principal(created)
            self._audit(actor.id, "MANAGER_CREATED", "principal", created.id, zid=zid)
            return created

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

    def qualification_state(self, student_id, resource, end=None):
        """Single eligibility check used by create, approve, reschedule and availability.

        Eligibility comes only from the latest QualificationSubmission for the
        resource's requirement. Sprint 1 creates VERIFIED records through manual
        review (review_qualification). A future source such as Moodle course
        completion should be added as an adapter that saves a VERIFIED
        QualificationSubmission (reviewed_by identifying the source, valid_until
        from the same validity policy). Booking rules here then need no change.
        """
        if not resource.required_qualification_id:
            return "NOT_CONFIGURED", False
        record = self.latest_submission(student_id, resource.required_qualification_id)
        if record is None:
            return "NOT_SUBMITTED", False
        if record.status == QualificationStatus.VERIFIED:
            if record.valid_until is not None and record.valid_until <= self.now():
                return "EXPIRED", False
            if end is not None and record.valid_until is not None and record.valid_until < end:
                return "EXPIRES_BEFORE_END", False
            return "VERIFIED", True
        return record.status.value, False

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

    def _require_bookable(self, resource):
        if not resource.bookable:
            status = resource.status.value if resource.active else "INACTIVE"
            raise DomainError("RESOURCE_UNAVAILABLE", "This resource is not accepting bookings right now.", 409,
                              {"resource_status": status, "status_reason": resource.status_reason})

    def _validate_period(self, resource, start, end):
        if start.tzinfo is None or start.utcoffset() is None or end.tzinfo is None or end.utcoffset() is None:
            raise DomainError("INVALID_TIME", "Start and end require UTC offsets.")
        self._require_bookable(resource)
        if start >= end or start <= self.now():
            raise DomainError("INVALID_TIME", "Use a future start time and an end later than start.")
        duration = (end - start).total_seconds() / 60
        if duration > resource.max_booking_minutes:
            raise DomainError("DURATION_LIMIT", "The booking exceeds this resource's maximum duration.")
        local_start = start.astimezone(ZoneInfo(resource.timezone))
        local_end = end.astimezone(ZoneInfo(resource.timezone))
        if (local_start.date() != local_end.date() or local_start.time().replace(tzinfo=None) < resource.opening_time
                or local_end.time().replace(tzinfo=None) > resource.closing_time):
            raise DomainError("OUTSIDE_OPENING_HOURS", "Book within one local day and the resource's opening hours.")
        opening = datetime.combine(local_start.date(), resource.opening_time, ZoneInfo(resource.timezone))
        offset = (local_start - opening).total_seconds() / 60
        if start.second or start.microsecond or end.second or end.microsecond or offset % resource.slot_minutes or duration % resource.slot_minutes:
            raise DomainError("INVALID_TIME_INCREMENT", f"Use {resource.slot_minutes}-minute time increments.")

    def booking_window(self, resource):
        """First and last local dates a new or rescheduled booking may start on."""
        today = self.now().astimezone(ZoneInfo(resource.timezone)).date()
        return today + timedelta(days=self.min_advance_days), today + timedelta(days=self.max_advance_days)

    def _window_details(self, resource):
        earliest, latest = self.booking_window(resource)
        return {"earliest_date": earliest.isoformat(), "latest_date": latest.isoformat(),
                "min_advance_days": self.min_advance_days, "max_advance_days": self.max_advance_days}

    def _window_reason(self, resource, start):
        earliest, latest = self.booking_window(resource)
        day = start.astimezone(ZoneInfo(resource.timezone)).date()
        return "BOOKING_TOO_SOON" if day < earliest else "BOOKING_TOO_FAR_AHEAD" if day > latest else None

    def _validate_horizon(self, resource, start):
        reason = self._window_reason(resource, start)
        if reason == "BOOKING_TOO_SOON":
            raise DomainError(reason, f"Bookings must be made at least {self.min_advance_days} days in advance.", 400,
                              self._window_details(resource))
        if reason == "BOOKING_TOO_FAR_AHEAD":
            raise DomainError(reason, f"Bookings can start at most {self.max_advance_days} days ahead.", 400,
                              self._window_details(resource))

    def _review_deadline(self, resource, start):
        """End of the Admin review window: pending_hold_minutes from now, but never after the booking starts."""
        return min(start, self.now() + timedelta(minutes=resource.pending_hold_minutes))

    def _require_eligible(self, actor_id, resource, end):
        """Only someone whose induction for this resource is verified and still valid at the end may request it."""
        eligibility, qualified = self.qualification_state(actor_id, resource, end)
        if eligibility == "NOT_CONFIGURED":
            raise DomainError("RESOURCE_POLICY_NOT_CONFIGURED", "Configure an induction requirement for this resource before accepting requests.", 409)
        if not qualified:
            raise DomainError("QUALIFICATION_REQUIRED",
                              "A verified induction that is valid for the whole booking is required before requesting this resource.",
                              403, {"qualification_status": eligibility, "requirement_id": resource.required_qualification_id})

    def _auto_decision(self, booking):
        """What the system decides when the review window ends without an Admin decision."""
        resource = self.repo.get_resource(booking.resource_id)
        if resource is None or not resource.bookable:
            return BookingStatus.REJECTED, "AUTO_REJECTED_RESOURCE_UNAVAILABLE", "The resource is not available for booking."
        eligibility, qualified = self.qualification_state(booking.student_id, resource, booking.end)
        if not qualified:
            return (BookingStatus.REJECTED, "AUTO_REJECTED_QUALIFICATION",
                    f"No valid induction for the whole booking (status {eligibility}).")
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
                if resource is None or not resource.bookable or self._overlaps(booking.resource_id, booking.start, booking.end, booking.id):
                    continue
                _, qualified = self.qualification_state(booking.student_id, resource, booking.end)
                if qualified:
                    deadline = self._review_deadline(resource, booking.start)
                    status, reason, action = BookingStatus.PENDING_APPROVAL, "PROMOTED_FROM_WAITLIST", "BOOKING_PROMOTED"
                    extra = {"hold_until": deadline, "review_due_at": deadline}
                else:
                    status, reason, action = BookingStatus.REJECTED, "QUALIFICATION_REQUIRED", "BOOKING_REJECTED"
                    extra = {"reviewed_by": "SYSTEM", "reviewed_at": now,
                             "decision_reason": "No current qualification covers this booking."}
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
            self._require_eligible(actor.id, resource, end)
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
                stored = self.storage.save(data, filename, content_type, actor.id)
                record = QualificationSubmission(str(uuid4()), actor.id, requirement_id, title.strip(), notes, stored.id, self.now())
                self.repo.save_submission(record)
                self._audit(actor.id, "QUALIFICATION_SUBMITTED", "qualification", record.id)
                return record
        except Exception:
            if stored:
                self.storage.delete(stored.id)
            raise

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
                self._validate_period(resource, source.start, source.end)
                eligibility, qualified = self.qualification_state(source.student_id, resource, source.end)
                if not qualified:
                    raise DomainError("QUALIFICATION_NOT_VERIFIED", "Verify current induction evidence covering the booking before approval.", 409, {"qualification_status": eligibility})
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
            eligibility, qualified = self.qualification_state(source.student_id, resource, end)
            if not qualified:
                raise DomainError(
                    "QUALIFICATION_NOT_VERIFIED",
                    "A current qualification covering the new booking period is required.",
                    409,
                    {"qualification_status": eligibility},
                )
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

    AUDIT_ENTITY_TYPES = ("booking", "qualification", "resource", "principal")

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
                # Students and admins (tutor-like students) may request; a verified, current induction is required.
                "can_request": actor.role in (Role.STUDENT, Role.ADMIN) and eligibility == "VERIFIED" and resource.bookable,
                "qualification_status": eligibility}
