"""Sprint 3 (1.16.0): what a Manager sets up on the website for people to read: induction types and their guidance,
the lab's contact details, room capacity and resource details; and the staff "Today" overview."""

from datetime import timedelta

from django.test import SimpleTestCase, override_settings

from booking.domain import QualificationStatus, ResourceDetail
from booking.tests.test_api import BookingAPIFixtureMixin
from booking.tests.test_sprint3 import Sprint3Fixture


class InductionSetupTests(Sprint3Fixture, SimpleTestCase):
    def test_manager_adds_an_induction_and_writes_its_guidance(self):
        created = self.service.create_requirement(self.manager, {
            "name": "Laser safety", "description": "Class 4 lasers", "how_to_complete": "Book the Friday session",
            "accepted_evidence": "Signed attendance sheet", "reviewer": "Lab manager", "contact": "lab@example.edu"})
        self.assertEqual(self.repo.get_requirement(created.id).how_to_complete, "Book the Friday session")
        updated = self.service.update_requirement(self.manager, created.id, {"contact": " safety@example.edu "})
        self.assertEqual((updated.contact, updated.name), ("safety@example.edu", "Laser safety"))
        actions = [item.action for item in self.repo.list_audit()]
        self.assertIn("REQUIREMENT_CREATED", actions)
        self.assertIn("REQUIREMENT_UPDATED", actions)

    def test_names_are_unique_and_only_managers_change_inductions(self):
        self.refused("REQUIREMENT_NAME_TAKEN", self.service.create_requirement, self.manager, {"name": self.requirement.name.upper()})
        self.refused("VALIDATION_ERROR", self.service.create_requirement, self.manager, {"name": " "})
        self.refused("VALIDATION_ERROR", self.service.update_requirement, self.manager, self.requirement.id, {"reviewer": "x" * 2001})
        self.refused("FORBIDDEN", self.service.create_requirement, self.admin, {"name": "Other"})
        self.refused("NOT_FOUND", self.service.update_requirement, self.manager, "missing", {"name": "Other"})

    def test_editing_texts_keeps_verified_evidence(self):
        self.service.update_requirement(self.manager, self.requirement.id, {"name": "General induction"})
        statuses = {item.status for item in self.repo.list_submissions(student_id=self.student.id)}
        self.assertEqual(statuses, {QualificationStatus.VERIFIED})


class SiteContactTests(Sprint3Fixture, SimpleTestCase):
    def test_empty_until_a_manager_saves_it_then_only_sent_fields_change(self):
        self.assertEqual(self.service.site_contact().email, "")
        self.service.update_site_contact(self.manager, {"email": "lab@unsw.example", "hours": "Mon-Fri 9-5"})
        saved = self.service.update_site_contact(self.manager, {"phone": "02 9000 0000"})
        self.assertEqual((saved.email, saved.phone, saved.hours), ("lab@unsw.example", "02 9000 0000", "Mon-Fri 9-5"))
        self.assertEqual(saved.updated_by, self.manager.id)

    def test_rules(self):
        self.refused("VALIDATION_ERROR", self.service.update_site_contact, self.manager, {"email": "not an email"})
        self.refused("VALIDATION_ERROR", self.service.update_site_contact, self.manager, {"fax": "1"})
        self.refused("FORBIDDEN", self.service.update_site_contact, self.admin, {"email": "a@b.co"})
        self.assertEqual(self.service.update_site_contact(self.manager, {"email": ""}).email, "")  # blank clears it


class ResourceDetailsTests(Sprint3Fixture, SimpleTestCase):
    def fields(self, **extra):
        return {"name": "Seminar room", "location": "Building K17, Level 3", "required_qualification_id": self.requirement.id, **extra}

    def test_rooms_have_a_capacity_and_any_resource_has_details(self):
        room = self.service.create_resource(self.manager, "ROOM", self.fields(capacity=12, details=[
            {"label": "Floor", "value": "Level 3"}, {"label": " ", "value": ""}, {"label": "Projector", "value": "Yes"}]))
        self.assertEqual(room.capacity, 12)
        self.assertEqual(room.details, (ResourceDetail("Floor", "Level 3"), ResourceDetail("Projector", "Yes")))  # empty row dropped
        updated, _ = self.service.update_resource(self.manager, room.id, {"details": [{"label": "Floor", "value": "Level 4"}]})
        self.assertEqual(updated.details, (ResourceDetail("Floor", "Level 4"),))
        changes = [item for item in self.repo.list_audit() if item.action == "RESOURCE_UPDATED"][-1].details["changes"]
        self.assertEqual(changes["details"], [[["Floor", "Level 3"], ["Projector", "Yes"]], [["Floor", "Level 4"]]])

    def test_rules(self):
        self.refused("VALIDATION_ERROR", self.service.create_resource, self.manager, "EQUIPMENT",
                     self.fields(name="Scope", capacity=3))
        self.refused("VALIDATION_ERROR", self.service.create_resource, self.manager, "ROOM", self.fields(capacity=0))
        self.refused("VALIDATION_ERROR", self.service.create_resource, self.manager, "ROOM",
                     self.fields(details=[{"label": "Model", "value": ""}]))
        self.refused("VALIDATION_ERROR", self.service.create_resource, self.manager, "ROOM",
                     self.fields(details=[{"label": f"L{n}", "value": "v"} for n in range(13)]))


