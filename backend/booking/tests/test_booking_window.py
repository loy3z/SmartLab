"""Booking window: a booking must start at least one week and at most four weeks (28 days) ahead."""

from datetime import datetime, time, timedelta

from django.test import SimpleTestCase, override_settings

from uuid import uuid4

from booking.domain import BookingStatus, Principal, Role
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
        self.service.min_advance_days, self.service.max_advance_days = 7, 28  # the shipped defaults
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
            "latest_date": (self.today + timedelta(days=28)).isoformat(),
            "min_advance_days": 7, "max_advance_days": 28})

    def test_defaults_are_one_week_to_twenty_eight_days(self):
        service = BookingService(MemoryRepository(), MemoryFileStorage())
        self.assertEqual((service.min_advance_days, service.max_advance_days), (7, 28))

    def test_the_coming_week_cannot_be_booked(self):
        for days in (1, 2, 6):
            with self.subTest(days=days):
                self.assert_refused("BOOKING_TOO_SOON", days)
        self.assert_refused("BOOKING_TOO_SOON", 6, hour=19)  # the last slot of day 6 is still too soon

    def test_first_and_last_days_of_the_window_are_bookable(self):
        self.assertEqual(self.book_on(7, hour=8).status, BookingStatus.PENDING_APPROVAL)
        self.assertEqual(self.book_on(28, hour=19).status, BookingStatus.PENDING_APPROVAL)

    def test_more_than_twenty_eight_days_ahead_is_refused(self):
        self.assert_refused("BOOKING_TOO_FAR_AHEAD", 29, hour=8)

    def test_staff_booking_for_someone_uses_the_same_last_day(self):
        for days, allowed in ((28, True), (29, False)):
            with self.subTest(days=days):
                start, end = self.at(days)
                if allowed:
                    booking = self.service.create_booking(self.admin, self.room.id, start, end, "On behalf",
                                                          on_behalf_of_zid=self.student.zid)[0]
                    self.assertEqual((booking.student_id, booking.status),
                                     (self.student.id, BookingStatus.PENDING_APPROVAL))
                else:
                    with self.assertRaises(DomainError) as denied:
                        self.service.create_booking(self.admin, self.room.id, start, end, "On behalf",
                                                    on_behalf_of_zid=self.student.zid)
                    self.assertEqual(denied.exception.code, "BOOKING_TOO_FAR_AHEAD")

    def test_series_preview_and_creation_enforce_the_window_for_staff_and_beneficiaries(self):
        manager = Principal(str(uuid4()), "z9888888", "Manager", Role.MANAGER, "z9888888@ad.unsw.edu.au")
        self.repo.save_principal(manager)
        first, last = self.today + timedelta(days=28), self.today + timedelta(days=29)
        for actor in (self.admin, manager):
            self.qualification(actor)
            for on_behalf in (False, True):
                with self.subTest(role=actor.role, on_behalf=on_behalf):
                    arguments = dict(resource_id=self.room.id, weekdays=[first.isoweekday(), last.isoweekday()],
                                     start_time=time(10), duration_minutes=60, first_date=first, last_date=last,
                                     on_behalf_of_zid=self.student.zid if on_behalf else None)
                    preview = self.service.preview_series(actor, **arguments)
                    self.assertEqual([(item["available"], item["reason_code"]) for item in preview["occurrences"]],
                                     [(True, None), (False, "BOOKING_TOO_FAR_AHEAD")])
                    before = len(self.repo.list_bookings())
                    with self.assertRaises(DomainError) as denied:
                        self.service.create_series(actor, purpose="Weekly lab", **arguments)
                    self.assertEqual(denied.exception.code, "SERIES_CONFLICT")
                    self.assertEqual(denied.exception.details["dates"],
                                     [{"date": last.isoformat(), "reason_code": "BOOKING_TOO_FAR_AHEAD"}])
                    self.assertEqual(len(self.repo.list_bookings()), before)
                    series, bookings = self.service.create_series(actor, purpose="Weekly lab",
                                                                  skip_dates=[last], **arguments)
                    self.assertEqual(len(bookings), 1)
                    self.assertEqual(bookings[0].start.astimezone(SYDNEY).date(), first)
                    self.assertEqual(bookings[0].student_id, self.student.id if on_behalf else actor.id)
                    self.service.cancel_series(actor, series.id)

    def test_series_keeps_the_minimum_advance_requirement(self):
        self.qualification(self.admin)
        first, last = self.today + timedelta(days=6), self.today + timedelta(days=7)
        preview = self.service.preview_series(self.admin, self.room.id, [first.isoweekday(), last.isoweekday()],
                                              time(10), 60, first, last)
        self.assertEqual([(item["available"], item["reason_code"]) for item in preview["occurrences"]],
                         [(False, "BOOKING_TOO_SOON"), (True, None)])

    def test_configured_window_applies_to_single_bookings_and_is_rechecked_when_creating_a_series(self):
        self.qualification(self.admin)
        self.service.max_advance_days = 35
        self.assertEqual(self.book_on(35, hour=8).status, BookingStatus.PENDING_APPROVAL)
        with self.assertRaises(DomainError) as denied:
            self.book_on(36)
        self.assertEqual(denied.exception.code, "BOOKING_TOO_FAR_AHEAD")
        day = self.today + timedelta(days=35)
        arguments = dict(resource_id=self.room.id, weekdays=[day.isoweekday()], start_time=time(10),
                         duration_minutes=60, first_date=day, last_date=day)
        self.assertEqual(self.service.preview_series(self.admin, **arguments)["available_count"], 1)
        self.service.max_advance_days = 28
        with self.assertRaises(DomainError) as denied:
            self.service.create_series(self.admin, purpose="Weekly lab", **arguments)
        self.assertEqual(denied.exception.details["dates"][0]["reason_code"], "BOOKING_TOO_FAR_AHEAD")
        self.service.max_advance_days = 35
        _, bookings = self.service.create_series(self.admin, purpose="Weekly lab", **arguments)
        self.assertEqual(len(bookings), 1)

    def test_a_manager_reschedule_may_move_earlier_but_not_past_the_last_day(self):
        manager = Principal(str(uuid4()), "z9888888", "Manager", Role.MANAGER, "z9888888@ad.unsw.edu.au")
        self.repo.save_principal(manager)
        booking = self.book_on(10)
        booking = self.service.review_booking(self.admin, booking.id, "APPROVED")
        start, end = self.at(29)
        with self.assertRaises(DomainError) as denied:
            self.service.reschedule_booking(manager, booking.id, start, end)
        self.assertEqual(denied.exception.code, "BOOKING_TOO_FAR_AHEAD")
        start, end = self.at(3)  # inside the coming week: allowed for a Manager
        self.assertEqual(self.service.reschedule_booking(manager, booking.id, start, end).start, start)
        start, end = self.at(8)
        self.assertEqual(self.service.reschedule_booking(manager, booking.id, start, end).start, start)

    def test_the_window_moves_with_the_clock(self):
        week_away, beyond_window = self.at(7), self.at(29, hour=8)
        self.now += timedelta(days=1)  # one day later the same dates are 6 and 28 days away
        with self.assertRaises(DomainError) as denied:
            self.book(start=week_away[0], end=week_away[1])
        self.assertEqual(denied.exception.code, "BOOKING_TOO_SOON")
        self.assertEqual(self.book(start=beyond_window[0], end=beyond_window[1]).status, BookingStatus.PENDING_APPROVAL)

    def test_existing_requests_are_still_decided_once_they_are_inside_the_coming_week(self):
        pending = self.book(start=self.at(7)[0], end=self.at(7)[1])
        self.assertEqual(pending.status, BookingStatus.PENDING_APPROVAL)
        self.now += timedelta(days=3)  # now inside the coming week; the review window has ended meanwhile
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(pending.id).status, BookingStatus.APPROVED)

    def test_availability_marks_days_outside_the_window(self):
        for days, reason in ((6, "TOO_SOON"), (7, None), (28, None), (29, "TOO_FAR_AHEAD")):
            with self.subTest(days=days):
                result = self.service.availability(self.student, self.room.id, self.today + timedelta(days=days))
                self.assertEqual({slot["reason_code"] for slot in result["slots"]}, {reason})
                self.assertEqual({slot["available"] for slot in result["slots"]}, {reason is None})
                self.assertEqual((result["earliest_date"], result["latest_date"]),
                                 ((self.today + timedelta(days=7)).isoformat(), (self.today + timedelta(days=28)).isoformat()))
                self.assertEqual((result["min_advance_days"], result["max_advance_days"]), (7, 28))

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
        self.service.min_advance_days, self.service.max_advance_days = 7, 28

    def test_settings_configure_the_runtime_window(self):
        service = reset_runtime()
        self.assertEqual((service.min_advance_days, service.max_advance_days), (7, 28))
        with override_settings(MIN_ADVANCE_DAYS=3, MAX_ADVANCE_DAYS=14):
            service = reset_runtime()
            self.assertEqual((service.min_advance_days, service.max_advance_days), (3, 14))

    def test_too_soon_and_too_far_errors_carry_the_window(self):
        today = NOW.astimezone(SYDNEY).date()
        for offset, code in ((3, "BOOKING_TOO_SOON"), (29, "BOOKING_TOO_FAR_AHEAD")):
            with self.subTest(offset=offset):
                response = self.create_booking(payload=self.payload(day_offset=offset))
                self.assert_error(response, 400)
                self.assertEqual(response.data["error"]["code"], code)
                self.assertEqual(response.data["error"]["details"]["earliest_date"], (today + timedelta(days=7)).isoformat())
                self.assertEqual(response.data["error"]["details"]["latest_date"], (today + timedelta(days=28)).isoformat())
        self.assertEqual(self.create_booking(payload=self.payload(day_offset=7)).data["status"], "PENDING_APPROVAL")

    def test_availability_reports_the_window_for_the_date_picker(self):
        today = NOW.astimezone(SYDNEY).date()
        response = self.verified.get(f"/api/v1/resources/{self.room['id']}/availability/",
                                     {"date": (today + timedelta(days=2)).isoformat(), "duration_minutes": 60})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual({slot["reason_code"] for slot in response.data["slots"]}, {"TOO_SOON"})
        self.assertEqual(response.data["earliest_date"], (today + timedelta(days=7)).isoformat())
        self.assertEqual(response.data["latest_date"], (today + timedelta(days=28)).isoformat())
        self.assertEqual((response.data["min_advance_days"], response.data["max_advance_days"]), (7, 28))

    def test_api_enforces_day_28_and_29_for_single_on_behalf_and_series_requests(self):
        for client, extra, hour in ((self.verified, {}, 8),
                                    (self.admin, {"on_behalf_of_zid": "z1000001"}, 10),
                                    (self.manager, {"on_behalf_of_zid": "z1000001"}, 12)):
            with self.subTest(hour=hour):
                accepted = client.post("/api/v1/bookings/", {**self.payload(day_offset=28, hour=hour), **extra}, format="json")
                self.assertEqual(accepted.status_code, 201, accepted.data)
                denied = client.post("/api/v1/bookings/", {**self.payload(day_offset=29, hour=hour), **extra}, format="json")
                self.assertEqual((denied.status_code, denied.data["error"]["code"]), (400, "BOOKING_TOO_FAR_AHEAD"))

        today = NOW.astimezone(SYDNEY).date()
        first, last = today + timedelta(days=28), today + timedelta(days=29)
        body = {"resource_id": self.room["id"], "weekdays": [first.isoweekday(), last.isoweekday()],
                "start_time": "14:00", "duration_minutes": 60, "first_date": first.isoformat(),
                "last_date": last.isoformat(), "on_behalf_of_zid": "z1000001"}
        preview = self.admin.post("/api/v1/bookings/series/preview/", body, format="json")
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual([(item["available"], item["reason_code"]) for item in preview.data["occurrences"]],
                         [(True, None), (False, "BOOKING_TOO_FAR_AHEAD")])
        denied = self.admin.post("/api/v1/bookings/series/", {**body, "purpose": "Weekly lab"}, format="json")
        self.assertEqual((denied.status_code, denied.data["error"]["code"]), (409, "SERIES_CONFLICT"))
        self.assertEqual(denied.data["error"]["details"]["dates"],
                         [{"date": last.isoformat(), "reason_code": "BOOKING_TOO_FAR_AHEAD"}])
        accepted = self.admin.post("/api/v1/bookings/series/",
                                   {**body, "purpose": "Weekly lab", "skip_dates": [last.isoformat()]}, format="json")
        self.assertEqual(accepted.status_code, 201, accepted.data)
        self.assertEqual(len(accepted.data["bookings"]), 1)
