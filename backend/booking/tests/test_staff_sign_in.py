"""Two sign-in entry points: students use university sign-in; Admins and Managers use the staff page
(zID + password). A Manager creates a staff account with an invite code; the staff member activates it by
choosing a password. The account's role, not the page used, decides access."""

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from booking.tests.test_api import BookingAPIFixtureMixin

SIGN_IN = "/api/v1/auth/staff-sign-in/"
ACTIVATE = "/api/v1/auth/staff-activate/"
USERS = "/api/v1/admin/users/"
DEMO_PASSWORD = "123"
FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher", "django.contrib.auth.hashers.PBKDF2PasswordHasher"]


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True, PASSWORD_HASHERS=FAST_HASHERS)
class StaffSignInTests(BookingAPIFixtureMixin, SimpleTestCase):
    def post(self, path, data):
        return APIClient().post(path, data, format="json")

    def code(self, response):
        return response.data["error"]["code"]

    def user(self, zid):
        return next(item for item in self.service.repo.list_principals() if item.zid == zid)

    def listed(self, zid):
        return next(item for item in self.manager.get(USERS).data["results"] if item["zid"] == zid)

    def add_staff(self, zid="z5111111", role="ADMIN"):
        response = self.manager.post("/api/v1/admin/users/staff/", {
            "zid": zid, "display_name": f"Staff {zid}", "university_email": f"{zid}@ad.unsw.edu.au", "role": role}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_seeded_staff_sign_in_and_get_the_role_of_their_account(self):
        for zid, role in (("z9000001", "ADMIN"), ("Z9000002", "MANAGER")):
            with self.subTest(zid=zid):
                response = self.post(SIGN_IN, {"zid": zid, "password": DEMO_PASSWORD})
                self.assertEqual((response.status_code, response.data["user"]["role"]), (200, role), response.data)
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access_token']}")
                self.assertEqual(client.get("/api/v1/auth/me/").data["role"], role)

    def test_each_entry_point_refuses_the_other_kind_of_account(self):
        student = self.post(SIGN_IN, {"zid": "z1000001", "password": DEMO_PASSWORD})
        self.assertEqual((student.status_code, self.code(student)), (403, "STUDENT_USES_SSO"))
        for zid in ("z9000001", "z9000002"):
            with self.subTest(zid=zid):
                staff = self.post("/api/v1/auth/demo-login/", {"zid": zid})
                self.assertEqual((staff.status_code, self.code(staff)), (403, "USE_STAFF_SIGN_IN"))

    def test_wrong_or_unknown_credentials_are_rejected(self):
        for data in ({"zid": "z9000001", "password": "wrong-password"}, {"zid": "z9999998", "password": DEMO_PASSWORD}):
            with self.subTest(data=data):
                response = self.post(SIGN_IN, data)
                self.assertEqual((response.status_code, self.code(response)), (401, "INVALID_CREDENTIALS"))
        self.assertEqual(self.post(SIGN_IN, {"zid": "z9000001"}).status_code, 400)

    def test_new_staff_activate_with_the_invite_code_then_sign_in(self):
        created = self.add_staff()
        self.assertEqual(created["activation_status"], "AWAITING_ACTIVATION")
        code = created["invite_code"]
        self.assertRegex(code, r"^[A-Z2-9]{4}-[A-Z2-9]{4}$")
        self.assertEqual(self.listed("z5111111")["invite_code"], code)

        early = self.post(SIGN_IN, {"zid": "z5111111", "password": "anything-at-all"})
        self.assertEqual((early.status_code, self.code(early)), (403, "ACCOUNT_NOT_ACTIVATED"))
        wrong = self.post(ACTIVATE, {"zid": "z5111111", "invite_code": "AAAA-AAAA", "password": "new-password-1"})
        self.assertEqual((wrong.status_code, self.code(wrong)), (400, "INVALID_INVITE_CODE"))
        other = self.post(ACTIVATE, {"zid": "z9000001", "invite_code": code, "password": "new-password-1"})
        self.assertEqual(self.code(other), "INVALID_INVITE_CODE")  # the code belongs to one account only
        short = self.post(ACTIVATE, {"zid": "z5111111", "invite_code": code, "password": "short"})
        self.assertEqual(short.status_code, 400)

        activated = self.post(ACTIVATE, {"zid": "z5111111", "invite_code": code.lower().replace("-", ""), "password": "new-password-1"})
        self.assertEqual((activated.status_code, activated.data["user"]["role"]), (200, "ADMIN"), activated.data)
        self.assertEqual(self.code(self.post(ACTIVATE, {"zid": "z5111111", "invite_code": code, "password": "again-password"})),
                         "INVALID_INVITE_CODE")  # one use only
        self.assertEqual(self.post(SIGN_IN, {"zid": "z5111111", "password": "new-password-1"}).status_code, 200)
        listed = self.listed("z5111111")
        self.assertEqual((listed["activation_status"], listed["invite_code"]), ("ACTIVATED", None))

    def test_manager_resets_access_with_a_new_code(self):
        self.add_staff()
        first = self.listed("z5111111")["invite_code"]
        self.post(ACTIVATE, {"zid": "z5111111", "invite_code": first, "password": "new-password-1"})
        target = self.user("z5111111")
        for client in (self.admin, self.verified):
            with self.subTest(client=client):
                self.assert_error(client.post(f"{USERS}{target.id}/reset-access/"), 403)
        reset = self.manager.post(f"{USERS}{target.id}/reset-access/")
        self.assertEqual((reset.status_code, reset.data["activation_status"]), (200, "AWAITING_ACTIVATION"), reset.data)
        self.assertNotEqual(reset.data["invite_code"], first)
        self.assertEqual(self.code(self.post(SIGN_IN, {"zid": "z5111111", "password": "new-password-1"})), "ACCOUNT_NOT_ACTIVATED")
        self.assertEqual(self.post(ACTIVATE, {"zid": "z5111111", "invite_code": reset.data["invite_code"],
                                              "password": "new-password-2"}).status_code, 200)
        self.assertEqual(self.user("z5111111").role.value, "ADMIN")  # the role never changes
        actions = [item.action for item in self.service.repo.list_audit()]
        self.assertIn("STAFF_ACCESS_RESET", actions)
        self.assertEqual(actions.count("STAFF_ACTIVATED"), 2)

    def test_reset_is_for_other_staff_only(self):
        student = self.manager.post(f"{USERS}{self.user('z1000001').id}/reset-access/")
        self.assertEqual((student.status_code, self.code(student)), (409, "STUDENT_USES_SSO"))
        own = self.manager.post(f"{USERS}{self.user('z9000002').id}/reset-access/")
        self.assertEqual((own.status_code, self.code(own)), (403, "SELF_MODIFICATION_FORBIDDEN"))

    def test_deactivated_staff_cannot_sign_in_or_activate(self):
        created = self.add_staff()
        for zid in ("z9000001", "z5111111"):
            self.manager.patch(f"{USERS}{self.user(zid).id}/", {"active": False}, format="json")
        signed = self.post(SIGN_IN, {"zid": "z9000001", "password": DEMO_PASSWORD})
        self.assertEqual((signed.status_code, self.code(signed)), (403, "ACCOUNT_DEACTIVATED"))
        activate = self.post(ACTIVATE, {"zid": "z5111111", "invite_code": created["invite_code"], "password": "new-password-1"})
        self.assertEqual(self.code(activate), "ACCOUNT_DEACTIVATED")

    def test_password_hashes_never_leave_the_server(self):
        self.add_staff()
        everyone = self.manager.get(USERS).data["results"]
        signed = self.post(SIGN_IN, {"zid": "z9000002", "password": DEMO_PASSWORD}).data
        for payload in (everyone, signed):
            self.assertNotIn("password", str(payload))
            self.assertNotIn("pbkdf2", str(payload))

    def test_config_and_demo_switch(self):
        self.assertTrue(APIClient().get("/api/v1/auth/config/").data["staff_sign_in_enabled"])
        with override_settings(ENABLE_DEMO_AUTH=False):
            self.assertEqual(self.post(SIGN_IN, {"zid": "z9000001", "password": DEMO_PASSWORD}).status_code, 404)
            self.assertEqual(self.post(ACTIVATE, {"zid": "z9000001", "invite_code": "AAAA-AAAA", "password": "x" * 8}).status_code, 404)
