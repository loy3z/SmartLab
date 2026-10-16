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

from django.conf import settings
from django.db import connection, connections
from django.test import override_settings, TransactionTestCase

from booking.domain import (
    AuditRecord, BookingStatus, Principal, QualificationRequirement, QualificationStatus,
    Resource, ResourceKind, ResourceStatus, Role,
)
from booking.exceptions import DomainError
from booking.services import BookingService

SYDNEY = ZoneInfo("Australia/Sydney")
SCHEMA = Path(settings.BASE_DIR) / "database" / "schema.sql"


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
                          required_qualification_id=advanced.id, room_id=self.room.id)
        self.repo.save_resource(device)
        self.assertEqual(self.repo.get_resource(device.id), device)
        with self.assertRaises(DomainError) as denied:  # Advanced needs the General induction first
            self.service.submit_qualification(self.a, advanced.id, "Advanced", "", b"x", "a.pdf", "application/pdf")
        self.assertEqual(denied.exception.code, "PREREQUISITE_REQUIRED")

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

    def test_resource_status_is_persisted(self):
        self.service.set_resource_status(self.manager, self.room.id, "MAINTENANCE", "Repairs")
        stored = self.repo.get_resource(self.room.id)
        self.assertEqual((stored.status, stored.status_reason), (ResourceStatus.MAINTENANCE, "Repairs"))

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
