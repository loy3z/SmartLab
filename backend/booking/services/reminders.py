"""Sprint 3: reminders in the notification bell.

- The day before an approved booking (BookingRules.reminder_hours_before): "remember to press I'm here".
- When a verified induction expires soon (BookingRules.induction_reminder_days): "upload new evidence in time".
Each reminder is sent once: before sending, we look for the same reminder in the person's notifications.
Both run from process_due_requests, so they go out whenever the website is used or `manage.py process_due` runs.
"""
from datetime import timedelta
from zoneinfo import ZoneInfo

from ..domain import BookingStatus, QualificationStatus

BOOKING_REMINDER = "BOOKING_REMINDER"
INDUCTION_EXPIRING = "INDUCTION_EXPIRING"


class RemindersMixin:
    def _send_reminders(self):
        """Send every reminder that is due and not sent yet. Returns how many were sent."""
        return self._booking_reminders() + self._induction_reminders()

    def _already_sent(self, person_id, kind, booking_id=None, link=None):
        return any(item.kind == kind and (booking_id is None or item.booking_id == booking_id)
                   and (link is None or item.link == link) for item in self.repo.list_notifications(person_id))

    def _booking_reminders(self):
        now, sent = self.now(), 0
        horizon = now + timedelta(hours=self.rules().reminder_hours_before)
        for booking in self.repo.list_bookings():
            due = booking.status == BookingStatus.APPROVED and booking.attendance is None and now < booking.start <= horizon
            if not due or self._already_sent(booking.student_id, BOOKING_REMINDER, booking_id=booking.id):
                continue
            opens, closes = self.check_in_window(booking)
            resource = self.repo.get_resource(booking.resource_id)
            zone = resource.timezone if resource else "Australia/Sydney"
            window = f"{opens.astimezone(ZoneInfo(zone)):%H:%M} and {closes.astimezone(ZoneInfo(zone)):%H:%M}"
            self._notify(booking.student_id, BOOKING_REMINDER, "Booking coming up",
                         f"{self._booking_label(booking)}. Press I'm here in My Bookings between {window}, "
                         "or it counts as a missed booking. Cancel it if you no longer need it.", booking)
            sent += 1
        return sent

    def _induction_reminders(self):
        now, sent = self.now(), 0
        horizon = now + timedelta(days=self.rules().induction_reminder_days)
        latest = {}
        for submission in self.repo.list_submissions():
            key = (submission.student_id, submission.requirement_id)
            if key not in latest or submission.submitted_at >= latest[key].submitted_at:
                latest[key] = submission
        for submission in latest.values():
            expiring = (submission.status == QualificationStatus.VERIFIED and submission.valid_until is not None
                        and now < submission.valid_until <= horizon)
            link = f"/induction?requirement={submission.requirement_id}&submission={submission.id}"
            if not expiring or self._already_sent(submission.student_id, INDUCTION_EXPIRING, link=link):
                continue
            requirement = self.repo.get_requirement(submission.requirement_id)
            name = requirement.name if requirement else "induction"
            days = max(1, (submission.valid_until - now).days)
            self._notify(submission.student_id, INDUCTION_EXPIRING, "Induction expires soon",
                         f"Your {name} expires in {days} day(s). Bookings after that date need new evidence: "
                         "upload it now so staff can review it in time.", link=link)
            sent += 1
        return sent
