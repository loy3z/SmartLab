"""Booking page filters: equipment categories and the one-day grid of every matching resource (18 Oct)."""
from datetime import timedelta

from django.test import SimpleTestCase, override_settings

from booking.tests.test_api import NOW, SYDNEY, BookingAPIFixtureMixin

DAY = (NOW.astimezone(SYDNEY) + timedelta(days=3)).date().isoformat()


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class DayOverviewTests(BookingAPIFixtureMixin, SimpleTestCase):
    def overview(self, client=None, **params):
        response = (client or self.verified).get("/api/v1/resources/day-overview/", {"date": DAY, **params})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def names(self, data):
        return [row["resource"]["name"] for row in data["results"]]

    def test_demo_equipment_has_categories_and_rooms_do_not(self):
        resources = self.items(self.verified.get("/api/v1/resources/"))
        self.assertTrue(all(item["category"] is None for item in resources if item["kind"] == "ROOM"))
        self.assertTrue(all(item["category"] for item in resources if item["kind"] == "EQUIPMENT"))
        microscopy = self.items(self.verified.get("/api/v1/resources/", {"category": "Microscopy"}))
        self.assertEqual(sorted(item["name"] for item in microscopy), ["Microscope 001", "Microscope 002"])

    def test_one_call_returns_every_resource_with_the_same_slots_as_its_own_availability(self):
        data = self.overview()
        self.assertEqual(data["count"], 22)
        self.assertEqual(self.names(data)[:2], ["Lab Room 1", "Lab Room 2"])  # rooms first
        self.assertIn("Fabrication", data["categories"])
        self.assertEqual([room["name"] for room in data["rooms"]], ["Lab Room 1", "Lab Room 2"])
        row = data["results"][0]
        single = self.verified.get(f"/api/v1/resources/{row['resource']['id']}/availability/",
                                   {"date": DAY, "duration_minutes": 60}).data
        self.assertEqual(row["slots"], single["slots"])
        self.assertEqual(row["can_request"], single["can_request"])
        self.assertEqual(data["earliest_date"], single["earliest_date"])

    def test_filters_by_type_room_category_and_text(self):
        self.assertEqual(self.names(self.overview(kind="ROOM")), ["Lab Room 1", "Lab Room 2"])
        lab_two = self.overview(room_id="00000000-0000-0000-0000-000000000102")
        self.assertIn("Lab Room 2", self.names(lab_two))
        self.assertTrue(all(row["room_name"] == "Lab Room 2" for row in lab_two["results"] if row["resource"]["kind"] == "EQUIPMENT"))
        self.assertEqual(sorted(self.names(self.overview(category="Fabrication"))), ["3D Printer 001", "Laser Cutter 001"])
        self.assertEqual(self.names(self.overview(q="oscillo")), ["Oscilloscope 001", "Oscilloscope 002"])

    def test_bookable_only_hides_what_the_person_cannot_request(self):
        everything = self.overview(bookable_only="true")
        self.assertNotIn("Lab Room 2", self.names(everything))  # needs Advanced training
        self.assertIn("Lab Room 1", self.names(everything))
        self.assertEqual(self.overview(self.student, bookable_only="true")["count"], 0)  # no induction yet

    def test_free_at_keeps_only_resources_free_for_the_whole_duration(self):
        self.create_approved(payload=self.payload(hour=10, minutes=60))  # Lab Room 1, 10:00-11:00
        names = self.names(self.overview(kind="ROOM", free_at="10:30"))
        self.assertNotIn("Lab Room 1", names)
        self.assertIn("Lab Room 2", names)
        self.assertIn("Lab Room 1", self.names(self.overview(kind="ROOM", free_at="11:00")))
        self.assertNotIn("Lab Room 1", self.names(self.overview(kind="ROOM", free_at="09:30")))  # runs into 10:00

    def test_taken_times_show_as_booked_in_the_grid(self):
        self.create_approved(payload=self.payload(hour=10, minutes=60))
        row = self.overview(kind="ROOM", duration_minutes=60)["results"][0]
        ten = next(slot for slot in row["slots"] if slot["start"].endswith("T23:00:00Z"))  # 10:00 Sydney (AEDT)
        self.assertEqual((ten["available"], ten["reason_code"]), (False, "BOOKED"))

    def test_invalid_queries_are_refused(self):
        self.assertEqual(self.verified.get("/api/v1/resources/day-overview/").status_code, 400)
        # Sprint 3 (1.16.0): a length no resource allows is no longer an error; those resources are counted in too_long.
        odd = self.verified.get("/api/v1/resources/day-overview/", {"date": DAY, "duration_minutes": 45})
        self.assertEqual((odd.status_code, odd.data["count"]), (200, 0))
        self.assertGreater(odd.data["too_long"], 0)
        self.assertEqual(self.verified.get("/api/v1/resources/day-overview/", {"date": DAY, "kind": "BOAT"}).status_code, 400)
        self.assertEqual(self.verified.get("/api/v1/resources/day-overview/", {"date": DAY, "free_at": "25:00"}).status_code, 400)
        self.assertEqual(self.client.get("/api/v1/resources/day-overview/", {"date": DAY}).status_code, 401)
