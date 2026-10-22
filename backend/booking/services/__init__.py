"""Booking policy independent of HTTP and the database adapter.

``BookingService`` is the one entry point the API, scheduled commands and tests use. Its code is split by topic;
each file holds one part (all methods share ``self``: repo, storage, clock, rules and calendar_sync):

  base.py            clock, rules, role checks, audit, resource lookup, shared status groups
  accounts.py        user list, deactivation, staff accounts and sign-in, finding a person to book for
  resources.py       Manager resource settings (review window, maintenance/closed) and the bookings report
  qualifications.py  induction upload, review, validity and prerequisites
  checks.py          the one shared rule check and conflict lookups
  bookings.py        create (incl. on behalf, urgent), review, cancel, Manager reschedule
  waitlist.py        expiry, automatic decisions, waitlist promotion
  availability.py    one resource's slots for a day, and the booking page day overview
  audit.py           audit trail query

To add a feature, put its methods in the file for its topic (or a new mixin listed below) and its tests next to
the existing ones; import ``BookingService`` from ``booking.services`` as before.
"""
from .accounts import AccountsMixin, new_invite_code, normalize_invite_code
from .audit import AuditMixin
from .availability import AvailabilityMixin
from .base import ACTIVE_REQUEST_STATUSES, HEAD_STATUSES, UNDECIDED_STATUSES, ServiceBase
from .bookings import BookingsMixin
from .checks import ChecksMixin
from .qualifications import QualificationsMixin
from .resources import ResourcesMixin
from .waitlist import WaitlistMixin


class BookingService(AccountsMixin, ResourcesMixin, QualificationsMixin, BookingsMixin, WaitlistMixin,
                     AvailabilityMixin, AuditMixin, ChecksMixin, ServiceBase):
    """Every booking rule in one service (see the module docstring for where each part lives)."""


__all__ = ["BookingService", "ACTIVE_REQUEST_STATUSES", "HEAD_STATUSES", "UNDECIDED_STATUSES",
           "new_invite_code", "normalize_invite_code"]
