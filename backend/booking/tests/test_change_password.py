"""Sprint 3: an Admin or Manager changes their own password (POST auth/change-password/)."""

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from booking.tests.test_api import BookingAPIFixtureMixin
from booking.tests.test_staff_sign_in import DEMO_PASSWORD, FAST_HASHERS, SIGN_IN

CHANGE = "/api/v1/auth/change-password/"


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True, PASSWORD_HASHERS=FAST_HASHERS)
class ChangePasswordTests(BookingAPIFixtureMixin, SimpleTestCase):
    def sign_in(self, password):
        return APIClient().post(SIGN_IN, {"zid": "z9000001", "password": password}, format="json")

    def test_staff_change_their_password(self):
        response = self.admin.post(CHANGE, {"current_password": DEMO_PASSWORD, "new_password": "a-new-password"}, format="json")
        self.assertEqual((response.status_code, response.data), (200, {"changed": True}))
        self.assertEqual(self.sign_in(DEMO_PASSWORD).status_code, 401)
        self.assertEqual(self.sign_in("a-new-password").status_code, 200)
        self.assertEqual(self.service.repo.list_audit()[-1].action, "STAFF_PASSWORD_CHANGED")

    def test_rules(self):
        cases = (({"current_password": "wrong", "new_password": "a-new-password"}, 400, "INVALID_CREDENTIALS"),
                 ({"current_password": DEMO_PASSWORD, "new_password": "short"}, 400, "VALIDATION_ERROR"))
        for body, status, code in cases:
            response = self.admin.post(CHANGE, body, format="json")
            self.assertEqual((response.status_code, response.data["error"]["code"]), (status, code))
        same = self.manager.post(CHANGE, {"current_password": DEMO_PASSWORD, "new_password": DEMO_PASSWORD * 3}, format="json")
        self.assertEqual(same.status_code, 200)
        again = self.manager.post(CHANGE, {"current_password": DEMO_PASSWORD * 3, "new_password": DEMO_PASSWORD * 3}, format="json")
        self.assertEqual(again.data["error"]["code"], "VALIDATION_ERROR")   # must differ from the current one
        student = self.verified.post(CHANGE, {"current_password": "x", "new_password": "a-new-password"}, format="json")
        self.assertEqual((student.status_code, student.data["error"]["code"]), (403, "STUDENT_USES_SSO"))
        self.assertEqual(APIClient().post(CHANGE, {}, format="json").status_code, 401)
