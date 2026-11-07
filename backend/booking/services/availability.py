"""Read-only time views: one resource's day of slots, and the booking page day overview."""
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from ..domain import BookingStatus, ResourceKind, Role
from ..errors import DomainError
from .base import ACTIVE_REQUEST_STATUSES, HEAD_STATUSES
from .qualifications import EligibilitySources
from ..test_console import booking_rules_bypassed, test_availability, test_window


class _DaySources:
    """2026-10-29 (load test S7): what every resource of the day overview needs about the person and the day, read
    once (before: about 6 queries per resource, 130 for the 22 demo resources).

    Each part answers exactly what the single-resource path asks, filtered per resource in memory: the person's
    eligibility records, their freeze state, their active requests, and the bookings or active holds overlapping
    the day (the same rule as list_blocking_bookings, over the earliest opening to the latest closing).
    """
    def __init__(self, service, person, resources, day):
        repo, now = service.repo, service.now()
        self.eligibility = EligibilitySources(repo.list_submissions(student_id=person.id), repo.list_requirements())
        self.frozen_person = repo.get_principal(person.id) or person
        self.own_requests = repo.list_bookings(student_id=person.id, statuses=ACTIVE_REQUEST_STATUSES)
        opens = min(datetime.combine(day, item.opening_time, ZoneInfo(item.timezone)) for item in resources)
        closes = max(datetime.combine(day, item.closing_time, ZoneInfo(item.timezone)) for item in resources)
        stored = repo.list_bookings(statuses=(BookingStatus.APPROVED, *HEAD_STATUSES), start_to=closes, end_from=opens)
        self._blockers = {}
        for item in stored:
            if item.start < closes and opens < item.end and item.blocks_resource_at(now):
                self._blockers.setdefault(item.resource_id, []).append(item)

    def blockers_for(self, resource_id):
        return self._blockers.get(resource_id, [])


