"""Sprint 3 (2026-11-07, client Week 8): the three roles see different data.

- Admins see bookings that ended at most ADMIN_HISTORY_DAYS ago; the full history is for Managers.
- Internal information about a resource (owner, asset number, where it came from, specifications) is for Managers only
  and is never part of the resource data that students and Admins receive.
"""

from datetime import timedelta

from django.test import SimpleTestCase, override_settings

from booking.services.resources import ADMIN_HISTORY_DAYS
from booking.tests.test_api import BookingAPIFixtureMixin
from booking.tests.test_sprint3 import Sprint3Fixture


class AdminHistoryTests(Sprint3Fixture, SimpleTestCase):
    def test_admins_see_recent_bookings_and_managers_see_all(self):
        self.service._override_rule(max_advance_days=30)
        old = self.approved(self.student, days=1)
        recent = self.approved(self.student, days=20)
        self.now = recent.end + timedelta(days=ADMIN_HISTORY_DAYS - 1)
        self.assertEqual({item.id for item in self.service.booking_report(self.manager)}, {old.id, recent.id})
        self.assertEqual([item.id for item in self.service.booking_report(self.admin)], [recent.id])
        # An earlier "since" asked for by an Admin is moved up to the limit; a later one is kept.
        self.assertEqual([item.id for item in self.service.booking_report(self.admin, since=old.start - timedelta(days=1))],
                         [recent.id])
        self.assertEqual(self.service.booking_report(self.admin, since=recent.end), [])


class InternalInfoTests(Sprint3Fixture, SimpleTestCase):
    def test_only_a_manager_reads_and_changes_internal_information(self):
        empty = self.service.resource_internal_info(self.manager, self.room.id)
        self.assertEqual((empty.resource_id, empty.owner, empty.asset_number), (self.room.id, "", ""))
        saved = self.service.update_resource_internal_info(self.manager, self.room.id, {
            "owner": "  Dr Example  ", "asset_number": "UNSW-0001", "provided_by": "School grant 2024"})
        self.assertEqual((saved.owner, saved.asset_number, saved.updated_by), ("Dr Example", "UNSW-0001", self.manager.id))
        self.assertEqual(self.service.resource_internal_info(self.manager, self.room.id), saved)
        self.assertIn("RESOURCE_INTERNAL_INFO_UPDATED", [item.action for item in self.repo.list_audit()])
        for person in (self.admin, self.student):
            self.refused("FORBIDDEN", self.service.resource_internal_info, person, self.room.id)
            self.refused("FORBIDDEN", self.service.update_resource_internal_info, person, self.room.id, {"owner": "x"})
        self.refused("VALIDATION_ERROR", self.service.update_resource_internal_info, self.manager, self.room.id,
                     {"asset_number": "x" * 61})
        self.refused("NOT_FOUND", self.service.resource_internal_info, self.manager, "00000000-0000-0000-0000-000000000000")


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class InternalInfoAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def test_internal_information_stays_out_of_resource_data(self):
        url = f"/api/v1/admin/resources/{self.room['id']}/internal/"
        saved = self.manager.patch(url, {"owner": "Dr Example", "specifications": "2 x 27-inch screens"}, format="json")
        self.assertEqual((saved.status_code, saved.data["owner"]), (200, "Dr Example"))
        self.assertEqual(self.manager.get(url).data["specifications"], "2 x 27-inch screens")
        self.assertEqual(self.admin.get(url).status_code, 403)
        self.assertEqual(self.verified.patch(url, {"owner": "Me"}, format="json").status_code, 403)
        self.assertEqual(self.manager.patch(url, {"unknown": "x"}, format="json").status_code, 400)
        for client in (self.verified, self.admin, self.manager):
            detail = client.get(f"/api/v1/resources/{self.room['id']}/").data
            self.assertFalse({"owner", "asset_number", "provided_by", "specifications"} & set(detail))
