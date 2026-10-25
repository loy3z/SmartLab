"""Sprint 3: create a Manager account from the server, for example the very first one.

    python manage.py create_manager --zid z9000003 --name "Lab Manager" --email z9000003@ad.unsw.edu.au

Prints a one-time invite code. The new Manager opens the Staff sign-in page, chooses "First time? Activate your
account", and enters the zID, this code and their own password. Afterwards they add other staff on the website
(User Management -> Add staff). Needs the PostgreSQL adapter: memory data only lives inside the web server process.
"""
from django.core.management.base import BaseCommand, CommandError

from booking.errors import DomainError
from booking.repository import MemoryRepository
from booking.runtime import get_service


class Command(BaseCommand):
    help = "Create a Manager account and print its one-time invite code."

    def add_arguments(self, parser):
        parser.add_argument("--zid", required=True, help="z followed by 7 digits")
        parser.add_argument("--name", required=True, help="full name shown on the website")
        parser.add_argument("--email", required=True, help="university email address")

    def handle(self, *args, **options):
        service = get_service()
        if isinstance(service.repo, MemoryRepository):
            raise CommandError("Memory data is process-local. Use PostgreSQL (REPOSITORY_FACTORY), or Add staff on the "
                               "running demo website.")
        try:
            manager, code = service.bootstrap_manager(options["zid"], options["name"], options["email"])
        except DomainError as error:
            raise CommandError(f"{error.code}: {error.message}") from error
        self.stdout.write(f"Created Manager {manager.zid} ({manager.display_name}).")
        self.stdout.write(f"Invite code: {code}")
        self.stdout.write("They activate the account on the Staff sign-in page with this zID and code.")
