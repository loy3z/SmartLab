"""Duration-based approval, Manager resource status, user creation and booking reports."""

import csv
import io
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from booking.domain import BookingStatus, Principal, QualificationStatus, ResourceStatus, Role
from booking.exceptions import DomainError
from booking.tests.test_api import BookingAPIFixtureMixin
from booking.tests.test_services import BookingFixtureMixin


class ServiceFixture(BookingFixtureMixin):
    def setUp(self):
        super().setUp()
        self.manager = Principal(str(uuid4()), "z9888888", "Manager", Role.MANAGER, "z9888888@ad.unsw.edu.au")
        self.repo.save_principal(self.manager)

    def make_student(self, zid):
        principal = Principal(str(uuid4()), zid, zid, Role.STUDENT, f"{zid}@ad.unsw.edu.au")
        self.repo.save_principal(principal)
        return principal

    def book_minutes(self, minutes, principal=None, offset_minutes=0):
        start = self.start + timedelta(minutes=offset_minutes)
        booking = self.book(principal, start=start, end=start + timedelta(minutes=minutes))
        self.now += timedelta(seconds=1)  # requests arrive one after another
        return booking

    def status(self, booking):
        return self.repo.get_booking(booking.id).status


class DurationApprovalTests(ServiceFixture, SimpleTestCase):
    def test_up_to_120_minutes_is_automatic_and_longer_goes_to_a_reviewer(self):
        self.qualification()
        self.assertEqual(self.room.auto_approve_max_minutes, 120)
        self.assertEqual(self.book_minutes(120).status, BookingStatus.APPROVED)
        long = self.book_minutes(150, offset_minutes=180)
        self.assertEqual((long.status, long.reason_code), (BookingStatus.PENDING_APPROVAL, "DURATION_REVIEW"))
        self.assertEqual(long.hold_until, long.start)

    def test_long_request_keeps_its_slot_until_decided_and_others_queue_behind_it(self):
        self.qualification()
        other = self.make_student("z3333333")
        self.qualification(other)
        long = self.book_minutes(180)
        queued = self.book_minutes(60, other)
        self.assertEqual((queued.status, queued.reason_code), (BookingStatus.WAITLISTED, "TEMPORARY_HOLD_CONFLICT"))
        self.now += timedelta(days=1)  # far beyond the 30-minute induction hold
        self.service.process_due_requests()
        self.assertEqual(self.status(long), BookingStatus.PENDING_APPROVAL)
        self.assertEqual(self.status(queued), BookingStatus.WAITLISTED)
        self.service.review_booking(self.admin, long.id, "REJECTED", "Too long for a teaching week")
        self.assertEqual(self.status(queued), BookingStatus.APPROVED)

    def test_reviewer_can_approve_the_long_request(self):
        self.qualification()
        long = self.book_minutes(240)
        approved = self.service.review_booking(self.admin, long.id, "APPROVED", "")
        self.assertEqual((approved.status, approved.reason_code), (BookingStatus.APPROVED, "MANUALLY_APPROVED"))

    def test_long_request_still_needs_review_after_induction_is_verified(self):
        submission = self.qualification(status=QualificationStatus.PENDING)
        long = self.book_minutes(180)
        self.assertEqual(long.status, BookingStatus.WAITING_QUALIFICATION)
        self.service.review_qualification(self.admin, submission.id, "VERIFIED")
        current = self.repo.get_booking(long.id)
        self.assertEqual((current.status, current.reason_code), (BookingStatus.PENDING_APPROVAL, "DURATION_REVIEW"))
        self.assertEqual(current.hold_until, current.start)

    def test_waitlisted_long_request_is_promoted_to_review_not_approval(self):
        first, second = self.make_student("z3333333"), self.make_student("z4444444")
        self.qualification(first)
        self.qualification(second)
        short = self.book_minutes(60, first)
        long = self.book_minutes(180, second)
        self.assertEqual(long.status, BookingStatus.WAITLISTED)
        self.service.cancel_booking(first, short.id)
        current = self.repo.get_booking(long.id)
        self.assertEqual((current.status, current.reason_code), (BookingStatus.PENDING_APPROVAL, "DURATION_REVIEW"))
        self.assertEqual(current.hold_until, current.start)

    def test_reschedule_cannot_exceed_the_automatic_limit(self):
        self.qualification()
        booking = self.book_minutes(60)
        with self.assertRaises(DomainError) as denied:
            self.service.reschedule_booking(self.student, booking.id, self.start, self.start + timedelta(minutes=150))
        self.assertEqual(denied.exception.code, "RESCHEDULE_NEEDS_REVIEW")
        self.assertEqual(denied.exception.details, {"auto_approve_max_minutes": 120})
        moved = self.service.reschedule_booking(self.student, booking.id, self.start, self.start + timedelta(minutes=120))
        self.assertEqual(moved.end - moved.start, timedelta(minutes=120))

    def test_availability_can_ignore_the_booking_being_rescheduled(self):
        self.qualification()
        booking = self.book_minutes(60)
        day = self.start.date()
        def slot_at_start(**kwargs):
            result = self.service.availability(self.student, self.room.id, day, 90, **kwargs)
            return next(slot for slot in result["slots"] if slot["start"] == self.start)
        before = slot_at_start()
        self.assertEqual((before["reason_code"], before["requested_by_me"]), ("BOOKED", True))
        after = slot_at_start(exclude_booking_id=booking.id)
        self.assertEqual((after["available"], after["requested_by_me"]), (True, False))
        other = self.make_student("z3333333")
        with self.assertRaises(DomainError):
            self.service.availability(other, self.room.id, day, 90, exclude_booking_id=booking.id)

    def test_manager_sets_the_limit_per_resource(self):
        self.qualification()
        updated = self.service.set_booking_policy(self.manager, self.room.id, auto_approve_max_minutes=240)
        self.assertEqual((updated.auto_approve_max_minutes, updated.pending_hold_minutes), (240, 30))
        self.assertEqual(self.book_minutes(180).status, BookingStatus.APPROVED)
        with self.assertRaises(DomainError) as denied:
            self.service.set_booking_policy(self.admin, self.room.id, auto_approve_max_minutes=60)
        self.assertEqual(denied.exception.status, 403)
        for value in (0, 1441, True, None):
            with self.subTest(value=value), self.assertRaises(DomainError):
                self.service.set_booking_policy(self.manager, self.room.id, auto_approve_max_minutes=value)