class AvailabilityMixin:
    def availability(self, actor, resource_id, day, duration_minutes=30, exclude_booking_id=None,
                     for_zid=None, urgent=False, additional_hours=False, long_booking=False):
        """Free and taken times of one day.

        exclude_booking_id: the booking being rescheduled, so its current time shows as free.
        for_zid (Admin/Manager): show eligibility and own requests for the person being booked for.
        urgent: times before the minimum advance window count as available (an urgent request).
        additional_hours: the minimum lead time is waived, but the normal duration/horizon and eligibility apply.
        long_booking: show the technical resource limit, but keep the normal lead time and horizon.
        """
        self.process_due_requests()
        return self._availability(actor, self.resource(resource_id), day, duration_minutes, exclude_booking_id,
                                  for_zid, urgent, additional_hours=additional_hours, long_booking=long_booking)

    def _availability(self, actor, resource, day, duration_minutes=30, exclude_booking_id=None, for_zid=None,
                      urgent=False, shared=None, additional_hours=False, long_booking=False):
        """shared: a _DaySources read once for every resource of the day overview (2026-10-29, load test S7)."""
        person = self._beneficiary(actor, for_zid)
        if long_booking and (additional_hours or urgent):
            raise DomainError("VALIDATION_ERROR", "Longer bookings cannot be combined with urgent or additional-hours requests.")
        exclude = None
        if exclude_booking_id:
            excluded = self.booking_for(actor, exclude_booking_id)
            if excluded.resource_id != resource.id:
                raise DomainError("VALIDATION_ERROR", "exclude_booking_id must be a booking for this resource.")
            exclude = excluded.id
        if booking_rules_bypassed(actor, person.id) and not (additional_hours or long_booking):
            return test_availability(self, actor, resource, day, duration_minutes, exclude)
        if not resource.active:
            raise DomainError("RESOURCE_UNAVAILABLE", "The resource is inactive.", 409)
        # 2026-11-06 (client, Week 8): a Manager's booking skips the person's rules (see _create_manager_booking).
        override = actor.role == Role.MANAGER and not (additional_hours or long_booking)
        normal_maximum = self._normal_booking_limit(resource)[2]
        max_slots, quota_slot_minutes, maximum = (self._long_booking_limit(resource) if long_booking or override
                                                 else self._normal_booking_limit(resource))
        step = self._selection_step_minutes(resource)
        if duration_minutes < 1 or duration_minutes > maximum or duration_minutes % step:
            raise DomainError(
                "INVALID_DURATION",
                f"Choose a booking length up to {maximum / 60:g} h in {step}-minute increments.",
                400,
                {"max_slots": max_slots, "slot_minutes": quota_slot_minutes,
                 "selection_step_minutes": step},
            )
        zone = ZoneInfo(resource.timezone)
        cursor = datetime.combine(day, resource.opening_time, zone).astimezone(UTC)
        closing = datetime.combine(day, resource.closing_time, zone).astimezone(UTC)
        sources = shared.eligibility if shared else None
        eligibility, _ = self.qualification_state(person.id, resource, sources=sources)
        frozen_person = shared.frozen_person if shared else (self.repo.get_principal(person.id) or person)  # Sprint 3: booking freeze
        mine = shared.own_requests if shared else self.repo.list_bookings(student_id=person.id, resource_id=resource.id)
        own_requests = [item for item in mine
                        if item.resource_id == resource.id and item.status in ACTIVE_REQUEST_STATUSES and item.id != exclude]
        # 2026-10-29 (load test S6): one query for the whole opening day instead of one per slot (22 resources made
        # the day overview run 500+ queries). Every slot lies inside the day, so filtering this list by the same
        # strict overlap gives exactly what _overlaps would return for that slot.
        day_blockers = (shared.blockers_for(resource.id) if shared
                        else self.repo.list_blocking_bookings(resource.id, cursor, closing, self.now(), exclude))
        slots = []
        while cursor + timedelta(minutes=duration_minutes) <= closing:
            end = cursor + timedelta(minutes=duration_minutes)
            blockers = [item for item in day_blockers if item.start < end and cursor < item.end]
            holds = [item for item in blockers if item.hold_is_active(self.now())]
            requested_by_me = any(cursor < item.end and item.start < end for item in own_requests)
            window = self._window_reason(resource, cursor)
            reason = ("START_TIME_PASSED" if cursor <= self.now() else
                      "RESOURCE_UNAVAILABLE" if not resource.bookable else
                      "TOO_SOON" if window == "BOOKING_TOO_SOON" and not (urgent or additional_hours or override) else
                      "TOO_FAR_AHEAD" if window == "BOOKING_TOO_FAR_AHEAD" and not override else
                      "BOOKED" if any(item.status == BookingStatus.APPROVED for item in blockers) else
                      "TEMPORARILY_HELD" if holds else None)
            slots.append({"start": cursor, "end": end, "available": reason is None, "reason_code": reason,
                          "hold_until": max(item.hold_until for item in holds) if reason == "TEMPORARILY_HELD" else None,
                          "held_by_me": bool(holds) and all(item.student_id == person.id for item in holds)
                          if reason == "TEMPORARILY_HELD" else False,
                          "requested_by_me": requested_by_me})
            cursor += timedelta(minutes=step)
        window_details = self._window_details(resource)
        if additional_hours or override:
            window_details.update(earliest_date=self.now().astimezone(zone).date().isoformat(), min_advance_days=0)
        if override:
            window_details.update(latest_date=None)
        return {"resource_id": resource.id, "date": day.isoformat(), "timezone": resource.timezone,
                "duration_minutes": duration_minutes, "slots": slots, **window_details,
                "booking_slot_minutes": quota_slot_minutes, "max_booking_slots": max_slots,
                "selection_step_minutes": step, "max_booking_minutes": maximum,
                "normal_max_booking_minutes": normal_maximum,
                "min_booking_minutes": (normal_maximum // step + 1) * step if long_booking else step,
                "resource_status": resource.status.value, "status_reason": resource.status_reason,
                "review_window_minutes": resource.pending_hold_minutes,
                # Everyone follows the same rules: the person's induction (and its prerequisites) must be current.
                "can_request": (person.active and resource.bookable) if override else (
                    person.active and eligibility == "VERIFIED" and resource.bookable
                    and not frozen_person.frozen_at(self.now()) and (not long_booking or maximum > normal_maximum)),
                "manager_override": override,
                "frozen_until": frozen_person.frozen_until if frozen_person.frozen_at(self.now()) else None,
                "qualification_status": eligibility,
                "missing_prerequisite_id": (self.missing_prerequisite(person.id, resource.required_qualification_id,
                                                                      sources=sources) or (None,))[0]
                if eligibility == "PREREQUISITE_REQUIRED" else None,
                "booking_for": {"id": person.id, "zid": person.zid, "display_name": person.display_name,
                                "role": person.role.value},
                "urgent": bool(urgent), "additional_hours": bool(additional_hours),
                "long_booking": bool(long_booking),
                "additional_hours_approval_window_hours": self.rules().additional_hours_approval_window_hours}

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
        shared = _DaySources(self, actor, active, day) if active else None  # 2026-10-29 (load test S7)
        for resource in sorted(active, key=lambda item: (item.kind != ResourceKind.ROOM, item.name)):
            if kind and resource.kind.value != kind:
                continue
            if room_id and room_id not in (resource.id, resource.room_id):
                continue
            if category and resource.category != category:
                continue
            if query and query not in f"{resource.name} {resource.location} {resource.category or ''}".casefold():
                continue
            maximum = (1440 if booking_rules_bypassed(actor) else self._long_booking_limit(resource)[2]
                       if actor.role == Role.MANAGER else self._normal_booking_limit(resource)[2])  # 2026-11-06
            step = resource.slot_minutes if booking_rules_bypassed(actor) else self._selection_step_minutes(resource)
            if duration_minutes > maximum or duration_minutes % step:  # Sprint 3 (1.16.0)
                too_long += 1
                continue
            result = self._availability(actor, resource, day, duration_minutes, shared=shared)
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
        elif actor.role == Role.MANAGER and active:  # 2026-11-06 (client, Week 8): Manager override, from today
            window.update(earliest_date=self.now().astimezone(ZoneInfo("Australia/Sydney")).date().isoformat(),
                          latest_date=None, min_advance_days=0, manager_override=True)
        return {"date": day.isoformat(), "duration_minutes": duration_minutes, "timezone": "Australia/Sydney", **window,
                "too_long": too_long, "not_bookable": not_bookable,  # Sprint 3 (1.16.0)
                "rooms": [{"id": item.id, "name": item.name} for item in sorted(rooms.values(), key=lambda r: r.name)],
                "categories": sorted({item.category for item in active if item.category}),
                "count": len(rows), "results": rows}
