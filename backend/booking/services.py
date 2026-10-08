"""Booking policy independent of HTTP and the eventual database adapter."""
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5
from zoneinfo import ZoneInfo
from .domain import AuditRecord, Booking, BookingStatus, QualificationSubmission, QualificationStatus, Role
from .errors import DomainError

class BookingService:
    def __init__(self, repo, storage, clock=None, wait_hours=24, calendar_sync=None):
        self.repo, self.storage = repo, storage
        self.clock = clock or (lambda: datetime.now(UTC))
        self.wait_hours = wait_hours
        self.calendar_sync = calendar_sync

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
        if not actor.active or actor.role not in (Role.ADMIN, Role.MANAGER):
            raise DomainError("FORBIDDEN", "This action requires an Admin or Manager account.", 403)

    def set_pending_hold_minutes(self, actor, resource_id, minutes):
        if not actor.active or actor.role != Role.MANAGER:
            raise DomainError("FORBIDDEN", "Only an active Manager may configure booking policies.", 403)
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 10080:
            raise DomainError("VALIDATION_ERROR", "pending_hold_minutes must be an integer from 1 to 10080.")
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
            eligibility, qualified = self.qualification_state(actor.id, resource, end)
            if eligibility == "NOT_CONFIGURED":
                raise DomainError("RESOURCE_POLICY_NOT_CONFIGURED", "Configure an induction requirement for this resource before accepting requests.", 409)
            if eligibility not in ("PENDING", "VERIFIED"):
                raise DomainError("QUALIFICATION_REQUIRED", "Submit current induction evidence before requesting this resource.", 403, {"qualification_status": eligibility, "requirement_id": resource.required_qualification_id})
            now = self.now()
            conflicts = self._overlaps(resource_id, start, end)
            review_due = None
            if conflicts:
                status = BookingStatus.PENDING_APPROVAL
                reason = "TIME_CONFLICT" if any(item.status == BookingStatus.APPROVED for item in conflicts) else "TEMPORARY_HOLD_CONFLICT"
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

    def review_qualification(self, actor, submission_id, decision, reason="", valid_until=None):
        self.require_staff(actor)
        self.process_due_requests()
        if decision not in ("VERIFIED", "REJECTED"):
            raise DomainError("VALIDATION_ERROR", "Choose VERIFIED or REJECTED.")
        if decision == "REJECTED" and not reason.strip():
            raise DomainError("REASON_REQUIRED", "A rejection reason is required.")
        if valid_until is not None and (valid_until.tzinfo is None or valid_until.utcoffset() is None or valid_until <= self.now()):
            raise DomainError("INVALID_VALIDITY", "The qualification expiry must be a future time with a UTC offset.")
        source = self.submission_for(actor, submission_id)
        resource_ids = sorted(item.id for item in self.repo.list_resources() if item.required_qualification_id == source.requirement_id)
        with self.repo.atomic(resource_ids=resource_ids, student_ids=[source.student_id]):
            source = self.submission_for(actor, submission_id)
            if source.status != QualificationStatus.PENDING:
                raise DomainError("ALREADY_REVIEWED", "This evidence has already been reviewed.", 409)
            if actor.id == source.student_id:
                raise DomainError("SELF_REVIEW_FORBIDDEN", "You cannot review your own evidence.", 403)
            updated = replace(source, status=QualificationStatus(decision), reviewed_by=actor.id, reviewed_at=self.now(),
                              rejection_reason=reason.strip() if decision == "REJECTED" else None,
                              valid_until=valid_until.astimezone(UTC) if decision == "VERIFIED" and valid_until else None)
            self.repo.save_submission(updated)
            self._audit(actor.id, f"QUALIFICATION_{decision}", "qualification", updated.id, reason=reason.strip())
            changed = []
            for booking in sorted(self.repo.list_bookings(student_id=source.student_id), key=lambda item: (item.created_at, item.id)):
                if booking.status != BookingStatus.WAITING_QUALIFICATION or booking.resource_id not in resource_ids:
                    continue
                if booking.start <= self.now():
                    next_status, next_reason = BookingStatus.EXPIRED, "START_TIME_PASSED"
                elif decision == "REJECTED":
                    next_status, next_reason = BookingStatus.PENDING_APPROVAL, "QUALIFICATION_REJECTED"
                else:
                    resource = self.resource(booking.resource_id)
                    _, eligible = self.qualification_state(booking.student_id, resource, booking.end)
                    if not eligible:
                        next_status, next_reason = BookingStatus.PENDING_APPROVAL, "QUALIFICATION_EXPIRES_BEFORE_END"
                    elif not resource.active:
                        next_status, next_reason = BookingStatus.PENDING_APPROVAL, "RESOURCE_UNAVAILABLE"
                    elif self._overlaps(booking.resource_id, booking.start, booking.end, booking.id):
                        next_status, next_reason = BookingStatus.PENDING_APPROVAL, "TIME_CONFLICT"
                    else:
                        next_status, next_reason = BookingStatus.APPROVED, "AUTO_APPROVED_AFTER_QUALIFICATION"
                revised = replace(booking, status=next_status, reason_code=next_reason, updated_at=self.now())
                self._save_booking(revised)
                self._audit(actor.id, "BOOKING_REEVALUATED", "booking", revised.id, status=next_status.value, reason_code=next_reason)
                changed.append(revised)
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
            if source.status != BookingStatus.PENDING_APPROVAL:
                raise DomainError("REQUEST_NOT_REVIEWABLE", "Only a pending manual request can be reviewed.", 409)
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
            return revised

    def process_due_requests(self):
        """Idempotent time processing; call from queries or a future scheduler."""
        changed = []
        for candidate in self.repo.list_bookings():
            if candidate.status not in (BookingStatus.WAITING_QUALIFICATION, BookingStatus.PENDING_APPROVAL):
                continue
            with self.repo.atomic(resource_ids=[candidate.resource_id], student_ids=[candidate.student_id]):
                current = self.repo.get_booking(candidate.id)
                if current.status not in (BookingStatus.WAITING_QUALIFICATION, BookingStatus.PENDING_APPROVAL):
                    continue
                if current.start <= self.now():
                    status, reason = BookingStatus.EXPIRED, "START_TIME_PASSED"
                elif current.status == BookingStatus.WAITING_QUALIFICATION and current.review_due_at and current.review_due_at <= self.now():
                    status, reason = BookingStatus.PENDING_APPROVAL, "QUALIFICATION_WAIT_EXCEEDED"
                else:
                    continue
                updated = replace(current, status=status, reason_code=reason, updated_at=self.now())
                self._save_booking(updated)
                self._audit("SYSTEM", "BOOKING_TIME_PROCESSED", "booking", updated.id, status=status.value, reason_code=reason)
                changed.append(updated)
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
            reason = ("START_TIME_PASSED" if cursor <= self.now() else
                      "BOOKED" if any(item.status == BookingStatus.APPROVED for item in blockers) else
                      "TEMPORARILY_HELD" if holds else None)
            slots.append({"start": cursor, "end": end, "available": reason is None, "reason_code": reason,
                          "hold_until": max(item.hold_until for item in holds) if reason == "TEMPORARILY_HELD" else None,
                          "held_by_me": bool(holds) and all(item.student_id == actor.id for item in holds)
                          if reason == "TEMPORARILY_HELD" else False})
            cursor += timedelta(minutes=resource.slot_minutes)
        return {"resource_id": resource.id, "date": day.isoformat(), "timezone": resource.timezone,
                "duration_minutes": duration_minutes, "slots": slots,
                "can_request": actor.role == Role.STUDENT and eligibility in ("PENDING", "VERIFIED"),
                "qualification_status": eligibility}
