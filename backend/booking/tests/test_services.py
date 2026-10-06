"""Business workflow tests, using the same repository port as a database adapter."""

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
from threading import Barrier
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from booking.domain import (
    AuditRecord, BookingStatus, Principal, QualificationRequirement,
    QualificationStatus, QualificationSubmission, Resource, ResourceKind, Role,
)
from booking.exceptions import DomainError
from booking.repository import MemoryRepository
from booking.services import BookingService
from booking.storage import MemoryFileStorage


class BookingWorkflowTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2030, 1, 7, 0, tzinfo=timezone.utc)
        self.repo = MemoryRepository()
        self.service = BookingService(
            self.repo, MemoryFileStorage(), clock=lambda: self.now, wait_hours=24
        )
        self.student = Principal(str(uuid4()), "z1111111", "First student", Role.STUDENT)
        self.other = Principal(str(uuid4()), "z2222222", "Second student", Role.STUDENT)
        self.admin = Principal(str(uuid4()), "z9999999", "Administrator", Role.ADMIN)
        for principal in (self.student, self.other, self.admin):
            self.repo.save_principal(principal)
        self.requirement = QualificationRequirement(str(uuid4()), "Lab induction", "Required induction")
        self.repo.save_requirement(self.requirement)
        self.room = Resource(
            id=str(uuid4()), name="Laboratory", kind=ResourceKind.ROOM,
            location="Building A", description="Teaching laboratory",
            required_qualification_id=self.requirement.id,
            opening_time=time(8), closing_time=time(20),
        )
        self.repo.save_resource(self.room)
        self.start = datetime(2030, 1, 10, 10, tzinfo=ZoneInfo("Australia/Sydney"))
        self.end = self.start + timedelta(hours=1)

    def qualification(self, principal=None, status=QualificationStatus.VERIFIED, valid_until=None):
        principal = principal or self.student
        submission = QualificationSubmission(
            id=str(uuid4()), student_id=principal.id, requirement_id=self.requirement.id,
            title="Induction certificate", notes="", file_id="private-file",
            submitted_at=self.now, status=status,
            reviewed_by=self.admin.id if status != QualificationStatus.PENDING else None,
            reviewed_at=self.now if status != QualificationStatus.PENDING else None,
            valid_until=valid_until,
        )
        self.repo.save_submission(submission)
        return submission

    def book(self, principal=None, **overrides):
        arguments = {
            "resource_id": self.room.id, "start": self.start, "end": self.end,
            "purpose": "Practical session",
        }
        arguments.update(overrides)
        return self.service.create_booking(principal or self.student, **arguments)[0]

    def test_parallel_submissions_cannot_double_book_a_resource(self):
        self.qualification(self.student)
        self.qualification(self.other)
        barrier = Barrier(2)

        def submit(principal):
            barrier.wait(timeout=5)
            return self.book(principal)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, (self.student, self.other)))

        self.assertCountEqual(
            [booking.status for booking in results],
            [BookingStatus.APPROVED, BookingStatus.PENDING_APPROVAL],
        )
        approved = [b for b in self.repo.list_bookings() if b.status == BookingStatus.APPROVED]
        self.assertEqual(len(approved), 1)

    def test_parallel_retries_with_same_key_return_one_booking(self):
        self.qualification()
        barrier = Barrier(2)

        def submit(_):
            barrier.wait(timeout=5)
            return self.book(idempotency_key="double-click")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))

        self.assertEqual(results[0].id, results[1].id)
        self.assertEqual(len(self.repo.list_bookings()), 1)

    def test_qualification_must_cover_booking_end_but_exact_end_is_valid(self):
        submission = self.qualification(valid_until=self.end - timedelta(seconds=1))
        with self.assertRaises(DomainError) as denied:
            self.book()
        self.assertEqual(denied.exception.status, 403)
        self.repo.save_submission(replace(submission, valid_until=self.end))
        self.assertEqual(self.book().status, BookingStatus.APPROVED)

    def test_latest_rejected_or_expired_submission_blocks_new_requests(self):
        self.qualification()
        original = self.book()
        self.now += timedelta(seconds=1)
        self.qualification(status=QualificationStatus.REJECTED)
        with self.assertRaises(DomainError) as denied:
            self.book(start=self.start + timedelta(hours=2), end=self.end + timedelta(hours=2))
        self.assertEqual(denied.exception.status, 403)
        self.assertEqual(self.repo.get_booking(original.id).status, BookingStatus.APPROVED)

        self.now += timedelta(seconds=1)
        self.qualification(valid_until=self.now - timedelta(seconds=1))
        with self.assertRaises(DomainError) as expired:
            self.book(start=self.start + timedelta(hours=2), end=self.end + timedelta(hours=2))
        self.assertEqual(expired.exception.status, 403)

    def test_24_hour_escalation_and_exact_start_expiration(self):
        self.qualification(status=QualificationStatus.PENDING)
        booking = self.book()
        self.assertEqual(booking.status, BookingStatus.WAITING_QUALIFICATION)
        self.now += timedelta(hours=24) - timedelta(microseconds=1)
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.WAITING_QUALIFICATION)
        self.now += timedelta(microseconds=1)
        changed = self.service.process_due_requests()
        self.assertEqual(len(changed), 1)
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.PENDING_APPROVAL)
        self.assertEqual(self.service.process_due_requests(), [])
        self.now = self.start
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.EXPIRED)

    def test_request_starting_within_24_hours_enters_manual_review_immediately(self):
        self.qualification(status=QualificationStatus.PENDING)
        start = self.now.astimezone(ZoneInfo("Australia/Sydney")).replace(hour=15)
        booking = self.book(start=start, end=start + timedelta(hours=1))
        self.assertEqual(booking.status, BookingStatus.PENDING_APPROVAL)
        self.assertEqual(booking.reason_code, "REQUEST_STARTS_BEFORE_REVIEW")

    def test_qualification_review_reassesses_waiting_requests_and_respects_conflicts(self):
        submission = self.qualification(status=QualificationStatus.PENDING)
        waiting = self.book()
        self.qualification(self.other)
        winner = self.book(self.other)
        reviewed, changed = self.service.review_qualification(
            self.admin, submission.id, "VERIFIED"
        )
        self.assertEqual(reviewed.status, QualificationStatus.VERIFIED)
        self.assertEqual([booking.id for booking in changed], [waiting.id])
        self.assertEqual(self.repo.get_booking(waiting.id).status, BookingStatus.PENDING_APPROVAL)
        with self.assertRaises(DomainError) as conflict:
            self.service.review_booking(self.admin, waiting.id, "APPROVED")
        self.assertEqual(conflict.exception.status, 409)
        self.service.cancel_booking(self.other, winner.id)
        approved = self.service.review_booking(self.admin, waiting.id, "APPROVED")
        self.assertEqual(approved.status, BookingStatus.APPROVED)

    def test_qualification_review_does_not_auto_approve_already_escalated_request(self):
        submission = self.qualification(status=QualificationStatus.PENDING)
        booking = self.book()
        self.now += timedelta(hours=24)
        self.service.process_due_requests()
        self.service.review_qualification(self.admin, submission.id, "VERIFIED")
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.PENDING_APPROVAL)
        approved = self.service.review_booking(self.admin, booking.id, "APPROVED")
        self.assertEqual(approved.status, BookingStatus.APPROVED)

    def test_qualification_review_observes_24_hour_deadline_without_a_prior_poll(self):
        submission = self.qualification(status=QualificationStatus.PENDING)
        booking = self.book()
        self.now += timedelta(hours=24)
        self.service.review_qualification(self.admin, submission.id, "VERIFIED")
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.PENDING_APPROVAL)

    def test_qualification_and_booking_rejections_require_reason_at_service_boundary(self):
        submission = self.qualification(status=QualificationStatus.PENDING)
        booking = self.book()
        self.now += timedelta(hours=24)
        self.service.process_due_requests()
        for review in (
            lambda: self.service.review_qualification(self.admin, submission.id, "REJECTED"),
            lambda: self.service.review_booking(self.admin, booking.id, "REJECTED"),
        ):
            with self.subTest(review=review), self.assertRaises(DomainError):
                review()
        self.assertEqual(self.repo.get_submission(submission.id).status, QualificationStatus.PENDING)
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.PENDING_APPROVAL)

    def test_booking_review_rechecks_current_qualification(self):
        self.qualification()
        first = self.book()
        candidate = self.book()
        self.service.cancel_booking(self.student, first.id)
        self.now += timedelta(seconds=1)
        self.qualification(status=QualificationStatus.REJECTED)
        with self.assertRaises(DomainError) as invalid:
            self.service.review_booking(self.admin, candidate.id, "APPROVED")
        self.assertEqual(invalid.exception.status, 409)
        self.assertEqual(self.repo.get_booking(candidate.id).status, BookingStatus.PENDING_APPROVAL)

    def test_adjacent_intervals_and_separate_equipment_do_not_conflict(self):
        self.qualification()
        first = self.book()
        adjacent = self.book(start=self.end, end=self.end + timedelta(hours=1))
        equipment = replace(self.room, id=str(uuid4()), name="Microscope", kind=ResourceKind.EQUIPMENT)
        self.repo.save_resource(equipment)
        independent = self.book(resource_id=equipment.id)
        self.assertEqual(
            [first.status, adjacent.status, independent.status], [BookingStatus.APPROVED] * 3
        )

    def test_inactive_resource_and_unaligned_or_cross_day_times_are_rejected(self):
        self.qualification()
        self.repo.save_resource(replace(self.room, active=False))
        with self.assertRaises(DomainError):
            self.book()
        self.repo.save_resource(self.room)
        for start, end in (
            (self.start + timedelta(minutes=1), self.end + timedelta(minutes=1)),
            (self.start, self.end + timedelta(days=1)),
            (self.start.astimezone().replace(tzinfo=None), self.end.astimezone().replace(tzinfo=None)),
        ):
            with self.subTest(start=start), self.assertRaises(DomainError):
                self.book(start=start, end=end)

    def test_completed_booking_cannot_be_retroactively_cancelled(self):
        self.qualification()
        booking = self.book()
        self.now = booking.end
        with self.assertRaises(DomainError):
            self.service.cancel_booking(self.student, booking.id)
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.APPROVED)


