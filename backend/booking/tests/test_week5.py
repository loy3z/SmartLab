"""Week 5 client review fixes.

C01 every decision path applies the same rules; C02 the requester's account is re-checked;
C04 induction prerequisites (Advanced needs a current General); booking rules come from a provider.
"""

from dataclasses import replace
from datetime import time, timedelta
from io import StringIO
from uuid import uuid4

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from booking.domain import (BookingStatus, Principal, QualificationRequirement, QualificationStatus,
                            QualificationSubmission, Resource, ResourceKind, Role)
from booking.exceptions import DomainError
from booking.rules import BookingRules
from booking.services import BookingService
from booking.tests.test_api import BookingAPIFixtureMixin
from booking.tests.test_services import BookingFixtureMixin


class SharedRuleCheckTests(BookingFixtureMixin, SimpleTestCase):
    """C01: create, Admin approval, automatic approval, promotion and reschedule use one rule check."""

    def setUp(self):
        super().setUp()
        self.qualification()
        self.qualification(self.other)

    def close_at_nine(self):
        self.repo.save_resource(replace(self.repo.get_resource(self.room.id), closing_time=time(9)))

    def test_closing_time_change_stops_admin_and_automatic_approval_alike(self):
        booking = self.book()  # 10:00-11:00
        self.close_at_nine()
        with self.assertRaises(DomainError) as manual:
            self.service.review_booking(self.admin, booking.id, "APPROVED")
        self.assertEqual(manual.exception.code, "OUTSIDE_OPENING_HOURS")
        self.now = booking.review_due_at
        decided = self.service.process_due_requests()
        self.assertEqual([(item.status, item.reason_code) for item in decided],
                         [(BookingStatus.REJECTED, "AUTO_REJECTED_BOOKING_RULES")])
        self.assertIn("opening hours", decided[0].decision_reason)
        audit = [item for item in self.repo.list_audit() if item.entity_id == booking.id and item.action == "BOOKING_AUTO_REJECTED"]
        self.assertEqual(audit[0].details["reason_code"], "AUTO_REJECTED_BOOKING_RULES")

    def test_shorter_maximum_duration_and_new_increment_also_apply_at_decision_time(self):
        base = self.now
        for day, change in enumerate(({"max_booking_minutes": 30}, {"slot_minutes": 45}), start=1):
            with self.subTest(change=change):
                self.now = base
                self.repo.save_resource(self.room)
                booking = self.book(start=self.start + timedelta(days=day), end=self.end + timedelta(days=day))
                self.repo.save_resource(replace(self.room, **change))
                self.now = booking.review_due_at
                decided = [item for item in self.service.process_due_requests() if item.id == booking.id]
                self.assertEqual(decided[0].reason_code, "AUTO_REJECTED_BOOKING_RULES")

    def test_promotion_rejects_a_queued_request_that_no_longer_fits_the_rules(self):
        first = self.book()
        queued = self.book(self.other)
        self.close_at_nine()
        self.service.cancel_booking(self.student, first.id)
        promoted = self.repo.get_booking(queued.id)
        self.assertEqual((promoted.status, promoted.reason_code), (BookingStatus.REJECTED, "OUTSIDE_OPENING_HOURS"))

    def test_window_is_not_rechecked_while_a_request_waits(self):
        self.service.min_advance_days = 3
        booking = self.book()  # start is 3 days ahead
        self.now = booking.review_due_at  # now only 2 days ahead: too soon for a new request, still approved
        decided = self.service.process_due_requests()
        self.assertEqual(decided[0].status, BookingStatus.APPROVED)


class AccountStatusTests(BookingFixtureMixin, SimpleTestCase):
    """C02: an inactive requester is never approved, by an Admin, automatically or from the waitlist."""

    def setUp(self):
        super().setUp()
        self.qualification()
        self.qualification(self.other)

    def deactivate(self, person):
        self.repo.save_principal(replace(person, active=False))  # as if changed elsewhere, bypassing the cascade

    def test_inactive_requester_is_rejected_automatically_and_cannot_be_approved(self):
        booking = self.book()
        self.deactivate(self.student)
        with self.assertRaises(DomainError) as manual:
            self.service.review_booking(self.admin, booking.id, "APPROVED")
        self.assertEqual(manual.exception.code, "ACCOUNT_INACTIVE")
        self.now = booking.review_due_at
        decided = self.service.process_due_requests()
        self.assertEqual((decided[0].status, decided[0].reason_code),
                         (BookingStatus.REJECTED, "AUTO_REJECTED_ACCOUNT_INACTIVE"))

    def test_inactive_requester_is_not_promoted(self):
        first, queued = self.book(), self.book(self.other)
        self.deactivate(self.other)
        self.service.cancel_booking(self.student, first.id)
        self.assertEqual((self.repo.get_booking(queued.id).status, self.repo.get_booking(queued.id).reason_code),
                         (BookingStatus.REJECTED, "ACCOUNT_INACTIVE"))

    def test_deactivation_rejects_undecided_requests_and_cancels_future_approved_bookings(self):  # 2026-11-10 (U3): approved ones used to stay
        manager = Principal(str(uuid4()), "z9888888", "Manager", Role.MANAGER, "z9888888@ad.unsw.edu.au")
        self.repo.save_principal(manager)
        approved = self.service.review_booking(self.admin, self.book().id, "APPROVED")
        pending = self.book(start=self.end, end=self.end + timedelta(hours=1))
        queued = self.book(self.other, start=self.end, end=self.end + timedelta(hours=1))
        self.service.update_user(manager, self.student.id, active=False)
        self.assertEqual(self.repo.get_booking(approved.id).status, BookingStatus.CANCELLED)
        self.assertEqual(self.repo.get_booking(pending.id).reason_code, "ACCOUNT_DEACTIVATED")
        self.assertEqual(self.repo.get_booking(queued.id).status, BookingStatus.PENDING_APPROVAL)  # time passed on


