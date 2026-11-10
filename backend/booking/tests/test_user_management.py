"""Manager-only user list. Students and staff (Admin, Manager) are separate accounts: staff are added with
Add staff, keep the role they were created with, and never come from promoting a student."""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from booking.domain import QualificationStatus, QualificationSubmission, Role
from booking.exceptions import DomainError
from booking.tests.test_api import BookingAPIFixtureMixin

USERS = "/api/v1/admin/users/"


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class UserManagementAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def user(self, zid):
        return next(item for item in self.service.repo.list_principals() if item.zid == zid)

    def patch(self, zid, data, client=None):
        return (client or self.manager).patch(f"{USERS}{self.user(zid).id}/", data, format="json")

    def pass_inductions(self, zid, status=QualificationStatus.VERIFIED, valid_until=None):
        """Give this person a submission for every induction requirement."""
        for requirement in self.service.repo.list_requirements():
            self.service.repo.save_submission(QualificationSubmission(
                str(uuid4()), self.user(zid).id, requirement.id, "Certificate", "", "file", self.service.now(),
                status=status, reviewed_by=self.user("z9000001").id, reviewed_at=self.service.now(), valid_until=valid_until))

    def add_manager(self, zid="z5999999"):
        response = self.manager.post("/api/v1/admin/users/managers/", {
            "zid": zid, "display_name": "Second manager", "university_email": f"{zid}@ad.unsw.edu.au"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return self.user(zid)

    def add_staff(self, zid, role):
        return self.manager.post("/api/v1/admin/users/staff/", {
            "zid": zid, "display_name": f"Staff {zid}", "university_email": f"{zid}@ad.unsw.edu.au", "role": role}, format="json")

    def test_only_an_active_manager_can_see_or_change_the_list(self):
        for client in (self.verified, self.student, self.admin):
            with self.subTest(client=client):
                self.assert_error(client.get(USERS), 403)
                self.assert_error(self.patch("z9000001", {"role": "MANAGER"}, client), 403)
        self.assert_error(self.client.get(USERS), 401)

    def test_list_and_filters(self):
        # Compare against the seeded repository instead of a fixed roster, so adding demo users does not break this test.
        seeded = self.service.repo.list_principals()
        everyone = self.items(self.manager.get(USERS))
        self.assertEqual({item["zid"] for item in everyone}, {item.zid for item in seeded})
        self.assertTrue({"z1000001", "z9000001", "z9000002"} <= {item["zid"] for item in everyone})
        self.assertEqual(set(everyone[0]), {"id", "zid", "display_name", "role", "active", "university_email",
                                            "inductions", "induction_status", "is_staff",
                                            "activation_status", "invite_code"})
        self.assertEqual({item["zid"]: item["is_staff"] for item in everyone}["z9000001"], True)
        self.assertEqual({item["zid"]: item["is_staff"] for item in everyone}["z1000001"], False)
        for role in (Role.STUDENT, Role.ADMIN, Role.MANAGER):
            with self.subTest(role=role):
                listed = self.items(self.manager.get(USERS, {"role": role.value}))
                self.assertEqual({item["zid"] for item in listed}, {item.zid for item in seeded if item.role == role})
                self.assertTrue(listed)
        students = self.items(self.manager.get(USERS, {"q": "z1000"}))
        self.assertEqual({item["zid"] for item in students}, {item.zid for item in seeded if "z1000" in item.zid})
        self.assertTrue(all("z1000" in item["zid"] for item in students))
        self.assert_error(self.manager.get(USERS, {"role": "OWNER"}), 400)

    def test_students_are_never_given_a_staff_role(self):
        self.pass_inductions("z1000002")  # passing every induction proves lab eligibility, not employment
        for role in ("ADMIN", "MANAGER"):
            with self.subTest(role=role):
                refused = self.patch("z1000002", {"role": role})
                self.assert_error(refused, 409)
                self.assertEqual(refused.data["error"]["code"], "ROLE_CHANGE_NOT_ALLOWED")
        self.assertEqual(self.user("z1000002").role, Role.STUDENT)

    def test_staff_are_not_turned_into_students(self):
        refused = self.patch("z9000001", {"role": "STUDENT"})
        self.assert_error(refused, 409)
        self.assertEqual(refused.data["error"]["code"], "ROLE_CHANGE_NOT_ALLOWED")

    def test_add_staff_creates_admin_or_manager_accounts(self):
        admin = self.add_staff("z5111111", "ADMIN")
        self.assertEqual((admin.status_code, admin.data["role"], admin.data["is_staff"]), (201, "ADMIN", True))
        self.assertEqual(self.add_staff("z5222222", "MANAGER").data["role"], "MANAGER")
        self.assert_error(self.add_staff("z5333333", "STUDENT"), 400)
        duplicate = self.add_staff("z1000001", "ADMIN")
        self.assert_error(duplicate, 409)
        self.assertEqual(duplicate.data["error"]["code"], "USER_EXISTS")
        for client in (self.admin, self.verified):
            with self.subTest(client=client):
                self.assert_error(client.post("/api/v1/admin/users/staff/", {
                    "zid": "z5444444", "display_name": "X", "university_email": "z5444444@ad.unsw.edu.au", "role": "ADMIN"},
                    format="json"), 403)

    def test_admin_and_manager_roles_are_fixed(self):
        other = self.add_manager()
        for zid, role in (("z9000001", "MANAGER"), (other.zid, "ADMIN")):
            with self.subTest(zid=zid):
                refused = self.patch(zid, {"role": role})
                self.assert_error(refused, 409)
                self.assertEqual(refused.data["error"]["code"], "ROLE_CHANGE_NOT_ALLOWED")
        self.assertEqual((self.user("z9000001").role, self.user(other.zid).role), (Role.ADMIN, Role.MANAGER))
        self.assert_error(self.admin.get(USERS), 403)
        # Sending the current role is not a change.
        self.assertEqual(self.patch("z9000001", {"role": "ADMIN", "active": True}).status_code, 200)

    def test_deactivating_a_student_rejects_their_undecided_requests(self):
        pending = self.create_booking().data
        self.assertEqual(pending["status"], "PENDING_APPROVAL")
        self.patch("z1000001", {"active": False})
        booking = self.service.repo.get_booking(pending["id"])
        self.assertEqual((booking.status.value, booking.reason_code), ("REJECTED", "ACCOUNT_DEACTIVATED"))

    def test_deactivating_a_student_cancels_their_future_approved_bookings(self):
        # 2026-11-10 (U3): an approved booking of a deactivated person no longer holds the time; they are told.
        approved = self.create_approved()
        self.assertEqual(approved["status"], "APPROVED")
        self.patch("z1000001", {"active": False})
        booking = self.service.repo.get_booking(approved["id"])
        self.assertEqual((booking.status.value, booking.reason_code), ("CANCELLED", "CANCELLED_BY_STAFF"))
        told = [item for item in self.service.repo.list_notifications(self.user("z1000001").id) if item.kind == "BOOKING_CANCELLED"]
        self.assertEqual(len(told), 1)

    def test_list_shows_each_persons_induction_status(self):
        people = {item["zid"]: item for item in self.items(self.manager.get(USERS))}
        self.assertEqual(people["z1000001"]["induction_status"], "INCOMPLETE")
        self.assertEqual({item["name"]: item["status"] for item in people["z1000001"]["inductions"]},
                         {"General laboratory induction": "VERIFIED", "Advanced laboratory training": "NOT_SUBMITTED"})
        self.pass_inductions("z1000003")
        self.assertEqual(self.patch("z1000003", {"active": True}).data["induction_status"], "VERIFIED")

    def test_a_new_manager_can_manage_others(self):
        other = self.add_manager()
        client = self.login(other.zid)
        self.assertEqual(self.patch("z9000001", {"active": False}, client).data["active"], False)
        self.assertEqual(self.patch(other.zid, {"active": False}).data["active"], False)

    def test_deactivated_users_are_locked_out_until_reactivated(self):
        self.assertEqual(self.patch("z1000001", {"active": False}).data["active"], False)
        self.assert_error(self.verified.get("/api/v1/auth/me/"), 401)
        self.assertEqual([item["zid"] for item in self.items(self.manager.get(USERS, {"active": "false"}))], ["z1000001"])
        self.patch("z1000001", {"active": True})
        self.assertEqual(self.verified.get("/api/v1/auth/me/").status_code, 200)

    def test_a_deactivated_student_is_told_so_at_sign_in(self):
        # 2026-11-10 (U4): before, they were told to create the account first, and creating it said the zID existed.
        self.patch("z1000001", {"active": False})
        response = self.client.post("/api/v1/auth/demo-login/", {"zid": "z1000001"}, format="json")
        self.assert_error(response, 403)
        self.assertEqual(response.data["error"]["code"], "ACCOUNT_DEACTIVATED")
        self.assertEqual(response.data["error"]["message"], "This account has been deactivated. Contact the lab.")
        unknown = self.client.post("/api/v1/auth/demo-login/", {"zid": "z7777777"}, format="json")
        self.assertEqual(unknown.data["error"]["code"], "INVALID_DEMO_USER")

    def test_manager_cannot_change_themselves(self):
        response = self.patch("z9000002", {"role": "STUDENT"})
        self.assert_error(response, 403)
        self.assertEqual(response.data["error"]["code"], "SELF_MODIFICATION_FORBIDDEN")

    def test_invalid_updates_are_rejected(self):
        for data in ({}, {"role": "OWNER"}, {"role": "ADMIN", "zid": "z1"}, {"active": "maybe"}):
            with self.subTest(data=data):
                self.assert_error(self.patch("z1000002", data), 400)
        self.assert_error(self.manager.patch(f"{USERS}00000000-0000-0000-0000-000000000999/", {"role": "ADMIN"}, format="json"), 404)

    def test_changes_are_audited(self):
        self.patch("z9000001", {"active": False})
        record = self.items(self.manager.get("/api/v1/admin/audit/", {"action": "USER_UPDATED"}))
        self.assertEqual(len(record), 1)
        self.assertEqual(record[0]["actor"]["zid"], "z9000002")
        self.assertEqual({key: record[0]["details"][key] for key in ("zid", "previous_active", "active", "role")},
                         {"zid": "z9000001", "previous_active": True, "active": False, "role": "ADMIN"})

    def test_two_managers_cannot_lock_everyone_out_concurrently(self):
        second = self.add_manager()
        first = self.user("z9000002")
        self.service.update_user(first, second.id, active=False)
        # `second` still holds a manager identity from before it was deactivated.
        with self.assertRaises(DomainError) as denied:
            self.service.update_user(replace(second, active=True), first.id, active=False)
        self.assertEqual(denied.exception.code, "LAST_MANAGER")
        self.assertTrue(self.user("z9000002").active)
        self.assertFalse(self.user(second.zid).active)

    def test_manager_has_every_admin_permission(self):
        submission = self.submit()
        for method, url, data in (
            ("get", "/api/v1/admin/qualifications/", None),
            ("post", f"/api/v1/admin/qualifications/{submission['id']}/review/", {"decision": "VERIFIED"}),
            ("get", "/api/v1/admin/bookings/", None),
            ("get", "/api/v1/admin/audit/", None),
            ("post", "/api/v1/admin/process-due/", {}),
            ("get", "/api/v1/admin/outlook/", None),
            ("get", f"/api/v1/qualifications/{submission['id']}/file/", None),
        ):
            with self.subTest(url=url):
                response = getattr(self.manager, method)(url, data, format="json") if data is not None else getattr(self.manager, method)(url)
                self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        self.assertEqual(self.user("z9000002").role, Role.MANAGER)