class RepositoryTransactionTests(SimpleTestCase):
    def test_failed_transaction_rolls_back_record_and_audit_together(self):
        repository = MemoryRepository()
        student = Principal("student", "z1234567", "Student", Role.STUDENT)
        repository.save_principal(student)
        with self.assertRaises(RuntimeError):
            with repository.atomic(student_ids=[student.id]):
                repository.save_principal(replace(student, active=False))
                repository.append_audit(
                    AuditRecord(
                        "audit", student.id, "DISABLE", "principal", student.id,
                        datetime(2030, 1, 1, tzinfo=timezone.utc),
                    )
                )
                raise RuntimeError("Simulated database transaction failure")

        self.assertTrue(repository.get_principal(student.id).active)
        self.assertEqual(repository.list_audit(), [])

    def test_audit_details_cannot_be_modified_through_a_returned_record(self):
        repository = MemoryRepository()
        original = {"decision": {"status": "APPROVED"}}
        repository.append_audit(
            AuditRecord(
                "audit", "admin", "REVIEW", "booking", "booking",
                datetime(2030, 1, 1, tzinfo=timezone.utc), original,
            )
        )
        original["decision"]["status"] = "REJECTED"
        result = repository.list_audit()
        result[0].details["decision"]["status"] = "CANCELLED"

        self.assertEqual(
            repository.list_audit()[0].details["decision"]["status"], "APPROVED"
        )
