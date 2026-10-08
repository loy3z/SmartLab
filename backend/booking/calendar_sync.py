"""Transactional outbox for create/update/cancel; network calls run after commit."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import uuid4

from .domain import AuditRecord, BookingStatus, OutlookSyncRecord
from .errors import DomainError
from .outlook import OutlookError


class CalendarSyncService:
    def __init__(self, repo, provider, enabled=False, clock=None):
        self.repo, self.provider, self.enabled = repo, provider, enabled
        self.clock = clock or (lambda: datetime.now(UTC))
        self._lock = RLock()

    def now(self):
        return self.clock().astimezone(UTC)

    def schedule(self, booking):
        """Called inside the booking transaction; record+booking commit together."""
        if not self.enabled:
            return
        current = self.repo.get_outlook_sync(booking.id)
        if booking.status == BookingStatus.APPROVED and current is None:
            self.repo.save_outlook_sync(OutlookSyncRecord(
                booking.id, "CREATE", "PENDING", self.provider.target_path(), self.now(),
                booking_revision=booking.revision,
            ))
        elif (booking.status == BookingStatus.APPROVED and current and current.action != "DELETE"
              and booking.revision > current.booking_revision):
            running = current.status == "IN_PROGRESS" and current.lease_until and current.lease_until > self.now()
            action = "UPDATE" if current.event_id or current.create_attempted or current.status == "SYNCED" else "CREATE"
            self.repo.save_outlook_sync(replace(
                current,
                action=action,
                status="IN_PROGRESS" if running else "PENDING",
                revision=current.revision + 1,
                booking_revision=booking.revision,
                updated_at=self.now(),
                next_attempt_at=None,
                lease_until=current.lease_until if running else None,
                last_error=None,
            ))
        elif booking.status == BookingStatus.CANCELLED and current and current.action != "DELETE":
            running = current.status == "IN_PROGRESS" and current.lease_until and current.lease_until > self.now()
            self.repo.save_outlook_sync(replace(current, action="DELETE", status="IN_PROGRESS" if running else "PENDING",
                revision=current.revision + 1, updated_at=self.now(), next_attempt_at=None,
                lease_until=current.lease_until if running else None, last_error=None))

    def describe(self, booking):
        empty = {"status": "NOT_REQUIRED", "action": None, "web_link": None, "last_error": None}
        if booking.status != BookingStatus.APPROVED and not (self.enabled and self.repo.get_outlook_sync(booking.id)):
            return empty
        if not self.enabled:
            return {**empty, "status": "DISABLED"}
        record = self.repo.get_outlook_sync(booking.id)
        if record is None:
            return {**empty, "status": "PENDING", "action": "CREATE"}
        return {"status": record.status, "action": record.action,
                "web_link": record.web_link if record.action in ("CREATE", "UPDATE") and record.status == "SYNCED" else None,
                "last_error": record.last_error}

    def reconcile(self):
        # Also handles approved bookings that predate enabling the integration.
        if not self.enabled:
            return
        for candidate in self.repo.list_bookings():
            with self.repo.atomic(resource_ids=[candidate.resource_id], student_ids=[candidate.student_id]):
                self.schedule(self.repo.get_booking(candidate.id))

    def process_booking(self, booking_id):
        if not self.enabled:
            return None
        with self._lock:
            # A concurrent cancellation may require a follow-up DELETE.
            for _ in range(2):
                source = self.repo.get_booking(booking_id)
                if not source:
                    return None
                with self.repo.atomic(resource_ids=[source.resource_id], student_ids=[source.student_id]):
                    source = self.repo.get_booking(booking_id)
                    self.schedule(source)
                    record = self.repo.get_outlook_sync(booking_id)
                    if not record or record.status == "SYNCED":
                        return record
                    now = self.now()
                    if record.next_attempt_at and record.next_attempt_at > now:
                        return record
                    if record.status == "IN_PROGRESS" and record.lease_until and record.lease_until > now:
                        return record
                    creating = record.action == "CREATE" or (record.action in ("UPDATE", "DELETE") and not record.event_id and record.create_attempted)
                    claimed = replace(record, status="IN_PROGRESS", attempts=record.attempts + 1,
                        create_attempted=record.create_attempted or creating, updated_at=now, lease_until=now + timedelta(minutes=5))
                    self.repo.save_outlook_sync(claimed)
                event_id, web_link, ical_uid = claimed.event_id, claimed.web_link, claimed.ical_uid
                try:
                    student = resource = None
                    if creating or claimed.action == "UPDATE":
                        student = self.repo.get_principal(source.student_id)
                        resource = self.repo.get_resource(source.resource_id)
                        if not student or not student.university_email:
                            raise OutlookError("STUDENT_EMAIL_NOT_CONFIGURED")
                        if not resource:
                            raise OutlookError("RESOURCE_NOT_FOUND")
                    if creating:
                        event = self.provider.create_event(source, student, resource, claimed.calendar_path)
                        event_id, web_link, ical_uid = event.id, event.web_link, event.ical_uid
                    # Save a recovered/created ID before issuing DELETE so retry
                    # can recover from a crash, timeout or failed cancellation.
                    with self.repo.atomic(resource_ids=[source.resource_id], student_ids=[source.student_id]):
                        latest = self.repo.get_outlook_sync(booking_id)
                        if event_id:
                            latest = replace(latest, event_id=event_id, web_link=web_link, ical_uid=ical_uid)
                            self.repo.save_outlook_sync(latest)
                    if claimed.action == "UPDATE" and event_id and not creating:
                        event = self.provider.update_event(source, student, resource, claimed.calendar_path, event_id)
                        event_id = event.id
                        web_link = event.web_link or web_link
                        ical_uid = event.ical_uid or ical_uid
                        with self.repo.atomic(resource_ids=[source.resource_id], student_ids=[source.student_id]):
                            latest = self.repo.get_outlook_sync(booking_id)
                            latest = replace(latest, event_id=event_id, web_link=web_link, ical_uid=ical_uid)
                            self.repo.save_outlook_sync(latest)
                    elif claimed.action == "UPDATE" and not event_id:
                        raise OutlookError("OUTLOOK_EVENT_ID_MISSING")
                    if claimed.action == "DELETE" and event_id:
                        self.provider.delete_event(claimed.calendar_path, event_id)
                except OutlookError as exc:
                    with self.repo.atomic(resource_ids=[source.resource_id], student_ids=[source.student_id]):
                        latest = self.repo.get_outlook_sync(booking_id)
                        if latest.revision == claimed.revision:
                            delay = max(exc.retry_after, min(30 * 2 ** min(latest.attempts - 1, 7), 3600))
                            latest = replace(latest, status="FAILED", last_error=exc.code, lease_until=None,
                                next_attempt_at=self.now() + timedelta(seconds=delay), updated_at=self.now())
                            self.repo.save_outlook_sync(latest)
                            self._audit(booking_id, "OUTLOOK_SYNC_FAILED", code=exc.code, calendar_action=claimed.action)
                        else:
                            latest = replace(latest, status="PENDING", lease_until=None, next_attempt_at=None)
                            self.repo.save_outlook_sync(latest)
                    return latest
                with self.repo.atomic(resource_ids=[source.resource_id], student_ids=[source.student_id]):
                    latest = self.repo.get_outlook_sync(booking_id)
                    if latest.revision == claimed.revision:
                        latest = replace(latest, status="SYNCED", last_error=None, next_attempt_at=None,
                            lease_until=None, updated_at=self.now(), last_success_at=self.now())
                        self.repo.save_outlook_sync(latest)
                        self._audit(booking_id, "OUTLOOK_SYNC_SUCCEEDED", calendar_action=claimed.action)
                        return latest
                    # Approval changed to cancellation while Graph was running.
                    self.repo.save_outlook_sync(replace(latest, status="PENDING", lease_until=None, next_attempt_at=None))
            return self.repo.get_outlook_sync(booking_id)

    def process_pending(self, limit=10):
        if not self.enabled:
            return []
        self.reconcile()
        due = sorted((item for item in self.repo.list_outlook_sync()
            if item.status != "SYNCED" and (not item.next_attempt_at or item.next_attempt_at <= self.now())
            and not (item.status == "IN_PROGRESS" and item.lease_until and item.lease_until > self.now())),
            key=lambda item: (item.updated_at, item.booking_id))
        return [self.process_booking(item.booking_id) for item in due[:limit]]

    def retry(self, booking):
        if not self.enabled:
            raise DomainError("OUTLOOK_DISABLED", "Enable Outlook synchronisation first.", 409)
        with self.repo.atomic(resource_ids=[booking.resource_id], student_ids=[booking.student_id]):
            self.schedule(self.repo.get_booking(booking.id))
            record = self.repo.get_outlook_sync(booking.id)
            if not record:
                raise DomainError("OUTLOOK_SYNC_NOT_REQUIRED", "Only approved bookings and their cancellations synchronise.", 409)
            if record.status == "IN_PROGRESS" and record.lease_until and record.lease_until > self.now():
                raise DomainError("OUTLOOK_SYNC_IN_PROGRESS", "This booking is already synchronising.", 409)
            if record.status != "SYNCED":
                self.repo.save_outlook_sync(replace(record, status="PENDING", next_attempt_at=None))
        return self.process_booking(booking.id)

    def _audit(self, booking_id, action, **details):
        self.repo.append_audit(AuditRecord(str(uuid4()), "SYSTEM", action, "booking", booking_id, self.now(), details))
