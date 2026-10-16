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


class ResourceStatus(str, Enum):
    """Operational state set by a Manager. Only AVAILABLE accepts new requests; existing bookings are kept."""
    AVAILABLE = "AVAILABLE"
    MAINTENANCE = "MAINTENANCE"
    CLOSED = "CLOSED"


class QualificationStatus(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


# A submission is the qualification record; no separate grant is required.
SubmissionStatus = QualificationStatus


class BookingStatus(str, Enum):
    WAITING_QUALIFICATION = "WAITING_QUALIFICATION"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    # Queued behind an approved booking or an earlier pending request; never blocks a slot.
    WAITLISTED = "WAITLISTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


# Upper bound for a resource's review window (two weeks). The default window is 24 hours.
MAX_PENDING_HOLD_MINUTES = 20160


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
    university_email: str
    active: bool = True

    def __post_init__(self) -> None:
        if not self.university_email or "@" not in self.university_email or any(char.isspace() for char in self.university_email):
            raise ValueError("A university email address is required for each principal.")

    @property
    def is_staff(self) -> bool:
        """Admins and Managers are university staff. Staff review and manage; they do not book."""
        return self.role in (Role.ADMIN, Role.MANAGER)

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False


@dataclass(frozen=True)
class StaffCredential:
    """How an Admin or Manager signs in on the staff page (students use university sign-in instead).

    Kept apart from Principal so a password hash can never appear in a user response. A Manager creates
    the staff account with an invite code; the staff member activates it by choosing a password, which
    clears the code. Resetting access clears the password and issues a new code.
    """
    principal_id: str
    password_hash: str | None = None  # Django password hash; None until the account is activated
    invite_code: str | None = None    # one-time code handed over by a Manager; None once activated
    updated_at: datetime | None = None

    @property
    def activated(self) -> bool:
        return self.password_hash is not None


@dataclass(frozen=True)
class QualificationRequirement:
    id: str
    name: str
    description: str
    # Requirements that must be verified and current first (e.g. Advanced needs General). Stored data,
    # not code: change it with BookingService.set_prerequisites or in the database.
    prerequisite_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "prerequisite_ids", tuple(str(item) for item in self.prerequisite_ids))
        if self.id in self.prerequisite_ids:
            raise ValueError("A requirement cannot be its own prerequisite.")


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
    # Review window: a pending request holds its slot this long while an Admin decides; then the system decides.
    pending_hold_minutes: int = 1440
    status: ResourceStatus = ResourceStatus.AVAILABLE
    status_reason: str | None = None
    # Equipment: the room it is kept in. Rooms: None. Display and grouping only; a room being closed
    # does not stop its equipment being borrowed.
    room_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ResourceKind):
            object.__setattr__(self, "kind", ResourceKind(self.kind))
        if self.kind == ResourceKind.ROOM and self.room_id is not None:
            raise ValueError("A room cannot belong to another room.")
        if isinstance(self.pending_hold_minutes, bool) or not isinstance(self.pending_hold_minutes, int) \
                or not 1 <= self.pending_hold_minutes <= MAX_PENDING_HOLD_MINUTES:
            raise ValueError(f"pending_hold_minutes must be an integer from 1 to {MAX_PENDING_HOLD_MINUTES}.")
        if not isinstance(self.status, ResourceStatus):
            object.__setattr__(self, "status", ResourceStatus(self.status))

    @property
    def bookable(self) -> bool:
        """Accepts new requests and approvals: listed (active) and not under maintenance or closed."""
        return self.active and self.status == ResourceStatus.AVAILABLE


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
    revision: int = 1
    hold_until: datetime | None = None

    def __post_init__(self) -> None:
        _require_aware(
            start=self.start,
            end=self.end,
            created_at=self.created_at,
            review_due_at=self.review_due_at,
            reviewed_at=self.reviewed_at,
            updated_at=self.updated_at,
            hold_until=self.hold_until,
        )

    def hold_is_active(self, at: datetime) -> bool:
        _require_aware(at=at)
        return bool(self.status in (BookingStatus.WAITING_QUALIFICATION, BookingStatus.PENDING_APPROVAL)
                    and self.hold_until and self.hold_until > at)

    def blocks_resource_at(self, at: datetime) -> bool:
        return self.status == BookingStatus.APPROVED or self.hold_is_active(at)


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


@dataclass(frozen=True)
class OutlookSyncRecord:
    """Outbox entry and external event mapping; never contains credentials."""

    booking_id: str
    action: str
    status: str
    calendar_path: str
    updated_at: datetime
    revision: int = 1
    booking_revision: int = 1
    event_id: str | None = None
    web_link: str | None = None
    ical_uid: str | None = None
    attempts: int = 0
    create_attempted: bool = False
    next_attempt_at: datetime | None = None
    lease_until: datetime | None = None
    last_error: str | None = None
    last_success_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_aware(updated_at=self.updated_at, next_attempt_at=self.next_attempt_at,
                       lease_until=self.lease_until, last_success_at=self.last_success_at)
