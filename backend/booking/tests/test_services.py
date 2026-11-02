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


class BookingFixtureMixin:
    def setUp(self):
        self.now = datetime(2030, 1, 7, 0, tzinfo=timezone.utc)
        self.repo = MemoryRepository()
        self.service = BookingService(
            self.repo, MemoryFileStorage(), clock=lambda: self.now,
            # Workflow tests book a few days ahead; the booking window has its own tests in test_booking_window.py.
            min_advance_days=0, max_advance_days=7,
        )
        self.student = Principal(str(uuid4()), "z1111111", "First student", Role.STUDENT, "z1111111@ad.unsw.edu.au")
        self.other = Principal(str(uuid4()), "z2222222", "Second student", Role.STUDENT, "z2222222@ad.unsw.edu.au")
        self.admin = Principal(str(uuid4()), "z9999999", "Administrator", Role.ADMIN, "z9999999@ad.unsw.edu.au")
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

    def book_approved(self, principal=None, **overrides):
        """Submit a request and have the Admin approve it (every request starts pending)."""
        booking = self.book(principal, **overrides)
        return self.service.review_booking(self.admin, booking.id, "APPROVED")

class BookingWorkflowTests(BookingFixtureMixin, SimpleTestCase):
    def test_normal_booking_uses_whole_half_hour_slots_and_stops_at_six(self):
        self.qualification()
        six_slots = self.book(end=self.start + timedelta(hours=3))
        self.assertEqual(six_slots.status, BookingStatus.PENDING_APPROVAL)

        with self.assertRaises(DomainError) as too_long:
            self.book(start=self.start + timedelta(hours=4), end=self.start + timedelta(hours=7, minutes=30))
        self.assertEqual(too_long.exception.code, "DURATION_LIMIT")
        self.assertEqual(too_long.exception.details, {
            "max_slots": 6, "slot_minutes": 30, "resource_max_minutes": 480,
        })

        with self.assertRaises(DomainError) as partial_slot:
            self.book(start=self.start + timedelta(hours=4), end=self.start + timedelta(hours=4, minutes=15))
        self.assertEqual(partial_slot.exception.code, "INVALID_SLOT_COUNT")

    def test_resource_may_keep_a_shorter_normal_booking_limit(self):
        self.qualification()
        self.room = replace(self.room, max_booking_minutes=120)
        self.repo.save_resource(self.room)
        self.assertEqual(self.book(end=self.start + timedelta(hours=2)).status, BookingStatus.PENDING_APPROVAL)
        with self.assertRaises(DomainError) as denied:
            self.book(start=self.start + timedelta(hours=3), end=self.start + timedelta(hours=5, minutes=30))
        self.assertEqual((denied.exception.code, denied.exception.details["max_slots"]), ("DURATION_LIMIT", 4))

    def test_availability_reports_the_effective_normal_slot_limit(self):
        self.qualification()
        result = self.service.availability(self.student, self.room.id, self.start.date(), 180)
        self.assertEqual(
            (result["booking_slot_minutes"], result["max_booking_slots"], result["max_booking_minutes"]),
            (30, 6, 180),
        )
        with self.assertRaises(DomainError) as denied:
            self.service.availability(self.student, self.room.id, self.start.date(), 210)
        self.assertEqual(denied.exception.code, "INVALID_DURATION")

    def test_parallel_submissions_cannot_double_book_a_resource(self):
        self.qualification(self.student)
        self.qualification(self.other)
        barrier = Barrier(2)

        def submit(principal):
            barrier.wait(timeout=5)
            return self.book(principal)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, (self.student, self.other)))

        self.assertCountEqual([booking.status for booking in results],
                              [BookingStatus.PENDING_APPROVAL, BookingStatus.WAITLISTED])
        holders = [b for b in self.repo.list_bookings() if b.status == BookingStatus.PENDING_APPROVAL]
        self.assertEqual(len(holders), 1)

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

    def test_parallel_submissions_cannot_exceed_the_future_booking_limit(self):
        self.qualification()
        self.service._override_rule(max_active_future_bookings=8)
        for index in range(7):
            start = self.start + timedelta(hours=index)
            self.book(start=start, end=start + timedelta(minutes=30))
        barrier = Barrier(2)

        def submit(index):
            start = self.start + timedelta(days=1, hours=index)
            barrier.wait(timeout=5)
            try:
                return self.book(start=start, end=start + timedelta(minutes=30)).status
            except DomainError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))

        self.assertCountEqual(results, [BookingStatus.PENDING_APPROVAL, "FUTURE_BOOKING_LIMIT_REACHED"])
        active = [item for item in self.repo.list_bookings()
                  if item.student_id == self.student.id and item.status in (
                      BookingStatus.WAITING_QUALIFICATION,
                      BookingStatus.PENDING_APPROVAL,
                      BookingStatus.WAITLISTED,
                      BookingStatus.APPROVED,
                  )]
        self.assertEqual(len(active), 8)

    def test_qualification_must_cover_booking_end_but_exact_end_is_valid(self):
        submission = self.qualification(valid_until=self.end - timedelta(seconds=1))
        with self.assertRaises(DomainError) as denied:
            self.book()
        self.assertEqual((denied.exception.status, denied.exception.details["qualification_status"]), (403, "EXPIRES_BEFORE_END"))
        self.repo.save_submission(replace(submission, valid_until=self.end))
        self.assertEqual(self.book().status, BookingStatus.PENDING_APPROVAL)

    def test_only_a_verified_induction_allows_a_request(self):
        for status in (QualificationStatus.PENDING, QualificationStatus.REJECTED):
            with self.subTest(status=status):
                self.qualification(status=status)
                with self.assertRaises(DomainError) as denied:
                    self.book()
                self.assertEqual((denied.exception.code, denied.exception.details["qualification_status"]),
                                 ("QUALIFICATION_REQUIRED", status.value))
                self.now += timedelta(seconds=1)
        with self.assertRaises(DomainError):
            self.book(self.other)  # never submitted
        self.qualification()
        self.assertEqual(self.book().status, BookingStatus.PENDING_APPROVAL)

    def test_latest_rejected_or_expired_submission_blocks_new_requests(self):
        self.qualification()
        original = self.book_approved()
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

    def test_pending_request_is_decided_automatically_when_the_review_window_ends(self):
        self.qualification()
        booking = self.book()
        self.assertEqual((booking.status, booking.reason_code), (BookingStatus.PENDING_APPROVAL, "AWAITING_REVIEW"))
        self.assertEqual(booking.hold_until, self.now + timedelta(hours=24))
        self.assertEqual(booking.review_due_at, booking.hold_until)
        self.now = booking.review_due_at - timedelta(microseconds=1)
        self.assertEqual(self.service.process_due_requests(), [])
        self.now = booking.review_due_at
        changed = self.service.process_due_requests()
        self.assertEqual([(item.status, item.reason_code, item.reviewed_by) for item in changed],
                         [(BookingStatus.APPROVED, "AUTO_APPROVED_AFTER_REVIEW_WINDOW", "SYSTEM")])
        self.assertEqual(self.service.process_due_requests(), [])

    def test_review_window_never_runs_past_the_start_and_undecided_requests_expire_at_start(self):
        self.qualification()
        self.room = replace(self.room, pending_hold_minutes=20160)
        self.repo.save_resource(self.room)
        booking = self.book()
        self.assertEqual(booking.review_due_at, booking.start)
        self.now = booking.start
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.EXPIRED)

    def test_window_end_rejects_a_request_that_no_longer_follows_the_rules(self):
        self.qualification()
        booking = self.book()
        self.now += timedelta(seconds=1)
        self.qualification(valid_until=booking.end - timedelta(seconds=1))  # renewed evidence ends before the booking
        self.now = booking.review_due_at
        changed = self.service.process_due_requests()
        self.assertEqual([(item.status, item.reason_code) for item in changed],
                         [(BookingStatus.REJECTED, "AUTO_REJECTED_QUALIFICATION")])
        self.assertIn("EXPIRES_BEFORE_END", changed[0].decision_reason)

    def test_admin_can_decide_before_the_window_ends(self):
        self.qualification()
        approved = self.service.review_booking(self.admin, self.book().id, "APPROVED")
        self.assertEqual((approved.status, approved.reason_code), (BookingStatus.APPROVED, "MANUALLY_APPROVED"))
        rejected = self.service.review_booking(self.admin, self.book(start=self.end, end=self.end + timedelta(hours=1)).id,
                                               "REJECTED", "Room reserved for a class")
        self.assertEqual((rejected.status, rejected.decision_reason), (BookingStatus.REJECTED, "Room reserved for a class"))
        self.now += timedelta(days=2)
        self.assertEqual(self.service.process_due_requests(), [])

    def test_qualification_and_booking_rejections_require_reason_at_service_boundary(self):
        submission = self.qualification(self.other, status=QualificationStatus.PENDING)
        self.qualification()
        booking = self.book()
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
        candidate = self.book()
        self.now += timedelta(seconds=1)
        self.qualification(status=QualificationStatus.REJECTED)  # recorded directly, bypassing review side effects
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
        self.assertEqual([first.status, adjacent.status, independent.status], [BookingStatus.PENDING_APPROVAL] * 3)

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
        booking = self.book_approved()
        self.now = booking.end
        with self.assertRaises(DomainError):
            self.service.cancel_booking(self.student, booking.id)
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.APPROVED)


class RepositoryTransactionTests(SimpleTestCase):
    def test_failed_transaction_rolls_back_record_and_audit_together(self):
        repository = MemoryRepository()
        student = Principal("student", "z1234567", "Student", Role.STUDENT, "z1234567@ad.unsw.edu.au")
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
