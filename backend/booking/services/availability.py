"""Read-only time views: one resource's day of slots, and the booking page day overview."""
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from ..domain import BookingStatus, ResourceKind
from ..errors import DomainError
from .base import ACTIVE_REQUEST_STATUSES
from ..test_console import booking_rules_bypassed, test_availability, test_window


class AvailabilityMixin:
    def availability(self, actor, resource_id, day, duration_minutes=30, exclude_booking_id=None,
                     for_zid=None, urgent=False):
        """Free and taken times of one day.

        exclude_booking_id: the booking being rescheduled, so its current time shows as free.
        for_zid (Admin/Manager): show eligibility and own requests for the person being booked for.
        urgent: times before the minimum advance window count as available (an urgent request).
        """
        self.process_due_requests()
        return self._availability(actor, self.resource(resource_id), day, duration_minutes, exclude_booking_id,
                                  for_zid, urgent)

    def _availability(self, actor, resource, day, duration_minutes=30, exclude_booking_id=None, for_zid=None,
                      urgent=False):
        person = self._beneficiary(actor, for_zid)
        exclude = None
        if exclude_booking_id:
            excluded = self.booking_for(actor, exclude_booking_id)
            if excluded.resource_id != resource.id:
                raise DomainError("VALIDATION_ERROR", "exclude_booking_id must be a booking for this resource.")
            exclude = excluded.id
        if booking_rules_bypassed(actor, person.id):
            return test_availability(self, actor, resource, day, duration_minutes, exclude)
        if not resource.active:
            raise DomainError("RESOURCE_UNAVAILABLE", "The resource is inactive.", 409)
        if duration_minutes < 1 or duration_minutes > resource.max_booking_minutes or duration_minutes % resource.slot_minutes:
            raise DomainError("INVALID_DURATION", f"Use multiples of {resource.slot_minutes} minutes, up to {resource.max_booking_minutes}.")
        zone = ZoneInfo(resource.timezone)
        cursor = datetime.combine(day, resource.opening_time, zone).astimezone(UTC)
        closing = datetime.combine(day, resource.closing_time, zone).astimezone(UTC)
        eligibility, _ = self.qualification_state(person.id, resource)
        frozen_person = self.repo.get_principal(person.id) or person  # Sprint 3: booking freeze
        own_requests = [item for item in self.repo.list_bookings(student_id=person.id, resource_id=resource.id)
                        if item.status in ACTIVE_REQUEST_STATUSES and item.id != exclude]
        slots = []
        while cursor + timedelta(minutes=duration_minutes) <= closing:
            end = cursor + timedelta(minutes=duration_minutes)
            blockers = self._overlaps(resource.id, cursor, end, exclude)
            holds = [item for item in blockers if item.hold_is_active(self.now())]
            requested_by_me = any(cursor < item.end and item.start < end for item in own_requests)
            window = self._window_reason(resource, cursor)
            reason = ("START_TIME_PASSED" if cursor <= self.now() else
                      "RESOURCE_UNAVAILABLE" if not resource.bookable else
                      "TOO_SOON" if window == "BOOKING_TOO_SOON" and not urgent else
                      "TOO_FAR_AHEAD" if window == "BOOKING_TOO_FAR_AHEAD" else
                      "BOOKED" if any(item.status == BookingStatus.APPROVED for item in blockers) else
                      "TEMPORARILY_HELD" if holds else None)
            slots.append({"start": cursor, "end": end, "available": reason is None, "reason_code": reason,
                          "hold_until": max(item.hold_until for item in holds) if reason == "TEMPORARILY_HELD" else None,
                          "held_by_me": bool(holds) and all(item.student_id == person.id for item in holds)
                          if reason == "TEMPORARILY_HELD" else False,
                          "requested_by_me": requested_by_me})
            cursor += timedelta(minutes=resource.slot_minutes)
        return {"resource_id": resource.id, "date": day.isoformat(), "timezone": resource.timezone,
                "duration_minutes": duration_minutes, "slots": slots, **self._window_details(resource),
                "resource_status": resource.status.value, "status_reason": resource.status_reason,
                "review_window_minutes": resource.pending_hold_minutes,
                # Everyone follows the same rules: the person's induction (and its prerequisites) must be current.
                "can_request": (person.active and eligibility == "VERIFIED" and resource.bookable
                                and not frozen_person.frozen_at(self.now())),
                "frozen_until": frozen_person.frozen_until if frozen_person.frozen_at(self.now()) else None,
                "qualification_status": eligibility,
                "missing_prerequisite_id": (self.missing_prerequisite(person.id, resource.required_qualification_id) or (None,))[0]
                if eligibility == "PREREQUISITE_REQUIRED" else None,
                "booking_for": {"id": person.id, "zid": person.zid, "display_name": person.display_name,
                                "role": person.role.value},
                "urgent": bool(urgent)}

    def day_overview(self, actor, day, duration_minutes=60, kind=None, room_id=None, category=None, query=None,
                     bookable_only=False, free_at=None):
        """Every matching resource's free and taken times on one day, for the booking page's day grid.

        Same rules as ``availability`` (one shared check). Filters: kind (ROOM/EQUIPMENT), room_id (the room itself
        and the equipment kept in it), category (equipment type), query (name/location), bookable_only (the person
        may request it now), free_at (local "HH:MM": keep only resources free for the whole duration from then).

        Sprint 3 (1.16.0): resources that cannot be booked for this length (longer than their maximum, or not a
        multiple of their time step) are left out and counted in ``too_long`` instead of failing the whole page
        (before, one such resource made the whole request fail with INVALID_DURATION).
        Rows hidden by bookable_only are counted by reason in ``not_bookable`` (resource status when it is out of
        service, FROZEN when the person's booking is frozen, otherwise their induction status), so the page can say
        why nothing is shown.
        """
        self.process_due_requests()
        query = (query or "").strip().casefold()
        active = [item for item in self.repo.list_resources() if item.active]
        rooms = {item.id: item for item in active if item.kind == ResourceKind.ROOM}
        rows, too_long, not_bookable = [], 0, {}
        for resource in sorted(active, key=lambda item: (item.kind != ResourceKind.ROOM, item.name)):
            if kind and resource.kind.value != kind:
                continue
            if room_id and room_id not in (resource.id, resource.room_id):
                continue
            if category and resource.category != category:
                continue
            if query and query not in f"{resource.name} {resource.location} {resource.category or ''}".casefold():
                continue
            maximum = 1440 if booking_rules_bypassed(actor) else resource.max_booking_minutes
            if duration_minutes > maximum or duration_minutes % resource.slot_minutes:  # Sprint 3 (1.16.0)
                too_long += 1
                continue
            result = self._availability(actor, resource, day, duration_minutes)
            if bookable_only and not result["can_request"]:
                status, induction = result["resource_status"], result["qualification_status"]
                reason = (status if status != "AVAILABLE" else "FROZEN" if result["frozen_until"]
                          else induction if induction != "VERIFIED" else "NOT_AVAILABLE")
                not_bookable[reason] = not_bookable.get(reason, 0) + 1  # Sprint 3 (1.16.0)
                continue
            if free_at is not None:
                start = datetime.combine(day, free_at, ZoneInfo(resource.timezone)).astimezone(UTC)
                if not any(slot["start"] == start and slot["available"] and not slot["requested_by_me"]
                           for slot in result["slots"]):
                    continue
            rows.append({"resource": resource, "room_name": rooms[resource.room_id].name if resource.room_id in rooms else None,
                         **{key: result[key] for key in ("can_request", "qualification_status", "resource_status",
                                                         "status_reason", "slots")}})
        window = self._window_details(next(iter(active))) if active else {}
        if booking_rules_bypassed(actor):
            window = test_window(self)
        return {"date": day.isoformat(), "duration_minutes": duration_minutes, "timezone": "Australia/Sydney", **window,
                "too_long": too_long, "not_bookable": not_bookable,  # Sprint 3 (1.16.0)
                "rooms": [{"id": item.id, "name": item.name} for item in sorted(rooms.values(), key=lambda r: r.name)],
                "categories": sorted({item.category for item in active if item.category}),
                "count": len(rows), "results": rows}
