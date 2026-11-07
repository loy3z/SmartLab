"""Database port and single-process demonstration implementation.

A production adapter must acquire locks for the supplied student/resource IDs
inside ``atomic``, and commit all booking, eligibility and audit changes in the
same transaction. Submission and approval must use that same locking path;
querying availability then independently saving cannot prevent double bookings.
The memory implementation is neither durable nor safe across multiple workers.
"""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from threading import RLock
from typing import ContextManager, Iterator, Protocol, Sequence

from .domain import (
    SiteContact,  # Sprint 3 (1.16.0)
    ResourceInternalInfo,  # 2026-11-07
    Announcement,  # Sprint 3 (1.19.0)
    NotificationPreference,  # Sprint 3 (2026-10-25)
    AuditRecord,
    Booking,
    BookingSeries,
    BookingStatus,
    CalendarFeed,
    EmailDelivery,
    Notification,
    Principal,
    OutlookSyncRecord,
    QualificationRequirement,
    QualificationStatus,
    QualificationSubmission,
    Resource,
    StaffCredential,
)


def booking_matches(booking: Booking, *, statuses: Sequence[BookingStatus] | None = None,
                    start_from: datetime | None = None, start_to: datetime | None = None,
                    end_from: datetime | None = None, due_by: datetime | None = None,
                    created_by: str | None = None, unmarked: bool = False,
                    extension_end_after: datetime | None = None) -> bool:
    """The list_bookings keyword filters (2026-10-29, load test R1); PostgresRepository applies the same ones in SQL.

    Every bound is inclusive, so a filter only narrows what is read: callers still apply their own exact checks.
    due_by keeps bookings whose start or review deadline is at or before it (time processing);
    unmarked keeps bookings with no attendance recorded.
    extension_end_after (Sprint 3) keeps requests whose proposed end has not yet passed (exclusive).
    """
    return ((statuses is None or booking.status in statuses)
            and (start_from is None or booking.start >= start_from)
            and (start_to is None or booking.start <= start_to)
            and (end_from is None or booking.end >= end_from)
            and (due_by is None or booking.start <= due_by
                 or (booking.review_due_at is not None and booking.review_due_at <= due_by))
            and (created_by is None or booking.created_by == created_by)
            and (not unmarked or booking.attendance is None)
            and (extension_end_after is None
                 or (booking.extension_end is not None and booking.extension_end > extension_end_after)))


