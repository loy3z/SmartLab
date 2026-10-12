"""Sprint 1 fixed induction validity: one term, counted in days from approval."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, override_settings

from booking.domain import BookingStatus, QualificationStatus
from booking.exceptions import DomainError
from booking.repository import MemoryRepository
from booking.runtime import get_service, reset_runtime
from booking.services import BookingService
from booking.storage import MemoryFileStorage
from booking.tests.test_api import NOW, BookingAPIFixtureMixin
from booking.tests.test_services import BookingFixtureMixin

SYDNEY = ZoneInfo("Australia/Sydney")
PDF = b"%PDF-1.4\nInduction certificate\n%%EOF"


class QualificationValidityServiceTests(BookingFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.service.max_advance_days = 365  # these scenarios book months ahead to reach the expiry

    def verify_pending(self, principal=None):
        submission = self.qualification(principal, status=QualificationStatus.PENDING)
        reviewed, _ = self.service.review_qualification(self.admin, submission.id, "VERIFIED")
        return reviewed

    def test_verified_induction_expires_120_days_after_review_by_default(self):
        self.assertEqual(self.service.qualification_validity_days, 120)
        reviewed = self.verify_pending()
        self.assertEqual(reviewed.reviewed_at, self.now)
        self.assertEqual(reviewed.valid_until, self.now + timedelta(days=120))
        audit = [item for item in self.repo.list_audit() if item.action == "QUALIFICATION_VERIFIED"][-1]
        self.assertEqual(audit.details["valid_until"], reviewed.valid_until.isoformat())

    def test_rejected_induction_has_no_expiry(self):
        submission = self.qualification(status=QualificationStatus.PENDING)
        reviewed, _ = self.service.review_qualification(self.admin, submission.id, "REJECTED", "Wrong certificate")
        self.assertIsNone(reviewed.valid_until)

    def test_validity_days_are_configurable_and_bounded(self):
        service = BookingService(MemoryRepository(), MemoryFileStorage(), clock=lambda: self.now,
                                 qualification_validity_days=30)
        self.assertEqual(service.qualification_expiry(self.now), self.now + timedelta(days=30))
        for invalid in (0, 3651, 1.5, True, "120"):
            with self.subTest(days=invalid), self.assertRaises(ValueError):
                BookingService(MemoryRepository(), MemoryFileStorage(), qualification_validity_days=invalid)

    def test_booking_must_end_within_the_validity_period(self):
        self.verify_pending()
        expiry = self.now + timedelta(days=120)  # 2030-05-07 10:00 Sydney (AEST)
        inside = self.book(start=expiry - timedelta(hours=1), end=expiry)
        self.assertEqual(inside.status, BookingStatus.PENDING_APPROVAL)
        with self.assertRaises(DomainError) as denied:
            self.book(start=expiry, end=expiry + timedelta(hours=1))
        self.assertEqual(denied.exception.status, 403)
        self.assertEqual(denied.exception.code, "QUALIFICATION_REQUIRED")
        self.assertEqual(denied.exception.details["qualification_status"], "EXPIRES_BEFORE_END")

    def test_cannot_renew_early_but_can_resubmit_after_expiry(self):
        self.verify_pending()
        with self.assertRaises(DomainError) as early:
            self.service.submit_qualification(self.student, self.requirement.id, "Renewal", "", PDF, "cert.pdf", "application/pdf")
        self.assertEqual(early.exception.code, "QUALIFICATION_ALREADY_VERIFIED")

        self.now += timedelta(days=120)
        later = datetime(2030, 5, 14, 10, tzinfo=SYDNEY)
        with self.assertRaises(DomainError) as expired:
            self.book(start=later, end=later + timedelta(hours=1))
        self.assertEqual(expired.exception.details["qualification_status"], "EXPIRED")

        renewed = self.service.submit_qualification(self.student, self.requirement.id, "Renewal", "", PDF, "cert.pdf", "application/pdf")
        reviewed, _ = self.service.review_qualification(self.admin, renewed.id, "VERIFIED")
        self.assertEqual(reviewed.valid_until, self.now + timedelta(days=120))
        self.assertEqual(self.book(start=later, end=later + timedelta(hours=1)).status, BookingStatus.PENDING_APPROVAL)

    def test_request_ending_after_the_expiry_is_refused_at_submission(self):
        self.verify_pending()
        start = datetime(2030, 5, 20, 10, tzinfo=SYDNEY)  # after the 120-day expiry
        with self.assertRaises(DomainError) as denied:
            self.book(start=start, end=start + timedelta(hours=1))
        self.assertEqual(denied.exception.details["qualification_status"], "EXPIRES_BEFORE_END")

@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class QualificationValidityAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def test_review_sets_fixed_expiry_and_rejects_reviewer_supplied_expiry(self):
        submission = self.submit()
        url = f"/api/v1/admin/qualifications/{submission['id']}/review/"
        custom = self.admin.post(url, {"decision": "VERIFIED", "valid_until": "2027-12-31T00:00:00Z"}, format="json")
        self.assert_error(custom, 400)
        self.assertEqual(self.student.get(f"/api/v1/qualifications/{submission['id']}/").data["status"], "PENDING")

        reviewed = self.admin.post(url, {"decision": "VERIFIED"}, format="json")
        self.assertEqual(reviewed.status_code, 200, reviewed.data)
        expected = (NOW + timedelta(days=120)).isoformat().replace("+00:00", "Z")
        self.assertEqual(reviewed.data["submission"]["valid_until"], expected)
        self.assertEqual(reviewed.data["submission"]["effective_status"], "VERIFIED")

    @override_settings(QUALIFICATION_VALIDITY_DAYS=30)
    def test_setting_controls_service_and_seeded_demo_qualification(self):
        reset_runtime()
        service = get_service()
        self.assertEqual(service.qualification_validity_days, 30)
        seeded = [item for item in service.repo.list_submissions() if item.status == QualificationStatus.VERIFIED]
        self.assertEqual(len(seeded), 1)
        self.assertEqual(seeded[0].valid_until - seeded[0].reviewed_at, timedelta(days=30))
        self.assertLessEqual(abs(seeded[0].reviewed_at - datetime.now(timezone.utc)), timedelta(minutes=5))
