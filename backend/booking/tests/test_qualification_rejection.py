"""Rejecting induction evidence ends every pending booking that depends on it."""

from datetime import timedelta
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from booking.domain import (BookingStatus, QualificationRequirement, QualificationStatus,
                            QualificationSubmission, Resource, ResourceKind)
from booking.tests.test_api import BookingAPIFixtureMixin
from booking.tests.test_services import BookingFixtureMixin

REASON = "Certificate does not cover this laboratory"


class QualificationRejectionServiceTests(BookingFixtureMixin, SimpleTestCase):
    """A person books with a verified induction, later uploads new evidence (for example after it expired),
    and that new evidence is rejected: their undecided requests that depend on it cannot be approved."""

    def reject(self, submission):
        return self.service.review_qualification(self.admin, submission.id, "REJECTED", REASON)

    def new_evidence(self, principal=None):
        self.now += timedelta(seconds=1)
        return self.qualification(principal, status=QualificationStatus.PENDING)

    def assert_rejected_by_qualification(self, booking_id):
        booking = self.repo.get_booking(booking_id)
        self.assertEqual(booking.status, BookingStatus.REJECTED)
        self.assertEqual(booking.reason_code, "QUALIFICATION_REJECTED")
        self.assertEqual(booking.decision_reason, REASON)
        self.assertEqual(booking.reviewed_by, self.admin.id)
        self.assertFalse(booking.blocks_resource_at(self.now))

    def test_pending_request_is_rejected_and_slot_passed_to_the_queue(self):
        self.qualification()
        self.qualification(self.other)
        pending = self.book()
        queued = self.book(self.other)
        self.assertEqual(queued.status, BookingStatus.WAITLISTED)
        _, changed = self.reject(self.new_evidence())
        self.assertEqual([item.id for item in changed], [pending.id])
        self.assert_rejected_by_qualification(pending.id)
        self.assertEqual(self.repo.get_booking(queued.id).status, BookingStatus.PENDING_APPROVAL)

    def test_waitlisted_requests_are_rejected_too_but_approved_bookings_are_kept(self):
        self.qualification()
        self.qualification(self.other)
        approved = self.book_approved()
        holder = self.book(self.other, start=self.end, end=self.end + timedelta(hours=1))
        waiting = self.book(start=self.end, end=self.end + timedelta(hours=1))
        self.assertEqual(waiting.status, BookingStatus.WAITLISTED)
        _, changed = self.reject(self.new_evidence())
        self.assertEqual([item.id for item in changed], [waiting.id])
        self.assert_rejected_by_qualification(waiting.id)
        self.assertEqual(self.repo.get_booking(approved.id).status, BookingStatus.APPROVED)
        self.assertEqual(self.repo.get_booking(holder.id).status, BookingStatus.PENDING_APPROVAL)

    def test_other_requirements_and_other_students_are_untouched(self):
        advanced = QualificationRequirement(str(uuid4()), "Advanced training", "")
        self.repo.save_requirement(advanced)
        studio = Resource(str(uuid4()), "Studio", ResourceKind.ROOM, "Building B", "", required_qualification_id=advanced.id)
        self.repo.save_resource(studio)
        self.qualification()
        self.repo.save_submission(QualificationSubmission(
            id=str(uuid4()), student_id=self.student.id, requirement_id=advanced.id, title="Advanced", notes="",
            file_id="private-file", submitted_at=self.now, status=QualificationStatus.VERIFIED))
        studio_booking = self.book(resource_id=studio.id)
        self.qualification(self.other)
        other_booking = self.book(self.other, start=self.start + timedelta(hours=2), end=self.end + timedelta(hours=2))
        self.reject(self.new_evidence())
        self.assertEqual(self.repo.get_booking(studio_booking.id).status, BookingStatus.PENDING_APPROVAL)
        self.assertEqual(self.repo.get_booking(other_booking.id).status, BookingStatus.PENDING_APPROVAL)

    def test_rejection_is_recorded_in_the_audit_trail(self):
        self.qualification()
        booking = self.book()
        submission = self.new_evidence()
        self.reject(submission)
        record = [item for item in self.repo.list_audit() if item.entity_id == booking.id][-1]
        self.assertEqual(record.action, "BOOKING_REJECTED")
        self.assertEqual(record.actor_id, self.admin.id)
        self.assertEqual(record.details["reason_code"], "QUALIFICATION_REJECTED")
        self.assertEqual(record.details["qualification_id"], submission.id)


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class QualificationRejectionAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def test_student_sees_rejected_induction_and_cannot_book_until_resubmitted_and_verified(self):
        submission = self.submit()
        self.assert_error(self.create_booking(self.student), 403)
        reviewed = self.admin.post(f"/api/v1/admin/qualifications/{submission['id']}/review/",
                                   {"decision": "REJECTED", "reason": REASON}, format="json")
        self.assertEqual(reviewed.status_code, 200, reviewed.data)
        self.assertEqual(reviewed.data["updated_bookings"], [])
        dashboard = self.student.get("/api/v1/dashboard/").data
        self.assertEqual((dashboard["qualifications"][0]["status"], dashboard["qualifications"][0]["rejection_reason"]),
                         ("REJECTED", REASON))
        refused = self.create_booking(self.student)
        self.assert_error(refused, 403)
        self.assertEqual(refused.data["error"]["details"]["qualification_status"], "REJECTED")
        self.verify_student()
        self.assertEqual(self.create_booking(self.student).data["status"], "PENDING_APPROVAL")