def submission_matches(submission: QualificationSubmission, *, student_ids: Sequence[str] | None = None,
                       statuses: Sequence[QualificationStatus] | None = None,
                       valid_from: datetime | None = None, valid_to: datetime | None = None) -> bool:
    """The list_submissions keyword filters (2026-10-29, load test S8); PostgresRepository applies them in SQL.
    valid_from / valid_to bound valid_until (inclusive) and skip submissions without one."""
    return ((student_ids is None or submission.student_id in student_ids)
            and (statuses is None or submission.status in statuses)
            and (valid_from is None or (submission.valid_until is not None and submission.valid_until >= valid_from))
            and (valid_to is None or (submission.valid_until is not None and submission.valid_until <= valid_to)))


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
    # 2026-10-29 (load test S8): keyword filters as for list_bookings (inclusive bounds; see submission_matches).
    def list_submissions(
        self,
        student_id: str | None = None,
        requirement_id: str | None = None,
        *,
        student_ids: Sequence[str] | None = None,
        statuses: Sequence[QualificationStatus] | None = None,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
    ) -> list[QualificationSubmission]: ...
    def save_submission(self, submission: QualificationSubmission) -> None: ...
    def get_booking(self, booking_id: str) -> Booking | None: ...
    # 2026-10-29 (load test R1): the keyword filters let callers read only the rows they may need instead of every
    # booking ever made. Time bounds are inclusive; callers keep their exact checks (see booking_matches above).
    def list_bookings(
        self,
        student_id: str | None = None,
        resource_id: str | None = None,
        *,
        statuses: Sequence[BookingStatus] | None = None,
        start_from: datetime | None = None,
        start_to: datetime | None = None,
        end_from: datetime | None = None,
        due_by: datetime | None = None,
        created_by: str | None = None,
        unmarked: bool = False,
        extension_end_after: datetime | None = None,
    ) -> list[Booking]: ...
    def save_booking(self, booking: Booking) -> None: ...
    # Sprint 3 (1.20.0): per-person visibility, separate from the shared booking.
    def hidden_booking_ids(self, principal_id: str) -> set[str]: ...
    def hide_booking(self, principal_id: str, booking_id: str, at: datetime) -> None: ...
    def list_blocking_bookings(
        self, resource_id: str, start: datetime, end: datetime, at: datetime,
        exclude_id: str | None = None,
    ) -> list[Booking]: ...
    def append_audit(self, record: AuditRecord) -> None: ...
    def list_audit(self) -> list[AuditRecord]: ...
    def get_outlook_sync(self, booking_id: str) -> OutlookSyncRecord | None: ...
    def list_outlook_sync(self) -> list[OutlookSyncRecord]: ...
    def save_outlook_sync(self, record: OutlookSyncRecord) -> None: ...
    def get_credential(self, principal_id: str) -> StaffCredential | None: ...
    def save_credential(self, credential: StaffCredential) -> None: ...
    # Sprint 3: notifications (newest first).
    def save_notification(self, notification: Notification) -> None: ...
    def get_notification(self, notification_id: str) -> Notification | None: ...
    def list_notifications(self, recipient_id: str) -> list[Notification]: ...
    # 2026-10-29 (load test S1): notifications of one kind about any of these bookings, for reminder de-duplication.
    def list_booking_notifications(self, kind: str, booking_ids: Sequence[str]) -> list[Notification]: ...
    # 2026-10-29 (load test S8): notifications of one kind to any of these people (induction reminder de-duplication).
    def list_kind_notifications(self, kind: str, recipient_ids: Sequence[str]) -> list[Notification]: ...
    def save_email_delivery(self, delivery: EmailDelivery) -> None: ...
    def get_email_delivery(self, notification_id: str) -> EmailDelivery | None: ...
    def list_email_deliveries(self) -> list[EmailDelivery]: ...
    def claim_email_deliveries(
        self, now: datetime, limit: int, worker_id: str, lease_until: datetime,
    ) -> list[EmailDelivery]: ...
    # Sprint 3 (2026-10-25): per-person notification category choices (a missing row means enabled).
    # Sprint 3 (1.19.0): announcement storage port.
    def save_announcement(self, announcement: Announcement) -> None: ...
    def get_announcement(self, announcement_id: str) -> Announcement | None: ...
    def list_announcements(self) -> list[Announcement]: ...
    def save_notification_preference(self, preference: NotificationPreference) -> None: ...
    def list_notification_preferences(self, principal_id: str) -> list[NotificationPreference]: ...
    # Calendar subscription addresses (one per person).
    def get_calendar_feed(self, principal_id: str) -> CalendarFeed | None: ...
    def get_calendar_feed_by_token(self, token: str) -> CalendarFeed | None: ...
    def save_calendar_feed(self, feed: CalendarFeed) -> None: ...
    # Weekly series made by staff; the occurrences are ordinary bookings with series_id.
    def save_series(self, series: BookingSeries) -> None: ...
    def get_series(self, series_id: str) -> BookingSeries | None: ...
    # Sprint 3 (1.16.0): the lab's contact details (one record; None until a Manager saves it).
    def get_site_contact(self) -> SiteContact | None: ...
    def save_site_contact(self, contact: SiteContact) -> None: ...
    # 2026-11-07: Manager-only internal information, one record per resource.
    def get_resource_internal_info(self, resource_id: str) -> ResourceInternalInfo | None: ...
    def save_resource_internal_info(self, info: ResourceInternalInfo) -> None: ...


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
        self._hidden_bookings: dict[tuple[str, str], datetime] = {}  # Sprint 3 (1.20.0)
        self._audit: list[AuditRecord] = []
        self._outlook_sync: dict[str, OutlookSyncRecord] = {}
        self._credentials: dict[str, StaffCredential] = {}
        self._notifications: dict[str, Notification] = {}
        self._email_deliveries: dict[str, EmailDelivery] = {}
        self._notification_preferences: dict[str, NotificationPreference] = {}
        self._announcements: dict[str, Announcement] = {}  # Sprint 3 (1.19.0)
        self._calendar_feeds: dict[str, CalendarFeed] = {}
        self._series: dict[str, BookingSeries] = {}
        self._site_contact: SiteContact | None = None  # Sprint 3 (1.16.0)
        self._resource_internal: dict[str, ResourceInternalInfo] = {}  # 2026-11-07

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
                self._hidden_bookings.copy(),  # Sprint 3 (1.20.0): include visibility in rollback.
                deepcopy(self._audit),
                self._outlook_sync.copy(),
                self._credentials.copy(),
                self._notifications.copy(),
                self._email_deliveries.copy(),
                self._calendar_feeds.copy(),
                self._series.copy(),
                self._site_contact,  # Sprint 3 (1.16.0)
                self._resource_internal.copy(),  # 2026-11-07
                self._notification_preferences.copy(), self._announcements.copy(),  # Sprint 3 (1.19.0)
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
                    self._hidden_bookings,
                    self._audit,
                    self._outlook_sync,
                    self._credentials,
                    self._notifications,
                    self._email_deliveries,
                    self._calendar_feeds,
                    self._series,
                    self._site_contact,
                    self._resource_internal,
                    self._notification_preferences, self._announcements,  # Sprint 3 (1.19.0)
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
        **filters,
    ) -> list[QualificationSubmission]:
        with self._lock:
            return [
                submission
                for submission in self._submissions.values()
                if (student_id is None or submission.student_id == student_id)
                and (requirement_id is None or submission.requirement_id == requirement_id)
                and submission_matches(submission, **filters)
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
        **filters,
    ) -> list[Booking]:
        with self._lock:
            return [
                booking
                for booking in self._bookings.values()
                if (student_id is None or booking.student_id == student_id)
                and (resource_id is None or booking.resource_id == resource_id)
                and booking_matches(booking, **filters)
            ]

    def save_booking(self, booking: Booking) -> None:
        with self._lock:
            self._bookings[booking.id] = booking

    # Sprint 3 (1.20.0): never remove the shared booking or change its status.
    def hidden_booking_ids(self, principal_id: str) -> set[str]:
        with self._lock:
            return {booking_id for person_id, booking_id in self._hidden_bookings if person_id == principal_id}

    def hide_booking(self, principal_id: str, booking_id: str, at: datetime) -> None:
        with self._lock:
            self._hidden_bookings.setdefault((principal_id, booking_id), at)

    def list_blocking_bookings(self, resource_id, start, end, at, exclude_id=None):
        """Use server time, strict overlap and active pending holds, not status alone."""
        with self._lock:
            return [item for item in self._bookings.values()
                    if item.resource_id == resource_id and item.id != exclude_id
                    and start < item.end and item.start < end and item.blocks_resource_at(at)]

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
            self._credentials.clear()
            self._notifications.clear()
            self._email_deliveries.clear()
            self._calendar_feeds.clear()
            self._series.clear()
            self._resource_internal.clear()

    def get_outlook_sync(self, booking_id: str) -> OutlookSyncRecord | None:
        with self._lock:
            return self._outlook_sync.get(booking_id)

    def list_outlook_sync(self) -> list[OutlookSyncRecord]:
        with self._lock:
            return list(self._outlook_sync.values())

    def save_outlook_sync(self, record: OutlookSyncRecord) -> None:
        with self._lock:
            self._outlook_sync[record.booking_id] = record

    def get_credential(self, principal_id: str) -> StaffCredential | None:
        with self._lock:
            return self._credentials.get(principal_id)

    def save_credential(self, credential: StaffCredential) -> None:
        with self._lock:
            self._credentials[credential.principal_id] = credential

    # Sprint 3 records -------------------------------------------------------------------------------------

    def save_notification(self, notification: Notification) -> None:
        with self._lock:
            self._notifications[notification.id] = notification

    def get_notification(self, notification_id: str) -> Notification | None:
        with self._lock:
            return self._notifications.get(notification_id)

    def list_notifications(self, recipient_id: str) -> list[Notification]:
        with self._lock:
            return sorted((item for item in self._notifications.values() if item.recipient_id == recipient_id),
                          key=lambda item: (item.created_at, item.id), reverse=True)

    def list_booking_notifications(self, kind: str, booking_ids: Sequence[str]) -> list[Notification]:
        wanted = set(booking_ids)
        with self._lock:
            return sorted((item for item in self._notifications.values()
                           if item.kind == kind and item.booking_id in wanted),
                          key=lambda item: (item.created_at, item.id), reverse=True)

    def list_kind_notifications(self, kind: str, recipient_ids: Sequence[str]) -> list[Notification]:
        wanted = set(recipient_ids)
        with self._lock:
            return sorted((item for item in self._notifications.values()
                           if item.kind == kind and item.recipient_id in wanted),
                          key=lambda item: (item.created_at, item.id), reverse=True)

    def save_email_delivery(self, delivery: EmailDelivery) -> None:
        with self._lock:
            self._email_deliveries[delivery.notification_id] = delivery

    def get_email_delivery(self, notification_id: str) -> EmailDelivery | None:
        with self._lock:
            return self._email_deliveries.get(notification_id)

    def list_email_deliveries(self) -> list[EmailDelivery]:
        with self._lock:
            return sorted(self._email_deliveries.values(),
                          key=lambda item: (item.created_at, item.notification_id))

    def claim_email_deliveries(self, now, limit, worker_id, lease_until):
        """Atomically lease due work; the memory adapter mirrors PostgreSQL worker semantics."""
        with self._lock:
            due = [item for item in self._email_deliveries.values()
                   if ((item.status in ("PENDING", "RETRY")
                        and (item.next_attempt_at is None or item.next_attempt_at <= now))
                       or (item.status == "IN_PROGRESS"
                           and (item.lease_until is None or item.lease_until <= now)))]
            due.sort(key=lambda item: (item.next_attempt_at or item.created_at,
                                       item.created_at, item.notification_id))
            claimed = []
            for item in due[:limit]:
                item = replace(item, status="IN_PROGRESS", attempts=item.attempts + 1,
                               updated_at=now, lease_until=lease_until, worker_id=worker_id)
                self._email_deliveries[item.notification_id] = item
                claimed.append(item)
            return claimed

    # Sprint 3 (2026-10-25): notification category choices.
    def save_notification_preference(self, preference: NotificationPreference) -> None:
        with self._lock:
            self._notification_preferences[preference.id] = preference

    def list_notification_preferences(self, principal_id: str) -> list[NotificationPreference]:
        with self._lock:
            return sorted((item for item in self._notification_preferences.values()
                           if item.principal_id == principal_id), key=lambda item: item.category)

    def get_calendar_feed(self, principal_id: str) -> CalendarFeed | None:
        with self._lock:
            return self._calendar_feeds.get(principal_id)

    def get_calendar_feed_by_token(self, token: str) -> CalendarFeed | None:
        with self._lock:
            return next((item for item in self._calendar_feeds.values() if item.token == token), None)

    def save_calendar_feed(self, feed: CalendarFeed) -> None:
        with self._lock:
            self._calendar_feeds[feed.principal_id] = feed

    def save_series(self, series: BookingSeries) -> None:
        with self._lock:
            self._series[series.id] = series

    def get_series(self, series_id: str) -> BookingSeries | None:
        with self._lock:
            return self._series.get(series_id)

    # Sprint 3 (1.16.0)
    def get_site_contact(self) -> SiteContact | None:
        with self._lock:
            return self._site_contact

    def save_site_contact(self, contact: SiteContact) -> None:
        with self._lock:
            self._site_contact = contact

    def get_resource_internal_info(self, resource_id: str) -> ResourceInternalInfo | None:
        with self._lock:
            return self._resource_internal.get(resource_id)

    def save_resource_internal_info(self, info: ResourceInternalInfo) -> None:
        with self._lock:
            self._resource_internal[info.resource_id] = info

    # Sprint 3 (1.19.0): records participate in the same rollback snapshot as resource status.
    def save_announcement(self, announcement: Announcement) -> None:
        with self._lock:
            self._announcements[announcement.id] = announcement

    def get_announcement(self, announcement_id: str) -> Announcement | None:
        with self._lock:
            return self._announcements.get(announcement_id)

    def list_announcements(self) -> list[Announcement]:
        with self._lock:
            return sorted(self._announcements.values(), key=lambda item: (item.created_at, item.id), reverse=True)
