"""Sprint 3 (1.16.0): the lab's contact details, set by a Manager on the website (no code or config change needed).

Shown wherever people may need a person: the Help page, My Bookings and the Induction & Training page. Every field
is optional; the website only shows the ones that are filled in.
"""
import re
from dataclasses import replace

from ..domain import SITE_CONTACT_ID, SiteContact
from ..errors import DomainError

CONTACT_FIELDS = {"email": 200, "phone": 60, "hours": 200, "note": 1000}  # field -> longest allowed text


class SiteContactMixin:
    def site_contact(self):
        """The saved contact details, or an empty record before a Manager has saved any."""
        return self.repo.get_site_contact() or SiteContact(SITE_CONTACT_ID)

    def update_site_contact(self, actor, changes):
        """Manager: change any of email, phone, hours (when someone answers) and note. Only the fields sent change."""
        self.require_manager(actor)
        unknown = set(changes) - set(CONTACT_FIELDS)
        if unknown:
            raise DomainError("VALIDATION_ERROR", f"Unknown fields: {', '.join(sorted(unknown))}.")
        cleaned = {}
        for field, value in changes.items():
            text = (value or "").strip()
            if len(text) > CONTACT_FIELDS[field]:
                raise DomainError("VALIDATION_ERROR", f"{field} can be up to {CONTACT_FIELDS[field]} characters.", 400,
                                  {field: ["Too long."]})
            if field == "email" and text and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text):
                raise DomainError("VALIDATION_ERROR", "Give a valid email address, or leave it empty.", 400,
                                  {"email": ["Not an email address."]})
            cleaned[field] = text
        with self.repo.atomic():
            current = self.site_contact()
            updated = replace(current, **cleaned, updated_at=self.now(), updated_by=actor.id)
            self.repo.save_site_contact(updated)
            self._audit(actor.id, "SITE_CONTACT_UPDATED", "site_contact", SITE_CONTACT_ID,
                        changes={field: [getattr(current, field), getattr(updated, field)]
                                 for field in cleaned if getattr(current, field) != getattr(updated, field)})
            return updated
