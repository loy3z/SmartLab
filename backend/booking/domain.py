"""Immutable booking records, independent of Django and database selection.

All persisted timestamps are timezone-aware. SSO identities are represented by
the minimum local principal record; this application never stores SSO passwords.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time
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


# Sprint 3: attendance of an approved booking (check-in).
ATTENDANCE_VALUES = ("CHECKED_IN", "NO_SHOW", "EXCUSED", "NOT_TRACKED")

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
    # Sprint 3: missed check-ins since the last freeze. Reaching the rules' limit freezes booking for a while.
    no_show_count: int = 0
    # While in the future, this person cannot be booked for (their reviewing rights are unaffected).
    frozen_until: datetime | None = None

    def __post_init__(self) -> None:
        _require_aware(frozen_until=self.frozen_until)
        if not self.university_email or "@" not in self.university_email or any(char.isspace() for char in self.university_email):
            raise ValueError("A university email address is required for each principal.")

    @property
    def is_staff(self) -> bool:
        """Admins and Managers are university staff: they review and manage, and may also book."""
        return self.role in (Role.ADMIN, Role.MANAGER)

    def frozen_at(self, at: datetime) -> bool:
        return bool(self.frozen_until and self.frozen_until > at)

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
    # Sprint 3 (1.16.0): guidance a Manager writes for people who do not have this induction yet (shown on the
    # Induction & Training page). Free text; empty means "not written yet".
    how_to_complete: str = ""      # where and how to do the training
    accepted_evidence: str = ""    # what proof to upload
    reviewer: str = ""             # who checks the evidence
    contact: str = ""              # who to ask

    def __post_init__(self) -> None:
        object.__setattr__(self, "prerequisite_ids", tuple(str(item) for item in self.prerequisite_ids))
        if self.id in self.prerequisite_ids:
            raise ValueError("A requirement cannot be its own prerequisite.")


@dataclass(frozen=True)
class ResourceDetail:
    """Sprint 3 (1.16.0): one "label: value" line on a resource, e.g. ("Model", "Rigol DS1054Z")."""
    label: str
    value: str


@dataclass(frozen=True)
class SiteContact:
    """Sprint 3 (1.16.0): how to reach the lab. One record (id SITE_CONTACT_ID), edited by a Manager and shown on the
    Help page, My Bookings and the Induction & Training page. Empty fields are not shown."""
    id: str
    email: str = ""
    phone: str = ""
    hours: str = ""
    note: str = ""
    updated_at: datetime | None = None
    updated_by: str | None = None


SITE_CONTACT_ID = "00000000-0000-0000-0000-000000000c01"


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
    # Equipment type used to filter the booking page (e.g. "Microscopy", "Fabrication"). Rooms: None.
    category: str | None = None
    # Sprint 3 (1.16.0): rooms: how many people fit (None = not given; equipment always None). Any resource: extra
    # "label: value" lines the Manager chooses (e.g. Model: Rigol DS1054Z, Floor: Level 3), so the lab decides what
    # information people need without code changes.
    capacity: int | None = None
    details: tuple["ResourceDetail", ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ResourceKind):
            object.__setattr__(self, "kind", ResourceKind(self.kind))
        # Sprint 3 (1.16.0): details may arrive as dicts (JSON from the database); store them as ResourceDetail.
        object.__setattr__(self, "details", tuple(item if isinstance(item, ResourceDetail) else ResourceDetail(**item)
                                                  for item in self.details))
        if self.kind == ResourceKind.EQUIPMENT and self.capacity is not None:
            raise ValueError("Only rooms have a capacity.")
        if self.kind == ResourceKind.ROOM and self.room_id is not None:
            raise ValueError("A room cannot belong to another room.")
        if self.category is not None and (not isinstance(self.category, str) or not 1 <= len(self.category.strip()) <= 60):
            raise ValueError("category must be 1-60 characters, or empty.")
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
    # Who created the request. ``student_id`` is the person the booking is for (the beneficiary); an Admin
    # or Manager may create one on behalf of someone else. None on records made before this field existed.
    created_by: str | None = None
    # Urgent request: starts sooner than the normal booking window allows, so only a Manager may approve it
    # (never automatic). Induction and conflict rules still apply.
    urgent: bool = False
    urgent_reason: str | None = None
    # Sprint 3: weekly series created by staff (see BookingSeries); None for single bookings.
    series_id: str | None = None
    # Sprint 3: attendance of an approved booking: CHECKED_IN (the person confirmed they were there), NO_SHOW (not confirmed
    # in time), EXCUSED (the resource was unavailable) or NOT_TRACKED (started before check-in existed).
    attendance: str | None = None
    checked_in_at: datetime | None = None
    # Sprint 3 (1.16.0): change request. This request asks to move the approved booking ``replaces_id`` (same person,
    # same resource) to a new time. The old booking stays until this one is approved, then it is cancelled
    # automatically (services/changes.py). None for ordinary requests.
    replaces_id: str | None = None

    def __post_init__(self) -> None:
        if self.attendance is not None and self.attendance not in ATTENDANCE_VALUES:
            raise ValueError("attendance must be CHECKED_IN, NO_SHOW, EXCUSED or NOT_TRACKED.")
        _require_aware(
            checked_in_at=self.checked_in_at,
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


# Sprint 3 records ----------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class BookingSeries:
    """A weekly series created by staff. Each occurrence is an ordinary Booking with this series_id."""
    id: str
    student_id: str        # the person the bookings are for
    created_by: str
    resource_id: str
    weekdays: str          # ISO weekdays, comma separated: "1,3" is Monday and Wednesday
    start_time: time       # local time of the resource
    duration_minutes: int
    first_date: date
    last_date: date
    purpose: str
    created_at: datetime

    def __post_init__(self) -> None:
        _require_aware(created_at=self.created_at)

    @property
    def weekday_numbers(self) -> tuple[int, ...]:
        return tuple(int(item) for item in self.weekdays.split(",") if item)


@dataclass(frozen=True)
class Notification:
    """One message for one person. Shown on the website; delivery channels (e.g. Outlook mail) can send it too."""
    id: str
    recipient_id: str
    kind: str
    title: str
    body: str
    created_at: datetime
    link: str | None = None          # page in the web app, e.g. "/bookings?booking=<id>"
    booking_id: str | None = None
    read_at: datetime | None = None
    # Sprint 3 (1.19.0): channel choices are captured when the notification is created.
    in_app: bool = True
    email: bool = True

    def __post_init__(self) -> None:
        _require_aware(created_at=self.created_at, read_at=self.read_at)


@dataclass(frozen=True)
class NotificationPreference:
    """Sprint 3 (2026-10-25): one person's choice for one notification category.

    A missing row means the category is on, so new accounts keep every notification by default.
    """
    id: str            # stable UUID built from (principal_id, category)
    principal_id: str
    category: str      # bookings | reminders | induction | account | resources
    enabled: bool
    email_enabled: bool = True  # Sprint 3 (1.19.0): independent email preference.


@dataclass(frozen=True)
class CalendarFeed:
    """Secret calendar subscription address of one person (the token is the only key to the feed)."""
    principal_id: str
    token: str
    created_at: datetime

    def __post_init__(self) -> None:
        _require_aware(created_at=self.created_at)


class UnfreezeStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class UnfreezeRequest:
    id: str
    principal_id: str
    reason: str
    created_at: datetime
    status: UnfreezeStatus = UnfreezeStatus.PENDING
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, UnfreezeStatus):
            object.__setattr__(self, "status", UnfreezeStatus(self.status))
        _require_aware(created_at=self.created_at, decided_at=self.decided_at)


# Sprint 3 (1.19.0): explicit author role preserves the signature of signed test sessions too.
@dataclass(frozen=True)
class Announcement:
    id: str
    title: str
    body: str
    kind: str
    resource_id: str | None
    created_by: str
    created_at: datetime
    expires_at: datetime | None = None
    removed_at: datetime | None = None
    removed_by: str | None = None
    updated_at: datetime | None = None
    author_role: str = "ADMIN"
    expected_back: datetime | None = None

    def __post_init__(self):
        _require_aware(created_at=self.created_at, expires_at=self.expires_at, removed_at=self.removed_at,
                       updated_at=self.updated_at, expected_back=self.expected_back)
