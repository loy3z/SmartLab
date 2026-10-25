"""Sprint 3 (2026-10-25): per-person notification category choices and the induction-submitted notice."""
from uuid import uuid4

from django.test import SimpleTestCase

from booking.domain import Principal, Role
from booking.services.notifications import NOTIFICATION_CATEGORIES
from booking.tests.test_sprint3 import Sprint3Fixture


class NotificationPreferenceTests(Sprint3Fixture, SimpleTestCase):
    def test_every_category_is_on_until_the_person_turns_it_off(self):
        preferences = self.service.notification_preferences(self.student)
        self.assertEqual([item["category"] for item in preferences], list(NOTIFICATION_CATEGORIES))
        self.assertTrue(all(item["enabled"] for item in preferences))

    def test_turning_bookings_off_stops_booking_notices_and_turning_it_on_restores_them(self):
        self.service.save_notification_preferences(self.student, {"bookings": False})
        self.request(self.student, days=3)
        self.assertEqual(self.notices(self.student, "BOOKING_SUBMITTED"), [])
        self.service.save_notification_preferences(self.student, {"bookings": True})
        self.request(self.student, days=4)
        self.assertEqual(len(self.notices(self.student, "BOOKING_SUBMITTED")), 1)

    def test_choices_are_saved_per_person(self):
        self.service.save_notification_preferences(self.student, {"bookings": False})
        self.assertFalse(self.service.notification_preferences(self.student)[0]["enabled"])
        self.assertTrue(all(item["enabled"] for item in self.service.notification_preferences(self.other)))

    def test_unknown_category_is_rejected(self):
        self.refused("VALIDATION_ERROR", self.service.save_notification_preferences,
                     self.student, {"everything": False})

    def test_submitting_induction_evidence_sends_a_notice(self):
        newcomer = Principal(str(uuid4()), "z9555555", "Newcomer", Role.STUDENT, "z9555555@ad.unsw.edu.au")
        self.repo.save_principal(newcomer)
        requirement = self.repo.list_requirements()[0]
        self.service.submit_qualification(newcomer, requirement.id, "Certificate", "",
                                          b"%PDF-1.4 test", "certificate.pdf", "application/pdf")
        sent = self.notices(newcomer, "INDUCTION_SUBMITTED")
        self.assertEqual(len(sent), 1)
        self.assertIn(requirement.name, sent[0].body)

    def test_induction_notice_also_respects_the_switch(self):
        newcomer = Principal(str(uuid4()), "z9555556", "Newcomer", Role.STUDENT, "z9555556@ad.unsw.edu.au")
        self.repo.save_principal(newcomer)
        requirement = self.repo.list_requirements()[0]
        self.service.save_notification_preferences(newcomer, {"induction": False})
        self.service.submit_qualification(newcomer, requirement.id, "Certificate", "",
                                          b"%PDF-1.4 test", "certificate.pdf", "application/pdf")
        self.assertEqual(self.notices(newcomer, "INDUCTION_SUBMITTED"), [])
