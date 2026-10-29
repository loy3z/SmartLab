"""Integration tests for the PostgreSQL adapter (booking/postgres.py) against a real database.

Skipped unless the PostgreSQL adapter is configured, e.g. (PowerShell, after the steps in database/README.md):

    $env:REPOSITORY_FACTORY = 'booking.postgres.PostgresRepository'
    python manage.py test booking.tests.test_postgres

Django creates and drops a separate test database (test_<DB_NAME>); your own data is not touched.
The schema is loaded from database/schema.sql, so these tests also check that file.
"""

import threading
import unittest
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from unittest.mock import patch

from django.conf import settings
from django.db import IntegrityError, connection, connections, transaction  # Sprint 3 (1.16.0): IntegrityError, transaction
from django.db import close_old_connections  # 2026-10-29 (load test S3)
from django.test import override_settings, TransactionTestCase
from django.test.utils import CaptureQueriesContext

from booking.domain import (
    AuditRecord, Booking, BookingStatus, Principal, QualificationRequirement, QualificationStatus,
    Resource, ResourceKind, ResourceStatus, Role,
)
from booking.repository import MemoryRepository  # 2026-10-29 (load test R1)
from booking.exceptions import DomainError
from booking.services import BookingService

SYDNEY = ZoneInfo("Australia/Sydney")
from booking.tests.test_119 import Acceptance119  # Sprint 3 (1.19.0): identical adapter acceptance cases.
SCHEMA = Path(settings.BASE_DIR) / "database" / "schema.sql"


