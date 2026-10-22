"""Client email, 17 Oct: staff booking, booking on behalf of someone, urgent requests, Manager-only reschedule.

- Admins and Managers may book for themselves and on behalf of other users; the booking records both the
  person it is for (student_id) and who created it (created_by).
- The same eligibility, induction, opening-hours and conflict rules apply to everyone.
- Urgent requests may skip the minimum advance window, but only a Manager can approve them.
- Routine requests are still approved automatically when the review window ends, whatever the role.
"""

import csv
import io
from datetime import datetime, timedelta
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from booking.domain import BookingStatus, Principal, Role
from booking.exceptions import DomainError
from booking.tests.test_api import SYDNEY, BookingAPIFixtureMixin
from booking.tests.test_services import BookingFixtureMixin


class StaffBookingServiceTests(BookingFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.service.min_advance_days, self.service.max_advance_days = 7, 30  # the shipped defaults
        self.manager = Principal(str(uuid4()), "z9888888", "Manager", Role.MANAGER, "z9888888@ad.unsw.edu.au")
        self.repo.save_principal(self.manager)
        self.today = self.now.astimezone(SYDNEY).date()
        self.qualification(self.student)

    def at(self, days, hour=10):
        start = datetime.combine(self.today + timedelta(days=days), datetime.min.time(), SYDNEY).replace(hour=hour)
        return start, start + timedelta(hours=1)

    def request(self, actor, days=10, hour=10, **extra):
        start, end = self.at(days, hour)
        return self.service.create_booking(actor, self.room.id, start, end, "Practical session", **extra)[0]

    def refused(self, code, call, *args, **kwargs):
        with self.assertRaises(DomainError) as denied:
            call(*args, **kwargs)
        self.assertEqual(denied.exception.code, code)
        return denied.exception

    # --- on behalf of someone -------------------------------------------------------------------------

    def test_admin_books_on_behalf_of_a_student_and_both_people_are_recorded(self):
        booking = self.request(self.admin, on_behalf_of_zid="Z1111111")
        self.assertEqual((booking.student_id, booking.created_by, booking.status),
                         (self.student.id, self.admin.id, BookingStatus.PENDING_APPROVAL))
        created = [item for item in self.repo.list_audit() if item.action == "BOOKING_CREATED"]
        self.assertEqual((created[-1].actor_id, created[-1].details["booked_for"]), (self.admin.id, self.student.id))
        # The student owns it: they can see and cancel it.
        self.assertEqual(self.service.booking_for(self.student, booking.id).id, booking.id)

    def test_eligibility_is_checked_for_the_person_booked_for(self):
        self.qualification(self.admin)
        self.refused("QUALIFICATION_REQUIRED", self.request, self.admin, on_behalf_of_zid=self.other.zid)
        self.qualification(self.other)
        self.assertEqual(self.request(self.admin, on_behalf_of_zid=self.other.zid).student_id, self.other.id)

    def test_only_staff_book_for_someone_else_and_only_for_an_active_account(self):
        self.refused("FORBIDDEN", self.request, self.student, on_behalf_of_zid=self.other.zid)
        self.refused("PERSON_NOT_FOUND", self.request, self.admin, on_behalf_of_zid="z1234567")
        self.repo.save_principal(Principal(self.other.id, self.other.zid, self.other.display_name, Role.STUDENT,
                                           self.other.university_email, active=False))
        self.refused("ACCOUNT_INACTIVE", self.request, self.admin, on_behalf_of_zid=self.other.zid)

    def test_the_creator_cannot_review_a_request_they_made_for_someone_else(self):
        booking = self.request(self.admin, on_behalf_of_zid=self.student.zid)
        self.refused("SELF_REVIEW_FORBIDDEN", self.service.review_booking, self.admin, booking.id, "APPROVED")
        self.assertEqual(self.service.review_booking(self.manager, booking.id, "APPROVED").status, BookingStatus.APPROVED)

    def test_the_same_person_cannot_get_two_overlapping_requests_through_staff(self):
        self.request(self.student)
        self.refused("DUPLICATE_BOOKING", self.request, self.admin, on_behalf_of_zid=self.student.zid)

    def test_staff_follow_the_normal_window_and_conflict_rules(self):
        self.qualification(self.manager)
        self.refused("BOOKING_TOO_SOON", self.request, self.manager, days=2)
        self.request(self.student)
        self.assertEqual(self.request(self.manager).status, BookingStatus.WAITLISTED)

    # --- urgent requests ------------------------------------------------------------------------------

    def test_urgent_request_skips_only_the_minimum_window_and_waits_for_a_manager(self):
        self.refused("BOOKING_TOO_SOON", self.request, self.student, days=2)
        self.refused("URGENT_REASON_REQUIRED", self.request, self.student, days=2, urgent=True)
        self.refused("URGENT_NOT_NEEDED", self.request, self.student, days=10, urgent=True, urgent_reason="Deadline")
        self.refused("BOOKING_TOO_FAR_AHEAD", self.request, self.student, days=31, urgent=True, urgent_reason="Deadline")
        booking = self.request(self.student, days=2, urgent=True, urgent_reason="Thesis experiment rerun")
        self.assertEqual((booking.status, booking.reason_code, booking.review_due_at, booking.urgent),
                         (BookingStatus.PENDING_APPROVAL, "URGENT_AWAITING_MANAGER", None, True))
        self.assertTrue(booking.hold_is_active(self.now))
        # Never decided automatically.
        self.now += timedelta(days=1)
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.PENDING_APPROVAL)
        self.refused("URGENT_NEEDS_MANAGER", self.service.review_booking, self.admin, booking.id, "APPROVED")
        self.refused("URGENT_NEEDS_MANAGER", self.service.review_booking, self.admin, booking.id, "REJECTED", "No")
        approved = self.service.review_booking(self.manager, booking.id, "APPROVED")
        self.assertEqual((approved.status, approved.reviewed_by), (BookingStatus.APPROVED, self.manager.id))

    def test_urgent_request_still_needs_induction_and_free_time(self):
        self.refused("QUALIFICATION_REQUIRED", self.request, self.other, days=2, urgent=True, urgent_reason="Deadline")
        self.request(self.student, days=2, urgent=True, urgent_reason="Deadline")
        self.qualification(self.other)
        self.refused("BOOKING_CONFLICT", self.request, self.other, days=2, urgent=True, urgent_reason="Deadline")

    def test_undecided_urgent_request_expires_at_its_start(self):
        booking = self.request(self.student, days=2, urgent=True, urgent_reason="Deadline")
        self.now = booking.start
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.EXPIRED)

    def test_a_manager_cannot_approve_an_urgent_request_they_created(self):
        booking = self.request(self.manager, days=2, on_behalf_of_zid=self.student.zid, urgent=True, urgent_reason="Visiting examiner")
        self.assertEqual((booking.student_id, booking.created_by), (self.student.id, self.manager.id))
        self.refused("SELF_REVIEW_FORBIDDEN", self.service.review_booking, self.manager, booking.id, "APPROVED")
        second = Principal(str(uuid4()), "z9777777", "Second manager", Role.MANAGER, "z9777777@ad.unsw.edu.au")
        self.repo.save_principal(second)
        self.assertEqual(self.service.review_booking(second, booking.id, "APPROVED").status, BookingStatus.APPROVED)

    # --- availability ---------------------------------------------------------------------------------

    def test_availability_for_someone_else_and_for_urgent_requests(self):
        day = self.today + timedelta(days=2)
        normal = self.service.availability(self.student, self.room.id, day, 60)
        self.assertEqual({slot["reason_code"] for slot in normal["slots"]}, {"TOO_SOON"})
        urgent = self.service.availability(self.student, self.room.id, day, 60, urgent=True)
        self.assertTrue(all(slot["available"] for slot in urgent["slots"]))
        mine = self.service.availability(self.admin, self.room.id, day, 60)
        self.assertEqual((mine["can_request"], mine["booking_for"]["zid"]), (False, self.admin.zid))
        for_student = self.service.availability(self.admin, self.room.id, day, 60, for_zid=self.student.zid)
        self.assertEqual((for_student["can_request"], for_student["booking_for"]["zid"]), (True, self.student.zid))
        self.refused("FORBIDDEN", self.service.availability, self.student, self.room.id, day, 60, for_zid=self.other.zid)


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class StaffBookingAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def test_admin_books_for_a_student_and_both_see_it(self):
        found = self.admin.get("/api/v1/people/lookup/", {"zid": "z1000001"})
        self.assertEqual((found.status_code, found.data["zid"]), (200, "z1000001"))
        self.assert_error(self.verified.get("/api/v1/people/lookup/", {"zid": "z1000002"}), 403)
        self.assert_error(self.admin.get("/api/v1/people/lookup/", {"zid": "z1234567"}), 404)

        response = self.create_booking(self.admin, {**self.payload(), "on_behalf_of_zid": "z1000001"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data["booked_for"]["zid"], response.data["created_by_user"]["zid"], response.data["on_behalf"]),
                         ("z1000001", "z9000001", True))
        ids = lambda client: [item["id"] for item in self.items(client.get("/api/v1/bookings/"))]
        self.assertIn(response.data["id"], ids(self.verified))
        self.assertIn(response.data["id"], ids(self.admin))
        self.assertNotIn(response.data["id"], ids(self.manager))
        self.assert_error(self.create_booking(self.verified, {**self.payload(day_offset=4), "on_behalf_of_zid": "z1000002"}), 403)

        export = self.manager.get("/api/v1/admin/bookings/export/")
        rows = list(csv.DictReader(io.StringIO(export.content.decode("utf-8-sig"))))
        row = next(item for item in rows if item["Booking ID"] == response.data["id"])
        self.assertEqual((row["Student zID"], row["Created by"]), ("z1000001", "z9000001"))

    def test_urgent_request_through_the_api(self):
        self.service.min_advance_days = 7
        payload = {**self.payload(day_offset=2), "urgent": True, "urgent_reason": "Equipment needed before a deadline"}
        created = self.create_booking(self.verified, payload)
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual((created.data["urgent"], created.data["reason_code"]), (True, "URGENT_AWAITING_MANAGER"))
        queue = self.items(self.admin.get("/api/v1/admin/bookings/"))
        self.assertTrue(any(item["id"] == created.data["id"] and item["urgent"] for item in queue))
        path = f"/api/v1/admin/bookings/{created.data['id']}/review/"
        self.assert_error(self.admin.post(path, {"decision": "APPROVED"}, format="json"), 403)
        self.assertEqual(self.manager.post(path, {"decision": "APPROVED"}, format="json").data["status"], "APPROVED")
        slots = self.verified.get(f"/api/v1/resources/{self.room['id']}/availability/",
                                  {"date": (datetime.fromisoformat(payload["start"]).date() + timedelta(days=0)).isoformat(),
                                   "duration_minutes": 60, "urgent": "true"})
        self.assertEqual(slots.status_code, 200, slots.data)
        self.assertTrue(slots.data["urgent"])
