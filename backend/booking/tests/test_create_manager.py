"""Sprint 3: manage.py create_manager makes a Manager (e.g. the first one) without writing SQL."""

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from booking.domain import Role
from booking.exceptions import DomainError
from booking.tests.test_services import BookingFixtureMixin


class BootstrapManagerTests(BookingFixtureMixin, SimpleTestCase):
    def test_creates_a_manager_with_an_invite_code(self):
        manager, code = self.service.bootstrap_manager("Z9000123", " Lab Manager ", "z9000123@ad.unsw.edu.au")
        self.assertEqual((manager.zid, manager.display_name, manager.role), ("z9000123", "Lab Manager", Role.MANAGER))
        self.assertEqual(self.repo.get_credential(manager.id).invite_code, code)
        audit = self.repo.list_audit()[-1]
        self.assertEqual((audit.actor_id, audit.action, audit.entity_id), ("SYSTEM", "MANAGER_CREATED", manager.id))
        # The new Manager activates the account like any staff member.
        activated = self.service.activate_staff("z9000123", code, "a-good-password")
        self.assertEqual(activated.id, manager.id)

    def test_same_rules_as_add_staff(self):
        for zid, error in (("z1111111", "USER_EXISTS"), ("9000123", "VALIDATION_ERROR")):
            with self.assertRaises(DomainError) as denied:
                self.service.bootstrap_manager(zid, "Someone", "someone@ad.unsw.edu.au")
            self.assertEqual(denied.exception.code, error)


class CreateManagerCommandTests(BookingFixtureMixin, SimpleTestCase):
    def run_command(self, *args):
        out = StringIO()
        with mock.patch("booking.management.commands.create_manager.get_service", return_value=self.service), \
                mock.patch("booking.management.commands.create_manager.MemoryRepository", type("Durable", (), {})):
            call_command("create_manager", *args, stdout=out)
        return out.getvalue()

    def test_prints_the_invite_code(self):
        output = self.run_command("--zid", "z9000124", "--name", "Lab Manager", "--email", "z9000124@ad.unsw.edu.au")
        manager = next(item for item in self.repo.list_principals() if item.zid == "z9000124")
        self.assertIn(f"Invite code: {self.repo.get_credential(manager.id).invite_code}", output)

    def test_errors_are_reported(self):
        with self.assertRaises(CommandError) as failed:
            self.run_command("--zid", "z1111111", "--name", "Taken", "--email", "z1111111@ad.unsw.edu.au")
        self.assertIn("USER_EXISTS", str(failed.exception))

    def test_refuses_memory_data(self):
        with mock.patch("booking.management.commands.create_manager.get_service", return_value=self.service):
            with self.assertRaises(CommandError):
                call_command("create_manager", "--zid", "z9000125", "--name", "X", "--email", "x@ad.unsw.edu.au", stdout=StringIO())
