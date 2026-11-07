"""Manager resource settings: adding and editing rooms and equipment, archiving them, the review window,
maintenance/closed status, and the bookings report.

Resource setup rules (all checked in _check_resource_fields):
- Every resource needs a name, a location and the induction people must have to book it.
- Names are unique among listed (not archived) resources, ignoring upper/lower case.
- A room has no room and no category. Equipment may name the listed room it is kept in, and a category.
- Bookings use slot_minutes steps (15, 30 or 60). Opening and closing times fall on those steps, closing is
  after opening, and the longest booking is a whole number of steps that fits inside the opening hours.
- The kind (room or equipment) is fixed once created: to change it, add a new resource and archive the old one.
Editing never changes existing bookings; the new rules apply to later requests, approvals and automatic
decisions. The edit returns the future bookings that no longer fit, so the Manager can decide about them.
Archiving hides a resource (active = false) instead of deleting it, so bookings and the audit trail keep it.
"""
from dataclasses import replace
from datetime import time, timedelta
from uuid import uuid4

from ..domain import (MAX_PENDING_HOLD_MINUTES, BookingStatus, Resource, ResourceDetail, ResourceInternalInfo, ResourceKind,
                      ResourceStatus, Role)
from ..errors import DomainError
from .base import ACTIVE_REQUEST_STATUSES

SLOT_CHOICES = (15, 30, 60)
# Fields a Manager may set when adding a resource; editing may change all of them except kind.
EDITABLE_FIELDS = ("name", "location", "description", "required_qualification_id", "room_id", "category",
                   "slot_minutes", "max_booking_minutes", "opening_time", "closing_time", "pending_hold_minutes",
                   "capacity", "details")  # Sprint 3 (1.16.0): capacity, details
MAX_DETAILS = 12  # Sprint 3 (1.16.0): "label: value" lines per resource
# 2026-11-07 (client, Week 8): Admins see bookings that ended at most this many days ago; full history is for Managers.
ADMIN_HISTORY_DAYS = 7
# 2026-11-07 (client, Week 8): Manager-only internal fields and their longest length.
INTERNAL_FIELDS = {"owner": 120, "asset_number": 60, "provided_by": 120, "specifications": 2000}


