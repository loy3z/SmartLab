"""One-way Outlook synchronisation: the website is the only authority (client email, 17 Oct).

Transactional outbox for create/update/cancel; network calls run after commit. The system never reads changes
made in Outlook, so nothing done there can bypass the booking rules or become an approved booking. A person may
delete the event from their own calendar; only a later change on the website (a Manager's reschedule) writes it
again, with the new time.
"""
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
        self.last_check = None  # result of the latest connection check in this process
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

    def describe(self, booking, records=None):
        """records (2026-10-29, load test S2): sync records by booking id, read once for a whole list of bookings."""
        def stored():
            return records.get(booking.id) if records is not None else self.repo.get_outlook_sync(booking.id)

        empty = {"status": "NOT_REQUIRED", "action": None, "web_link": None, "last_error": None}
        if booking.status != BookingStatus.APPROVED and not (self.enabled and stored()):
            return empty
        if not self.enabled:
            return {**empty, "status": "DISABLED"}
        record = stored()
        if record is None:
            return {**empty, "status": "PENDING", "action": "CREATE"}
        return {"status": record.status, "action": record.action,
                "web_link": record.web_link if record.action in ("CREATE", "UPDATE") and record.status == "SYNCED" else None,
                "last_error": record.last_error}

    def reconcile(self):
        # Also handles approved bookings that predate enabling the integration. A booking that has already
        # ended is not written: a calendar entry in the past helps nobody.
        if not self.enabled:
            return
        now = self.now()
        for candidate in self.repo.list_bookings():
            if candidate.status == BookingStatus.APPROVED and candidate.end <= now and not self.repo.get_outlook_sync(candidate.id):
                continue
            with self.repo.atomic(resource_ids=[candidate.resource_id], student_ids=[candidate.student_id]):
                self.schedule(self.repo.get_booking(candidate.id))

    def _people(self, source):
        student = self.repo.get_principal(source.student_id)
        resource = self.repo.get_resource(source.resource_id)
        creator = self.repo.get_principal(source.created_by) if source.created_by else None
        return student, resource, creator

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
                    student = resource = creator = None
                    if creating or claimed.action == "UPDATE":
                        student, resource, creator = self._people(source)
                        if not student or not student.university_email:
                            raise OutlookError("STUDENT_EMAIL_NOT_CONFIGURED")
                        if not resource:
                            raise OutlookError("RESOURCE_NOT_FOUND")
                    if creating:
                        # A replacement for an event the person deleted keeps the old iCal UID until it is written;
                        # it needs a new transactionId, or Graph would treat it as a retry of the deleted event.
                        transaction_id = booking_id if not claimed.ical_uid else f"{booking_id}.{claimed.revision}"
                        event = self.provider.create_event(source, student, resource, claimed.calendar_path,
                                                           creator=creator, transaction_id=transaction_id)
                        event_id, web_link, ical_uid = event.id, event.web_link, event.ical_uid
                    # Save a recovered/created ID before issuing DELETE so retry
                    # can recover from a crash, timeout or failed cancellation.
                    with self.repo.atomic(resource_ids=[source.resource_id], student_ids=[source.student_id]):
                        latest = self.repo.get_outlook_sync(booking_id)
                        if event_id:
                            latest = replace(latest, event_id=event_id, web_link=web_link, ical_uid=ical_uid)
                            self.repo.save_outlook_sync(latest)
                    if claimed.action == "UPDATE" and event_id and not creating:
                        event = self.provider.update_event(source, student, resource, claimed.calendar_path, event_id,
                                                           creator=creator)
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
                    if exc.code == "GRAPH_HTTP_404" and claimed.action == "UPDATE" and not creating:
                        # The person deleted the event; a Manager has now changed the booking, so write the new time.
                        if self._event_gone(booking_id, claimed):
                            return self.process_booking(booking_id)
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
                        now = self.now()
                        latest = replace(latest, status="SYNCED", last_error=None, next_attempt_at=None,
                            lease_until=None, updated_at=now, last_success_at=now)
                        self.repo.save_outlook_sync(latest)
                        self._audit(booking_id, "OUTLOOK_SYNC_SUCCEEDED", calendar_action=claimed.action)
                        return latest
                    # Approval changed to cancellation while Graph was running.
                    self.repo.save_outlook_sync(replace(latest, status="PENDING", lease_until=None, next_attempt_at=None))
            return self.repo.get_outlook_sync(booking_id)

    def _event_gone(self, booking_id, claimed):
        """An UPDATE found no event: switch the job to CREATE so the new time reaches the calendar again."""
        source = self.repo.get_booking(booking_id)
        with self.repo.atomic(resource_ids=[source.resource_id], student_ids=[source.student_id]):
            latest = self.repo.get_outlook_sync(booking_id)
            if latest is None or latest.revision != claimed.revision:
                return False
            # ical_uid is kept until the new event is written: it marks this CREATE as a replacement.
            self.repo.save_outlook_sync(replace(
                latest, action="CREATE", status="PENDING", event_id=None, web_link=None, create_attempted=False,
                revision=latest.revision + 1, attempts=0, next_attempt_at=None, lease_until=None, last_error=None,
                updated_at=self.now()))
            self._audit(booking_id, "OUTLOOK_EVENT_RECREATED", reason="EVENT_NOT_FOUND")
            return True

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

    def check_connection(self):
        """Read the organiser calendar once. Remembers the result for the status page."""
        result = {"at": self.now(), "ok": False, "code": None, "mode": getattr(self.provider, "mode", "adapter"),
                  "calendar_name": None, "owner": None}
        try:
            details = self.provider.check_connection()
            result.update(ok=True, calendar_name=details.get("calendar_name"), owner=details.get("owner"))
        except OutlookError as exc:
            result["code"] = {"GRAPH_HTTP_401": "TOKEN_EXPIRED"}.get(exc.code, exc.code)
        self.last_check = result
        return result

    def overview(self):
        """Staff status page (development aid): counts plus one row per synchronised booking, failures first."""
        items, counts = [], {"total": 0, "synced": 0, "pending": 0, "failed": 0}
        for record in self.repo.list_outlook_sync():
            booking = self.repo.get_booking(record.booking_id)
            if booking is None:
                continue
            person, resource, creator = self._people(booking)
            counts["total"] += 1
            counts["synced" if record.status == "SYNCED" else "failed" if record.status == "FAILED" else "pending"] += 1
            priority = 0 if record.status == "FAILED" else 1 if record.status != "SYNCED" else 2
            items.append((priority, booking.start, booking.id, {
                "booking_id": booking.id, "booking_status": booking.status, "start": booking.start, "end": booking.end,
                "urgent": booking.urgent,
                "resource": {"id": booking.resource_id, "name": resource.name if resource else None,
                             "location": resource.location if resource else None},
                "booked_for": {"zid": person.zid, "display_name": person.display_name} if person else None,
                "booked_by": ({"zid": creator.zid, "display_name": creator.display_name}
                              if creator and creator.id != booking.student_id else None),
                "invited": bool(person and getattr(self.provider, "invites", lambda _: True)(person)),
                "sync": {"status": record.status, "action": record.action, "attempts": record.attempts,
                         "last_error": record.last_error, "next_attempt_at": record.next_attempt_at,
                         "last_success_at": record.last_success_at,
                         "web_link": record.web_link if record.action in ("CREATE", "UPDATE") else None},
            }))
        items.sort(key=lambda item: (item[0], item[1], item[2]))
        return {"summary": counts, "items": [item[3] for item in items]}

    def _audit(self, booking_id, action, actor_id="SYSTEM", **details):
        self.repo.append_audit(AuditRecord(str(uuid4()), actor_id, action, "booking", booking_id, self.now(), details))
