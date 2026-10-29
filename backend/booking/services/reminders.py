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

    def _booking_reminders(self):
        now, sent = self.now(), 0
        horizon = now + timedelta(hours=self.rules().reminder_hours_before)
        # 2026-10-29 (load test S1): read only bookings that may be due, and look up the reminders already sent for
        # them in one query (before: every booking, then one notification query per due booking).
        candidates = self.repo.list_bookings(statuses=[BookingStatus.APPROVED], unmarked=True, start_from=now, start_to=horizon)
        sent_for = {(item.recipient_id, item.booking_id) for item in
                    self.repo.list_booking_notifications(BOOKING_REMINDER, [item.id for item in candidates])} if candidates else set()
        for booking in candidates:
            due = booking.status == BookingStatus.APPROVED and booking.attendance is None and now < booking.start <= horizon
            if not due or (booking.student_id, booking.id) in sent_for:
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
        # 2026-10-29 (load test S8): a reminder is due only for a person who has a verified induction expiring in the
        # window, so find those first (usually none: one query) and read only their submissions to find each latest
        # one, instead of every submission on every request. Reminders already sent are read in one query.
        expiring_soon = self.repo.list_submissions(statuses=[QualificationStatus.VERIFIED], valid_from=now, valid_to=horizon)
        if not expiring_soon:
            return 0
        people = sorted({item.student_id for item in expiring_soon})
        sent_links = {(item.recipient_id, item.link) for item in self.repo.list_kind_notifications(INDUCTION_EXPIRING, people)}
        latest = {}
        for submission in self.repo.list_submissions(student_ids=people):
            key = (submission.student_id, submission.requirement_id)
            if key not in latest or submission.submitted_at >= latest[key].submitted_at:
                latest[key] = submission
        for submission in latest.values():
            expiring = (submission.status == QualificationStatus.VERIFIED and submission.valid_until is not None
                        and now < submission.valid_until <= horizon)
            link = f"/induction?requirement={submission.requirement_id}&submission={submission.id}"
            if not expiring or (submission.student_id, link) in sent_links:
                continue
            requirement = self.repo.get_requirement(submission.requirement_id)
            name = requirement.name if requirement else "induction"
            days = max(1, (submission.valid_until - now).days)
            self._notify(submission.student_id, INDUCTION_EXPIRING, "Induction expires soon",
                         f"Your {name} expires in {days} day(s). Bookings after that date need new evidence: "
                         "upload it now so staff can review it in time.", link=link)
            sent += 1
        return sent