class PrerequisiteTests(BookingFixtureMixin, SimpleTestCase):
    """C04: Advanced training needs a verified, current General induction (stored, configurable)."""

    def setUp(self):
        super().setUp()
        self.manager = Principal(str(uuid4()), "z9888888", "Manager", Role.MANAGER, "z9888888@ad.unsw.edu.au")
        self.repo.save_principal(self.manager)
        self.general = self.requirement
        self.advanced = QualificationRequirement(str(uuid4()), "Advanced training", "", prerequisite_ids=(self.general.id,))
        self.repo.save_requirement(self.advanced)
        self.lab2 = Resource(str(uuid4()), "Lab Room 2", ResourceKind.ROOM, "Building A", "",
                             required_qualification_id=self.advanced.id)
        self.repo.save_resource(self.lab2)

    def verified(self, requirement, valid_until=None, person=None):
        person = person or self.student
        record = QualificationSubmission(str(uuid4()), person.id, requirement.id, "Certificate", "", "file", self.now,
                                         status=QualificationStatus.VERIFIED, reviewed_by=self.admin.id,
                                         reviewed_at=self.now, valid_until=valid_until or self.now + timedelta(days=120))
        self.repo.save_submission(record)
        self.now += timedelta(seconds=1)
        return record

    def submit_advanced(self):
        return self.service.submit_qualification(self.student, self.advanced.id, "Advanced", "", b"x", "a.pdf", "application/pdf")

    def test_advanced_evidence_needs_a_current_general_induction_first(self):
        with self.assertRaises(DomainError) as denied:
            self.submit_advanced()
        self.assertEqual((denied.exception.code, denied.exception.details["prerequisite_id"]),
                         ("PREREQUISITE_REQUIRED", self.general.id))
        self.verified(self.general)
        self.assertEqual(self.submit_advanced().status, QualificationStatus.PENDING)

    def test_advanced_cannot_be_verified_when_general_is_no_longer_current(self):
        self.verified(self.general, valid_until=self.now + timedelta(days=1))
        submission = self.submit_advanced()
        self.now += timedelta(days=2)
        with self.assertRaises(DomainError) as denied:
            self.service.review_qualification(self.admin, submission.id, "VERIFIED")
        self.assertEqual(denied.exception.code, "PREREQUISITE_REQUIRED")
        self.assertEqual(self.service.review_qualification(self.admin, submission.id, "REJECTED", "Renew General first")[0].status,
                         QualificationStatus.REJECTED)

    def test_booking_advanced_needs_both_current_until_the_booking_ends(self):
        args = {"resource_id": self.lab2.id}
        self.verified(self.advanced)  # e.g. imported; General missing
        self.assertEqual(self.service.qualification_state(self.student.id, self.lab2, self.end), ("PREREQUISITE_REQUIRED", False))
        with self.assertRaises(DomainError) as denied:
            self.book(**args)
        self.assertEqual((denied.exception.code, denied.exception.details["prerequisite_id"]),
                         ("QUALIFICATION_REQUIRED", self.general.id))
        self.verified(self.general, valid_until=self.end - timedelta(minutes=1))  # General ends before the booking does
        with self.assertRaises(DomainError):
            self.book(**args)
        self.verified(self.general)
        self.assertEqual(self.book(**args).status, BookingStatus.PENDING_APPROVAL)

    def test_general_withdrawn_before_the_decision_rejects_the_advanced_booking(self):
        self.verified(self.general)
        self.verified(self.advanced)
        booking = self.book(resource_id=self.lab2.id)
        self.repo.save_submission(QualificationSubmission(  # newer General evidence was rejected
            str(uuid4()), self.student.id, self.general.id, "Renewal", "", "file", self.now,
            status=QualificationStatus.REJECTED, reviewed_by=self.admin.id, reviewed_at=self.now, rejection_reason="Invalid"))
        self.now = booking.review_due_at
        decided = self.service.process_due_requests()
        self.assertEqual((decided[0].status, decided[0].reason_code), (BookingStatus.REJECTED, "AUTO_REJECTED_QUALIFICATION"))
        self.assertIn("PREREQUISITE_REQUIRED", decided[0].decision_reason)

    def test_prerequisites_are_data_changed_by_a_manager_and_cannot_loop(self):
        self.assertEqual(self.service.set_prerequisites(self.manager, self.advanced.id, []).prerequisite_ids, ())
        self.assertEqual(self.service.qualification_state(self.student.id, self.lab2)[0], "NOT_SUBMITTED")
        self.service.set_prerequisites(self.manager, self.advanced.id, [self.general.id])
        for requirement, wanted in ((self.general, [self.advanced.id]), (self.general, [self.general.id])):
            with self.subTest(wanted=wanted), self.assertRaises(DomainError) as denied:
                self.service.set_prerequisites(self.manager, requirement.id, wanted)
            self.assertEqual(denied.exception.code, "PREREQUISITE_CYCLE")
        with self.assertRaises(DomainError):
            self.service.set_prerequisites(self.admin, self.advanced.id, [])
        audit = [item for item in self.repo.list_audit() if item.action == "REQUIREMENT_PREREQUISITES_UPDATED"]
        self.assertEqual(len(audit), 2)


