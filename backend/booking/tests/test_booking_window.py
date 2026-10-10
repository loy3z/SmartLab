"""Booking window: a booking must start at least one week and at most one month (30 days) ahead."""

from datetime import datetime, timedelta

from django.test import SimpleTestCase, override_settings

from booking.domain import BookingStatus, QualificationStatus
from booking.exceptions import DomainError
from booking.repository import MemoryRepository
from booking.runtime import reset_runtime
from booking.services import BookingService
from booking.storage import MemoryFileStorage
from booking.tests.test_api import NOW, SYDNEY, BookingAPIFixtureMixin
from booking.tests.test_services import BookingFixtureMixin


class BookingWindowServiceTests(BookingFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.service.min_advance_days, self.service.max_advance_days = 7, 30  # the shipped defaults
        self.today = self.now.astimezone(SYDNEY).date()
        self.qualification()

    def at(self, days, hour=10):
        start = datetime.combine(self.today + timedelta(days=days), datetime.min.time(), SYDNEY).replace(hour=hour)
        return start, start + timedelta(hours=1)

    def book_on(self, days, hour=10):
        start, end = self.at(days, hour)
        return self.book(start=start, end=end)

    def assert_refused(self, code, days, hour=10):
        with self.assertRaises(DomainError) as denied:
            self.book_on(days, hour)
        self.assertEqual(denied.exception.code, code)
        self.assertEqual(denied.exception.status, 400)
        self.assertEqual(denied.exception.details, {
            "earliest_date": (self.today + timedelta(days=7)).isoformat(),
            "latest_date": (self.today + timedelta(days=30)).isoformat(),
            "min_advance_days": 7, "max_advance_days": 30})

    def test_defaults_are_one_week_to_thirty_days(self):
        service = BookingService(MemoryRepository(), MemoryFileStorage())
        self.assertEqual((service.min_advance_days, service.max_advance_days), (7, 30))

    def test_the_coming_week_cannot_be_booked(self):
        for days in (1, 2, 6):
            with self.subTest(days=days):
                self.assert_refused("BOOKING_TOO_SOON", days)
        self.assert_refused("BOOKING_TOO_SOON", 6, hour=19)  # the last slot of day 6 is still too soon

    def test_first_and_last_days_of_the_window_are_bookable(self):
        self.assertEqual(self.book_on(7, hour=8).status, BookingStatus.APPROVED)
        self.assertEqual(self.book_on(30, hour=19).status, BookingStatus.APPROVED)

    def test_more_than_thirty_days_ahead_is_refused(self):
        self.assert_refused("BOOKING_TOO_FAR_AHEAD", 31, hour=8)

    def test_reschedule_must_also_stay_inside_the_window(self):
        booking = self.book_on(10)
        for days, code in ((3, "BOOKING_TOO_SOON"), (31, "BOOKING_TOO_FAR_AHEAD")):
            start, end = self.at(days)
            with self.subTest(days=days), self.assertRaises(DomainError) as denied:
                self.service.reschedule_booking(self.student, booking.id, start, end)
            self.assertEqual(denied.exception.code, code)
        start, end = self.at(8)
        self.assertEqual(self.service.reschedule_booking(self.student, booking.id, start, end).start, start)

    def test_the_window_moves_with_the_clock(self):
        week_away, month_away = self.at(7), self.at(31, hour=8)
        self.now += timedelta(days=1)  # one day later the same dates are 6 and 30 days away
        with self.assertRaises(DomainError) as denied:
            self.book(start=week_away[0], end=week_away[1])
        self.assertEqual(denied.exception.code, "BOOKING_TOO_SOON")
        self.assertEqual(self.book(start=month_away[0], end=month_away[1]).status, BookingStatus.APPROVED)

    def test_existing_requests_are_still_decided_once_they_are_inside_the_coming_week(self):
        submission = self.qualification(self.other, status=QualificationStatus.PENDING)
        pending = self.book(self.other, start=self.at(7)[0], end=self.at(7)[1])
        self.assertEqual(pending.status, BookingStatus.WAITING_QUALIFICATION)
        self.now += timedelta(days=3)
        self.service.review_qualification(self.admin, submission.id, "VERIFIED")
        self.assertEqual(self.repo.get_booking(pending.id).status, BookingStatus.APPROVED)

    def test_availability_marks_days_outside_the_window(self):
        for days, reason in ((6, "TOO_SOON"), (7, None), (30, None), (31, "TOO_FAR_AHEAD")):
            with self.subTest(days=days):
                result = self.service.availability(self.student, self.room.id, self.today + timedelta(days=days))
                self.assertEqual({slot["reason_code"] for slot in result["slots"]}, {reason})
                self.assertEqual({slot["available"] for slot in result["slots"]}, {reason is None})
                self.assertEqual((result["earliest_date"], result["latest_date"]),
                                 ((self.today + timedelta(days=7)).isoformat(), (self.today + timedelta(days=30)).isoformat()))
                self.assertEqual((result["min_advance_days"], result["max_advance_days"]), (7, 30))

    def test_invalid_windows_are_rejected(self):
        self.assertEqual(BookingService(MemoryRepository(), MemoryFileStorage(), min_advance_days=0).min_advance_days, 0)
        for kwargs in ({"min_advance_days": -1}, {"min_advance_days": 8, "max_advance_days": 7},
                       {"max_advance_days": 0}, {"min_advance_days": 1.5}, {"max_advance_days": 366}):
            with self.subTest(**kwargs), self.assertRaises(ValueError):
                BookingService(MemoryRepository(), MemoryFileStorage(), **kwargs)


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class BookingWindowAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.service.min_advance_days, self.service.max_advance_days = 7, 30

    def test_settings_configure_the_runtime_window(self):
        service = reset_runtime()
        self.assertEqual((service.min_advance_days, service.max_advance_days), (7, 30))
        with override_settings(MIN_ADVANCE_DAYS=3, MAX_ADVANCE_DAYS=14):
            service = reset_runtime()
            self.assertEqual((service.min_advance_days, service.max_advance_days), (3, 14))

    def test_too_soon_and_too_far_errors_carry_the_window(self):
        today = NOW.astimezone(SYDNEY).date()
        for offset, code in ((3, "BOOKING_TOO_SOON"), (31, "BOOKING_TOO_FAR_AHEAD")):
            with self.subTest(offset=offset):
                response = self.create_booking(payload=self.payload(day_offset=offset))
                self.assert_error(response, 400)
                self.assertEqual(response.data["error"]["code"], code)
                self.assertEqual(response.data["error"]["details"]["earliest_date"], (today + timedelta(days=7)).isoformat())
                self.assertEqual(response.data["error"]["details"]["latest_date"], (today + timedelta(days=30)).isoformat())
        self.assertEqual(self.create_booking(payload=self.payload(day_offset=7)).data["status"], "APPROVED")

    def test_availability_reports_the_window_for_the_date_picker(self):
        today = NOW.astimezone(SYDNEY).date()
        response = self.verified.get(f"/api/v1/resources/{self.room['id']}/availability/",
                                     {"date": (today + timedelta(days=2)).isoformat(), "duration_minutes": 60})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual({slot["reason_code"] for slot in response.data["slots"]}, {"TOO_SOON"})
        self.assertEqual(response.data["earliest_date"], (today + timedelta(days=7)).isoformat())
        self.assertEqual(response.data["latest_date"], (today + timedelta(days=30)).isoformat())
        self.assertEqual((response.data["min_advance_days"], response.data["max_advance_days"]), (7, 30))
