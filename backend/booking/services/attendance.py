"""Sprint 3: Check-in ("I'm here"), missed bookings and the booking freeze.

An approved booking can be checked in by the person it is for from shortly before its start until shortly after
it (BookingRules.check_in_opens_minutes / check_in_closes_minutes, never after the end). If nobody checks in by
then, the booking counts as missed, unless the resource was under maintenance or closed. When a person's missed
count reaches BookingRules.freeze_after_no_shows, their booking is frozen for freeze_days: every later booking and
request of theirs is cancelled and they cannot be booked for (by themselves or by staff). Staff keep their
reviewing rights while frozen. A frozen person can ask to be unfrozen; an Admin or Manager decides, or unfreezes
them directly. The check-in button can be pressed from anywhere, so this discourages forgetting rather than
cheating.
"""
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from ..domain import BookingStatus, UnfreezeRequest, UnfreezeStatus
from ..errors import DomainError
from .base import ACTIVE_REQUEST_STATUSES


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
        """Mark approved bookings whose check-in time has passed without a check-in. Returns cancelled bookings."""
        cancelled = []
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
                person = self.repo.get_principal(current.student_id)
                count = person.no_show_count + 1
                limit = self.rules().freeze_after_no_shows
                self._audit("SYSTEM", "BOOKING_NO_SHOW", "booking", current.id, no_show_count=count)
                if count >= limit:
                    cancelled += self._freeze(person, now)
                else:
                    self.repo.save_principal(replace(person, no_show_count=count))
                    self._notify(person.id, "NO_SHOW_RECORDED", "Missed booking recorded",
                                 f"You did not check in for {self._booking_label(current)}. Missed bookings: {count} of "
                                 f"{limit}; at {limit} your booking is frozen for {self.rules().freeze_days} days.", current)
        return cancelled

    def _freeze(self, person, now):
        """Freeze booking and cancel every later booking or request of this person (freed time goes to the waitlist)."""
        until = now + timedelta(days=self.rules().freeze_days)
        self.repo.save_principal(replace(person, no_show_count=0, frozen_until=until))
        self._audit("SYSTEM", "ACCOUNT_FROZEN", "principal", person.id, frozen_until=until.isoformat())
        cancelled = []
        for booking in self.repo.list_bookings(student_id=person.id):
            if booking.status not in ACTIVE_REQUEST_STATUSES or booking.start <= now:
                continue
            with self.repo.atomic(resource_ids=[booking.resource_id], student_ids=[person.id]):
                current = self.repo.get_booking(booking.id)
                if current.status not in ACTIVE_REQUEST_STATUSES:
                    continue
                revised = replace(current, status=BookingStatus.CANCELLED, reason_code="ACCOUNT_FROZEN", updated_at=now)
                self._save_booking(revised)
                self._audit("SYSTEM", "BOOKING_CANCELLED", "booking", revised.id, reason_code="ACCOUNT_FROZEN")
                cancelled.append(revised)
                cancelled += self._promote_waitlist(revised.resource_id)
        self._notify(person.id, "ACCOUNT_FROZEN", "Booking frozen",
                     f"You missed {self.rules().freeze_after_no_shows} bookings, so you cannot book until "
                     f"{self._local_day(until)}. Your {len([item for item in cancelled if item.student_id == person.id])} "
                     "later booking(s) and request(s) were cancelled. You can ask staff to unfreeze you.",
                     link="/bookings")
        self._remember_changed(cancelled)
        return cancelled

    def _local_day(self, value):
        local = value.astimezone(ZoneInfo("Australia/Sydney"))
        return f"{local.day} {local:%b %Y}"

    def frozen_violation(self, person):
        if person.frozen_at(self.now()):
            return DomainError("ACCOUNT_FROZEN", "Booking is frozen for this person after missed bookings.", 403,
                               {"frozen_until": person.frozen_until.isoformat().replace("+00:00", "Z"), "zid": person.zid})
        return None

    # Unfreeze requests -------------------------------------------------------------------------------------

    def request_unfreeze(self, actor, reason):
        reason = (reason or "").strip()
        if not reason or len(reason) > 1000:
            raise DomainError("VALIDATION_ERROR", "Explain why you should be unfrozen (up to 1000 characters).")
        with self.repo.atomic(student_ids=[actor.id]):
            person = self.repo.get_principal(actor.id)
            if not person.frozen_at(self.now()):
                raise DomainError("NOT_FROZEN", "Your booking is not frozen.", 409)
            if any(item.status == UnfreezeStatus.PENDING for item in self.repo.list_unfreeze_requests(actor.id)):
                raise DomainError("UNFREEZE_ALREADY_REQUESTED", "You already have a request waiting for staff.", 409)
            request = UnfreezeRequest(str(uuid4()), actor.id, reason, self.now())
            self.repo.save_unfreeze_request(request)
            self._audit(actor.id, "UNFREEZE_REQUESTED", "principal", actor.id, request_id=request.id)
            return request

    def my_unfreeze_requests(self, actor):
        return list(reversed(self.repo.list_unfreeze_requests(actor.id)))

    def list_unfreeze_requests(self, actor, status=None):
        self.require_staff(actor)
        items = self.repo.list_unfreeze_requests()
        return [item for item in items if status is None or item.status.value == status]

    def review_unfreeze(self, actor, request_id, decision, reason=""):
        self.require_staff(actor)
        if decision not in ("APPROVED", "REJECTED"):
            raise DomainError("VALIDATION_ERROR", "Choose APPROVED or REJECTED.")
        reason = (reason or "").strip()
        if decision == "REJECTED" and not reason:
            raise DomainError("REASON_REQUIRED", "A rejection reason is required.")
        request = self.repo.get_unfreeze_request(str(request_id))
        if request is None:
            raise DomainError("NOT_FOUND", "Unfreeze request not found.", 404)
        with self.repo.atomic(student_ids=[request.principal_id]):
            request = self.repo.get_unfreeze_request(request.id)
            if request.status != UnfreezeStatus.PENDING:
                raise DomainError("ALREADY_REVIEWED", "This request was already decided.", 409)
            if request.principal_id == actor.id:
                raise DomainError("SELF_REVIEW_FORBIDDEN", "Another Admin or Manager must decide your own request.", 403)
            decided = replace(request, status=UnfreezeStatus(decision), decided_by=actor.id, decided_at=self.now(),
                              decision_reason=reason or None)
            self.repo.save_unfreeze_request(decided)
            self._audit(actor.id, f"UNFREEZE_{decision}", "principal", request.principal_id, request_id=request.id,
                        reason=reason)
            if decision == "APPROVED":
                self._lift_freeze(request.principal_id)
                self._notify(request.principal_id, "UNFREEZE_APPROVED", "Booking unfrozen",
                             "Your unfreeze request was approved. You can book again.", link="/resources")
            else:
                self._notify(request.principal_id, "UNFREEZE_REJECTED", "Unfreeze request rejected",
                             f"Your unfreeze request was rejected. Reason: {reason}", link="/bookings")
            return decided

    def unfreeze(self, actor, principal_id, reason=""):
        """Staff lift a freeze directly (also closes the person's waiting request, if any)."""
        self.require_staff(actor)
        principal_id = str(principal_id)
        if principal_id == actor.id:
            raise DomainError("SELF_MODIFICATION_FORBIDDEN", "Another Admin or Manager must unfreeze you.", 403)
        with self.repo.atomic(student_ids=[principal_id]):
            person = self.repo.get_principal(principal_id)
            if person is None:
                raise DomainError("NOT_FOUND", "User not found.", 404)
            if not person.frozen_at(self.now()):
                raise DomainError("NOT_FROZEN", "This person's booking is not frozen.", 409)
            self._lift_freeze(principal_id)
            for request in self.repo.list_unfreeze_requests(principal_id):
                if request.status == UnfreezeStatus.PENDING:
                    self.repo.save_unfreeze_request(replace(request, status=UnfreezeStatus.APPROVED, decided_by=actor.id,
                                                            decided_at=self.now(), decision_reason=(reason or "").strip() or None))
            self._audit(actor.id, "ACCOUNT_UNFROZEN", "principal", principal_id, reason=(reason or "").strip())
            self._notify(principal_id, "ACCOUNT_UNFROZEN", "Booking unfrozen", "Staff lifted your booking freeze. You can book again.",
                         link="/resources")
            return self.repo.get_principal(principal_id)

    def _lift_freeze(self, principal_id):
        person = self.repo.get_principal(principal_id)
        self.repo.save_principal(replace(person, frozen_until=None, no_show_count=0))