class RulesProviderTests(BookingFixtureMixin, SimpleTestCase):
    """Booking rules are read from a provider on every check, so a changed value applies at once."""

    def test_a_provider_changes_the_window_without_code_changes(self):
        class Editable:
            rules = BookingRules(min_advance_days=0, max_advance_days=7)

            def current(self):
                return self.rules

        provider = Editable()
        service = BookingService(self.repo, self.service.storage, clock=lambda: self.now, rules=provider)
        self.qualification()
        service.create_booking(self.student, self.room.id, self.start, self.end, "Within the window")
        provider.rules = BookingRules(min_advance_days=5, max_advance_days=7)
        with self.assertRaises(DomainError) as denied:
            service.create_booking(self.student, self.room.id, self.end, self.end + timedelta(hours=1), "Now too soon")
        self.assertEqual((denied.exception.code, denied.exception.details["min_advance_days"]), ("BOOKING_TOO_SOON", 5))

    def test_invalid_rules_are_refused(self):
        for values in ({"min_advance_days": 9, "max_advance_days": 3}, {"qualification_validity_days": 0},
                       {"default_review_window_minutes": 20161}, {"booking_slot_minutes": 0},
                       {"max_slots_per_booking": 0}, {"max_active_future_bookings": 0}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                BookingRules(**values)


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True, OUTLOOK_ENABLED=False)
class Week5APITests(BookingAPIFixtureMixin, SimpleTestCase):
    def test_requirements_list_their_prerequisites_and_manager_can_change_them(self):
        requirements = {item["name"]: item for item in self.items(self.verified.get("/api/v1/qualification-requirements/"))}
        general, advanced = requirements["General laboratory induction"], requirements["Advanced laboratory training"]
        self.assertEqual(advanced["prerequisite_ids"], [general["id"]])
        url = f"/api/v1/admin/qualification-requirements/{advanced['id']}/"
        self.assert_error(self.admin.patch(url, {"prerequisite_ids": []}, format="json"), 403)
        self.assertEqual(self.manager.patch(url, {"prerequisite_ids": []}, format="json").data["prerequisite_ids"], [])
        looped = self.manager.patch(f"/api/v1/admin/qualification-requirements/{general['id']}/",
                                    {"prerequisite_ids": [general["id"]]}, format="json")
        self.assert_error(looped, 409)

    def test_equipment_lists_its_room(self):
        resources = self.items(self.verified.get("/api/v1/resources/"))
        rooms = {item["id"]: item["name"] for item in resources if item["kind"] == "ROOM"}
        equipment = [item for item in resources if item["kind"] == "EQUIPMENT"]
        self.assertEqual(len(rooms), 2)
        self.assertEqual(len(equipment), 20)
        self.assertTrue(all(rooms[item["room_id"]] == item["location"] for item in equipment))
        self.assertTrue(all(item["room_id"] is None for item in resources if item["kind"] == "ROOM"))

    def test_availability_names_a_missing_prerequisite(self):
        advanced_room = next(item for item in self.items(self.verified.get("/api/v1/resources/")) if item["name"] == "Lab Room 2")
        day = (self.service.now() + timedelta(days=8)).date().isoformat()
        data = self.student.get(f"/api/v1/resources/{advanced_room['id']}/availability/", {"date": day}).data
        self.assertEqual((data["qualification_status"], data["can_request"]), ("PREREQUISITE_REQUIRED", False))
        self.assertIsNotNone(data["missing_prerequisite_id"])


class ProcessDueCommandTests(BookingFixtureMixin, SimpleTestCase):
    """C07: decide due requests on a schedule, without waiting for someone to open the site."""

    def test_command_refuses_the_process_local_memory_demo(self):
        with self.assertRaises(CommandError):
            call_command("process_due", stdout=StringIO())

    def test_command_runs_the_shared_service(self):
        from unittest import mock
        self.qualification()
        booking = self.book()
        self.now = booking.review_due_at
        out = StringIO()
        with mock.patch("booking.management.commands.process_due.get_service", return_value=self.service), \
                mock.patch("booking.management.commands.process_due.MemoryRepository", ()):
            call_command("process_due", stdout=out)
        self.assertIn("Decided or expired 1 request(s)", out.getvalue())
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.APPROVED)
