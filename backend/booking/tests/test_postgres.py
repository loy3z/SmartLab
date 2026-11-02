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
    AuditRecord, Booking, BookingStatus, EmailDelivery, Principal, QualificationRequirement, QualificationStatus,
    QualificationSubmission,  # 2026-10-29 (load test S8)
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
        # Sprint 3 (2026-11-01): email claiming reads the global queue, unlike person/resource-scoped fixtures.
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM public.email_delivery')
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

    def test_011_email_migration_can_run_twice(self):
        migration = Path(settings.BASE_DIR) / 'database/migrations/011_durable_email_delivery.sql'
        with connection.cursor() as cursor:
            cursor.execute(migration.read_text())
            cursor.execute(migration.read_text())
            cursor.execute("SELECT to_regclass('public.email_delivery')")
            self.assertEqual(cursor.fetchone()[0], "email_delivery")

    def test_additional_hours_round_trip_and_do_not_hold_time_until_approved(self):
        from booking.postgres import PostgresRepository
        pending = self.raw_booking(
            self.start, BookingStatus.PENDING_APPROVAL, additional_hours=True,
            additional_hours_reason="Extra weekly time for the experiment",
            active_data_collection=True, data_collection_reason="Collecting the final sample series")
        reloaded = PostgresRepository()
        self.assertEqual(reloaded.get_booking(pending.id), pending)
        self.assertEqual(reloaded.list_blocking_bookings(self.room.id, self.start, self.end, self.now), [])
        normal = self.raw_booking(self.start, BookingStatus.PENDING_APPROVAL, student=self.b,
                                  hold_until=self.now + timedelta(hours=24))
        self.assertEqual([item.id for item in reloaded.list_blocking_bookings(
            self.room.id, self.start, self.end, self.now)], [normal.id])
        approved = replace(pending, status=BookingStatus.APPROVED, reviewed_by=self.manager.id,
                           reviewed_at=self.now, decision_reason="Approved for the requested time")
        self.repo.save_booking(approved)
        self.assertEqual(reloaded.get_booking(approved.id), approved)
        self.assertEqual({item.id for item in reloaded.list_blocking_bookings(
            self.room.id, self.start, self.end, self.now)}, {approved.id, normal.id})

    def test_additional_hours_database_constraints_protect_nonholding_requests(self):
        booking = self.raw_booking(self.start, BookingStatus.PENDING_APPROVAL, additional_hours=True,
                                   additional_hours_reason="Extra weekly time")
        invalid_updates = [
            ("additional_hours_reason = NULL", []),
            ("additional_hours_reason = '   '", []),
            ("active_data_collection = true", []),
            ("active_data_collection = true, data_collection_reason = '   '", []),
            ("additional_hours = false, active_data_collection = true, data_collection_reason = 'Collecting samples'", []),
            ("hold_until = %s", [self.now + timedelta(hours=1)]),
            ("review_due_at = %s", [self.now + timedelta(hours=48)]),
            ("urgent = true", []),
        ]
        for assignments, params in invalid_updates:
            with self.subTest(assignments=assignments), self.assertRaises(IntegrityError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(f"UPDATE public.booking SET {assignments} WHERE id = %s", [*params, booking.id])
        self.assertEqual(self.repo.get_booking(booking.id), booking)

    def test_012_migration_can_run_twice_without_changing_additional_requests(self):
        pending = self.raw_booking(self.start, BookingStatus.PENDING_APPROVAL, additional_hours=True,
                                   additional_hours_reason="Extra weekly time", active_data_collection=True,
                                   data_collection_reason="Collecting final samples")
        migration = Path(settings.BASE_DIR) / 'database/migrations/012_additional_hours_requests.sql'
        with connection.cursor() as cursor:
            cursor.execute(migration.read_text(encoding='utf-8'))
            cursor.execute(migration.read_text(encoding='utf-8'))
        self.assertEqual(self.repo.get_booking(pending.id), pending)

    def test_012_migrates_legacy_bookings_twice_without_changing_existing_fields(self):
        legacy = self.raw_booking(self.start, BookingStatus.PENDING_APPROVAL,
                                  hold_until=self.now + timedelta(hours=24),
                                  review_due_at=self.now + timedelta(hours=24))
        migration = Path(settings.BASE_DIR) / 'database/migrations/012_additional_hours_requests.sql'
        # PostgreSQL transactional DDL restores the modern structure and every other row after this test.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('''ALTER TABLE public.booking DROP COLUMN additional_hours,
                                  DROP COLUMN additional_hours_reason, DROP COLUMN active_data_collection,
                                  DROP COLUMN data_collection_reason''')
                cursor.execute(migration.read_text(encoding='utf-8'))
                cursor.execute(migration.read_text(encoding='utf-8'))
            restored = self.repo.get_booking(legacy.id)
            self.assertEqual(restored, legacy)
            self.assertEqual((restored.additional_hours, restored.additional_hours_reason,
                              restored.active_data_collection, restored.data_collection_reason),
                             (False, None, False, None))
            transaction.set_rollback(True)

    def test_long_booking_round_trip_preserves_pending_hold_and_manager_approval(self):
        from booking.postgres import PostgresRepository
        pending = Booking(str(uuid4()), self.a.id, self.room.id, self.start,
                          self.start + timedelta(hours=4), "Continuous experiment", self.now,
                          BookingStatus.PENDING_APPROVAL, "LONG_BOOKING_AWAITING_MANAGER",
                          hold_until=self.now + timedelta(hours=24), review_due_at=self.now + timedelta(hours=24),
                          created_by=self.a.id, long_booking=True,
                          long_booking_reason="The experiment requires four uninterrupted hours")
        self.repo.save_booking(pending)
        reloaded = PostgresRepository()
        self.assertEqual(reloaded.get_booking(pending.id), pending)
        self.assertEqual([item.id for item in reloaded.list_blocking_bookings(
            self.room.id, pending.start, pending.end, self.now)], [pending.id])
        approved = replace(pending, status=BookingStatus.APPROVED, reviewed_by=self.manager.id,
                           reviewed_at=self.now, decision_reason="Approved for this four-hour session")
        self.repo.save_booking(approved)
        self.assertEqual(reloaded.get_booking(approved.id), approved)
        self.assertEqual([item.id for item in reloaded.list_blocking_bookings(
            self.room.id, approved.start, approved.end, self.now + timedelta(hours=25))], [approved.id])

    def test_long_booking_database_constraints_reject_missing_reason_and_mixed_request_kinds(self):
        from booking.domain import BookingSeries
        booking = self.raw_booking(self.start, BookingStatus.PENDING_APPROVAL, long_booking=True,
                                   long_booking_reason="Continuous experiment")
        series = BookingSeries(str(uuid4()), self.a.id, self.admin.id, self.room.id,
                               str(self.start.isoweekday()), time(10), 60, self.start.date(),
                               self.start.date(), "Ordinary weekly session", self.now)
        self.repo.save_series(series)
        invalid_updates = [
            ("long_booking_reason = NULL", [], "booking_long_booking_reason_check"),
            ("long_booking_reason = '   '", [], "booking_long_booking_reason_check"),
            ("urgent = true", [], "booking_long_booking_kind_check"),
            ("additional_hours = true, additional_hours_reason = 'More weekly time'", [], "booking_long_booking_kind_check"),
            ("series_id = %s", [series.id], "booking_long_booking_kind_check"),
        ]
        for assignments, params, constraint in invalid_updates:
            with self.subTest(assignments=assignments):
                with self.assertRaises(IntegrityError) as denied, transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(f"UPDATE public.booking SET {assignments} WHERE id = %s", [*params, booking.id])
                self.assertEqual(denied.exception.__cause__.diag.constraint_name, constraint)
        self.assertEqual(self.repo.get_booking(booking.id), booking)

    def test_013_migration_can_run_twice_without_changing_long_or_additional_requests(self):
        long = self.raw_booking(self.start, BookingStatus.PENDING_APPROVAL, long_booking=True,
                                long_booking_reason="Continuous experiment", hold_until=self.now + timedelta(hours=24),
                                review_due_at=self.now + timedelta(hours=24))
        extra = self.raw_booking(self.start + timedelta(hours=2), BookingStatus.PENDING_APPROVAL,
                                 additional_hours=True, additional_hours_reason="More weekly time",
                                 active_data_collection=True, data_collection_reason="Collecting the final samples")
        migration = Path(settings.BASE_DIR) / 'database/migrations/013_long_booking_requests.sql'
        with connection.cursor() as cursor:
            cursor.execute(migration.read_text(encoding='utf-8'))
            cursor.execute(migration.read_text(encoding='utf-8'))
        self.assertEqual(self.repo.get_booking(long.id), long)
        self.assertEqual(self.repo.get_booking(extra.id), extra)

    def test_012_then_013_upgrade_preserves_normal_and_additional_booking_records(self):
        normal = self.raw_booking(self.start, BookingStatus.PENDING_APPROVAL,
                                  hold_until=self.now + timedelta(hours=24), review_due_at=self.now + timedelta(hours=24))
        extra = self.raw_booking(self.start + timedelta(hours=2), BookingStatus.APPROVED,
                                 additional_hours=True, additional_hours_reason="More weekly time",
                                 active_data_collection=True, data_collection_reason="Collecting final samples",
                                 reviewed_by=self.manager.id, reviewed_at=self.now)
        migrations = [Path(settings.BASE_DIR) / 'database/migrations' / name for name in (
            '012_additional_hours_requests.sql', '013_long_booking_requests.sql')]
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('ALTER TABLE public.booking DROP COLUMN long_booking, DROP COLUMN long_booking_reason')
                for _ in range(2):
                    for migration in migrations:
                        cursor.execute(migration.read_text(encoding='utf-8'))
            for original in (normal, extra):
                restored = self.repo.get_booking(original.id)
                self.assertEqual(restored, original)
                self.assertEqual((restored.long_booking, restored.long_booking_reason), (False, None))
            transaction.set_rollback(True)

    # Sprint 3 (2026-11-01): an existing table from main's original 011 must also converge.
    def test_011_normalizes_the_legacy_foreign_key_without_losing_email(self):
        from booking.domain import Notification
        notice = Notification(str(uuid4()), self.a.id, "BOOKING_REMINDER", "Title", "Body", self.now)
        self.repo.save_notification(notice)
        delivery = EmailDelivery(notice.id, self.a.university_email, "Subject", "Body", "PENDING", self.now, self.now)
        self.repo.save_email_delivery(delivery)
        migration = Path(settings.BASE_DIR) / 'database/migrations/011_durable_email_delivery.sql'
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('ALTER TABLE public.email_delivery RENAME CONSTRAINT email_delivery_notification_fk TO email_delivery_notification_id_fkey')
                cursor.execute(migration.read_text())
                cursor.execute(migration.read_text())
                cursor.execute("SELECT conname FROM pg_constraint WHERE conrelid='public.email_delivery'::regclass AND contype='f'")
                self.assertEqual(cursor.fetchall(), [("email_delivery_notification_fk",)])
            self.assertEqual(self.repo.get_email_delivery(notice.id), delivery)
            transaction.set_rollback(True)

    def test_concurrent_booking_reminders_create_one_notification_and_email(self):
        from booking.tests.test_reminders import concurrent_reminder_check
        self.raw_booking(self.now + timedelta(hours=3), BookingStatus.APPROVED)
        concurrent_reminder_check(self, self.service, self.a, "BOOKING_REMINDER", self.service._booking_reminders)

    def test_concurrent_induction_reminders_create_one_notification_and_email(self):
        from booking.tests.test_reminders import concurrent_reminder_check
        self.verified(self.a)
        self.now += timedelta(days=110)
        concurrent_reminder_check(self, self.service, self.a, "INDUCTION_EXPIRING", self.service._induction_reminders)

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
        delivery = EmailDelivery(older.id, self.a.university_email, "Subject", "Body", "PENDING", self.now, self.now)
        self.repo.save_email_delivery(delivery)
        claimed = self.repo.claim_email_deliveries(self.now, 1, "postgres-test", self.now + timedelta(minutes=5))
        self.assertEqual(len(claimed), 1)
        self.assertEqual((claimed[0].notification_id, claimed[0].status, claimed[0].attempts),
                         (older.id, "IN_PROGRESS", 1))
        self.assertEqual(self.repo.get_email_delivery(older.id), claimed[0])
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

    def decoded_bookings(self, wanted=Booking):
        """Ids of every booking (or ``wanted``) row read from PostgreSQL inside the with-block."""
        from booking import postgres
        original, seen = postgres._decode, []

        def spy(record_type, row):
            record = original(record_type, row)
            if record_type is wanted:
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
                 {"created_by": "not-a-uuid"},
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

    # 2026-10-29 (tasks-load-2026-10-29.md round 2: S2, S6).

    def test_load_availability_reads_each_resource_once_for_the_whole_day(self):
        short = Resource(str(uuid4()), "Short day", ResourceKind.ROOM, "Building A", "Test room",
                         required_qualification_id=self.requirement.id, opening_time=time(8), closing_time=time(10))
        self.repo.save_resource(short)
        self.raw_booking(datetime(2030, 1, 10, 9, tzinfo=SYDNEY), BookingStatus.APPROVED, student=self.b)
        day = self.start.date()

        def queries(resource):
            with CaptureQueriesContext(connection) as captured:
                result = self.service.availability(self.a, resource.id, day, 30)
            return len(captured.captured_queries), result["slots"]

        few, _ = queries(short)       # 4 slots
        many, slots = queries(self.room)  # 24 slots
        self.assertEqual(many, few)
        reasons = {slot["start"].astimezone(SYDNEY).strftime("%H:%M"): slot["reason_code"] for slot in slots}
        self.assertEqual((reasons["08:30"], reasons["09:00"], reasons["09:30"], reasons["10:00"]), (None, "BOOKED", "BOOKED", None))

    def runtime_service(self, outlook=False):
        """Serve the API and booking_json from this test's service (the runtime one refuses to start outside DEBUG)."""
        from booking import runtime
        from booking.calendar_sync import CalendarSyncService
        from booking.tests.test_outlook import FakeCalendar
        self.service.calendar_sync = CalendarSyncService(self.repo, FakeCalendar(), enabled=outlook, clock=lambda: self.now)
        return patch.object(runtime, "_service", self.service)

    def staff_list_fixture(self):
        """An on-behalf booking with an open change request, two overlapping waitlisted requests and a plain one."""
        when = datetime(2030, 1, 11, 10, tzinfo=SYDNEY)
        original = self.raw_booking(when, BookingStatus.APPROVED, created_by=self.admin.id)
        change = self.raw_booking(when + timedelta(hours=2), BookingStatus.PENDING_APPROVAL, created_by=self.a.id,
                                  replaces_id=original.id, review_due_at=when)
        first = self.raw_booking(when + timedelta(hours=4), BookingStatus.WAITLISTED, student=self.b, created_by=self.b.id)
        second = self.raw_booking(when + timedelta(hours=4), BookingStatus.WAITLISTED, student=self.person())
        return original, change, first, second

    def test_load_staff_list_json_is_the_same_with_shared_lookups(self):
        from booking.views._common import BookingListLookups, booking_json
        original, change, first, second = self.staff_list_fixture()
        everything = self.repo.list_bookings(resource_id=self.room.id)
        for outlook in (False, True):
            with self.runtime_service(outlook):
                for listed in (everything, [change, second]):  # the second list leaves the replaced booking out
                    lookups = BookingListLookups(self.service, listed)
                    for booking in listed:
                        with self.subTest(status=booking.status.value, size=len(listed), outlook=outlook):
                            self.assertEqual(booking_json(booking, lookups), booking_json(booking))
        self.enterContext(self.runtime_service())
        shared = BookingListLookups(self.service, everything)
        self.assertEqual(booking_json(original, shared)["open_change"]["id"], change.id)
        self.assertEqual(booking_json(change, shared)["replaces_booking"]["id"], original.id)
        first_in_queue = (first.created_at, first.id) < (second.created_at, second.id)  # same created_at: id decides
        self.assertEqual((booking_json(first, shared)["waitlist_position"], booking_json(second, shared)["waitlist_position"]),
                         (1, 2) if first_in_queue else (2, 1))
        self.assertEqual(booking_json(original, shared)["created_by_user"]["id"], self.admin.id)

    def test_load_booking_records_queries_do_not_grow_with_the_list(self):
        from rest_framework.test import APIClient
        self.enterContext(self.runtime_service())
        client = APIClient()
        client.force_authenticate(user=self.admin)
        url = f"/api/v1/admin/bookings/?status=ALL&resource_id={self.room.id}"

        def queries():
            with CaptureQueriesContext(connection) as captured:
                response = client.get(url, HTTP_HOST="localhost")
            self.assertEqual(response.status_code, 200, response.content[:300])
            return len(captured.captured_queries), response.json()["count"]

        self.staff_list_fixture()
        small = queries()
        for i in range(10):
            self.staff_list_fixture()  # 40 more bookings with every kind of lookup
        large = queries()
        self.assertEqual((large[0], large[1]), (small[0], small[1] + 40))

    # 2026-10-29 (tasks-load-2026-10-29.md round 3: S7, S8).

    def extra_room(self, name, requirement_id):
        room = Resource(str(uuid4()), name, ResourceKind.ROOM, "Building A", "Test room",
                        required_qualification_id=requirement_id, opening_time=time(8), closing_time=time(20))
        self.repo.save_resource(room)
        return room

    def test_load_day_overview_reads_the_person_once_and_matches_each_resource(self):
        advanced = QualificationRequirement(str(uuid4()), "Advanced", "Needs the lab induction", prerequisite_ids=(self.requirement.id,))
        self.repo.save_requirement(advanced)
        advanced_room = self.extra_room("Advanced room", advanced.id)
        self.verified(self.a)
        when = datetime(2030, 1, 10, 9, tzinfo=SYDNEY)
        self.raw_booking(when, BookingStatus.APPROVED, student=self.b)  # taken
        self.raw_booking(when + timedelta(hours=2), BookingStatus.PENDING_APPROVAL, hold_until=self.now + timedelta(days=1))  # a's own, held
        day = self.start.date()
        fields = ("can_request", "qualification_status", "resource_status", "status_reason", "slots")

        def overview(person):
            with CaptureQueriesContext(connection) as captured:
                result = self.service.day_overview(person, day, 60)
            return len(captured.captured_queries), {row["resource"].id: row for row in result["results"]}

        before, _ = overview(self.a)
        for i in range(5):
            self.extra_room(f"Extra room {i}", self.requirement.id)
        after, rows = overview(self.a)
        self.assertEqual(after, before)
        for person in (self.a, self.b):  # b has no induction: the advanced room needs its prerequisite first
            _, rows = overview(person)
            for resource in self.repo.list_resources():
                if resource.id in rows:
                    single = self.service._availability(person, resource, day, 60)
                    with self.subTest(person=person.zid, resource=resource.name):
                        self.assertEqual({key: rows[resource.id][key] for key in fields}, {key: single[key] for key in fields})
            if person is self.b:
                self.assertEqual((rows[self.room.id]["qualification_status"], rows[advanced_room.id]["qualification_status"]),
                                 ("NOT_SUBMITTED", "PREREQUISITE_REQUIRED"))

    def test_load_induction_reminders_read_only_people_with_inductions_expiring_soon(self):
        settled = [self.verified(self.person()) for _ in range(30)]  # valid for 120 days: nothing is due yet
        spy, seen = self.decoded_bookings(QualificationSubmission)
        with spy:
            self.service.process_due_requests()
        self.assertEqual(set(seen) & {item.id for item in settled}, set())

        # The latest submission still decides: c's verified induction is about to expire, d already uploaded new evidence.
        c, d = self.person(), self.person()
        self.verified(c)
        self.verified(d)
        self.now += timedelta(days=110)
        stored = self.storage.save(b"%PDF-1.4 renewal", "renewal.pdf", "application/pdf", d.id)
        self.repo.save_submission(QualificationSubmission(str(uuid4()), d.id, self.requirement.id, "Renewal", "", stored.id, self.now))
        self.service.process_due_requests()
        self.service.process_due_requests()  # sent once only

        def reminders(person):
            return len([item for item in self.repo.list_notifications(person.id) if item.kind == "INDUCTION_EXPIRING"])
        self.assertEqual((reminders(c), reminders(d)), (1, 0))

    def test_load_submission_filters_match_the_memory_repository(self):
        # Sprint 3 (2026-11-01): NULL validity, inclusive bounds, empty filters and invalid UUID list members.
        memory = MemoryRepository()
        self.verified(self.a)
        record = self.repo.list_submissions(student_id=self.a.id)[0]
        records = [replace(record, id=str(uuid4()), submitted_at=self.now + timedelta(seconds=i),
                           status=status, valid_until=valid)
                   for i, (status, valid) in enumerate([
                       (QualificationStatus.PENDING, None),
                       (QualificationStatus.VERIFIED, self.now),
                       (QualificationStatus.VERIFIED, self.now + timedelta(days=1)),
                       (QualificationStatus.REJECTED, None)])]
        for item in records:
            self.repo.save_submission(item)
        for item in self.repo.list_submissions(student_id=self.a.id):
            memory.save_submission(item)
        cases = [{}, {"student_ids": []}, {"student_ids": ["bad-uuid"]},
                 {"student_ids": ["bad-uuid", self.a.id]}, {"statuses": []},
                 {"statuses": [QualificationStatus.VERIFIED]}, {"valid_from": self.now},
                 {"valid_to": self.now}, {"valid_from": self.now, "valid_to": self.now + timedelta(days=1)}]
        for filters in cases:
            with self.subTest(filters=filters):
                self.assertEqual(self.repo.list_submissions(student_id=self.a.id, **filters),
                                 memory.list_submissions(student_id=self.a.id, **filters))

    def test_concurrent_email_workers_claim_a_job_once(self):
        from booking.domain import Notification
        from booking.postgres import PostgresRepository
        notification = Notification(str(uuid4()), self.a.id, "BOOKING_APPROVED", "Approved", "Body", self.now)
        self.repo.save_notification(notification)
        self.repo.save_email_delivery(EmailDelivery(
            notification.id, self.a.university_email, "Subject", "Body", "PENDING", self.now, self.now))
        barrier, claims, errors = threading.Barrier(2), [], []

        def claim(worker_id):
            try:
                barrier.wait()
                claimed = PostgresRepository().claim_email_deliveries(
                    self.now, 1, worker_id, self.now + timedelta(minutes=5))
                claims.append([item.notification_id for item in claimed])
            except Exception as error:  # pragma: no cover - reported below
                errors.append(error)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=claim, args=(worker_id,)) for worker_id in ("worker-a", "worker-b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(sorted(len(items) for items in claims), [0, 1])

    def test_scheduler_recovers_when_the_database_connection_is_lost(self):
        # 2026-11-01: the scheduler has no requests, so nothing else clears a connection the server has closed.
        from io import StringIO
        from types import SimpleNamespace
        from django.core.management import call_command
        cycles = []

        def lose_connection():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pid = cursor.fetchone()[0]

            def terminate():
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_terminate_backend(%s)", [pid])
                finally:
                    connections.close_all()
            thread = threading.Thread(target=terminate)
            thread.start()
            thread.join()

        def one_cycle(*_args, **_kwargs):
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            cycles.append("ok")
            if len(cycles) == 1:
                lose_connection()

        stop = unittest.mock.Mock()
        stop.wait.side_effect = [False, False, True]
        module = "booking.management.commands.run_scheduler"
        with patch(f"{module}.get_service", return_value=SimpleNamespace(repo=object())), \
                patch(f"{module}.Event", return_value=stop), \
                patch(f"{module}.call_command", side_effect=one_cycle), \
                patch(f"{module}.signal.signal"), patch(f"{module}.signal.getsignal"), \
                patch(f"{module}.logger.exception"):
            call_command("run_scheduler", "--interval-seconds", "1", stdout=StringIO(), stderr=StringIO())
        self.assertEqual(cycles, ["ok", "ok", "ok"])

    def test_email_worker_recovers_without_closing_the_request_transaction(self):
        # Sprint 3 (2026-11-01): real background connection, expired lifetime and server disconnect.
        from types import SimpleNamespace
        from booking.email_channel import EmailOutbox
        pids, wrappers = [], []

        def batch(_limit):
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_backend_pid()')
                pids.append(cursor.fetchone()[0])
            wrappers.append(connections['default'])

        outbox = EmailOutbox()
        outbox.BATCH_WINDOW_SECONDS = 0
        service = SimpleNamespace(email_delivery=SimpleNamespace(process_pending=batch))
        with patch('booking.runtime.get_service', return_value=service), self.repo.atomic():
            request_connection = connection.connection
            for cycle in range(3):
                outbox.put('wake')
                self.assertTrue(outbox.wait(5))
                self.assertEqual(len(pids), cycle + 1)
                self.assertIs(connection.connection, request_connection)
                self.assertTrue(connection.in_atomic_block)
                with connection.cursor() as cursor:
                    cursor.execute('SELECT 1')
                    self.assertEqual(cursor.fetchone(), (1,))
                    if cycle == 0:
                        cursor.execute('SELECT pg_terminate_backend(%s)', [pids[-1]])
                        self.assertTrue(cursor.fetchone()[0])
                if cycle == 1:
                    wrappers[-1].close_at = 0  # expire this worker's connection before the next batch
            self.assertEqual(len(set(pids)), 3)
            # Close on the owning worker thread; its production lifetime normally lasts until process exit.
            service.email_delivery.process_pending = lambda _limit: connections.close_all()
            outbox.put('cleanup')
            self.assertTrue(outbox.wait(5))
