"""Edge cases around roles, inductions, cancellation and time limits.

Each test pins the behaviour the rules give the system today. A refusal is always checked together
with what it left behind, because a refused request that still holds a slot is the failure the
client asked about. Cases already covered by another module are referenced in the edge-case report
instead of being repeated here.
"""

from dataclasses import replace
from datetime import datetime, time, timedelta
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from booking.domain import BookingStatus, QualificationStatus, QualificationSubmission
from booking.exceptions import DomainError
from booking.tests.test_api import NOW, SYDNEY, BookingAPIFixtureMixin
from booking.tests.test_services import BookingFixtureMixin


class PeriodAndQuotaEdgeTests(BookingFixtureMixin, SimpleTestCase):
    """The time limits at their exact boundary, including a Sydney daylight-saving day."""

    def setUp(self):
        super().setUp()
        self.qualification()
        self.service.max_advance_days = 365  # the daylight-saving days below are months away

    def test_a_booking_cannot_end_at_its_start_or_start_in_the_past(self):
        # Both are refused before the window or opening-hours rules, so the code stays INVALID_TIME.
        for start, end in (
            (self.start, self.start),
            (self.now - timedelta(days=1), self.now - timedelta(days=1) + timedelta(hours=1)),
        ):
            with self.subTest(start=start), self.assertRaises(DomainError) as denied:
                self.book(start=start, end=end)
            self.assertEqual((denied.exception.code, denied.exception.status), ("INVALID_TIME", 400))

    def test_times_outside_opening_hours_or_across_midnight_are_refused(self):
        # A room opens 08:00-20:00: a request touching either edge is outside its hours.
        for start, end in (
            (self.start.replace(hour=7), self.start.replace(hour=8)),
            (self.start.replace(hour=20), self.start.replace(hour=21)),
        ):
            with self.subTest(start=start), self.assertRaises(DomainError) as denied:
                self.book(start=start, end=end)
            self.assertEqual(denied.exception.code, "OUTSIDE_OPENING_HOURS")

        # Two local days are refused even when the clock times look inside the hours, so a room that
        # stayed open until midnight would still not be bookable across the date boundary.
        self.repo.save_resource(replace(self.room, closing_time=time(23, 59)))
        start = self.start.replace(hour=23)
        with self.assertRaises(DomainError) as denied:
            self.book(start=start, end=start + timedelta(hours=2))
        self.assertEqual(denied.exception.code, "OUTSIDE_OPENING_HOURS")

    def test_the_weekly_allowance_allows_exactly_twelve_hours_then_refuses_the_next_slot(self):
        # Four three-hour requests are the client's 12-hour week; the fifth slot must be the one that fails.
        monday = datetime(2030, 1, 7, 10, tzinfo=SYDNEY)
        for day in range(1, 5):
            begin = monday + timedelta(days=day)
            booking = self.book(start=begin, end=begin + timedelta(hours=3))
            self.assertEqual(booking.status, BookingStatus.PENDING_APPROVAL)

        first_slot = monday + timedelta(days=5)
        with self.assertRaises(DomainError) as denied:
            self.book(start=first_slot, end=first_slot + timedelta(minutes=30))
        self.assertEqual((denied.exception.code, denied.exception.status), ("WEEKLY_LIMIT_REACHED", 409))
        self.assertEqual((denied.exception.details["used_slots"], denied.exception.details["limit_slots"]), (24, 24))
        self.assertEqual(denied.exception.details["requested_slots"], 1)
        self.assertIn("12 h", denied.exception.message)

    def test_daylight_saving_days_keep_sydney_local_time(self):
        # The booking is stored in UTC but placed on the Sydney clock, so the offset shows which
        # side of the change the day falls on (April: AEST +10, October: AEDT +11).
        for day, offset in (
            (datetime(2030, 4, 7, 10, tzinfo=SYDNEY), timedelta(hours=10)),
            (datetime(2030, 10, 6, 10, tzinfo=SYDNEY), timedelta(hours=11)),
        ):
            with self.subTest(day=day):
                booking = self.book(start=day, end=day + timedelta(hours=1))
                local = booking.start.astimezone(SYDNEY)
                self.assertEqual((local.date(), local.hour), (day.date(), 10))
                self.assertEqual(local.utcoffset(), offset)
                self.assertEqual(booking.end - booking.start, timedelta(hours=1))


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class RoleAndLifecycleAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    """What a caller may do over HTTP, and what a refusal leaves behind."""

    def test_unauthenticated_requests_are_refused_with_401(self):
        # Missing credentials are an identity problem, not a permission one: the caller gets 401.
        calls = (
            ("get", "/api/v1/bookings/", None),
            ("post", "/api/v1/bookings/", self.payload()),
            ("get", "/api/v1/admin/bookings/", None),
            ("get", "/api/v1/admin/overview/", None),
            ("post", "/api/v1/admin/process-due/", {}),
            ("patch", f"/api/v1/admin/qualification-requirements/{self.requirement_id}/", {"reviewer": "Someone"}),
            ("post", f"/api/v1/bookings/{uuid4()}/cancel/", {}),
        )
        for method, url, data in calls:
            with self.subTest(method=method, url=url):
                call = getattr(self.client, method)
                response = call(url) if data is None else call(url, data, format="json")
                self.assert_error(response, 401)

    def test_a_student_cannot_decide_a_booking_or_an_induction(self):
        created = self.create_booking(self.verified)
        self.assertEqual(created.status_code, 201, created.data)
        self.assert_error(
            self.student.post(f"/api/v1/admin/bookings/{created.data['id']}/review/",
                              {"decision": "APPROVED"}, format="json"), 403)
        submission = self.submit(self.student)
        self.assert_error(
            self.student.post(f"/api/v1/admin/qualifications/{submission['id']}/review/",
                              {"decision": "VERIFIED"}, format="json"), 403)

    def test_only_a_manager_may_take_a_resource_out_of_service(self):
        # Resource status is a Manager decision; an Admin may review requests but not change the lab.
        url = f"/api/v1/admin/resources/{self.room['id']}/status/"
        self.assert_error(self.admin.patch(url, {"status": "MAINTENANCE", "reason": "Leaking tap"}, format="json"), 403)
        saved = self.manager.patch(url, {"status": "MAINTENANCE", "reason": "Leaking tap"}, format="json")
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data["resource"]["status"], "MAINTENANCE")

    def test_an_expired_induction_refuses_the_request_and_creates_no_booking(self):
        holder = next(person for person in self.service.repo.list_principals() if person.zid == "z1000001")
        record = next(item for item in self.service.repo.list_submissions(student_id=holder.id))
        self.service.repo.save_submission(replace(record, valid_until=NOW - timedelta(minutes=1)))

        response = self.create_booking(self.verified)
        self.assert_error(response, 403)
        self.assertEqual(
            (response.data["error"]["code"], response.data["error"]["details"]["qualification_status"]),
            ("QUALIFICATION_REQUIRED", "EXPIRED"))
        self.assertEqual(self.items(self.verified.get("/api/v1/bookings/")), [])

    def test_a_missing_prerequisite_refuses_the_request_and_creates_no_booking(self):
        # Advanced training is not enough on its own: Lab Room 2 also needs the current General induction.
        requirements = {item.name: item for item in self.service.repo.list_requirements()}
        general = requirements["General laboratory induction"]
        advanced = requirements["Advanced laboratory training"]
        student = next(person for person in self.service.repo.list_principals() if person.zid == "z1000002")
        self.service.repo.save_submission(QualificationSubmission(
            id=str(uuid4()), student_id=student.id, requirement_id=advanced.id, title="Advanced certificate",
            notes="", file_id="private-file", submitted_at=NOW, status=QualificationStatus.VERIFIED,
            reviewed_by=str(uuid4()), reviewed_at=NOW, valid_until=NOW + timedelta(days=120)))
        room = next(item for item in self.items(self.verified.get("/api/v1/resources/")) if item["name"] == "Lab Room 2")

        response = self.create_booking(self.student, self.payload(resource=room))
        self.assert_error(response, 403)
        details = response.data["error"]["details"]
        self.assertEqual(
            (response.data["error"]["code"], details["prerequisite_id"], details["prerequisite_status"]),
            ("QUALIFICATION_REQUIRED", general.id, "NOT_SUBMITTED"))
        self.assertEqual(self.items(self.student.get("/api/v1/bookings/")), [])

    def test_cancelling_keeps_the_row_the_audit_record_and_the_staff_history(self):
        booking = self.create_approved()
        cancelled = self.verified.post(f"/api/v1/bookings/{booking['id']}/cancel/", {}, format="json")
        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        self.assertEqual((cancelled.data["status"], cancelled.data["reason_code"]), ("CANCELLED", "CANCELLED_BY_USER"))

        stored = self.service.repo.get_booking(booking["id"])
        self.assertIsNotNone(stored)  # cancelled, never deleted
        self.assertEqual(stored.status, BookingStatus.CANCELLED)
        audits = [item for item in self.service.repo.list_audit()
                  if item.action == "BOOKING_CANCELLED" and item.entity_id == booking["id"]]
        self.assertEqual(len(audits), 1)

        history = self.items(self.admin.get("/api/v1/admin/bookings/", {"status": "ALL"}))
        row = next(item for item in history if item["id"] == booking["id"])
        self.assertEqual(row["status"], "CANCELLED")

    def test_repeating_a_cancel_keeps_the_state_and_writes_no_second_audit_record(self):
        """A client retry must be safe: the second cancel answers 200 and changes nothing.

        Users double-click and browsers resend; the retry confirms the booking is cancelled instead of
        failing, and it must not add a second audit line or touch the stored record.
        """
        booking = self.create_approved()
        first = self.verified.post(f"/api/v1/bookings/{booking['id']}/cancel/", {}, format="json")
        self.assertEqual(first.status_code, 200, first.data)
        again = self.verified.post(f"/api/v1/bookings/{booking['id']}/cancel/", {}, format="json")
        self.assertEqual(again.status_code, 200, again.data)
        self.assertEqual(again.data["id"], booking["id"])
        self.assertEqual((again.data["status"], again.data["reason_code"]), ("CANCELLED", "CANCELLED_BY_USER"))
        audits = [item for item in self.service.repo.list_audit()
                  if item.action == "BOOKING_CANCELLED" and item.entity_id == booking["id"]]
        self.assertEqual(len(audits), 1)
        self.assertEqual(self.service.repo.get_booking(booking["id"]).status, BookingStatus.CANCELLED)

    def test_cancelling_after_the_start_is_refused_and_keeps_the_booking(self):
        booking = self.create_approved()
        self.service.clock = lambda: datetime.fromisoformat(booking["start"]) + timedelta(minutes=1)
        response = self.verified.post(f"/api/v1/bookings/{booking['id']}/cancel/", {}, format="json")
        self.assert_error(response, 409)
        self.assertEqual(response.data["error"]["code"], "REQUEST_NOT_CANCELLABLE")
        self.assertEqual(self.service.repo.get_booking(booking["id"]).status, BookingStatus.APPROVED)

    def test_cancelling_a_rejected_request_is_refused(self):
        created = self.create_booking(self.verified)
        self.assertEqual(created.status_code, 201, created.data)
        rejected = self.admin.post(f"/api/v1/admin/bookings/{created.data['id']}/review/",
                                   {"decision": "REJECTED", "reason": "Room reserved for a class"}, format="json")
        self.assertEqual(rejected.status_code, 200, rejected.data)

        response = self.verified.post(f"/api/v1/bookings/{created.data['id']}/cancel/", {}, format="json")
        self.assert_error(response, 409)
        self.assertEqual(response.data["error"]["code"], "REQUEST_NOT_CANCELLABLE")
        self.assertEqual(self.service.repo.get_booking(created.data["id"]).status, BookingStatus.REJECTED)