class ResourceStatusTests(ServiceFixture, SimpleTestCase):
    def close(self, status="MAINTENANCE", reason="Fume hood repair"):
        return self.service.set_resource_status(self.manager, self.room.id, status, reason)

    def test_maintenance_blocks_new_requests_but_keeps_existing_bookings(self):
        self.qualification()
        kept = self.book_minutes(60)
        resource, affected = self.close()
        self.assertEqual((resource.status, resource.status_reason), (ResourceStatus.MAINTENANCE, "Fume hood repair"))
        self.assertEqual([item.id for item in affected], [kept.id])
        self.assertEqual(self.status(kept), BookingStatus.APPROVED)
        with self.assertRaises(DomainError) as denied:
            self.book_minutes(60, offset_minutes=120)
        self.assertEqual(denied.exception.code, "RESOURCE_UNAVAILABLE")
        self.assertEqual(denied.exception.details, {"resource_status": "MAINTENANCE", "status_reason": "Fume hood repair"})

    def test_availability_shows_the_closure(self):
        self.qualification()
        self.close("CLOSED", "End of term")
        result = self.service.availability(self.student, self.room.id, self.start.date())
        self.assertEqual({slot["reason_code"] for slot in result["slots"]}, {"RESOURCE_UNAVAILABLE"})
        self.assertEqual((result["resource_status"], result["status_reason"], result["can_request"]), ("CLOSED", "End of term", False))

    def test_waitlist_waits_while_closed_and_is_promoted_on_reopening(self):
        first, second = self.make_student("z3333333"), self.make_student("z4444444")
        self.qualification(first)
        self.qualification(second)
        held = self.book_minutes(60, first)
        queued = self.book_minutes(60, second)
        self.close()
        self.service.cancel_booking(first, held.id)
        self.assertEqual(self.status(queued), BookingStatus.WAITLISTED)
        with self.assertRaises(DomainError):
            self.service.review_booking(self.admin, queued.id, "APPROVED", "")
        resource, _ = self.service.set_resource_status(self.manager, self.room.id, "AVAILABLE", "ignored")
        self.assertIsNone(resource.status_reason)
        self.assertEqual(self.status(queued), BookingStatus.APPROVED)

    def test_rules_for_changing_status(self):
        with self.assertRaises(DomainError) as denied:
            self.close(reason=" ")
        self.assertEqual(denied.exception.code, "REASON_REQUIRED")
        for actor in (self.admin, self.student):
            with self.subTest(actor=actor.zid), self.assertRaises(DomainError) as denied:
                self.service.set_resource_status(actor, self.room.id, "CLOSED", "x")
            self.assertEqual(denied.exception.status, 403)
        with self.assertRaises(DomainError):
            self.close("BROKEN")
        self.close()
        audit = [item for item in self.repo.list_audit() if item.action == "RESOURCE_STATUS_CHANGED"]
        self.assertEqual(audit[-1].details, {"previous_status": "AVAILABLE", "status": "MAINTENANCE", "reason": "Fume hood repair"})

    def test_staff_cancellation_is_marked(self):
        self.qualification()
        booking = self.book_minutes(60)
        self.assertEqual(self.service.cancel_booking(self.manager, booking.id).reason_code, "CANCELLED_BY_STAFF")


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class ManagerToolsAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def test_long_request_through_the_api(self):
        response = self.create_booking(payload=self.payload(minutes=180))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data["status"], response.data["reason_code"]), ("PENDING_APPROVAL", "DURATION_REVIEW"))
        self.assertEqual(self.room["auto_approve_max_minutes"], 120)
        availability = self.verified.get(f"/api/v1/resources/{self.room['id']}/availability/",
                                         {"date": self.payload()["start"][:10], "duration_minutes": 150})
        self.assertEqual((availability.data["needs_review"], availability.data["auto_approve_max_minutes"]), (True, 120))

    def test_booking_policy_accepts_either_setting(self):
        url = f"/api/v1/admin/resources/{self.room['id']}/booking-policy/"
        changed = self.manager.patch(url, {"auto_approve_max_minutes": 90}, format="json")
        self.assertEqual(changed.data, {"resource_id": self.room["id"], "pending_hold_minutes": 30, "auto_approve_max_minutes": 90})
        self.assert_error(self.manager.patch(url, {}, format="json"), 400)
        self.assertEqual(self.admin.get(url).data["auto_approve_max_minutes"], 90)

    def test_room_status_endpoint(self):
        booking = self.create_booking().data
        url = f"/api/v1/admin/resources/{self.room['id']}/status/"
        self.assert_error(self.admin.patch(url, {"status": "CLOSED", "reason": "x"}, format="json"), 403)
        self.assert_error(self.manager.patch(url, {"status": "CLOSED"}, format="json"), 400)
        changed = self.manager.patch(url, {"status": "MAINTENANCE", "reason": "Repairs"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(changed.data["resource"]["status"], "MAINTENANCE")
        self.assertEqual([item["id"] for item in changed.data["affected_bookings"]], [booking["id"]])
        self.assertEqual(changed.data["affected_bookings"][0]["student"]["zid"], "z1000001")
        listed = next(item for item in self.items(self.verified.get("/api/v1/resources/")) if item["id"] == self.room["id"])
        self.assertEqual((listed["status"], listed["status_reason"]), ("MAINTENANCE", "Repairs"))
        refused = self.create_booking(payload=self.payload(hour=14))
        self.assert_error(refused, 409)
        self.assertEqual(refused.data["error"]["code"], "RESOURCE_UNAVAILABLE")
        cancelled = self.manager.post(f"/api/v1/bookings/{booking['id']}/cancel/", {}, format="json")
        self.assertEqual(cancelled.data["reason_code"], "CANCELLED_BY_STAFF")

    def test_add_manager_creates_a_new_manager_account(self):
        url = "/api/v1/admin/users/managers/"
        body = {"zid": "Z5123456", "display_name": "Lab Owner", "university_email": "z5123456@ad.unsw.edu.au"}
        self.assert_error(self.admin.post(url, body, format="json"), 403)
        created = self.manager.post(url, body, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual((created.data["zid"], created.data["role"], created.data["active"]), ("z5123456", "MANAGER", True))
        self.assertEqual(created.data["induction_status"], "INCOMPLETE")  # no induction is needed to be a Manager
        duplicate = self.manager.post(url, body, format="json")
        self.assert_error(duplicate, 409)
        self.assertEqual(duplicate.data["error"]["code"], "USER_EXISTS")
        self.assert_error(self.manager.post(url, {**body, "zid": "z1000001"}, format="json"), 409)  # existing people are not converted
        for bad in ({**body, "zid": "5123456"}, {**body, "zid": "z1234568", "university_email": "bad"},
                    {**body, "zid": "z1234569", "role": "STUDENT"}, {**body, "zid": "z1234570", "display_name": ""}):
            with self.subTest(bad=bad):
                self.assert_error(self.manager.post(url, bad, format="json"), 400)
        self.assertEqual(self.login("z5123456").get("/api/v1/admin/users/").status_code, 200)
        self.assertEqual(self.manager.post("/api/v1/admin/users/", body, format="json").status_code, 405)  # no other way to add people
        audit = self.items(self.manager.get("/api/v1/admin/audit/", {"action": "MANAGER_CREATED"}))
        self.assertEqual([item["details"]["zid"] for item in audit], ["z5123456"])

    def test_staff_booking_list_filters_and_shows_who_booked(self):
        approved = self.create_booking().data
        self.submit()
        waiting = self.create_booking(self.student, self.payload(hour=14)).data
        default = self.items(self.admin.get("/api/v1/admin/bookings/"))
        self.assertEqual(default, [])  # still the manual-approval queue by default
        everything = self.items(self.admin.get("/api/v1/admin/bookings/", {"status": "ALL"}))
        self.assertEqual([item["id"] for item in everything], [approved["id"], waiting["id"]])
        self.assertEqual(everything[0]["student"]["zid"], "z1000001")
        self.assertEqual(everything[0]["resource_name"], self.room["name"])
        some = self.items(self.admin.get("/api/v1/admin/bookings/", {"status": "APPROVED,CANCELLED"}))
        self.assertEqual([item["id"] for item in some], [approved["id"]])
        mine = self.items(self.admin.get("/api/v1/admin/bookings/", {"status": "ALL", "student_id": waiting["student_id"]}))
        self.assertEqual([item["id"] for item in mine], [waiting["id"]])
        later = self.items(self.admin.get("/api/v1/admin/bookings/", {"status": "ALL", "since": waiting["start"]}))
        self.assertEqual([item["id"] for item in later], [waiting["id"]])
        for bad in ({"status": "NOPE"}, {"status": "APPROVED,,X"}, {"since": "2026-10-10T00:00:00"}, {"unknown": "1"}):
            with self.subTest(bad=bad):
                self.assert_error(self.admin.get("/api/v1/admin/bookings/", bad), 400)
        self.assert_error(self.verified.get("/api/v1/admin/bookings/", {"status": "ALL"}), 403)

    def test_manager_exports_every_booking_as_csv(self):
        payload = {**self.payload(), "purpose": "=HYPERLINK(\"x\")"}
        booking = self.create_booking(payload=payload).data
        self.assert_error(self.admin.get("/api/v1/admin/bookings/export/"), 403)
        response = self.manager.get("/api/v1/admin/bookings/export/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("bookings.csv", response["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(rows[0][:4], ["Booking ID", "Status", "Reason", "Resource"])
        self.assertEqual(len(rows), 2)
        row = dict(zip(rows[0], rows[1]))
        self.assertEqual((row["Booking ID"], row["Status"], row["Student zID"], row["Minutes"]), (booking["id"], "APPROVED", "z1000001", "60"))
        self.assertEqual((row["Date"], row["Start"]), (payload["start"][:10], payload["start"][11:16]))
        self.assertTrue(row["Purpose"].startswith("'="))
        empty = self.manager.get("/api/v1/admin/bookings/export/", {"status": "CANCELLED"})
        self.assertEqual(len(list(csv.reader(io.StringIO(empty.content.decode("utf-8-sig"))))), 1)

    def test_demo_seed_uses_the_default_limit(self):
        resource = self.service.repo.get_resource(self.room["id"])
        self.assertEqual(resource.auto_approve_max_minutes, 120)
        now = self.service.now()
        self.assertTrue(replace(resource, auto_approve_max_minutes=60).needs_review(now, now + timedelta(minutes=90)))
        self.assertFalse(resource.needs_review(now, now + timedelta(minutes=120)))
