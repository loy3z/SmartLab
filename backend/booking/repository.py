"""Database port and single-process demonstration implementation.

A production adapter must acquire locks for the supplied student/resource IDs
inside ``atomic``, and commit all booking, eligibility and audit changes in the
same transaction. Submission and approval must use that same locking path;
querying availability then independently saving cannot prevent double bookings.
The memory implementation is neither durable nor safe across multiple workers.
"""

from contextlib import contextmanager
from copy import deepcopy
from threading import RLock
from typing import ContextManager, Iterator, Protocol, Sequence

from .domain import (
    AuditRecord,
    Booking,
    Principal,
    OutlookSyncRecord,
    QualificationRequirement,
    QualificationSubmission,
    Resource,
)


class Repository(Protocol):
    def atomic(
        self,
        resource_ids: Sequence[str] = (),
        student_ids: Sequence[str] = (),
    ) -> ContextManager[None]: ...

    def get_resource(self, resource_id: str) -> Resource | None: ...
    def list_resources(self) -> list[Resource]: ...
    def save_resource(self, resource: Resource) -> None: ...
    def get_principal(self, principal_id: str) -> Principal | None: ...
    def list_principals(self) -> list[Principal]: ...
    def save_principal(self, principal: Principal) -> None: ...
    def get_requirement(self, requirement_id: str) -> QualificationRequirement | None: ...
    def list_requirements(self) -> list[QualificationRequirement]: ...
    def save_requirement(self, requirement: QualificationRequirement) -> None: ...
    def get_submission(self, submission_id: str) -> QualificationSubmission | None: ...
    def list_submissions(
        self,
        student_id: str | None = None,
        requirement_id: str | None = None,
    ) -> list[QualificationSubmission]: ...
    def save_submission(self, submission: QualificationSubmission) -> None: ...
    def get_booking(self, booking_id: str) -> Booking | None: ...
    def list_bookings(
        self,
        student_id: str | None = None,
        resource_id: str | None = None,
    ) -> list[Booking]: ...
    def save_booking(self, booking: Booking) -> None: ...
    def append_audit(self, record: AuditRecord) -> None: ...
    def list_audit(self) -> list[AuditRecord]: ...
    def get_outlook_sync(self, booking_id: str) -> OutlookSyncRecord | None: ...
    def list_outlook_sync(self) -> list[OutlookSyncRecord]: ...
    def save_outlook_sync(self, record: OutlookSyncRecord) -> None: ...


class MemoryRepository:
    """Thread-safe demo repository with rollback on failed atomic blocks.

    A single reentrant lock serialises transactions and reads/writes. The ID
    arguments are retained for adapters that use finer-grained database locks.
    Each process has its own records, so use only one demo server worker.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._resources: dict[str, Resource] = {}
        self._principals: dict[str, Principal] = {}
        self._requirements: dict[str, QualificationRequirement] = {}
        self._submissions: dict[str, QualificationSubmission] = {}
        self._bookings: dict[str, Booking] = {}
        self._audit: list[AuditRecord] = []
        self._outlook_sync: dict[str, OutlookSyncRecord] = {}

    @contextmanager
    def atomic(
        self,
        resource_ids: Sequence[str] = (),
        student_ids: Sequence[str] = (),
    ) -> Iterator[None]:
        with self._lock:
            snapshot = (
                self._resources.copy(),
                self._principals.copy(),
                self._requirements.copy(),
                self._submissions.copy(),
                self._bookings.copy(),
                deepcopy(self._audit),
                self._outlook_sync.copy(),
            )
            try:
                yield
            except BaseException:
                (
                    self._resources,
                    self._principals,
                    self._requirements,
                    self._submissions,
                    self._bookings,
                    self._audit,
                    self._outlook_sync,
                ) = snapshot
                raise

    def get_resource(self, resource_id: str) -> Resource | None:
        with self._lock:
            return self._resources.get(resource_id)

    def list_resources(self) -> list[Resource]:
        with self._lock:
            return list(self._resources.values())

    def save_resource(self, resource: Resource) -> None:
        with self._lock:
            self._resources[resource.id] = resource

    def get_principal(self, principal_id: str) -> Principal | None:
        with self._lock:
            return self._principals.get(principal_id)

    def list_principals(self) -> list[Principal]:
        with self._lock:
            return list(self._principals.values())

    def save_principal(self, principal: Principal) -> None:
        with self._lock:
            self._principals[principal.id] = principal

    def get_requirement(self, requirement_id: str) -> QualificationRequirement | None:
        with self._lock:
            return self._requirements.get(requirement_id)

    def list_requirements(self) -> list[QualificationRequirement]:
        with self._lock:
            return list(self._requirements.values())

    def save_requirement(self, requirement: QualificationRequirement) -> None:
        with self._lock:
            self._requirements[requirement.id] = requirement

    def get_submission(self, submission_id: str) -> QualificationSubmission | None:
        with self._lock:
            return self._submissions.get(submission_id)

    def list_submissions(
        self,
        student_id: str | None = None,
        requirement_id: str | None = None,
    ) -> list[QualificationSubmission]:
        with self._lock:
            return [
                submission
                for submission in self._submissions.values()
                if (student_id is None or submission.student_id == student_id)
                and (requirement_id is None or submission.requirement_id == requirement_id)
            ]

    def save_submission(self, submission: QualificationSubmission) -> None:
        with self._lock:
            self._submissions[submission.id] = submission

    def get_booking(self, booking_id: str) -> Booking | None:
        with self._lock:
            return self._bookings.get(booking_id)

    def list_bookings(
        self,
        student_id: str | None = None,
        resource_id: str | None = None,
    ) -> list[Booking]:
        with self._lock:
            return [
                booking
                for booking in self._bookings.values()
                if (student_id is None or booking.student_id == student_id)
                and (resource_id is None or booking.resource_id == resource_id)
            ]

    def save_booking(self, booking: Booking) -> None:
        with self._lock:
            self._bookings[booking.id] = booking

    def append_audit(self, record: AuditRecord) -> None:
        with self._lock:
            # Frozen dataclasses do not recursively freeze dicts. Copy both at
            # the write and read boundary to keep caller edits out of storage.
            self._audit.append(deepcopy(record))

    def list_audit(self) -> list[AuditRecord]:
        with self._lock:
            return deepcopy(self._audit)

    def clear(self) -> None:
        """Reset demo/test state; not part of the production Repository port."""
        with self._lock:
            self._resources.clear()
            self._principals.clear()
            self._requirements.clear()
            self._submissions.clear()
            self._bookings.clear()
            self._audit.clear()
            self._outlook_sync.clear()

    def get_outlook_sync(self, booking_id: str) -> OutlookSyncRecord | None:
        with self._lock:
            return self._outlook_sync.get(booking_id)

    def list_outlook_sync(self) -> list[OutlookSyncRecord]:
        with self._lock:
            return list(self._outlook_sync.values())

    def save_outlook_sync(self, record: OutlookSyncRecord) -> None:
        with self._lock:
            self._outlook_sync[record.booking_id] = record
