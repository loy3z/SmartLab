"""Database port and single-process demonstration implementation.

A production adapter must acquire locks for the supplied student/resource IDs
inside ``atomic``, and commit all booking, eligibility and audit changes in the
same transaction. Submission and approval must use that same locking path;
querying availability then independently saving cannot prevent double bookings.
The memory implementation is neither durable nor safe across multiple workers.
"""

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from threading import RLock
from typing import ContextManager, Iterator, Protocol, Sequence

from .domain import (
    SiteContact,  # Sprint 3 (1.16.0)
    NotificationPreference,  # Sprint 3 (2026-10-25)
    AuditRecord,
    Booking,
    BookingSeries,
    CalendarFeed,
    Notification,
    Principal,
    UnfreezeRequest,
    OutlookSyncRecord,
    QualificationRequirement,
    QualificationSubmission,
    Resource,
    StaffCredential,
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
    # Sprint 3 (2026-10-25): per-person notification category choices (a missing row means enabled).
    def save_notification_preference(self, preference: NotificationPreference) -> None: ...
    def list_notification_preferences(self, principal_id: str) -> list[NotificationPreference]: ...
    # Calendar subscription addresses (one per person).
    def get_calendar_feed(self, principal_id: str) -> CalendarFeed | None: ...
    def get_calendar_feed_by_token(self, token: str) -> CalendarFeed | None: ...
    def save_calendar_feed(self, feed: CalendarFeed) -> None: ...
    # Requests to lift a booking freeze.
    def save_unfreeze_request(self, request: UnfreezeRequest) -> None: ...
    def get_unfreeze_request(self, request_id: str) -> UnfreezeRequest | None: ...
    def list_unfreeze_requests(self, principal_id: str | None = None) -> list[UnfreezeRequest]: ...
    # Weekly series made by staff; the occurrences are ordinary bookings with series_id.
    def save_series(self, series: BookingSeries) -> None: ...
    def get_series(self, series_id: str) -> BookingSeries | None: ...
    # Sprint 3 (1.16.0): the lab's contact details (one record; None until a Manager saves it).
    def get_site_contact(self) -> SiteContact | None: ...
    def save_site_contact(self, contact: SiteContact) -> None: ...


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
        self._credentials: dict[str, StaffCredential] = {}
        self._notifications: dict[str, Notification] = {}
        self._notification_preferences: dict[str, NotificationPreference] = {}
        self._calendar_feeds: dict[str, CalendarFeed] = {}
        self._unfreeze_requests: dict[str, UnfreezeRequest] = {}
        self._series: dict[str, BookingSeries] = {}
        self._site_contact: SiteContact | None = None  # Sprint 3 (1.16.0)

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
                self._credentials.copy(),
                self._notifications.copy(),
                self._calendar_feeds.copy(),
                self._unfreeze_requests.copy(),
                self._series.copy(),
                self._site_contact,  # Sprint 3 (1.16.0)
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
                    self._credentials,
                    self._notifications,
                    self._calendar_feeds,
                    self._unfreeze_requests,
                    self._series,
                    self._site_contact,
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
            self._calendar_feeds.clear()
            self._unfreeze_requests.clear()
            self._series.clear()

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

    def save_unfreeze_request(self, request: UnfreezeRequest) -> None:
        with self._lock:
            self._unfreeze_requests[request.id] = request

    def get_unfreeze_request(self, request_id: str) -> UnfreezeRequest | None:
        with self._lock:
            return self._unfreeze_requests.get(request_id)

    def list_unfreeze_requests(self, principal_id: str | None = None) -> list[UnfreezeRequest]:
        with self._lock:
            return sorted((item for item in self._unfreeze_requests.values()
                           if principal_id is None or item.principal_id == principal_id),
                          key=lambda item: (item.created_at, item.id))

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
