"""Rejecting induction evidence ends every pending booking that depends on it."""

from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, override_settings

from booking.domain import (BookingStatus, QualificationRequirement, QualificationStatus,
                            QualificationSubmission, Resource, ResourceKind)
from booking.tests.test_api import BookingAPIFixtureMixin
from booking.tests.test_services import BookingFixtureMixin

SYDNEY = ZoneInfo("Australia/Sydney")
PDF = b"%PDF-1.4\nInduction certificate\n%%EOF"
REASON = "Certificate does not cover this laboratory"


class QualificationRejectionServiceTests(BookingFixtureMixin, SimpleTestCase):
    def reject(self, submission):
        return self.service.review_qualification(self.admin, submission.id, "REJECTED", REASON)

    def assert_rejected_by_qualification(self, booking_id):
        booking = self.repo.get_booking(booking_id)
        self.assertEqual(booking.status, BookingStatus.REJECTED)
        self.assertEqual(booking.reason_code, "QUALIFICATION_REJECTED")
        self.assertEqual(booking.decision_reason, REASON)
        self.assertEqual(booking.reviewed_by, self.admin.id)
        self.assertFalse(booking.blocks_resource_at(self.now))

    def test_waiting_request_is_rejected_and_slot_released_immediately(self):
        submission = self.qualification(status=QualificationStatus.PENDING)
        waiting = self.book()
        self.assertTrue(waiting.hold_is_active(self.now))
        _, changed = self.reject(submission)
        self.assertEqual([item.id for item in changed], [waiting.id])
        self.assert_rejected_by_qualification(waiting.id)
        # The hold no longer protects the slot, so a qualified student is approved at once.
        self.qualification(self.other)
        self.assertEqual(self.book(self.other).status, BookingStatus.APPROVED)

    def test_escalated_and_conflicting_requests_are_rejected_too(self):
        self.service.unverified_pending_limit = 2
        submission = self.qualification(status=QualificationStatus.PENDING)
        soon = datetime(2030, 1, 7, 15, tzinfo=SYDNEY)  # within 24 hours of now (11:00 Sydney)
        escalated = self.book(start=soon, end=soon + timedelta(hours=1))
        self.assertEqual(escalated.reason_code, "REQUEST_STARTS_BEFORE_REVIEW")
        self.qualification(self.other)
        self.book(self.other)  # approved booking on the default slot
        conflicting = self.book()
        self.assertEqual((conflicting.status, conflicting.reason_code), (BookingStatus.WAITLISTED, "TIME_CONFLICT"))
        _, changed = self.reject(submission)
        self.assertCountEqual([item.id for item in changed], [escalated.id, conflicting.id])
        for booking in (escalated, conflicting):
            self.assert_rejected_by_qualification(booking.id)

    def test_other_requirements_and_other_students_are_untouched(self):
        advanced = QualificationRequirement(str(uuid4()), "Advanced training", "")
        self.repo.save_requirement(advanced)
        studio = Resource(str(uuid4()), "Studio", ResourceKind.ROOM, "Building B", "", required_qualification_id=advanced.id)
        self.repo.save_resource(studio)
        submission = self.qualification(status=QualificationStatus.PENDING)
        self.repo.save_submission(QualificationSubmission(
            id=str(uuid4()), student_id=self.student.id, requirement_id=advanced.id, title="Advanced", notes="",
            file_id="private-file", submitted_at=self.now))
        studio_booking = self.book(resource_id=studio.id)
        self.qualification(self.other, status=QualificationStatus.PENDING)
        other_booking = self.book(self.other, start=self.start + timedelta(hours=2), end=self.end + timedelta(hours=2))
        self.reject(submission)
        self.assertEqual(self.repo.get_booking(studio_booking.id).status, BookingStatus.WAITING_QUALIFICATION)
        self.assertEqual(self.repo.get_booking(other_booking.id).status, BookingStatus.WAITING_QUALIFICATION)

    def test_student_can_resubmit_and_book_the_same_slot_again(self):
        submission = self.qualification(status=QualificationStatus.PENDING)
        first = self.book()
        self.reject(submission)
        self.now += timedelta(minutes=1)
        resubmitted = self.service.submit_qualification(self.student, self.requirement.id, "Corrected", "", PDF, "cert.pdf", "application/pdf")
        again = self.book()
        self.assertNotEqual(again.id, first.id)
        self.assertEqual(again.status, BookingStatus.WAITING_QUALIFICATION)
        self.assertTrue(again.hold_is_active(self.now))
        self.service.review_qualification(self.admin, resubmitted.id, "VERIFIED")
        self.assertEqual(self.repo.get_booking(again.id).status, BookingStatus.APPROVED)

    def test_rejection_is_recorded_in_the_audit_trail(self):
        submission = self.qualification(status=QualificationStatus.PENDING)
        booking = self.book()
        self.reject(submission)
        record = [item for item in self.repo.list_audit() if item.entity_id == booking.id][-1]
        self.assertEqual(record.action, "BOOKING_REJECTED")
        self.assertEqual(record.actor_id, self.admin.id)
        self.assertEqual(record.details["reason_code"], "QUALIFICATION_REJECTED")
        self.assertEqual(record.details["qualification_id"], submission.id)


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class QualificationRejectionAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def test_student_sees_rejected_induction_and_rejected_booking_with_reason(self):
        submission = self.submit()
        booking = self.create_booking(self.student).data
        self.assertEqual(booking["status"], "WAITING_QUALIFICATION")
        reviewed = self.admin.post(f"/api/v1/admin/qualifications/{submission['id']}/review/",
                                   {"decision": "REJECTED", "reason": REASON}, format="json")
        self.assertEqual(reviewed.status_code, 200, reviewed.data)
        self.assertEqual([(item["id"], item["status"]) for item in reviewed.data["updated_bookings"]],
                         [(booking["id"], "REJECTED")])
        dashboard = self.student.get("/api/v1/dashboard/").data
        self.assertEqual(dashboard["qualifications"][0]["status"], "REJECTED")
        self.assertEqual(dashboard["qualifications"][0]["rejection_reason"], REASON)
        detail = self.student.get(f"/api/v1/bookings/{booking['id']}/").data
        self.assertEqual((detail["status"], detail["reason_code"], detail["decision_reason"]),
                         ("REJECTED", "QUALIFICATION_REJECTED", REASON))
        self.assertFalse(detail["blocks_slot"])
        self.assertEqual(dashboard["counts"]["REJECTED"], 1)
