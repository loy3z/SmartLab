"""Sprint 3: Website notifications: the bell in the top bar.

A notification is stored in the same transaction as the change it describes. Booking changes are noticed in one
place (``_booking_changed``, called whenever a booking is saved), so every path that approves, rejects, promotes,
cancels or reschedules a booking tells the person it is for. Other notices (someone booked for you, induction
reviewed, missed check-in, freeze) are sent where they happen. Extra delivery channels (e.g. Outlook mail) are
plugged in through booking/notification_channels.py.
"""
from contextvars import ContextVar
from dataclasses import replace
from uuid import uuid4
from zoneinfo import ZoneInfo

from ..domain import BookingStatus, Notification, Role
from ..errors import DomainError

# Notifications created during the current request, so extra channels can send them after commit.
_new_notification_ids = ContextVar("booking_new_notification_ids", default=None)


def _local(value, zone):
    return value.astimezone(ZoneInfo(zone))


class NotificationsMixin:
    def describe_time(self, booking, resource=None):
        """Like "Mon 3 Nov 2026, 10:00-12:00", in the resource's time zone."""
        resource = resource or self.repo.get_resource(booking.resource_id)
        zone = resource.timezone if resource else "Australia/Sydney"
        start, end = _local(booking.start, zone), _local(booking.end, zone)
        return f"{start:%a} {start.day} {start:%b %Y}, {start:%H:%M}–{end:%H:%M}"

    def describe_moment(self, value, booking=None):
        """Like "Tue 4 Nov 2026, 10:00" in the resource's time zone (empty when value is None)."""
        if value is None:
            return ""
        resource = self.repo.get_resource(booking.resource_id) if booking else None
        local = _local(value, resource.timezone if resource else "Australia/Sydney")
        return f"{local:%a} {local.day} {local:%b %Y}, {local:%H:%M}"

    def _booking_label(self, booking):
        resource = self.repo.get_resource(booking.resource_id)
        return f"{resource.name if resource else 'Resource'} on {self.describe_time(booking, resource)}"

    def _notify(self, recipient_id, kind, title, body, booking=None, link=None):
        if not recipient_id:
            return None
        notification = Notification(str(uuid4()), str(recipient_id), kind, title, body, self.now(),
                                    link=link or ("/bookings" if booking else None),
                                    booking_id=booking.id if booking else None)
        self.repo.save_notification(notification)
        ids = _new_notification_ids.get()
        if ids is None:
            ids = []
            _new_notification_ids.set(ids)
        ids.append(notification.id)
        return notification

    def take_new_notification_ids(self):
        ids = _new_notification_ids.get() or []
        _new_notification_ids.set(None)
        return ids

    def _booking_changed(self, old, new):
        """Tell the person a booking is for when its outcome changes (called on every booking save)."""
        if old is None:
            return
        label = self._booking_label(new)
        if old.status != new.status:
            if new.status == BookingStatus.APPROVED:
                how = " automatically after the review window" if new.reason_code == "AUTO_APPROVED_AFTER_REVIEW_WINDOW" else ""
                if new.replaces_id:  # Sprint 3 (1.16.0): change request approved
                    self._notify(new.student_id, "CHANGE_APPROVED", "Booking moved",
                                 f"Your change was approved{how}: your booking is now {label}.{self._old_time_note(new, released=True)}", new)
                else:
                    self._notify(new.student_id, "BOOKING_APPROVED", "Booking approved", f"{label} was approved{how}.", new)
            elif new.status == BookingStatus.REJECTED:
                reason = f" Reason: {new.decision_reason}" if new.decision_reason else ""
                if new.replaces_id:  # Sprint 3 (1.16.0)
                    self._notify(new.student_id, "CHANGE_REJECTED", "Change request rejected",
                                 f"Your request to move to {label} was rejected.{reason}{self._old_time_note(new)}", new)
                else:
                    self._notify(new.student_id, "BOOKING_REJECTED", "Booking request rejected", f"{label} was rejected.{reason}", new)
            elif old.status == BookingStatus.WAITLISTED and new.status == BookingStatus.PENDING_APPROVAL:
                self._notify(new.student_id, "BOOKING_PROMOTED", "Your waitlisted request moved up",
                             f"A place opened up: {label} is now waiting for review.", new)
            elif new.status == BookingStatus.EXPIRED and old.status in (BookingStatus.WAITLISTED, BookingStatus.PENDING_APPROVAL):
                # Sprint 3: the start time came before a place opened up (waitlist) or before anyone decided.
                why = "no place opened up in time" if old.status == BookingStatus.WAITLISTED else "it was not decided in time"
                self._notify(new.student_id, "BOOKING_EXPIRED", "Request expired",
                             f"{label} expired: {why}.{self._old_time_note(new) if new.replaces_id else ''}", new)
            elif new.status == BookingStatus.CANCELLED and new.reason_code == "CANCELLED_BY_STAFF":
                self._notify(new.student_id, "BOOKING_CANCELLED", "Booking cancelled by staff", f"{label} was cancelled by staff.", new)
        elif new.status == BookingStatus.APPROVED and new.revision > old.revision:
            self._notify(new.student_id, "BOOKING_RESCHEDULED", "Booking moved by a Manager",
                         f"Your booking was moved to {label} (was {self.describe_time(old)}).", new)

    def _old_time_note(self, change, released=False):
        """Sprint 3 (1.16.0): sentence about the booking a change request replaces."""
        old = self.repo.get_booking(change.replaces_id) if change.replaces_id else None
        if old is None or old.status != BookingStatus.APPROVED:
            return ""
        if released:
            return f" Your earlier time ({self.describe_time(old)}) has been released."
        return f" Your current booking ({self.describe_time(old)}) stays as it is."

    def list_notifications(self, actor, unread_only=False, limit=50):
        items = self.repo.list_notifications(actor.id)
        unread = sum(1 for item in items if item.read_at is None)
        if unread_only:
            items = [item for item in items if item.read_at is None]
        return items[:limit], unread

    def mark_notification_read(self, actor, notification_id):
        notification = self.repo.get_notification(str(notification_id))
        if notification is None or notification.recipient_id != actor.id:
            raise DomainError("NOT_FOUND", "Notification not found.", 404)
        if notification.read_at is None:
            notification = replace(notification, read_at=self.now())
            self.repo.save_notification(notification)
        return notification

    def mark_all_notifications_read(self, actor):
        now, count = self.now(), 0
        for item in self.repo.list_notifications(actor.id):
            if item.read_at is None:
                self.repo.save_notification(replace(item, read_at=now))
                count += 1
        return count

    def _notify_managers(self, kind, title, body, booking=None, link=None, except_ids=()):
        for person in self.repo.list_principals():
            if person.role == Role.MANAGER and person.active and person.id not in except_ids:
                self._notify(person.id, kind, title, body, booking, link)
