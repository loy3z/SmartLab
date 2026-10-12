"""Manager-only staff list: change student/admin roles, (de)activate accounts, add managers."""

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

    def test_only_an_active_manager_can_see_or_change_the_list(self):
        for client in (self.verified, self.student, self.admin):
            with self.subTest(client=client):
                self.assert_error(client.get(USERS), 403)
                self.assert_error(self.patch("z1000002", {"role": "ADMIN"}, client), 403)
        self.assert_error(self.client.get(USERS), 401)

    def test_list_and_filters(self):
        # Compare against the seeded repository instead of a fixed roster, so adding demo users does not break this test.
        seeded = self.service.repo.list_principals()
        everyone = self.items(self.manager.get(USERS))
        self.assertEqual({item["zid"] for item in everyone}, {item.zid for item in seeded})
        self.assertTrue({"z1000001", "z9000001", "z9000002"} <= {item["zid"] for item in everyone})
        self.assertEqual(set(everyone[0]), {"id", "zid", "display_name", "role", "active", "university_email",
                                            "inductions", "induction_status"})
        for role in (Role.STUDENT, Role.ADMIN, Role.MANAGER):
            with self.subTest(role=role):
                listed = self.items(self.manager.get(USERS, {"role": role.value}))
                self.assertEqual({item["zid"] for item in listed}, {item.zid for item in seeded if item.role == role})
                self.assertTrue(listed)
        students = self.items(self.manager.get(USERS, {"q": "z1000"}))
        self.assertEqual({item["zid"] for item in students}, {item.zid for item in seeded if "z1000" in item.zid})
        self.assertTrue(all("z1000" in item["zid"] for item in students))
        self.assert_error(self.manager.get(USERS, {"role": "OWNER"}), 400)

    def test_promoting_and_demoting_takes_effect_on_the_next_request(self):
        self.pass_inductions("z1000002")
        changed = self.patch("z1000002", {"role": "ADMIN"})
        self.assertEqual((changed.status_code, changed.data["role"]), (200, "ADMIN"))
        self.assertEqual(self.student.get("/api/v1/admin/bookings/").status_code, 200)
        self.assertEqual(self.create_booking(self.student).status_code, 201)  # an Admin (tutor) may still book
        self.patch("z1000002", {"role": "STUDENT"})
        self.assert_error(self.student.get("/api/v1/admin/bookings/"), 403)

    def test_student_must_pass_every_induction_to_become_admin(self):
        # z1000001 has only the general induction; the advanced one is still missing.
        refused = self.patch("z1000001", {"role": "ADMIN"})
        self.assert_error(refused, 409)
        error = refused.data["error"]
        self.assertEqual(error["code"], "INDUCTION_REQUIRED_FOR_ADMIN")
        self.assertIn("Qualified demo student (z1000001) must pass every induction", error["message"])
        self.assertEqual([item["name"] for item in error["details"]["missing_inductions"]], ["Advanced laboratory training"])
        self.assertEqual(self.user("z1000001").role, Role.STUDENT)
        for status, valid_until in ((QualificationStatus.PENDING, None), (QualificationStatus.REJECTED, None),
                                    (QualificationStatus.VERIFIED, self.service.now() - timedelta(days=1))):
            with self.subTest(status=status, expired=valid_until is not None):
                self.pass_inductions("z1000002", status, valid_until)
                self.assert_error(self.patch("z1000002", {"role": "ADMIN"}), 409)
        self.pass_inductions("z1000002")
        self.assertEqual(self.patch("z1000002", {"role": "ADMIN"}).data["role"], "ADMIN")

    def test_list_shows_each_persons_induction_status(self):
        people = {item["zid"]: item for item in self.items(self.manager.get(USERS))}
        self.assertEqual(people["z1000001"]["induction_status"], "INCOMPLETE")
        self.assertEqual({item["name"]: item["status"] for item in people["z1000001"]["inductions"]},
                         {"General laboratory induction": "VERIFIED", "Advanced laboratory training": "NOT_SUBMITTED"})
        self.pass_inductions("z1000003")
        self.assertEqual(self.patch("z1000003", {"active": True}).data["induction_status"], "VERIFIED")

    def test_admins_can_be_moved_back_without_an_induction_check(self):
        self.assertEqual(self.patch("z9000001", {"role": "STUDENT"}).data["role"], "STUDENT")
        self.assertEqual(self.patch("z9000001", {"role": "ADMIN"}).status_code, 409)  # now a student without inductions

    def test_manager_role_comes_only_from_add_manager(self):
        for zid in ("z1000002", "z9000001"):
            with self.subTest(zid=zid):
                response = self.patch(zid, {"role": "MANAGER"})
                self.assert_error(response, 403)
                self.assertEqual(response.data["error"]["code"], "MANAGER_ROLE_NOT_ASSIGNABLE")
        other = self.add_manager()
        demoted = self.patch(other.zid, {"role": "ADMIN"})
        self.assert_error(demoted, 403)
        self.assertEqual(demoted.data["error"]["code"], "MANAGER_ROLE_NOT_ASSIGNABLE")
        self.assertEqual(self.patch(other.zid, {"active": False}).data["active"], False)  # deactivating is still allowed

    def test_a_new_manager_can_manage_others(self):
        other = self.add_manager()
        client = self.login(other.zid)
        self.pass_inductions("z1000002")
        self.assertEqual(self.patch("z1000002", {"role": "ADMIN"}, client).status_code, 200)

    def test_deactivated_users_are_locked_out_until_reactivated(self):
        self.assertEqual(self.patch("z1000001", {"active": False}).data["active"], False)
        self.assert_error(self.verified.get("/api/v1/auth/me/"), 401)
        self.assertEqual([item["zid"] for item in self.items(self.manager.get(USERS, {"active": "false"}))], ["z1000001"])
        self.patch("z1000001", {"active": True})
        self.assertEqual(self.verified.get("/api/v1/auth/me/").status_code, 200)

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
        self.pass_inductions("z1000002")
        self.patch("z1000002", {"role": "ADMIN"})
        record = self.items(self.manager.get("/api/v1/admin/audit/", {"action": "USER_UPDATED"}))
        self.assertEqual(len(record), 1)
        self.assertEqual(record[0]["actor"]["zid"], "z9000002")
        self.assertEqual({key: record[0]["details"][key] for key in ("zid", "previous_role", "role")},
                         {"zid": "z1000002", "previous_role": "STUDENT", "role": "ADMIN"})

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
