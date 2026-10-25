"""Sprint 3: usage report for Managers (booking/services/reports.py)."""

from datetime import timedelta

from django.test import SimpleTestCase, override_settings

from booking.exceptions import DomainError
from booking.tests.test_api import BookingAPIFixtureMixin
from booking.tests.test_sprint3 import Sprint3Fixture


class UsageReportTests(Sprint3Fixture, SimpleTestCase):
    def test_counts_hours_and_attendance(self):
        here = self.approved(self.student, days=1, hour=10)                     # checked in
        missed = self.approved(self.student, days=2, hour=10)                   # missed
        self.approved(self.other, days=3, hour=12)                              # still in the future
        cancelled = self.request(self.other, days=2, hour=14)
        self.service.cancel_booking(self.other, cancelled.id)
        self.now = here.start
        self.service.check_in(self.student, here.id)
        self.now = missed.end + timedelta(hours=1)
        report = self.service.usage_report(self.manager, self.today, self.today + timedelta(days=6))
        row = next(item for item in report["results"] if item["resource_id"] == self.room.id)
        self.assertEqual((row["approved"], row["booked_hours"], row["open_hours"]), (3, 3.0, 84.0))   # 7 days x 12 hours
        self.assertEqual((row["checked_in"], row["no_show"], row["attendance_rate"], row["cancelled"]), (1, 1, 0.5, 1))
        self.assertEqual(row["utilisation"], round(3 / 84, 3))
        self.assertEqual(report["totals"]["approved"], 3)
        self.assertEqual(report["days"], 7)

    def test_range_and_permissions(self):
        self.approved(self.student, days=1)
        outside = self.service.usage_report(self.manager, self.today + timedelta(days=5), self.today + timedelta(days=6))
        self.assertEqual(outside["results"][0]["approved"], 0)
        self.assertIsNone(outside["results"][0]["attendance_rate"])
        with self.assertRaises(DomainError):
            self.service.usage_report(self.manager, self.today, self.today - timedelta(days=1))
        self.assertEqual(self.service.usage_report(self.admin, self.today, self.today)["days"], 1)  # Admins too
        with self.assertRaises(DomainError) as denied:
            self.service.usage_report(self.student, self.today, self.today)
        self.assertEqual(denied.exception.code, "FORBIDDEN")


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class UsageReportAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def test_usage_report_api(self):
        response = self.manager.get("/api/v1/admin/reports/usage/?first_date=2030-01-01&last_date=2030-01-31")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data["first_date"], response.data["days"]), ("2030-01-01", 31))
        self.assertEqual(len(response.data["results"]), 22)                      # 2 rooms and 20 devices
        self.assertEqual(self.admin.get("/api/v1/admin/reports/usage/?first_date=2030-01-01&last_date=2030-01-31").status_code, 200)
        self.assertEqual(self.verified.get("/api/v1/admin/reports/usage/?first_date=2030-01-01&last_date=2030-01-31").status_code, 403)
        self.assertEqual(self.manager.get("/api/v1/admin/reports/usage/?first_date=2030-01-01").status_code, 400)