class ResourcesMixin:
    # Adding, editing and archiving resources (Manager only) ------------------------------------------------

    def list_all_resources(self, actor):
        """Manager: every resource, archived ones included (the booking pages only show listed ones)."""
        self.require_manager(actor)
        return sorted(self.repo.list_resources(), key=lambda item: (item.kind != ResourceKind.ROOM, item.name.casefold()))

    def create_resource(self, actor, kind, fields):
        """Manager: add a room or a piece of equipment. Unset numbers and times use the usual defaults."""
        self.require_manager(actor)
        if kind not in ResourceKind._value2member_map_:
            raise DomainError("VALIDATION_ERROR", "kind must be ROOM or EQUIPMENT.")
        unknown = set(fields) - set(EDITABLE_FIELDS)
        if unknown:
            raise DomainError("VALIDATION_ERROR", f"Unknown fields: {', '.join(sorted(unknown))}.")
        defaults = dict(description="", slot_minutes=30, max_booking_minutes=480, opening_time=time(8), closing_time=time(20),
                        pending_hold_minutes=self.rules().default_review_window_minutes, room_id=None, category=None,
                        capacity=None, details=())  # Sprint 3 (1.16.0)
        values = {**defaults, **{key: value for key, value in fields.items() if value is not None}}
        with self.repo.atomic():
            resource = self._check_resource_fields(ResourceKind(kind), values, resource_id=None)
            created = Resource(id=str(uuid4()), kind=ResourceKind(kind), **resource)
            self.repo.save_resource(created)
            self._audit(actor.id, "RESOURCE_CREATED", "resource", created.id, resource_kind=kind, **self._audit_fields(created))
            return created

    def update_resource(self, actor, resource_id, changes):
        """Manager: change a resource's details and booking rules. Returns (resource, future bookings that no longer fit).

        Existing bookings are kept as they are; the Manager decides whether to cancel or move the ones listed.
        """
        self.require_manager(actor)
        unknown = set(changes) - set(EDITABLE_FIELDS)
        if unknown:
            raise DomainError("VALIDATION_ERROR", f"Unknown or fixed fields: {', '.join(sorted(unknown))}.")
        with self.repo.atomic(resource_ids=[str(resource_id)]):
            current = self.resource(resource_id)
            values = {field: getattr(current, field) for field in EDITABLE_FIELDS}
            values.update(changes)
            checked = self._check_resource_fields(current.kind, values, resource_id=current.id)
            updated = replace(current, **checked)
            changed = {field: [self._audit_value(getattr(current, field)), self._audit_value(getattr(updated, field))]
                       for field in EDITABLE_FIELDS if getattr(current, field) != getattr(updated, field)}
            if changed:
                self.repo.save_resource(updated)
                self._audit(actor.id, "RESOURCE_UPDATED", "resource", current.id, changes=changed)
            return updated, self._bookings_outside_rules(updated)

    def resource_internal_info(self, actor, resource_id):
        """Manager only (client, Week 8): owner, UNSW asset number, where it came from, specifications. Empty until saved."""
        self.require_manager(actor)
        resource = self.resource(resource_id)
        return self.repo.get_resource_internal_info(resource.id) or ResourceInternalInfo(resource.id)

    def update_resource_internal_info(self, actor, resource_id, changes):
        """Manager only: change the internal fields sent (blank clears one). Students and Admins never see them."""
        self.require_manager(actor)
        cleaned = {}
        for field, value in changes.items():
            text = (value or "").strip()
            if field not in INTERNAL_FIELDS or len(text) > INTERNAL_FIELDS.get(field, 0):
                raise DomainError("VALIDATION_ERROR", f"{field}: unknown field or too long.", 400, {field: ["Unknown or too long."]})
            cleaned[field] = text
        with self.repo.atomic(resource_ids=[str(resource_id)]):
            current = self.resource_internal_info(actor, resource_id)
            updated = replace(current, **cleaned, updated_at=self.now(), updated_by=actor.id)
            self.repo.save_resource_internal_info(updated)
            self._audit(actor.id, "RESOURCE_INTERNAL_INFO_UPDATED", "resource", current.resource_id,
                        changes=sorted(field for field in cleaned if getattr(current, field) != getattr(updated, field)))
            return updated

    def archive_resource(self, actor, resource_id):
        """Manager: stop listing a resource. Refused while it still has future bookings or, for a room, listed equipment."""
        self.require_manager(actor)
        with self.repo.atomic(resource_ids=[str(resource_id)]):
            current = self.resource(resource_id)
            if not current.active:
                return current
            upcoming = [item for item in self.repo.list_bookings(resource_id=current.id)
                        if item.status in ACTIVE_REQUEST_STATUSES and item.end > self.now()]
            if upcoming:
                raise DomainError("RESOURCE_HAS_BOOKINGS", "Cancel or move this resource's future bookings and requests first.",
                                  409, {"booking_count": len(upcoming)})
            if current.kind == ResourceKind.ROOM:
                kept_here = [item.name for item in self.repo.list_resources() if item.active and item.room_id == current.id]
                if kept_here:
                    raise DomainError("ROOM_HAS_EQUIPMENT", "Move or archive the equipment kept in this room first.", 409,
                                      {"equipment": sorted(kept_here)})
            archived = replace(current, active=False)
            self.repo.save_resource(archived)
            self._audit(actor.id, "RESOURCE_ARCHIVED", "resource", current.id)
            return archived

    def restore_resource(self, actor, resource_id):
        """Manager: list an archived resource again (its name must still be free; equipment needs its room listed)."""
        self.require_manager(actor)
        with self.repo.atomic(resource_ids=[str(resource_id)]):
            current = self.resource(resource_id)
            if current.active:
                return current
            values = {field: getattr(current, field) for field in EDITABLE_FIELDS}
            self._check_resource_fields(current.kind, values, resource_id=current.id)
            restored = replace(current, active=True)
            self.repo.save_resource(restored)
            self._audit(actor.id, "RESOURCE_RESTORED", "resource", current.id)
            return restored

    def _check_resource_fields(self, kind, values, resource_id):
        """Apply the resource setup rules (see the module docstring). Returns the cleaned values or raises."""
        def invalid(field, message):
            raise DomainError("VALIDATION_ERROR", message, 400, {field: [message]})

        name = (values.get("name") or "").strip()
        location = (values.get("location") or "").strip()
        description = (values.get("description") or "").strip()
        if not 1 <= len(name) <= 120:
            invalid("name", "Give a name of up to 120 characters.")
        if not 1 <= len(location) <= 120:
            invalid("location", "Give a location of up to 120 characters.")
        if len(description) > 1000:
            invalid("description", "The description can be up to 1000 characters.")
        same_name = [item for item in self.repo.list_resources()
                     if item.active and item.id != resource_id and item.name.casefold() == name.casefold()]
        if same_name:
            raise DomainError("RESOURCE_NAME_TAKEN", "Another listed resource already has this name.", 409, {"name": name})

        requirement_id = values.get("required_qualification_id")
        if not requirement_id or self.repo.get_requirement(str(requirement_id)) is None:
            invalid("required_qualification_id", "Choose the induction people need to book this resource.")

        room_id = values.get("room_id") or None
        category = (values.get("category") or "").strip() or None
        if kind == ResourceKind.ROOM and (room_id or category):
            invalid("room_id" if room_id else "category", "A room cannot be kept in another room or have an equipment category.")
        if room_id:
            room = self.repo.get_resource(str(room_id))
            if room is None or room.kind != ResourceKind.ROOM or not room.active:
                invalid("room_id", "Choose a listed room for this equipment.")
        if category is not None and len(category) > 60:
            invalid("category", "The category can be up to 60 characters.")

        slot = values.get("slot_minutes")
        if slot not in SLOT_CHOICES:
            invalid("slot_minutes", "Bookings move in steps of 15, 30 or 60 minutes.")
        opening, closing = values.get("opening_time"), values.get("closing_time")
        if not isinstance(opening, time) or not isinstance(closing, time) or closing <= opening:
            invalid("closing_time", "Closing time must be after opening time.")
        for field, value in (("opening_time", opening), ("closing_time", closing)):
            if value.second or value.microsecond or (value.hour * 60 + value.minute) % slot:
                invalid(field, f"Use a time on a {slot}-minute step, e.g. 08:00.")
        open_minutes = (closing.hour * 60 + closing.minute) - (opening.hour * 60 + opening.minute)
        longest = values.get("max_booking_minutes")
        if isinstance(longest, bool) or not isinstance(longest, int) or longest < slot or longest % slot or longest > open_minutes:
            invalid("max_booking_minutes",
                    f"The longest booking must be a multiple of {slot} minutes and fit within the opening hours ({open_minutes} minutes).")
        hold = values.get("pending_hold_minutes")
        if isinstance(hold, bool) or not isinstance(hold, int) or not 1 <= hold <= MAX_PENDING_HOLD_MINUTES:
            invalid("pending_hold_minutes", f"The review window must be 1 to {MAX_PENDING_HOLD_MINUTES} minutes.")

        # Sprint 3 (1.16.0): capacity (rooms only, 1-1000 people) and up to MAX_DETAILS "label: value" lines.
        capacity = values.get("capacity")
        if capacity is not None:
            if kind != ResourceKind.ROOM:
                invalid("capacity", "Only rooms have a capacity.")
            if isinstance(capacity, bool) or not isinstance(capacity, int) or not 1 <= capacity <= 1000:
                invalid("capacity", "Capacity must be a whole number of people from 1 to 1000.")
        details = []
        for item in values.get("details") or ():
            label, value = ((item.label, item.value) if isinstance(item, ResourceDetail)
                            else ((item or {}).get("label", ""), (item or {}).get("value", "")))
            label, value = str(label).strip(), str(value).strip()
            if not label and not value:
                continue  # an empty row in the form
            if not 1 <= len(label) <= 40 or not 1 <= len(value) <= 200:
                invalid("details", "Each detail needs a label (up to 40 characters) and a value (up to 200).")
            details.append(ResourceDetail(label, value))
        if len(details) > MAX_DETAILS:
            invalid("details", f"Add at most {MAX_DETAILS} details.")

        return dict(name=name, location=location, description=description, required_qualification_id=str(requirement_id),
                    room_id=str(room_id) if room_id else None, category=category, slot_minutes=slot,
                    max_booking_minutes=longest, opening_time=opening, closing_time=closing, pending_hold_minutes=hold,
                    capacity=capacity, details=tuple(details))

    def _bookings_outside_rules(self, resource):
        """Future pending, waitlisted or approved bookings that break the resource's current time or induction rules."""
        result = []
        for booking in self.repo.list_bookings(resource_id=resource.id):
            if booking.status not in ACTIVE_REQUEST_STATUSES or booking.start <= self.now():
                continue
            problem = (self._period_violation(resource, booking.start, booking.end, allow_long_booking=booking.long_booking)
                       or self._qualification_violation(booking.student_id, resource, booking.end))
            if problem:
                result.append((booking, problem.code))
        return sorted(result, key=lambda pair: (pair[0].start, pair[0].id))

    def _audit_fields(self, resource):
        return {field: self._audit_value(getattr(resource, field)) for field in EDITABLE_FIELDS}

    @staticmethod
    def _audit_value(value):
        if isinstance(value, tuple):  # Sprint 3 (1.16.0): details as [label, value] pairs in the audit record
            return [[item.label, item.value] for item in value]
        return value.strftime("%H:%M") if isinstance(value, time) else value

    # Review window and maintenance status ----------------------------------------------------------------

    def set_pending_hold_minutes(self, actor, resource_id, minutes):
        return self.set_booking_policy(actor, resource_id, pending_hold_minutes=minutes)

    def set_booking_policy(self, actor, resource_id, pending_hold_minutes):
        """Manager only: how long a pending request waits for an Admin (holding its slot) before the system decides.

        Applies to requests that become pending afterwards; existing deadlines stay unchanged.
        """
        self.require_manager(actor)
        if isinstance(pending_hold_minutes, bool) or not isinstance(pending_hold_minutes, int) \
                or not 1 <= pending_hold_minutes <= MAX_PENDING_HOLD_MINUTES:
            raise DomainError("VALIDATION_ERROR", f"pending_hold_minutes must be an integer from 1 to {MAX_PENDING_HOLD_MINUTES}.")
        with self.repo.atomic(resource_ids=[str(resource_id)]):
            current = self.resource(resource_id)
            updated = replace(current, pending_hold_minutes=pending_hold_minutes)
            self.repo.save_resource(updated)
            self._audit(actor.id, "RESOURCE_BOOKING_POLICY_UPDATED", "resource", current.id,
                        previous_minutes=current.pending_hold_minutes, pending_hold_minutes=pending_hold_minutes)
            return updated

    def set_resource_status(self, actor, resource_id, status, reason=None, expected_back=None):
        """Manager only: open a resource or take it out of service (MAINTENANCE / CLOSED).

        Only new requests, approvals and waitlist promotions are stopped; existing bookings are kept so the
        Manager can decide whether to cancel them (they are returned as affected_bookings). Reopening the
        resource offers freed time to its waitlist again.

        Sprint 3 (1.16.0): when the status changes, everyone with a future booking or request on this resource is
        told (website notification, and email when email is on): see ``_notify_status_change``. Bookings on
        equipment kept in a room are not affected by the room's status, so they are not told.
        """
        self.require_manager(actor)
        if status not in ResourceStatus._value2member_map_:
            raise DomainError("VALIDATION_ERROR", "status must be AVAILABLE, MAINTENANCE or CLOSED.")
        reason = (reason or "").strip() or None
        if status != ResourceStatus.AVAILABLE.value and not reason:
            raise DomainError("REASON_REQUIRED", "Give a reason when taking a resource out of service.")
        with self.repo.atomic(resource_ids=[str(resource_id)]):
            current = self.resource(resource_id)
            updated = replace(current, status=ResourceStatus(status),
                              status_reason=None if status == ResourceStatus.AVAILABLE.value else reason)
            if updated != current:
                self.repo.save_resource(updated)
                self._audit(actor.id, "RESOURCE_STATUS_CHANGED", "resource", current.id,
                            previous_status=current.status.value, status=updated.status.value, reason=updated.status_reason)
                if updated.bookable:
                    self._promote_waitlist(updated.id)
            # Sprint 3 (1.19.0): status and its public announcement commit or roll back together.
            self._status_announcement(actor, updated, expected_back)
            affected = sorted((item for item in self.repo.list_bookings(resource_id=updated.id)
                               if item.status in ACTIVE_REQUEST_STATUSES and item.end > self.now()),
                              key=lambda item: (item.start, item.id))
            if updated.status != current.status:
                self._notify_status_change(updated, affected)  # Sprint 3 (1.16.0)
            return updated, affected

    def _notify_status_change(self, resource, affected):
        """Sprint 3 (1.16.0): tell each person with a future booking or request on this resource that its status changed.

        Out of service (MAINTENANCE / CLOSED): RESOURCE_OUT_OF_SERVICE with the Manager's reason. Bookings are kept
        (the Manager decides whether to cancel or move them, which sends its own notice); undecided requests cannot be
        approved until it reopens. Back to AVAILABLE: RESOURCE_REOPENED. One notice per booking, so each names its time.
        """
        state = {ResourceStatus.MAINTENANCE: "under maintenance", ResourceStatus.CLOSED: "closed"}.get(resource.status)
        for booking in affected:
            label = self._booking_label(booking)
            if state:
                outcome = ("Your booking is kept for now; staff will let you know if it has to change."
                           if booking.status == BookingStatus.APPROVED
                           else "Your request cannot be approved while it is out of service.")
                self._notify(booking.student_id, "RESOURCE_OUT_OF_SERVICE", f"{resource.name} is {state}",
                             f"{resource.name} is {state}: {resource.status_reason}. This affects {label}. {outcome}", booking)
            else:
                self._notify(booking.student_id, "RESOURCE_REOPENED", f"{resource.name} is open again",
                             f"{resource.name} is open again. {label} goes ahead as planned"
                             f"{'' if booking.status == BookingStatus.APPROVED else ' once your request is approved'}.", booking)

    def booking_report(self, actor, statuses=None, resource_id=None, student_id=None, since=None, until=None, query=None):
        """Admin/Manager: every booking matching the filters, ordered by start time (for lists, print and CSV).

        Sprint 3: query matches part of the zID or name of the person booked for or of the person who created it.
        2026-11-07 (client, Week 8): an Admin only sees bookings that ended in the last ADMIN_HISTORY_DAYS days or later;
        the full history is for Managers.
        """
        self.require_staff(actor)
        self.process_due_requests()
        if actor.role == Role.ADMIN:
            earliest = self.now() - timedelta(days=ADMIN_HISTORY_DAYS)
            since = max(since, earliest) if since else earliest
        query = (query or "").strip().casefold()
        people = {item.id: f"{item.zid} {item.display_name}".casefold() for item in self.repo.list_principals()} if query else {}
        # 2026-10-29 (load test S2): the repository narrows the rows read (inclusive bounds); the checks below are unchanged.
        stored = self.repo.list_bookings(str(student_id) if student_id is not None else None,
                                         str(resource_id) if resource_id is not None else None,
                                         statuses=[BookingStatus(value) for value in statuses] if statuses else None,
                                         end_from=since, start_to=until)
        records = [item for item in stored
                   if (not statuses or item.status.value in statuses)
                   and (resource_id is None or item.resource_id == str(resource_id))
                   and (student_id is None or item.student_id == str(student_id))
                   and (since is None or item.end > since) and (until is None or item.start < until)
                   and (not query or query in people.get(item.student_id, "") or query in people.get(item.created_by or "", ""))]
        return sorted(records, key=lambda item: (item.start, item.id))