class StaffOverviewTests(Sprint3Fixture, SimpleTestCase):
    def test_counts_and_lists_for_the_today_page(self):
        self.service.min_advance_days = 2                      # so a request for today has to be urgent
        self.request(days=3, hour=10)                          # pending, due in 24 h
        urgent_start, urgent_end = self.at(0, 18)
        self.now = urgent_start - timedelta(hours=5)
        self.service.create_booking(self.other, self.room.id, urgent_start, urgent_end, "Rerun", urgent=True, urgent_reason="Deadline")
        self.service.set_resource_status(self.manager, self.room.id, "MAINTENANCE", "Leak")
        overview = self.service.staff_overview(self.admin)
        self.assertEqual((overview["pending_bookings"], overview["urgent_requests"]), (1, 1))
        self.assertEqual(overview["out_of_service"][0]["resource"].id, self.room.id)
        self.assertEqual(overview["out_of_service"][0]["affected_bookings"], 2)
        self.assertFalse(overview["can_decide_urgent"])
        self.assertTrue(self.service.staff_overview(self.manager)["can_decide_urgent"])
        self.refused("FORBIDDEN", self.service.staff_overview, self.student)

    def test_due_soon_lists_pending_requests_whose_window_ends_within_six_hours(self):
        booking = self.request(days=3, hour=10)
        self.now = booking.review_due_at - timedelta(hours=7)
        self.assertEqual(self.service.staff_overview(self.admin)["due_soon"], [])
        self.now = booking.review_due_at - timedelta(hours=2)
        self.assertEqual([item.id for item in self.service.staff_overview(self.admin)["due_soon"]], [booking.id])

    def test_today_lists_approved_bookings_starting_today_in_sydney(self):
        booking = self.approved(days=1, hour=9)
        self.now = booking.start - timedelta(hours=3)          # the same Sydney day, earlier
        overview = self.service.staff_overview(self.admin)
        self.assertEqual(([item.id for item in overview["today"]], overview["today_count"]), ([booking.id], 1))


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class LabSetupAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def test_endpoints(self):
        created = self.manager.post("/api/v1/admin/qualification-requirements/", {"name": "Laser safety", "reviewer": "Lab"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        patched = self.manager.patch(f"/api/v1/admin/qualification-requirements/{created.data['id']}/",
                                     {"how_to_complete": "Friday session", "prerequisite_ids": [self.requirement_id]}, format="json")
        self.assertEqual(patched.status_code, 200, patched.data)
        self.assertEqual((patched.data["how_to_complete"], patched.data["prerequisite_ids"]), ("Friday session", [self.requirement_id]))
        listed = self.items(self.verified.get("/api/v1/qualification-requirements/"))
        self.assertIn("accepted_evidence", listed[0])
        self.assertEqual(self.admin.post("/api/v1/admin/qualification-requirements/", {"name": "X"}, format="json").status_code, 403)

        self.assertEqual(self.verified.get("/api/v1/site/contact/").data["email"], "")
        saved = self.manager.patch("/api/v1/site/contact/", {"email": "lab@unsw.example"}, format="json")
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(self.verified.get("/api/v1/site/contact/").data["email"], "lab@unsw.example")
        self.assertEqual(self.verified.patch("/api/v1/site/contact/", {"email": "a@b.co"}, format="json").status_code, 403)

        room = self.manager.patch(f"/api/v1/admin/resources/{self.room['id']}/",
                                  {"capacity": 20, "details": [{"label": "Floor", "value": "Level 3"}]}, format="json")
        self.assertEqual(room.status_code, 200, room.data)
        shown = next(item for item in self.items(self.verified.get("/api/v1/resources/")) if item["id"] == self.room["id"])
        self.assertEqual((shown["capacity"], shown["details"]), (20, [{"label": "Floor", "value": "Level 3"}]))

        overview = self.admin.get("/api/v1/admin/overview/")
        self.assertEqual(overview.status_code, 200, overview.data)
        self.assertIn("pending_inductions", overview.data)
        self.assertEqual(self.verified.get("/api/v1/admin/overview/").status_code, 403)
