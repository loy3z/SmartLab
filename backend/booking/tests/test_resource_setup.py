"""Sprint 3: Managers add, edit, archive and restore rooms and equipment on the website (booking/services/resources.py)."""

from datetime import time, timedelta
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from booking.domain import BookingStatus, Principal, ResourceKind, Role
from booking.exceptions import DomainError
from booking.tests.test_api import BookingAPIFixtureMixin
from booking.tests.test_services import BookingFixtureMixin


class ResourceSetupTests(BookingFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.manager = Principal(str(uuid4()), "z9888888", "Manager", Role.MANAGER, "z9888888@ad.unsw.edu.au")
        self.repo.save_principal(self.manager)

    def add(self, kind="EQUIPMENT", **fields):
        values = {"name": "Spectrometer 001", "location": "Lab Room 1", "required_qualification_id": self.requirement.id,
                  **fields}
        if kind == "EQUIPMENT":
            values.setdefault("room_id", self.room.id)
        return self.service.create_resource(self.manager, kind, values)

    def refused(self, code, call, *args, **kwargs):
        with self.assertRaises(DomainError) as denied:
            call(*args, **kwargs)
        self.assertEqual(denied.exception.code, code)
        return denied.exception

    def test_add_equipment_with_defaults_and_audit(self):
        item = self.add(category="Spectroscopy")
        self.assertEqual((item.kind, item.room_id, item.category, item.slot_minutes, item.max_booking_minutes),
                         (ResourceKind.EQUIPMENT, self.room.id, "Spectroscopy", 30, 480))
        self.assertEqual((item.opening_time, item.closing_time, item.pending_hold_minutes), (time(8), time(20), 1440))
        self.assertTrue(item.active and item.bookable)
        self.assertEqual(self.repo.get_resource(item.id), item)
        audit = [record for record in self.repo.list_audit() if record.action == "RESOURCE_CREATED"]
        self.assertEqual(audit[-1].details["name"], "Spectrometer 001")
        self.assertEqual(audit[-1].details["opening_time"], "08:00")

    def test_new_resource_can_be_booked_like_any_other(self):
        item = self.add()
        self.qualification(self.student)
        booking, _ = self.service.create_booking(self.student, item.id, self.start, self.end, "Measure samples")
        self.assertEqual(booking.status, BookingStatus.PENDING_APPROVAL)

    def test_only_a_manager_can_set_up_resources(self):
        values = {"name": "X", "location": "Y", "required_qualification_id": self.requirement.id}
        self.refused("FORBIDDEN", self.service.create_resource, self.admin, "ROOM", values)
        self.refused("FORBIDDEN", self.service.create_resource, self.student, "ROOM", values)
        self.refused("FORBIDDEN", self.service.list_all_resources, self.admin)

    def test_setup_rules(self):
        self.refused("RESOURCE_NAME_TAKEN", self.add, name="laboratory")       # names ignore upper/lower case
        self.refused("VALIDATION_ERROR", self.add, required_qualification_id=str(uuid4()))
        self.refused("VALIDATION_ERROR", self.add, kind="ROOM", room_id=self.room.id)
        self.refused("VALIDATION_ERROR", self.add, kind="ROOM", category="Microscopy")
        other = self.add(name="Bench 1")
        self.refused("VALIDATION_ERROR", self.add, name="Bench 2", room_id=other.id)  # equipment is not a room
        self.refused("VALIDATION_ERROR", self.add, slot_minutes=20)
        self.refused("VALIDATION_ERROR", self.add, opening_time=time(8, 15))          # not on a 30-minute step
        self.refused("VALIDATION_ERROR", self.add, opening_time=time(18), closing_time=time(9))
        self.refused("VALIDATION_ERROR", self.add, max_booking_minutes=45)            # not a multiple of 30
        self.refused("VALIDATION_ERROR", self.add, opening_time=time(9), closing_time=time(11), max_booking_minutes=180)
        self.refused("VALIDATION_ERROR", self.add, pending_hold_minutes=0)
        self.refused("VALIDATION_ERROR", self.service.create_resource, self.manager, "DESK", {})
        error = self.refused("VALIDATION_ERROR", self.add, name=" ")
        self.assertIn("name", error.details)

    def test_edit_keeps_bookings_and_lists_the_ones_that_no_longer_fit(self):
        self.qualification(self.student)
        late, _ = self.service.create_booking(self.student, self.room.id, self.start.replace(hour=18),
                                              self.start.replace(hour=19), "Evening session")
        early, _ = self.service.create_booking(self.student, self.room.id, self.start, self.end, "Morning session")
        updated, outside = self.service.update_resource(self.manager, self.room.id,
                                                        {"closing_time": time(17), "description": "Shorter hours"})
        self.assertEqual((updated.closing_time, updated.description), (time(17), "Shorter hours"))
        self.assertEqual([(booking.id, code) for booking, code in outside], [(late.id, "OUTSIDE_OPENING_HOURS")])
        self.assertEqual(self.repo.get_booking(late.id).status, BookingStatus.PENDING_APPROVAL)  # kept for the Manager
        self.assertNotIn(early.id, [booking.id for booking, _ in outside])
        change = [record for record in self.repo.list_audit() if record.action == "RESOURCE_UPDATED"][-1]
        self.assertEqual(change.details["changes"]["closing_time"], ["20:00", "17:00"])
        # A new request outside the new hours is refused.
        self.refused("OUTSIDE_OPENING_HOURS", self.service.create_booking, self.other, self.room.id,
                     self.start.replace(hour=17) + timedelta(days=1), self.start.replace(hour=18) + timedelta(days=1), "Late")

    def test_edit_rules(self):
        self.refused("VALIDATION_ERROR", self.service.update_resource, self.manager, self.room.id, {"kind": "EQUIPMENT"})
        item = self.add()
        moved, _ = self.service.update_resource(self.manager, item.id, {"room_id": None, "category": "Optics"})
        self.assertEqual((moved.room_id, moved.category), (None, "Optics"))
        unchanged, _ = self.service.update_resource(self.manager, item.id, {"name": "Spectrometer 001"})
        self.assertEqual(unchanged, moved)
        self.assertEqual(len([record for record in self.repo.list_audit() if record.action == "RESOURCE_UPDATED"]), 1)

    def test_archive_and_restore(self):
        item = self.add()
        self.refused("ROOM_HAS_EQUIPMENT", self.service.archive_resource, self.manager, self.room.id)
        self.qualification(self.student)
        booking, _ = self.service.create_booking(self.student, item.id, self.start, self.end, "Measure samples")
        error = self.refused("RESOURCE_HAS_BOOKINGS", self.service.archive_resource, self.manager, item.id)
        self.assertEqual(error.details["booking_count"], 1)
        self.service.cancel_booking(self.student, booking.id)
        archived = self.service.archive_resource(self.manager, item.id)
        self.assertFalse(archived.active)
        self.refused("RESOURCE_UNAVAILABLE", self.service.create_booking, self.student, item.id, self.start, self.end, "Again")
        self.assertIn(item.id, [resource.id for resource in self.service.list_all_resources(self.manager)])
        # Its name is free again while archived, so restoring checks it.
        self.add(name="Spectrometer 001", kind="ROOM", room_id=None)
        self.refused("RESOURCE_NAME_TAKEN", self.service.restore_resource, self.manager, item.id)

    def test_restore_brings_a_resource_back(self):
        item = self.add()
        self.service.archive_resource(self.manager, item.id)
        restored = self.service.restore_resource(self.manager, item.id)
        self.assertTrue(restored.active)
        actions = [record.action for record in self.repo.list_audit() if record.entity_id == item.id]
        self.assertEqual(actions, ["RESOURCE_CREATED", "RESOURCE_ARCHIVED", "RESOURCE_RESTORED"])


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class ResourceSetupAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def new_equipment(self, **extra):
        return {"kind": "EQUIPMENT", "name": "Spectrometer 900", "location": "Lab Room 1",
                "required_qualification_id": self.requirement_id, "room_id": self.room["id"],
                "category": "Imaging", "opening_time": "09:00", **extra}

    def test_add_list_edit_archive_restore(self):
        created = self.manager.post("/api/v1/admin/resources/", self.new_equipment(), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual((created.data["opening_time"], created.data["closing_time"], created.data["room_id"]),
                         ("09:00:00", "20:00:00", self.room["id"]))
        rid = created.data["id"]
        self.assertIn(rid, [item["id"] for item in self.items(self.verified.get("/api/v1/resources/"))])

        edited = self.manager.patch(f"/api/v1/admin/resources/{rid}/", {"max_booking_minutes": 120, "category": None}, format="json")
        self.assertEqual(edited.status_code, 200, edited.data)
        self.assertEqual((edited.data["resource"]["max_booking_minutes"], edited.data["resource"]["category"]), (120, None))
        self.assertEqual(edited.data["bookings_outside_rules"], [])
        fixed = self.manager.patch(f"/api/v1/admin/resources/{rid}/", {"kind": "ROOM"}, format="json")
        self.assertEqual((fixed.status_code, fixed.data["error"]["code"]), (409, "KIND_IS_FIXED"))

        archived = self.manager.post(f"/api/v1/admin/resources/{rid}/archive/", {}, format="json")
        self.assertEqual((archived.status_code, archived.data["active"]), (200, False))
        self.assertNotIn(rid, [item["id"] for item in self.items(self.verified.get("/api/v1/resources/"))])
        everything = self.items(self.manager.get("/api/v1/admin/resources/"))
        self.assertIn(rid, [item["id"] for item in everything])
        restored = self.manager.post(f"/api/v1/admin/resources/{rid}/restore/", {}, format="json")
        self.assertEqual((restored.status_code, restored.data["active"]), (200, True))

    def test_edit_lists_bookings_outside_new_rules(self):
        booking = self.verified.post("/api/v1/bookings/", self.payload(hour=18), format="json")
        self.assertEqual(booking.status_code, 201, booking.data)
        edited = self.manager.patch(f"/api/v1/admin/resources/{self.room['id']}/", {"closing_time": "17:00"}, format="json")
        rows = edited.data["bookings_outside_rules"]
        self.assertEqual([(row["id"], row["problem"]) for row in rows], [(booking.data["id"], "OUTSIDE_OPENING_HOURS")])
        self.assertEqual(rows[0]["student"]["zid"], "z1000001")

    def test_errors_and_permissions(self):
        self.assertEqual(self.admin.get("/api/v1/admin/resources/").status_code, 403)
        self.assertEqual(self.verified.post("/api/v1/admin/resources/", self.new_equipment(), format="json").status_code, 403)
        unknown = self.manager.post("/api/v1/admin/resources/", self.new_equipment(colour="red"), format="json")
        self.assertEqual(unknown.status_code, 400)
        taken = self.manager.post("/api/v1/admin/resources/", self.new_equipment(name=self.room["name"]), format="json")
        self.assertEqual((taken.status_code, taken.data["error"]["code"]), (409, "RESOURCE_NAME_TAKEN"))
        busy = self.manager.post(f"/api/v1/admin/resources/{self.room['id']}/archive/", {}, format="json")
        self.assertEqual((busy.status_code, busy.data["error"]["code"]), (409, "ROOM_HAS_EQUIPMENT"))