@unittest.skipUnless(getattr(settings, "USE_POSTGRES", False), "PostgreSQL adapter not configured.")
class Postgres119Tests(Acceptance119, TransactionTestCase):
    """Sprint 3 (1.19.0): real database channels, announcement permissions, lifecycle and atomicity."""
    databases = {"default"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.booking')")
            if cursor.fetchone()[0] is None:
                cursor.execute(_schema_statements())

    def setUp(self):
        from booking.postgres import PostgresRepository, PostgresFileStorage
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM public.announcement')
        self.setup_119(PostgresRepository(), PostgresFileStorage())

    def test_009_preserves_legacy_bell_choice_and_defaults_email_on_twice(self):
        # Transactional DDL rolls back at the end: no other test sees this temporary old structure.
        migration = Path(settings.BASE_DIR) / 'database/migrations/009_announcements_notification_channels.sql'
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('ALTER TABLE public.notification_preference DROP COLUMN email_enabled')
                cursor.execute('INSERT INTO public.notification_preference(id, principal_id, category, enabled) VALUES (%s,%s,%s,false)',
                               [str(uuid4()), self.student.id, 'bookings'])
                cursor.execute(migration.read_text())
                cursor.execute(migration.read_text())
                cursor.execute('SELECT enabled,email_enabled FROM public.notification_preference WHERE principal_id=%s', [self.student.id])
                self.assertEqual(cursor.fetchone(), (False, True))
            transaction.set_rollback(True)


def _schema_statements():
    """schema.sql is a pg_dump for psql; drop psql meta-commands and the session search_path reset."""
    lines = [line for line in SCHEMA.read_text(encoding="utf-8").splitlines()
             if not line.startswith("\\") and "set_config('search_path'" not in line]
    return "\n".join(lines)


@unittest.skipUnless(getattr(settings, "USE_POSTGRES", False), "PostgreSQL adapter not configured (set REPOSITORY_FACTORY).")
class PostgresAdapterTests(TransactionTestCase):
    databases = {"default"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.booking')")
            if cursor.fetchone()[0] is None:
                cursor.execute(_schema_statements())

    def setUp(self):
        # Each test uses its own people and resources, so tests never see each other's rows
        # (audit records are append-only and cannot be truncated between tests).
        from booking.postgres import PostgresFileStorage, PostgresRepository
        self.now = datetime(2030, 1, 7, 0, tzinfo=timezone.utc)
        self.repo, self.storage = PostgresRepository(), PostgresFileStorage()
        self.service = BookingService(self.repo, self.storage, clock=lambda: self.now, min_advance_days=0, max_advance_days=7)
        self.requirement = QualificationRequirement(str(uuid4()), "Lab induction", "Required induction")
        self.repo.save_requirement(self.requirement)
        self.room = Resource(str(uuid4()), "Laboratory", ResourceKind.ROOM, "Building A", "Test room",
                             required_qualification_id=self.requirement.id, opening_time=time(8), closing_time=time(20))
        self.repo.save_resource(self.room)
        self.admin = self.person(Role.ADMIN)
        self.manager = self.person(Role.MANAGER)
        self.a, self.b = self.person(), self.person()
        self.start = datetime(2030, 1, 10, 10, tzinfo=SYDNEY)
        self.end = self.start + timedelta(hours=1)

    def person(self, role=Role.STUDENT):
        zid = f"z{uuid4().int % 10_000_000:07d}"
        principal = Principal(str(uuid4()), zid, f"Test {zid}", role, f"{zid}@ad.unsw.edu.au")
        self.repo.save_principal(principal)
        return principal

    def verified(self, student):
        submission = self.service.submit_qualification(student, self.requirement.id, "Certificate", "", b"%PDF-1.4 test", "c.pdf", "application/pdf")
        return self.service.review_qualification(self.admin, submission.id, "VERIFIED")[0]

    def book(self, student, **overrides):
        args = {"resource_id": self.room.id, "start": self.start, "end": self.end, "purpose": "Practical"}
        args.update(overrides)
        booking = self.service.create_booking(student, **args)[0]
        self.now += timedelta(seconds=1)
        return booking

    def test_records_round_trip_with_types_intact(self):
        stored = self.repo.get_resource(self.room.id)
        self.assertEqual(stored, self.room)
        self.assertIsInstance(stored.kind, ResourceKind)
        self.assertIsInstance(stored.status, ResourceStatus)
        self.assertEqual(stored.pending_hold_minutes, 1440)
        self.assertEqual(self.repo.get_principal(self.a.id), self.a)
        self.assertIsNone(self.repo.get_booking("not-a-uuid"))
        record = AuditRecord(str(uuid4()), self.admin.id, "TEST", "booking", str(uuid4()), self.now, {"nested": {"ok": True}})
        self.repo.append_audit(record)
        self.assertIn(record, self.repo.list_audit())

    def test_prerequisites_and_equipment_rooms_round_trip(self):
        advanced = QualificationRequirement(str(uuid4()), "Advanced", "", prerequisite_ids=(self.requirement.id,))
        self.repo.save_requirement(advanced)
        self.assertEqual(self.repo.get_requirement(advanced.id).prerequisite_ids, (self.requirement.id,))
        device = Resource(str(uuid4()), "Microscope", ResourceKind.EQUIPMENT, "Laboratory", "",
                          required_qualification_id=advanced.id, room_id=self.room.id, category="Microscopy")
        self.repo.save_resource(device)
        self.assertEqual(self.repo.get_resource(device.id), device)
        with self.assertRaises(DomainError) as denied:  # Advanced needs the General induction first
            self.service.submit_qualification(self.a, advanced.id, "Advanced", "", b"x", "a.pdf", "application/pdf")
        self.assertEqual(denied.exception.code, "PREREQUISITE_REQUIRED")

    # Sprint 3 (1.20.0): persisted personal visibility and atomic rollback, on a real database.
    def test_history_removal_persists_per_person_without_deleting_the_booking(self):
        from booking.postgres import PostgresRepository
        self.verified(self.a)
        booking = self.service.create_booking(self.manager, self.room.id, self.start, self.end, 'History',
                                               on_behalf_of_zid=self.a.zid)[0]
        booking = self.service.cancel_booking(self.manager, booking.id)
        self.service.remove_booking_history(self.manager, booking.id)
        self.service.remove_booking_history(self.manager, booking.id)
        reloaded = PostgresRepository()
        self.assertEqual(reloaded.hidden_booking_ids(self.manager.id), {booking.id})
        self.assertEqual(reloaded.hidden_booking_ids(self.a.id), set())
        self.assertEqual(reloaded.get_booking(booking.id), booking)
        self.assertIn(booking, self.service.booking_report(self.manager))
        with self.assertRaises(RuntimeError):
            with self.repo.atomic(student_ids=[self.a.id]):
                self.repo.hide_booking(self.a.id, booking.id, self.now)
                raise RuntimeError('rollback')
        self.assertEqual(reloaded.hidden_booking_ids(self.a.id), set())

    def test_010_history_migration_can_run_twice_without_losing_removals(self):
        self.verified(self.a)
        booking = self.service.create_booking(self.a, self.room.id, self.start, self.end, 'History')[0]
        self.repo.hide_booking(self.a.id, booking.id, self.now)
        migration = Path(settings.BASE_DIR) / 'database/migrations/010_booking_history_removal.sql'
        with connection.cursor() as cursor:
            cursor.execute(migration.read_text())
            cursor.execute(migration.read_text())
        self.assertEqual(self.repo.hidden_booking_ids(self.a.id), {booking.id})

    @override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
    def test_staff_invite_activation_and_sign_in_are_persisted(self):
        staff = self.service.create_staff(self.manager, f"z{uuid4().int % 10_000_000:07d}", "New admin",
                                          "new.admin@ad.unsw.edu.au", Role.ADMIN)
        code = self.repo.get_credential(staff.id).invite_code
        self.assertEqual(self.service.staff_access(staff), {"activation_status": "AWAITING_ACTIVATION", "invite_code": code})
        self.service.activate_staff(staff.zid, code, "new-password-1")
        credential = self.repo.get_credential(staff.id)
        self.assertIsNone(credential.invite_code)
        self.assertTrue(credential.activated)
        self.assertEqual(self.service.staff_sign_in(staff.zid, "new-password-1").role, Role.ADMIN)
        self.service.reset_staff_access(self.manager, staff.id)
        self.assertFalse(self.repo.get_credential(staff.id).activated)

    def test_on_behalf_and_urgent_bookings_are_persisted(self):
        self.verified(self.a)
        for_a = self.book(self.admin, on_behalf_of_zid=self.a.zid)
        stored = self.repo.get_booking(for_a.id)
        self.assertEqual((stored.student_id, stored.created_by, stored.urgent), (self.a.id, self.admin.id, False))
        self.service.min_advance_days = 7
        urgent = self.book(self.a, start=self.start + timedelta(hours=2), end=self.end + timedelta(hours=2),
                           urgent=True, urgent_reason="Deadline")
        self.assertEqual(self.repo.get_booking(urgent.id), urgent)
        self.assertEqual(self.service.review_booking(self.manager, urgent.id, "APPROVED").status, BookingStatus.APPROVED)

    def test_reschedule_recreates_an_outlook_event_the_person_deleted(self):
        from booking.calendar_sync import CalendarSyncService
        from booking.tests.test_outlook import FakeCalendar
        provider = FakeCalendar()
        sync = CalendarSyncService(self.repo, provider, enabled=True, clock=lambda: self.now)
        self.service.calendar_sync = sync
        self.verified(self.a)
        booking = self.service.review_booking(self.admin, self.book(self.a).id, "APPROVED")
        sync.process_booking(booking.id)
        first = self.repo.get_outlook_sync(booking.id)
        self.assertEqual((first.status, first.action), ("SYNCED", "CREATE"))
        provider.outlook_delete(first.event_id)
        moved = self.service.reschedule_booking(self.manager, booking.id, self.start + timedelta(hours=2), self.end + timedelta(hours=2))
        record = sync.process_booking(moved.id)
        self.assertEqual((record.status, record.action), ("SYNCED", "CREATE"))
        self.assertNotEqual(record.event_id, first.event_id)
        self.assertEqual(provider.events[record.event_id].start, moved.start)
        self.assertEqual(self.repo.get_booking(booking.id), moved)
        self.assertIn("OUTLOOK_EVENT_RECREATED", [item.action for item in self.repo.list_audit() if item.entity_id == booking.id])

    def test_sprint3_records_round_trip(self):
        from booking.domain import BookingSeries, CalendarFeed, Notification, UnfreezeRequest, UnfreezeStatus
        feed = CalendarFeed(self.a.id, "t" * 32, self.now)
        self.repo.save_calendar_feed(feed)
        self.assertEqual(self.repo.get_calendar_feed(self.a.id), feed)
        self.assertEqual(self.repo.get_calendar_feed_by_token("t" * 32), feed)
        self.assertIsNone(self.repo.get_calendar_feed_by_token("unknown-token-value"))
        older = Notification(str(uuid4()), self.a.id, "BOOKING_APPROVED", "Approved", "Body", self.now, link="/bookings")
        newer = replace(older, id=str(uuid4()), created_at=self.now + timedelta(minutes=1), read_at=self.now + timedelta(minutes=2))
        self.repo.save_notification(older)
        self.repo.save_notification(newer)
        self.assertEqual(self.repo.list_notifications(self.a.id), [newer, older])
        self.assertEqual(self.repo.get_notification(older.id), older)
        request = UnfreezeRequest(str(uuid4()), self.a.id, "Sick", self.now)
        self.repo.save_unfreeze_request(request)
        stored = self.repo.get_unfreeze_request(request.id)
        self.assertEqual((stored, type(stored.status)), (request, UnfreezeStatus))
        with self.assertRaises(Exception):  # one waiting request per person (unique partial index)
            self.repo.save_unfreeze_request(UnfreezeRequest(str(uuid4()), self.a.id, "Again", self.now))
        self.assertEqual(self.repo.list_unfreeze_requests(self.a.id), [request])
        series = BookingSeries(str(uuid4()), self.a.id, self.admin.id, self.room.id, "1,3", time(9), 60,
                               self.start.date(), self.start.date() + timedelta(days=13), "Weekly", self.now)
        self.repo.save_series(series)
        self.assertEqual(self.repo.get_series(series.id), series)
        frozen = replace(self.a, no_show_count=2, frozen_until=self.now + timedelta(days=30))
        self.repo.save_principal(frozen)
        self.assertEqual(self.repo.get_principal(self.a.id), frozen)

    def test_weekly_series_check_in_and_freeze_are_persisted(self):
        self.verified(self.a)
        self.service._override_rule(max_advance_days=30, freeze_after_no_shows=1)
        first = self.start.date() + timedelta(days=(7 - self.start.weekday()) % 7)
        series, bookings = self.service.create_series(
            self.admin, self.room.id, [first.isoweekday()], time(10), 60, first, first + timedelta(days=13), "Weekly",
            on_behalf_of_zid=self.a.zid)
        stored = self.repo.get_booking(bookings[0].id)
        self.assertEqual((stored.series_id, stored.status, stored.attendance), (series.id, BookingStatus.APPROVED, None))
        self.now = bookings[0].start + timedelta(minutes=1)
        self.assertEqual(self.service.check_in(self.a, bookings[0].id).attendance, "CHECKED_IN")
        self.assertEqual(self.repo.get_booking(bookings[0].id).checked_in_at, self.now)
        self.now = bookings[1].start + timedelta(minutes=31)
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(bookings[1].id).attendance, "NO_SHOW")
        person = self.repo.get_principal(self.a.id)
        self.assertTrue(person.frozen_at(self.now))
        kinds = {item.kind for item in self.repo.list_notifications(self.a.id)}
        self.assertIn("ACCOUNT_FROZEN", kinds)

    def test_resource_setup_is_persisted(self):
        # Sprint 3: a Manager adds, edits, archives and restores a resource on the website.
        name = f"Spectrometer {uuid4().hex[:6]}"
        item = self.service.create_resource(self.manager, "EQUIPMENT", {
            "name": name, "location": "Lab", "required_qualification_id": self.room.required_qualification_id,
            "room_id": self.room.id, "category": "Optics", "opening_time": time(9), "max_booking_minutes": 120})
        self.assertEqual(self.repo.get_resource(item.id), item)
        self.service.update_resource(self.manager, item.id, {"closing_time": time(17), "category": None})
        self.assertEqual((self.repo.get_resource(item.id).closing_time, self.repo.get_resource(item.id).category), (time(17), None))
        self.service.archive_resource(self.manager, item.id)
        self.assertFalse(self.repo.get_resource(item.id).active)
        self.assertTrue(self.service.restore_resource(self.manager, item.id).active)
        self.assertTrue(self.repo.get_resource(item.id).active)

    def test_resource_status_is_persisted(self):
        self.service.set_resource_status(self.manager, self.room.id, "MAINTENANCE", "Repairs")
        stored = self.repo.get_resource(self.room.id)
        self.assertEqual((stored.status, stored.status_reason), (ResourceStatus.MAINTENANCE, "Repairs"))

    def test_guidance_details_and_contact_are_persisted(self):
        # Sprint 3 (1.16.0): induction guidance texts, room capacity and details (jsonb), the lab's contact row.
        requirement = self.service.create_requirement(self.manager, {"name": f"Laser {uuid4().hex[:6]}", "accepted_evidence": "Sheet"})
        self.assertEqual(self.repo.get_requirement(requirement.id), requirement)
        room, _ = self.service.update_resource(self.manager, self.room.id, {  # rooms of other tests share the name
            "name": f"Laboratory {uuid4().hex[:6]}", "capacity": 16, "details": [{"label": "Floor", "value": "Level 3"}, {"label": "Projector", "value": "Yes"}]})
        self.assertEqual(self.repo.get_resource(self.room.id), room)
        self.assertEqual(self.repo.get_resource(self.room.id).details[1].label, "Projector")
        saved = self.service.update_site_contact(self.manager, {"email": "lab@unsw.example", "note": "Ask at the front desk"})
        self.assertEqual(self.repo.get_site_contact(), saved)

    def test_change_request_is_persisted_and_replaces_the_old_booking(self):
        # Sprint 3 (1.16.0): replaces_id column, the one-open-change index and the automatic cancellation.
        self.verified(self.a)
        old = self.service.review_booking(self.admin, self.book(self.a).id, "APPROVED")
        change = self.service.request_time_change(self.a, old.id, self.start + timedelta(hours=4), self.end + timedelta(hours=4))[0]
        self.assertEqual(self.repo.get_booking(change.id).replaces_id, old.id)
        with self.assertRaises(IntegrityError):  # the database also allows only one open change per booking
            with transaction.atomic():
                self.repo.save_booking(replace(change, id=str(uuid4())))
        self.service.review_booking(self.admin, change.id, "APPROVED")
        self.assertEqual(self.repo.get_booking(old.id).status, BookingStatus.CANCELLED)
        self.service.set_resource_status(self.manager, self.room.id, "CLOSED", "Flood")
        kinds = {item.kind for item in self.repo.list_notifications(self.a.id)}
        self.assertTrue({"CHANGE_REQUESTED", "CHANGE_APPROVED", "RESOURCE_OUT_OF_SERVICE"} <= kinds)

    def test_evidence_file_and_review_are_persisted(self):
        submission = self.verified(self.a)
        self.assertEqual(submission.status, QualificationStatus.VERIFIED)
        self.assertEqual(submission.valid_until, self.now + timedelta(days=120))
        stored = self.storage.get(self.repo.get_submission(submission.id).file_id)
        self.assertEqual((stored.data, stored.size, stored.owner_id), (b"%PDF-1.4 test", 13, self.a.id))

    def test_unverified_student_cannot_book_and_nothing_is_written(self):
        with self.assertRaises(DomainError) as denied:
            self.book(self.a)
        self.assertEqual(denied.exception.code, "QUALIFICATION_REQUIRED")
        self.assertEqual(self.repo.list_bookings(student_id=self.a.id), [])

    def test_full_approval_flow(self):
        self.verified(self.a)
        self.verified(self.b)
        first, second = self.book(self.a), self.book(self.b)
        self.assertEqual(first.status, BookingStatus.PENDING_APPROVAL)
        self.assertEqual(first.review_due_at, first.created_at + timedelta(hours=24))
        self.assertEqual(second.status, BookingStatus.WAITLISTED)
        self.assertEqual([b.id for b in self.repo.list_blocking_bookings(self.room.id, self.start, self.end, self.now)], [first.id])

        approved = self.service.review_booking(self.admin, first.id, "APPROVED")
        self.assertEqual(self.repo.get_booking(first.id).status, BookingStatus.APPROVED)
        self.assertEqual(approved.reviewed_by, self.admin.id)

        self.service.cancel_booking(self.a, first.id)
        promoted = self.repo.get_booking(second.id)
        self.assertEqual((promoted.status, promoted.reason_code), (BookingStatus.PENDING_APPROVAL, "PROMOTED_FROM_WAITLIST"))

        self.now = promoted.review_due_at
        self.service.process_due_requests()
        decided = self.repo.get_booking(second.id)
        self.assertEqual((decided.status, decided.reason_code, decided.reviewed_by),
                         (BookingStatus.APPROVED, "AUTO_APPROVED_AFTER_REVIEW_WINDOW", "SYSTEM"))
        actions = [r.action for r in self.repo.list_audit() if r.entity_id in (first.id, second.id)]
        for expected in ("BOOKING_CREATED", "BOOKING_APPROVED", "BOOKING_CANCELLED", "BOOKING_PROMOTED", "BOOKING_AUTO_APPROVED"):
            self.assertIn(expected, actions)

    def test_rejected_evidence_keeps_the_reason(self):
        submission = self.service.submit_qualification(self.a, self.requirement.id, "Certificate", "", b"x", "c.pdf", "application/pdf")
        self.service.review_qualification(self.admin, submission.id, "REJECTED", "Unreadable")
        stored = self.repo.get_submission(submission.id)
        self.assertEqual((stored.status, stored.rejection_reason, stored.valid_until), (QualificationStatus.REJECTED, "Unreadable", None))

    def test_audit_records_cannot_be_changed(self):
        self.verified(self.a)
        with self.assertRaises(Exception):
            with connection.cursor() as cursor:
                cursor.execute("UPDATE public.audit_record SET action = 'X'")

    def test_failed_transaction_leaves_no_partial_writes(self):
        self.verified(self.a)
        booking = self.book(self.a)
        with self.assertRaises(RuntimeError):
            with self.repo.atomic(resource_ids=[self.room.id]):
                self.repo.save_booking(replace(booking, status=BookingStatus.CANCELLED))
                raise RuntimeError("boom")
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.PENDING_APPROVAL)

    def test_concurrent_requests_for_the_same_time_create_one_pending_request(self):
        self.verified(self.a)
        self.verified(self.b)
        barrier, results, errors = threading.Barrier(2), [], []

        def request(student):
            try:
                barrier.wait()
                results.append(self.service.create_booking(student, self.room.id, self.start, self.end, "Race")[0].status)
            except Exception as error:  # pragma: no cover - reported below
                errors.append(error)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=request, args=(s,)) for s in (self.a, self.b)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(sorted(s.value for s in results), ["PENDING_APPROVAL", "WAITLISTED"])

    # 2026-10-29 (tasks-load-2026-10-29.md R1, S1, S5, S3): per-request work must not grow with past bookings.

    def raw_booking(self, start, status, student=None, **fields):
        """Save a booking directly (no rules), as history or a fixture for time processing."""
        student = student or self.a
        booking = Booking(str(uuid4()), student.id, self.room.id, start, start + timedelta(hours=1), "History",
                          start - timedelta(days=10), status, None, **fields)
        self.repo.save_booking(booking)
        return booking

    def decoded_bookings(self):
        """Ids of every booking row read from PostgreSQL inside the with-block."""
        from booking import postgres
        original, seen = postgres._decode, []

        def spy(record_type, row):
            record = original(record_type, row)
            if record_type is Booking:
                seen.append(record.id)
            return record
        return patch.object(postgres, "_decode", spy), seen

    def test_load_list_booking_filters_match_the_memory_repository(self):
        memory = MemoryRepository()
        base = self.now + timedelta(hours=1)
        statuses = list(BookingStatus)
        for i in range(21):
            booking = Booking(str(uuid4()), self.a.id, self.room.id, base + timedelta(hours=i), base + timedelta(hours=i, minutes=30),
                              "Filters", self.now + timedelta(seconds=i), statuses[i % len(statuses)], None,
                              review_due_at=base + timedelta(hours=i % 3) if i % 2 else None,
                              created_by=self.admin.id if i % 3 == 0 else None,
                              attendance="NO_SHOW" if i % 4 == 0 else None)
            self.repo.save_booking(booking)
            memory.save_booking(booking)
        undecided = [BookingStatus.WAITING_QUALIFICATION, BookingStatus.PENDING_APPROVAL, BookingStatus.WAITLISTED]
        cases = [{}, {"statuses": [BookingStatus.APPROVED]}, {"statuses": undecided}, {"statuses": []},
                 {"start_from": base + timedelta(hours=3)}, {"start_to": base + timedelta(hours=5)},
                 {"end_from": base + timedelta(hours=6, minutes=30)}, {"due_by": base + timedelta(hours=2)},
                 {"created_by": self.admin.id}, {"unmarked": True},
                 {"statuses": [BookingStatus.APPROVED], "unmarked": True, "start_from": base, "start_to": base + timedelta(hours=14)}]
        for filters in cases:
            with self.subTest(filters=filters):
                ids = [item.id for item in self.repo.list_bookings(resource_id=self.room.id, **filters)]
                self.assertEqual(ids, [item.id for item in memory.list_bookings(resource_id=self.room.id, **filters)])

    def test_load_time_processing_and_staff_pages_do_not_read_past_bookings(self):
        from booking.views.bookings import my_bookings
        history = [self.raw_booking(self.now - timedelta(days=1 + i), status, student=self.b,
                                    attendance="NO_SHOW" if status == BookingStatus.APPROVED else None).id
                   for i in range(50)
                   for status in (BookingStatus.APPROVED, BookingStatus.REJECTED, BookingStatus.CANCELLED, BookingStatus.EXPIRED)]
        spy, seen = self.decoded_bookings()
        with spy:
            self.service.process_due_requests()
            self.service.staff_overview(self.admin)
            my_bookings(self.service, self.admin)
        self.assertEqual(set(seen) & set(history), set())

    def test_load_reminder_check_uses_the_same_queries_for_1_or_20_bookings(self):
        def queries_after_reminders():
            self.service.process_due_requests()  # sends any new reminder
            with CaptureQueriesContext(connection) as captured:
                self.service.process_due_requests()  # nothing new to send: this is the per-request cost
            return len(captured.captured_queries)

        soon = self.now + timedelta(hours=3)
        self.raw_booking(soon, BookingStatus.APPROVED)
        one = queries_after_reminders()
        for _ in range(19):
            self.raw_booking(soon, BookingStatus.APPROVED, student=self.person())
        twenty = queries_after_reminders()
        self.assertEqual(len([item for item in self.repo.list_notifications(self.a.id) if item.kind == "BOOKING_REMINDER"]), 1)
        self.assertEqual(twenty, one)

    def test_load_database_connection_is_reused_between_requests(self):
        def backend_pid():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                return cursor.fetchone()[0]

        connection.close()
        first = backend_pid()
        close_old_connections()  # what Django runs at the end of every request
        self.assertEqual(backend_pid(), first)
