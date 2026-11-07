"""Sprint 3: Check-in ("I'm here") and missed bookings.

An approved booking can be checked in by the person it is for from shortly before its start until shortly after
it (BookingRules.check_in_opens_minutes / check_in_closes_minutes, never after the end). If nobody checks in by
then, the booking is marked as missed (attendance NO_SHOW), unless the resource was under maintenance or closed
(EXCUSED). Missed bookings feed the usage report; there is no penalty. The booking freeze and unfreeze requests
were removed on 2026-11-07 (client, Week 8: make cancelling easy instead of penalising).
"""
from dataclasses import replace
from datetime import timedelta

from ..domain import BookingStatus
from ..errors import DomainError


class AttendanceMixin:
    def check_in_window(self, booking):
        rules = self.rules()
        opens = booking.start - timedelta(minutes=rules.check_in_opens_minutes)
        closes = min(booking.end, booking.start + timedelta(minutes=rules.check_in_closes_minutes))
        return opens, closes

    def check_in_state(self, booking):
        """For the booking JSON: whether the "I'm here" button should show now."""
        if booking.status != BookingStatus.APPROVED or booking.attendance is not None:
            return {"check_in_open": False, "check_in_opens_at": None, "check_in_closes_at": None}
        opens, closes = self.check_in_window(booking)
        now = self.now()
        return {"check_in_open": opens <= now < closes, "check_in_opens_at": opens, "check_in_closes_at": closes}

    def check_in(self, actor, booking_id):
        source = self.repo.get_booking(str(booking_id))
        if source is None or source.student_id != actor.id:
            raise DomainError("NOT_FOUND", "Booking not found.", 404)
        with self.repo.atomic(resource_ids=[source.resource_id], student_ids=[source.student_id]):
            source = self.repo.get_booking(source.id)
            if source.attendance == "CHECKED_IN":
                return source
            if source.status != BookingStatus.APPROVED or source.attendance is not None:
                raise DomainError("CHECK_IN_NOT_AVAILABLE", "Only an approved booking that is starting can be checked in.", 409)
            opens, closes = self.check_in_window(source)
            now = self.now()
            if now < opens:
                raise DomainError("CHECK_IN_NOT_OPEN", "Check-in opens shortly before the booking starts.", 409,
                                  {"check_in_opens_at": opens.isoformat().replace("+00:00", "Z")})
            if now >= closes:
                raise DomainError("CHECK_IN_CLOSED", "The check-in time for this booking has passed.", 409)
            updated = replace(source, attendance="CHECKED_IN", checked_in_at=now, updated_at=now)
            self._save_booking(updated)
            self._audit(actor.id, "BOOKING_CHECKED_IN", "booking", updated.id)
            return updated

    def _process_attendance(self):
        """Mark approved bookings whose check-in time has passed without a check-in. Changes no other booking."""
        # 2026-10-29 (load test S1): check-in closes after the start (check_in_closes_minutes >= 1), so only approved,
        # unmarked bookings that have started can be due. Past bookings are already marked and are not read again.
        for candidate in self.repo.list_bookings(statuses=[BookingStatus.APPROVED], unmarked=True, start_to=self.now()):
            if candidate.status != BookingStatus.APPROVED or candidate.attendance is not None:
                continue
            if self.check_in_window(candidate)[1] > self.now():
                continue
            with self.repo.atomic(resource_ids=[candidate.resource_id], student_ids=[candidate.student_id]):
                current = self.repo.get_booking(candidate.id)
                if current.status != BookingStatus.APPROVED or current.attendance is not None:
                    continue
                now = self.now()
                resource = self.repo.get_resource(current.resource_id)
                if resource is None or not resource.bookable:
                    self._save_booking(replace(current, attendance="EXCUSED", updated_at=now))
                    self._audit("SYSTEM", "BOOKING_ATTENDANCE_EXCUSED", "booking", current.id)
                    continue
                self._save_booking(replace(current, attendance="NO_SHOW", updated_at=now))
                self._audit("SYSTEM", "BOOKING_NO_SHOW", "booking", current.id)
                self._notify(current.student_id, "NO_SHOW_RECORDED", "Missed booking recorded",
                             f"You did not check in for {self._booking_label(current)}. "
                             "If you cannot come, please cancel the booking so someone else can use the time.", current)
