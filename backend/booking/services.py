"""Booking policy independent of HTTP and the eventual database adapter."""
import re
from contextvars import ContextVar
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5
from zoneinfo import ZoneInfo
from .domain import (MAX_PENDING_HOLD_MINUTES, AuditRecord, Booking, BookingStatus, QualificationSubmission,
                     QualificationStatus, Role)
from .errors import DomainError

# Requests that hold first place for their slot (blocking others while hold_until is in the future).
HEAD_STATUSES = (BookingStatus.WAITING_QUALIFICATION, BookingStatus.PENDING_APPROVAL)
# Requests that are still undecided, including those queued on the waitlist.
UNDECIDED_STATUSES = HEAD_STATUSES + (BookingStatus.WAITLISTED,)

# Bookings changed by automatic waitlist promotion during the current request, so the
# HTTP layer can push newly approved ones to Outlook. One list per thread/request context.
_promoted_ids = ContextVar("booking_promoted_ids", default=None)


def _bounded_int(name, value, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high}.")
    return value


class BookingService:
    def __init__(self, repo, storage, clock=None, wait_hours=24, calendar_sync=None, qualification_validity_days=120,
                 min_advance_days=7, max_advance_days=30, unverified_pending_limit=1):
        self.repo, self.storage = repo, storage
        self.clock = clock or (lambda: datetime.now(UTC))
        self.wait_hours = wait_hours
        self.calendar_sync = calendar_sync
        # Sprint 1 fixed policy: a verified induction lasts one term (default 120 days from approval).
        # Configured by QUALIFICATION_VALIDITY_DAYS; reviewers cannot choose a different expiry.
        if isinstance(qualification_validity_days, bool) or not isinstance(qualification_validity_days, int) \
                or not 1 <= qualification_validity_days <= 3650:
            raise ValueError("qualification_validity_days must be an integer from 1 to 3650.")
        self.qualification_validity_days = qualification_validity_days
        # Sprint 1 fixed rules (demo values, not client-confirmed policy):
        # a booking must start between min_advance_days and max_advance_days local calendar days from today
        # (default: at least one week ahead, at most 30 days ahead), and a student whose induction is still
        # under review may keep at most unverified_pending_limit undecided requests per qualification, so one
        # unverified student cannot lock many slots while waiting.
        self.min_advance_days = _bounded_int("min_advance_days", min_advance_days, 0, 365)
        self.max_advance_days = _bounded_int("max_advance_days", max_advance_days, 1, 365)
        if self.min_advance_days > self.max_advance_days:
            raise ValueError("min_advance_days must not exceed max_advance_days.")
        self.unverified_pending_limit = _bounded_int("unverified_pending_limit", unverified_pending_limit, 1, 100)

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
        managers = [item.id for item in self.repo.list_principals() if item.role == Role.MANAGER]
        with self.repo.atomic(student_ids=sorted(set(managers + [user_id]))):
            current = self.repo.get_principal(user_id)
            if current is None:
                raise DomainError("NOT_FOUND", "User not found.", 404)
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
        self.require_manager(actor)
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= MAX_PENDING_HOLD_MINUTES:
            raise DomainError("VALIDATION_ERROR", f"pending_hold_minutes must be an integer from 1 to {MAX_PENDING_HOLD_MINUTES}.")
        with self.repo.atomic(resource_ids=[str(resource_id)]):
            current = self.resource(resource_id)
            updated = replace(current, pending_hold_minutes=minutes)
            self.repo.save_resource(updated)
            self._audit(actor.id, "RESOURCE_BOOKING_POLICY_UPDATED", "resource", current.id,
                        previous_minutes=current.pending_hold_minutes, pending_hold_minutes=minutes)
            return updated

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

    def _validate_period(self, resource, start, end):
        if start.tzinfo is None or start.utcoffset() is None or end.tzinfo is None or end.utcoffset() is None:
            raise DomainError("INVALID_TIME", "Start and end require UTC offsets.")
        if not resource.active:
            raise DomainError("RESOURCE_UNAVAILABLE", "The resource is inactive.", 409)
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

    def _check_unverified_limit(self, student_id, resource):
        same_requirement = {item.id for item in self.repo.list_resources()
                            if item.required_qualification_id == resource.required_qualification_id}
        undecided = [item for item in self.repo.list_bookings(student_id=student_id)
                     if item.status in UNDECIDED_STATUSES and item.resource_id in same_requirement]
        if len(undecided) >= self.unverified_pending_limit:
            raise DomainError("PENDING_REQUEST_LIMIT",
                              "Your induction is still under review; wait for a decision before making more requests.", 409,
                              {"limit": self.unverified_pending_limit, "pending_booking_ids": [item.id for item in undecided]})

    def _promote_waitlist(self, resource_id):
        """Offer freed time to waitlisted requests in submission order (strict FIFO).

        Call inside a transaction that holds the resource lock, after anything that may free a
        slot: cancellation, rejection, expiry, rescheduling or a timed hold ending. A request is
        promoted only when no approved booking or active hold overlaps it; it is then handled as
        if newly submitted: qualified -> APPROVED, induction under review -> becomes the holder
        (only if it never held the slot before; each request gets one hold), otherwise REJECTED.
        Earlier requests are always considered first.
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
                if resource is None or not resource.active or self._overlaps(booking.resource_id, booking.start, booking.end, booking.id):
                    continue
                eligibility, qualified = self.qualification_state(booking.student_id, resource, booking.end)
                action = "BOOKING_PROMOTED"
                if qualified:
                    status, reason = BookingStatus.APPROVED, "PROMOTED_FROM_WAITLIST"
                elif eligibility == "PENDING":
                    if booking.hold_until is not None:
                        continue  # already had its hold; waits in the queue until its induction is verified
                    review_due = booking.review_due_at or booking.created_at + timedelta(hours=self.wait_hours)
                    status = (BookingStatus.PENDING_APPROVAL if review_due <= now or review_due >= booking.start
                              else BookingStatus.WAITING_QUALIFICATION)
                    reason = "PROMOTED_FROM_WAITLIST"
                    extra = {"review_due_at": review_due,
                             "hold_until": min(booking.start, now + timedelta(minutes=resource.pending_hold_minutes))}
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
        self.require_student(actor)
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
            eligibility, qualified = self.qualification_state(actor.id, resource, end)
            if eligibility == "NOT_CONFIGURED":
                raise DomainError("RESOURCE_POLICY_NOT_CONFIGURED", "Configure an induction requirement for this resource before accepting requests.", 409)
            if eligibility not in ("PENDING", "VERIFIED"):
                raise DomainError("QUALIFICATION_REQUIRED", "Submit current induction evidence before requesting this resource.", 403, {"qualification_status": eligibility, "requirement_id": resource.required_qualification_id})
            if not qualified:
                self._check_unverified_limit(actor.id, resource)
            now = self.now()
            conflicts = self._overlaps(resource_id, start, end)
            review_due = None
            if conflicts:
                # Strict FIFO: someone earlier holds or owns this time, so queue behind them.
                status = BookingStatus.WAITLISTED
                reason = "TIME_CONFLICT" if any(item.status == BookingStatus.APPROVED for item in conflicts) else "TEMPORARY_HOLD_CONFLICT"
                review_due = None if qualified else now + timedelta(hours=self.wait_hours)
            elif qualified:
                status, reason = BookingStatus.APPROVED, "AUTO_APPROVED"
            else:
                review_due = now + timedelta(hours=self.wait_hours)
                if review_due >= start:
                    status, reason = BookingStatus.PENDING_APPROVAL, "REQUEST_STARTS_BEFORE_REVIEW"
                else:
                    status, reason = BookingStatus.WAITING_QUALIFICATION, "QUALIFICATION_PENDING"
            booking = Booking(booking_id, actor.id, resource_id, start, end, purpose.strip(), now, status, reason,
                              review_due_at=review_due, updated_at=now,
                              hold_until=min(start, now + timedelta(minutes=resource.pending_hold_minutes))
                              if not conflicts and status in (BookingStatus.WAITING_QUALIFICATION, BookingStatus.PENDING_APPROVAL) else None)
            self._save_booking(booking)
            self._audit(actor.id, "BOOKING_CREATED", "booking", booking.id, status=status.value, reason_code=reason,
                        hold_until=booking.hold_until.isoformat() if booking.hold_until else None)
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
        self.require_student(actor)
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
            # VERIFIED re-evaluates only WAITING_QUALIFICATION requests (escalated ones stay with
            # the reviewer). REJECTED ends every pending request that depends on this qualification,
            # because none of them can be approved; the slot and any hold are released at once and
            # the student re-uploads evidence, then books again.
            reevaluate = (BookingStatus.WAITING_QUALIFICATION,) if decision == "VERIFIED" else UNDECIDED_STATUSES
            for booking in sorted(self.repo.list_bookings(student_id=source.student_id), key=lambda item: (item.created_at, item.id)):
                if booking.status not in reevaluate or booking.resource_id not in resource_ids:
                    continue
                if booking.start <= self.now():
                    next_status, next_reason = BookingStatus.EXPIRED, "START_TIME_PASSED"
                elif decision == "REJECTED":
                    revised = replace(booking, status=BookingStatus.REJECTED, reason_code="QUALIFICATION_REJECTED",
                                      reviewed_by=actor.id, reviewed_at=self.now(), decision_reason=reason.strip(),
                                      updated_at=self.now())
                    self._save_booking(revised)
                    self._audit(actor.id, "BOOKING_REJECTED", "booking", revised.id, reason=reason.strip(),
                                reason_code="QUALIFICATION_REJECTED", qualification_id=updated.id)
                    changed.append(revised)
                    continue
                else:
                    resource = self.resource(booking.resource_id)
                    _, eligible = self.qualification_state(booking.student_id, resource, booking.end)
                    if not eligible:
                        next_status, next_reason = BookingStatus.PENDING_APPROVAL, "QUALIFICATION_EXPIRES_BEFORE_END"
                    elif not resource.active:
                        next_status, next_reason = BookingStatus.PENDING_APPROVAL, "RESOURCE_UNAVAILABLE"
                    elif self._overlaps(booking.resource_id, booking.start, booking.end, booking.id):
                        # Its timed hold ended and the time was taken meanwhile: queue behind the holder.
                        next_status, next_reason = BookingStatus.WAITLISTED, "TIME_CONFLICT"
                    else:
                        next_status, next_reason = BookingStatus.APPROVED, "AUTO_APPROVED_AFTER_QUALIFICATION"
                revised = replace(booking, status=next_status, reason_code=next_reason, updated_at=self.now())
                self._save_booking(revised)
                self._audit(actor.id, "BOOKING_REEVALUATED", "booking", revised.id, status=next_status.value, reason_code=next_reason)
                changed.append(revised)
            released = {item.resource_id for item in changed if item.status in (BookingStatus.REJECTED, BookingStatus.EXPIRED)}
            if decision == "VERIFIED":
                # Waitlisted requests of this student can now be approved when their time is free.
                released |= {item.resource_id for item in self.repo.list_bookings(student_id=source.student_id)
                             if item.status == BookingStatus.WAITLISTED and item.resource_id in resource_ids}
            for resource_id in sorted(released):
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
            reviewable = (BookingStatus.PENDING_APPROVAL,) if decision == "APPROVED" else (BookingStatus.PENDING_APPROVAL, BookingStatus.WAITLISTED)
            if source.status not in reviewable:
                raise DomainError("REQUEST_NOT_REVIEWABLE", "Only a pending manual or waitlisted request can be reviewed.", 409)
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
            revised = replace(source, status=BookingStatus.CANCELLED, reason_code="CANCELLED_BY_USER", updated_at=self.now())
            self._save_booking(revised)
            self._audit(actor.id, "BOOKING_CANCELLED", "booking", revised.id)
            self._promote_waitlist(revised.resource_id)
            return revised

    def reschedule_booking(self, actor, booking_id, start, end):
        """Move a student's confirmed future booking to another valid free slot."""
        self.require_student(actor)
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
        """Idempotent time processing; call from queries or a future scheduler."""
        changed, released = [], set()
        for candidate in self.repo.list_bookings():
            if candidate.status not in UNDECIDED_STATUSES:
                continue
            with self.repo.atomic(resource_ids=[candidate.resource_id], student_ids=[candidate.student_id]):
                current = self.repo.get_booking(candidate.id)
                if current.status not in UNDECIDED_STATUSES:
                    continue
                if current.start <= self.now():
                    status, reason = BookingStatus.EXPIRED, "START_TIME_PASSED"
                    if current.status in HEAD_STATUSES:
                        released.add(current.resource_id)
                elif current.status in HEAD_STATUSES and current.hold_until and current.hold_until <= self.now():
                    # Hold ended while still undecided: give up the slot and join the waitlist.
                    # It keeps its place in submission order but is promoted only once qualified.
                    status, reason = BookingStatus.WAITLISTED, "HOLD_EXPIRED"
                    released.add(current.resource_id)
                elif current.status == BookingStatus.WAITING_QUALIFICATION and current.review_due_at and current.review_due_at <= self.now():
                    status, reason = BookingStatus.PENDING_APPROVAL, "QUALIFICATION_WAIT_EXCEEDED"
                else:
                    continue
                updated = replace(current, status=status, reason_code=reason, updated_at=self.now())
                self._save_booking(updated)
                self._audit("SYSTEM", "BOOKING_TIME_PROCESSED", "booking", updated.id, status=status.value, reason_code=reason)
                changed.append(updated)
        for resource_id in sorted(released):
            if any(item.status == BookingStatus.WAITLISTED for item in self.repo.list_bookings(resource_id=resource_id)):
                with self.repo.atomic(resource_ids=[resource_id]):
                    changed.extend(self._promote_waitlist(resource_id))
        return changed

    def availability(self, actor, resource_id, day, duration_minutes=30):
        self.process_due_requests()
        resource = self.resource(resource_id)
        if not resource.active:
            raise DomainError("RESOURCE_UNAVAILABLE", "The resource is inactive.", 409)
        if duration_minutes < 1 or duration_minutes > resource.max_booking_minutes or duration_minutes % resource.slot_minutes:
            raise DomainError("INVALID_DURATION", f"Use multiples of {resource.slot_minutes} minutes, up to {resource.max_booking_minutes}.")
        zone = ZoneInfo(resource.timezone)
        cursor = datetime.combine(day, resource.opening_time, zone).astimezone(UTC)
        closing = datetime.combine(day, resource.closing_time, zone).astimezone(UTC)
        eligibility, _ = self.qualification_state(actor.id, resource)
        slots = []
        while cursor + timedelta(minutes=duration_minutes) <= closing:
            end = cursor + timedelta(minutes=duration_minutes)
            blockers = self._overlaps(resource.id, cursor, end)
            holds = [item for item in blockers if item.hold_is_active(self.now())]
            window = self._window_reason(resource, cursor)
            reason = ("START_TIME_PASSED" if cursor <= self.now() else
                      "TOO_SOON" if window == "BOOKING_TOO_SOON" else
                      "TOO_FAR_AHEAD" if window == "BOOKING_TOO_FAR_AHEAD" else
                      "BOOKED" if any(item.status == BookingStatus.APPROVED for item in blockers) else
                      "TEMPORARILY_HELD" if holds else None)
            slots.append({"start": cursor, "end": end, "available": reason is None, "reason_code": reason,
                          "hold_until": max(item.hold_until for item in holds) if reason == "TEMPORARILY_HELD" else None,
                          "held_by_me": bool(holds) and all(item.student_id == actor.id for item in holds)
                          if reason == "TEMPORARILY_HELD" else False})
            cursor += timedelta(minutes=resource.slot_minutes)
        return {"resource_id": resource.id, "date": day.isoformat(), "timezone": resource.timezone,
                "duration_minutes": duration_minutes, "slots": slots, **self._window_details(resource),
                "can_request": actor.role == Role.STUDENT and eligibility in ("PENDING", "VERIFIED"),
                "qualification_status": eligibility}
