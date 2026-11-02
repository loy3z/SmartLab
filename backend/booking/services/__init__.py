"""Booking policy independent of HTTP and the database adapter.

``BookingService`` is the one entry point the API, scheduled commands and tests use. Its code is split by topic;
each file holds one part (all methods share ``self``: repo, storage, clock, rules and calendar_sync):

  base.py            clock, rules, role checks, audit, resource lookup, shared status groups
  accounts.py        user list, deactivation, staff accounts and sign-in, finding a person to book for
  resources.py       Manager resource settings (review window, maintenance/closed) and the bookings report
  qualifications.py  induction upload, review, validity and prerequisites
  checks.py          the one shared rule check and conflict lookups
  bookings.py        create (incl. on behalf, urgent), review, cancel, Manager reschedule
  additional_hours.py non-reserving spare-capacity requests and Manager-only allocation
  long_bookings.py    longer single-booking requests requiring a Manager's explicit decision
  waitlist.py        expiry, automatic decisions, waitlist promotion
  availability.py    one resource's slots for a day, and the booking page day overview
  audit.py           audit trail query
  notifications.py   website notifications (the bell); extra channels in booking/notification_channels.py
  calendar_feed.py   calendar subscription link (iCalendar feed, booking/ics.py)
  attendance.py      check-in, missed bookings, booking freeze and unfreeze requests
  series.py          weekly series made by staff
  reminders.py       reminders: booking coming up, induction expiring soon
  reports.py         usage report for Managers
  changes.py         change requests: the person a booking is for asks for a new time (Sprint 3)
  site_contact.py    the lab's contact details, set by a Manager (Sprint 3)
  overview.py        the staff "Today" page: what needs doing first (Sprint 3)
  announcements.py   attributed public notices and resource-status announcements (Sprint 3, 1.19.0)

To add a feature, put its methods in the file for its topic (or a new mixin listed below) and its tests next to
the existing ones; import ``BookingService`` from ``booking.services`` as before.
"""
from .announcements import AnnouncementsMixin  # Sprint 3 (1.19.0)
from .additional_hours import AdditionalHoursMixin
from .long_bookings import LongBookingsMixin
from .accounts import AccountsMixin, new_invite_code, normalize_invite_code
from .attendance import AttendanceMixin
from .audit import AuditMixin
from .availability import AvailabilityMixin
from .calendar_feed import CalendarFeedMixin
from .changes import ChangesMixin  # Sprint 3 (1.16.0)
from .overview import OverviewMixin  # Sprint 3 (1.16.0)
from .site_contact import SiteContactMixin  # Sprint 3 (1.16.0)
from .base import ACTIVE_REQUEST_STATUSES, HEAD_STATUSES, UNDECIDED_STATUSES, ServiceBase
from .bookings import BookingsMixin
from .checks import ChecksMixin
from .notifications import NotificationsMixin
from .qualifications import QualificationsMixin
from .reminders import RemindersMixin
from .reports import ReportsMixin
from .resources import ResourcesMixin
from .series import SeriesMixin
from .waitlist import WaitlistMixin


class BookingService(AnnouncementsMixin, AdditionalHoursMixin, LongBookingsMixin, AccountsMixin, ResourcesMixin, QualificationsMixin, BookingsMixin, ChangesMixin, SeriesMixin, WaitlistMixin,
                     AttendanceMixin, RemindersMixin, ReportsMixin, OverviewMixin, SiteContactMixin, AvailabilityMixin, CalendarFeedMixin, NotificationsMixin, AuditMixin,
                     ChecksMixin,
                     ServiceBase):
    """Every booking rule in one service (see the module docstring for where each part lives)."""


__all__ = ["BookingService", "ACTIVE_REQUEST_STATUSES", "HEAD_STATUSES", "UNDECIDED_STATUSES",
           "new_invite_code", "normalize_invite_code"]
