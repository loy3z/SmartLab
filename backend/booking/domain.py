"""Immutable booking records, independent of Django and database selection.

All persisted timestamps are timezone-aware. SSO identities are represented by
the minimum local principal record; this application never stores SSO passwords.
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Any


class Role(str, Enum):
    STUDENT = "STUDENT"
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"


class ResourceKind(str, Enum):
    ROOM = "ROOM"
    EQUIPMENT = "EQUIPMENT"


class QualificationStatus(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


# A submission is the qualification record; no separate grant is required.
SubmissionStatus = QualificationStatus


class BookingStatus(str, Enum):
    WAITING_QUALIFICATION = "WAITING_QUALIFICATION"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


def _require_aware(**timestamps: datetime | None) -> None:
    for name, value in timestamps.items():
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError(f"{name} must be a timezone-aware datetime")


@dataclass(frozen=True)
class Principal:
    id: str
    zid: str
    display_name: str
    role: Role
    active: bool = True

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False


@dataclass(frozen=True)
class QualificationRequirement:
    id: str
    name: str
    description: str


@dataclass(frozen=True)
class Resource:
    id: str
    name: str
    kind: ResourceKind
    location: str
    description: str
    active: bool = True
    required_qualification_id: str | None = None
    slot_minutes: int = 30
    max_booking_minutes: int = 480
    opening_time: time = time(8)
    closing_time: time = time(20)
    timezone: str = "Australia/Sydney"


@dataclass(frozen=True)
class QualificationSubmission:
    id: str
    student_id: str
    requirement_id: str
    title: str
    notes: str
    file_id: str
    submitted_at: datetime
    status: QualificationStatus = QualificationStatus.PENDING
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    valid_until: datetime | None = None

    def __post_init__(self) -> None:
        _require_aware(
            submitted_at=self.submitted_at,
            reviewed_at=self.reviewed_at,
            valid_until=self.valid_until,
        )


@dataclass(frozen=True)
class Booking:
    id: str
    student_id: str
    resource_id: str
    start: datetime
    end: datetime
    purpose: str
    created_at: datetime
    status: BookingStatus
    reason_code: str | None
    review_due_at: datetime | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    decision_reason: str | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_aware(
            start=self.start,
            end=self.end,
            created_at=self.created_at,
            review_due_at=self.review_due_at,
            reviewed_at=self.reviewed_at,
            updated_at=self.updated_at,
        )


@dataclass(frozen=True)
class AuditRecord:
    id: str
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    at: datetime
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_aware(at=self.at)
