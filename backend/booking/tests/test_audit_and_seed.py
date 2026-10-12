"""Admin audit trail API and the prototype seed data (about 2 labs and 20 devices)."""

from datetime import timedelta

from django.test import SimpleTestCase, override_settings

from booking.domain import ResourceKind
from booking.runtime import DEMO_RESOURCES, fixed_id
from booking.tests.test_api import NOW, BookingAPIFixtureMixin

AUDIT = "/api/v1/admin/audit/"


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class DemoSeedTests(BookingAPIFixtureMixin, SimpleTestCase):
    def test_prototype_has_two_labs_and_twenty_independent_devices(self):
        resources = self.items(self.verified.get("/api/v1/resources/"))
        kinds = [item["kind"] for item in resources]
        self.assertEqual(kinds.count("ROOM"), 2)
        self.assertEqual(kinds.count("EQUIPMENT"), 20)
        self.assertEqual(len({item["id"] for item in resources}), 22)
        self.assertEqual(len(self.items(self.verified.get("/api/v1/resources/?kind=EQUIPMENT"))), 20)
        requirements = {item["required_qualification_id"] for item in resources}
        self.assertEqual(requirements, {fixed_id(1), fixed_id(2)})
        self.assertEqual(len(DEMO_RESOURCES), 22)

    def test_existing_demo_ids_and_requirements_are_unchanged(self):
        by_id = {item["id"]: item for item in self.items(self.verified.get("/api/v1/resources/"))}
        for number, name, requirement in ((101, "Lab Room 1", 1), (102, "Lab Room 2", 2),
                                          (201, "Microscope 001", 1), (202, "Camera 001", 2)):
            with self.subTest(number=number):
                self.assertEqual(by_id[fixed_id(number)]["name"], name)
                self.assertEqual(by_id[fixed_id(number)]["required_qualification_id"], fixed_id(requirement))

    def test_each_device_has_its_own_availability(self):
        devices = [item for item in self.items(self.verified.get("/api/v1/resources/?kind=EQUIPMENT"))
                   if item["required_qualification_id"] == fixed_id(1)][:2]
        booked = self.create_booking(payload=self.payload(resource=devices[0]))
        self.assertEqual(booked.data["status"], "PENDING_APPROVAL", booked.data)
        other = self.create_booking(payload=self.payload(resource=devices[1]))
        self.assertEqual(other.data["status"], "PENDING_APPROVAL", other.data)  # each device has its own time

    def test_devices_can_be_found_by_location(self):
        lab2 = self.items(self.verified.get("/api/v1/resources/?kind=EQUIPMENT&q=lab room 2"))
        self.assertEqual(len(lab2), sum(1 for row in DEMO_RESOURCES if row[2] == ResourceKind.EQUIPMENT and row[3] == "Lab Room 2"))
        self.assertTrue(all(item["required_qualification_id"] == fixed_id(2) for item in lab2))


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class AuditTrailAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        # Room booking created then cancelled an hour later; equipment booking after that.
        self.room_booking = self.create_booking().data
        self.service.clock = lambda: NOW + timedelta(hours=1)
        self.verified.post(f"/api/v1/bookings/{self.room_booking['id']}/cancel/", {}, format="json")
        self.service.clock = lambda: NOW + timedelta(hours=2)
        self.equipment_booking = self.create_booking(payload=self.payload(resource=self.equipment)).data
        self.me = self.verified.get("/api/v1/auth/me/").data

    def audit(self, client=None, **params):
        response = (client or self.admin).get(AUDIT, params)
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        return response.data

    def actions(self, data):
        return [item["action"] for item in data["results"]]

    def test_only_admin_and_manager_can_read_the_trail(self):
        self.assert_error(self.verified.get(AUDIT), 403)
        self.assert_error(self.client.get(AUDIT), 401)
        self.assertEqual(self.manager.get(AUDIT).status_code, 200)

    def test_newest_first_with_actor_summary(self):
        data = self.audit()
        self.assertEqual(self.actions(data)[:3], ["BOOKING_CREATED", "BOOKING_CANCELLED", "BOOKING_CREATED"])
        times = [item["at"] for item in data["results"]]
        self.assertEqual(times, sorted(times, reverse=True))
        first = data["results"][0]
        self.assertEqual(first["entity_id"], self.equipment_booking["id"])
        self.assertEqual(first["actor"], {"id": self.me["id"], "zid": "z1000001",
                                          "display_name": self.me["display_name"], "role": "STUDENT"})
        self.assertEqual(set(first), {"id", "actor_id", "action", "entity_type", "entity_id", "at", "details", "actor"})

    def test_booking_history_by_entity(self):
        data = self.audit(entity_id=self.room_booking["id"])
        self.assertEqual(self.actions(data), ["BOOKING_CANCELLED", "BOOKING_CREATED"])
        self.assertEqual(data["results"][1]["details"]["status"], "PENDING_APPROVAL")

    def test_filter_by_resource_includes_policy_changes_but_not_other_resources(self):
        self.manager.patch(f"/api/v1/admin/resources/{self.room['id']}/booking-policy/",
                           {"pending_hold_minutes": 45}, format="json")
        data = self.audit(resource_id=self.room["id"])
        self.assertEqual(self.actions(data), ["RESOURCE_BOOKING_POLICY_UPDATED", "BOOKING_CANCELLED", "BOOKING_CREATED"])
        self.assertNotIn(self.equipment_booking["id"], [item["entity_id"] for item in data["results"]])

    def test_filter_by_student_and_action(self):
        self.submit()  # another student's qualification upload
        mine = self.audit(student_id=self.me["id"])
        self.assertEqual(self.actions(mine), ["BOOKING_CREATED", "BOOKING_CANCELLED", "BOOKING_CREATED"])
        cancelled = self.audit(action="BOOKING_CANCELLED")
        self.assertEqual(cancelled["count"], 1)
        uploads = self.audit(entity_type="qualification")
        self.assertEqual(self.actions(uploads), ["QUALIFICATION_SUBMITTED"])

    def test_time_window_and_pagination(self):
        window = self.audit(since=(NOW + timedelta(minutes=30)).isoformat(), until=(NOW + timedelta(hours=2)).isoformat())
        self.assertEqual(self.actions(window), ["BOOKING_CANCELLED"])
        page = self.audit(limit=1, offset=1)
        self.assertEqual((page["count"], page["limit"], page["offset"]), (3, 1, 1))
        self.assertEqual(self.actions(page), ["BOOKING_CANCELLED"])

    def test_invalid_queries_are_rejected(self):
        for params in ({"unknown": "x"}, {"since": "2026-10-05T00:00:00"}, {"limit": 0}, {"limit": 501},
                       {"entity_type": "room"}, {"resource_id": "not-a-uuid"}, {"action": "booking_created"},
                       {"since": NOW.isoformat(), "until": NOW.isoformat()}):
            with self.subTest(params=params):
                self.assert_error(self.admin.get(AUDIT, params), 400)
