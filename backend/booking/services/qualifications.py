"""Induction evidence: upload, manual review, validity, prerequisites (Advanced needs General) and the qualification
state a booking checks.
"""
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

from ..domain import BookingStatus, QualificationRequirement, QualificationSubmission, QualificationStatus, Role
from ..errors import DomainError
from .base import UNDECIDED_STATUSES


class QualificationsMixin:
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

    # Sprint 3 (1.16.0): Managers add induction types and write their guidance on the website ------------------

    REQUIREMENT_TEXT_FIELDS = ("name", "description", "how_to_complete", "accepted_evidence", "reviewer", "contact")

    def create_requirement(self, actor, fields):
        """Manager: add an induction type. Name required and unique (ignoring case); the guidance texts are optional."""
        self.require_manager(actor)
        with self.repo.atomic():
            values = self._check_requirement_fields(fields, requirement_id=None)
            created = QualificationRequirement(id=str(uuid4()), **values)
            self.repo.save_requirement(created)
            self._audit(actor.id, "REQUIREMENT_CREATED", "requirement", created.id, **values)
            return created

    def update_requirement(self, actor, requirement_id, changes):
        """Manager: change an induction's name, description or guidance. Only the fields sent are changed; who already
        holds the induction is not affected (verified evidence stays verified)."""
        self.require_manager(actor)
        with self.repo.atomic():
            current = self.repo.get_requirement(str(requirement_id))
            if current is None:
                raise DomainError("NOT_FOUND", "Qualification requirement not found.", 404)
            values = {field: getattr(current, field) for field in self.REQUIREMENT_TEXT_FIELDS}
            values.update(changes)
            updated = replace(current, **self._check_requirement_fields(values, requirement_id=current.id))
            changed = {field: [getattr(current, field), getattr(updated, field)]
                       for field in self.REQUIREMENT_TEXT_FIELDS if getattr(current, field) != getattr(updated, field)}
            if changed:
                self.repo.save_requirement(updated)
                self._audit(actor.id, "REQUIREMENT_UPDATED", "requirement", current.id, changes=changed)
            return updated

    def _check_requirement_fields(self, values, requirement_id):
        """Rules for induction texts: name 1-120 characters and not used by another induction; description up to
        1000; each guidance text up to 2000. Returns the trimmed values."""
        unknown = set(values) - set(self.REQUIREMENT_TEXT_FIELDS)
        if unknown:
            raise DomainError("VALIDATION_ERROR", f"Unknown fields: {', '.join(sorted(unknown))}.")
        cleaned = {field: (values.get(field) or "").strip() for field in self.REQUIREMENT_TEXT_FIELDS}

        def invalid(field, message):
            raise DomainError("VALIDATION_ERROR", message, 400, {field: [message]})

        if not 1 <= len(cleaned["name"]) <= 120:
            invalid("name", "Give a name of up to 120 characters.")
        if len(cleaned["description"]) > 1000:
            invalid("description", "The description can be up to 1000 characters.")
        for field in ("how_to_complete", "accepted_evidence", "reviewer", "contact"):
            if len(cleaned[field]) > 2000:
                invalid(field, "Each guidance text can be up to 2000 characters.")
        if any(item.id != requirement_id and item.name.casefold() == cleaned["name"].casefold()
               for item in self.repo.list_requirements()):
            raise DomainError("REQUIREMENT_NAME_TAKEN", "Another induction already has this name.", 409, {"name": cleaned["name"]})
        return cleaned

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
                # Sprint 3 (2026-10-25): tell the student their evidence arrived; submitting used to be silent.
                requirement = self.repo.get_requirement(requirement_id)
                self._notify(actor.id, "INDUCTION_SUBMITTED", "Induction evidence received",
                             f"Your evidence for {requirement.name} was received and is waiting for review.",
                             link="/induction")
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
            # Sprint 3: tell the person the review result.
            requirement = self.repo.get_requirement(updated.requirement_id)
            name = requirement.name if requirement else "induction"
            if decision == "VERIFIED":
                self._notify(updated.student_id, "QUALIFICATION_VERIFIED", "Induction approved",
                             f"Your {name} evidence was approved.", link="/induction")
            else:
                self._notify(updated.student_id, "QUALIFICATION_REJECTED", "Induction evidence rejected",
                             f"Your {name} evidence was rejected. Reason: {reason.strip()}", link="/induction")
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
