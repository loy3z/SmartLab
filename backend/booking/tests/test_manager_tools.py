"""Duration-based approval, Manager resource status, user creation and booking reports."""

import csv
import io
from datetime import timedelta
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from booking.domain import BookingStatus, Principal, ResourceStatus, Role
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

    def get(self, booking):
        return self.repo.get_booking(booking.id)

    def status(self, booking):
        return self.repo.get_booking(booking.id).status


class RescheduleAvailabilityTests(ServiceFixture, SimpleTestCase):
    def test_availability_can_ignore_the_booking_being_rescheduled(self):
        self.qualification()
        booking = self.service.review_booking(self.admin, self.book_minutes(60).id, "APPROVED")
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

    def test_reschedule_may_change_the_length(self):
        self.qualification()
        booking = self.service.review_booking(self.admin, self.book_minutes(60).id, "APPROVED")
        moved = self.service.reschedule_booking(self.manager, booking.id, self.start, self.start + timedelta(minutes=180))
        self.assertEqual((moved.status, moved.end - moved.start), (BookingStatus.APPROVED, timedelta(minutes=180)))


class ResourceStatusTests(ServiceFixture, SimpleTestCase):
    def close(self, status="MAINTENANCE", reason="Fume hood repair"):
        return self.service.set_resource_status(self.manager, self.room.id, status, reason)

    def test_maintenance_blocks_new_requests_but_keeps_existing_bookings(self):
        self.qualification()
        kept = self.service.review_booking(self.admin, self.book_minutes(60).id, "APPROVED")
        pending = self.book_minutes(60, offset_minutes=120)
        resource, affected = self.close()
        self.assertEqual((resource.status, resource.status_reason), (ResourceStatus.MAINTENANCE, "Fume hood repair"))
        self.assertEqual([item.id for item in affected], [kept.id, pending.id])
        self.assertEqual(self.status(kept), BookingStatus.APPROVED)
        self.now = pending.review_due_at  # nobody reviewed it while the room was closed
        self.service.process_due_requests()
        self.assertEqual((self.get(pending).status, self.get(pending).reason_code),
                         (BookingStatus.REJECTED, "AUTO_REJECTED_RESOURCE_UNAVAILABLE"))
        with self.assertRaises(DomainError) as denied:
            self.book_minutes(60, offset_minutes=240)
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
        self.assertEqual(self.status(queued), BookingStatus.PENDING_APPROVAL)

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
        approved = self.create_approved()
        self.verify_student()
        waiting = self.create_booking(self.student, self.payload(hour=14)).data
        default = self.items(self.admin.get("/api/v1/admin/bookings/"))
        self.assertEqual([item["id"] for item in default], [waiting["id"]])  # still the approval queue by default
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
        # Sprint 3 (Booking Records): search by part of the zID or name, case-insensitive.
        for query, expected in (("z1000001", [approved["id"]]), ("1000002", [waiting["id"]]), ("ZZZ", []), ("", [approved["id"], waiting["id"]])):
            with self.subTest(q=query):
                found = self.items(self.admin.get("/api/v1/admin/bookings/", {"status": "ALL", "q": query}))
                self.assertEqual([item["id"] for item in found], expected)
        for bad in ({"status": "NOPE"}, {"status": "APPROVED,,X"}, {"since": "2026-10-10T00:00:00"}, {"unknown": "1"}):
            with self.subTest(bad=bad):
                self.assert_error(self.admin.get("/api/v1/admin/bookings/", bad), 400)
        self.assert_error(self.verified.get("/api/v1/admin/bookings/", {"status": "ALL"}), 403)

    def test_manager_exports_every_booking_as_csv(self):
        payload = {**self.payload(), "purpose": "=HYPERLINK(\"x\")"}
        booking = self.create_approved(payload=payload)
        self.assertEqual(self.admin.get("/api/v1/admin/bookings/export/").status_code, 200)  # Sprint 3: Admins too
        self.assert_error(self.verified.get("/api/v1/admin/bookings/export/"), 403)
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
        self.assertEqual((row["Weekly series"], row["Attendance"]), ("", booking.get("attendance") or ""))  # Sprint 3 columns
        empty = self.manager.get("/api/v1/admin/bookings/export/", {"status": "CANCELLED"})
        self.assertEqual(len(list(csv.reader(io.StringIO(empty.content.decode("utf-8-sig"))))), 1)

