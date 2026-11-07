"""Sprint 3 (1.16.0): change requests (the person asks to move an approved booking), maintenance notices, and why
Find a free time hides resources (too long for them, or not bookable by this person)."""

from dataclasses import replace
from datetime import datetime, time, timedelta
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from booking.domain import BookingStatus, Principal, Role
from booking.tests.test_api import SYDNEY, BookingAPIFixtureMixin
from booking.tests.test_sprint3 import Sprint3Fixture


class ChangeRequestTests(Sprint3Fixture, SimpleTestCase):
    def change(self, booking, days, hour, actor=None, minutes=60):
        start, end = self.at(days, hour, minutes)
        return self.service.request_time_change(actor or self.student, booking.id, start, end)[0]

    def test_free_time_waits_for_review_and_the_old_booking_stays_until_approval(self):
        old = self.approved(days=3, hour=10)
        change = self.change(old, days=4, hour=14)
        self.assertEqual((change.status, change.replaces_id), (BookingStatus.PENDING_APPROVAL, old.id))
        self.assertEqual(self.repo.get_booking(old.id).status, BookingStatus.APPROVED)
        self.assertEqual(self.service.open_change_for(old).id, change.id)
        received = self.notices(self.student, "CHANGE_REQUESTED")[0]
        self.assertIn("stays until the new time is approved", received.body)

        approved = self.service.review_booking(self.admin, change.id, "APPROVED")
        self.assertEqual(approved.status, BookingStatus.APPROVED)
        released = self.repo.get_booking(old.id)
        self.assertEqual((released.status, released.reason_code), (BookingStatus.CANCELLED, "REPLACED_BY_CHANGE"))
        moved = self.notices(self.student, "CHANGE_APPROVED")[0]
        self.assertIn("has been released", moved.body)
        self.assertEqual(self.notices(self.student, "BOOKING_CANCELLED"), [])  # no confusing "cancelled" notice
        self.assertIsNone(self.service.open_change_for(old))
        self.assertIn("BOOKING_REPLACED", [item.action for item in self.repo.list_audit()])

    def test_moving_by_an_hour_overlaps_the_old_time_without_counting_as_a_clash(self):
        old = self.approved(days=3, hour=10)
        start, end = self.at(3, 10, 120)  # 10:00-12:00 instead of 10:00-11:00
        change = self.service.request_time_change(self.student, old.id, start + timedelta(minutes=30), end)[0]
        self.assertEqual(change.status, BookingStatus.PENDING_APPROVAL)
        self.service.review_booking(self.admin, change.id, "APPROVED")
        self.assertEqual(self.repo.get_booking(old.id).status, BookingStatus.CANCELLED)

    def test_taken_time_joins_the_waitlist_and_moves_once_the_time_frees(self):
        old = self.approved(days=3, hour=10)
        theirs = self.approved(self.other, days=4, hour=14)
        waiting = self.request(self.other, days=3, hour=10)  # someone waits for the student's old time
        self.assertEqual(waiting.status, BookingStatus.WAITLISTED)

        change = self.change(old, days=4, hour=14)
        self.assertEqual(change.status, BookingStatus.WAITLISTED)
        self.assertEqual(self.repo.get_booking(old.id).status, BookingStatus.APPROVED)

        self.service.cancel_booking(self.other, theirs.id)  # the wanted time frees: the change moves up
        self.assertEqual(self.repo.get_booking(change.id).status, BookingStatus.PENDING_APPROVAL)
        self.service.review_booking(self.admin, change.id, "APPROVED")
        self.assertEqual(self.repo.get_booking(old.id).status, BookingStatus.CANCELLED)
        # The released old time goes to the person waiting for it.
        self.assertEqual(self.repo.get_booking(waiting.id).status, BookingStatus.PENDING_APPROVAL)

    def test_rejected_or_withdrawn_change_keeps_the_old_booking(self):
        old = self.approved(days=3, hour=10)
        change = self.change(old, days=4, hour=14)
        self.service.review_booking(self.admin, change.id, "REJECTED", "Lab needed for a class")
        self.assertEqual(self.repo.get_booking(old.id).status, BookingStatus.APPROVED)
        rejected = self.notices(self.student, "CHANGE_REJECTED")[0]
        self.assertIn("Lab needed for a class", rejected.body)
        self.assertIn("stays as it is", rejected.body)

        again = self.change(old, days=5, hour=9)  # a new change is allowed after the first was decided
        self.service.cancel_booking(self.student, again.id)
        self.assertEqual(self.repo.get_booking(old.id).status, BookingStatus.APPROVED)

    def test_the_system_approval_at_the_end_of_the_review_window_also_replaces(self):
        old = self.approved(days=3, hour=10)
        change = self.change(old, days=4, hour=14)
        self.now = change.review_due_at
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(change.id).status, BookingStatus.APPROVED)
        self.assertEqual(self.repo.get_booking(old.id).status, BookingStatus.CANCELLED)

    def test_only_the_owner_of_a_future_approved_booking_can_ask_once_for_a_different_time(self):
        old = self.approved(days=3, hour=10)
        start, end = self.at(4, 14)
        self.refused("NOT_FOUND", self.service.request_time_change, self.other, old.id, start, end)
        self.refused("FORBIDDEN", self.service.request_time_change, self.admin, old.id, start, end)
        self.refused("VALIDATION_ERROR", self.service.request_time_change, self.student, old.id, old.start, old.end)
        pending = self.request(days=5, hour=9)
        self.refused("REQUEST_NOT_CHANGEABLE", self.service.request_time_change, self.student, pending.id, start, end)
        first = self.change(old, days=4, hour=14)
        error = self.refused("CHANGE_ALREADY_REQUESTED", self.service.request_time_change, self.student, old.id, *self.at(5, 14))
        self.assertEqual(error.details["booking_id"], first.id)
        self.now = old.start + timedelta(minutes=1)
        self.refused("REQUEST_NOT_CHANGEABLE", self.service.request_time_change, self.student, old.id, *self.at(6, 14))

    def test_the_old_booking_does_not_count_twice_in_the_weekly_limit(self):
        week = [self.approved(days=day, hour=8, minutes=180) for day in (1, 2, 3, 4)]
        change = self.change(week[0], days=1, hour=14, minutes=180)
        self.assertEqual(change.status, BookingStatus.PENDING_APPROVAL)

    def test_the_old_booking_and_its_open_change_count_as_one_future_booking(self):
        self.service._override_rule(max_active_future_bookings=2)
        old = self.approved(days=2, hour=8, minutes=30)
        change = self.change(old, days=3, hour=8, minutes=30)
        self.assertEqual(change.status, BookingStatus.PENDING_APPROVAL)
        self.assertEqual(self.request(days=4, hour=8, minutes=30).status, BookingStatus.PENDING_APPROVAL)
        self.refused("FUTURE_BOOKING_LIMIT_REACHED", self.request, self.student,
                     days=5, hour=8, minutes=30)


class ExtendBookingTests(Sprint3Fixture, SimpleTestCase):
    """2026-11-07 (client, Week 8): the person asks to finish a booking in progress later; a Manager decides."""

    def at_hour(self, booking, hour, minute=0):
        return datetime.combine(booking.start.astimezone(SYDNEY).date(), time(hour, minute), SYDNEY)

    def extend(self, booking, hour, minute=0, actor=None):
        return self.service.extend_booking(actor or self.student, booking.id, self.at_hour(booking, hour, minute))

    def test_a_request_waits_for_a_manager_who_approves_it(self):
        booking = self.approved(days=3, hour=10)  # 10:00-11:00
        self.refused("EXTENSION_NOT_AVAILABLE", self.extend, booking, 12)  # not started yet
        self.now = booking.start + timedelta(minutes=40)
        asked = self.extend(booking, 12)
        self.assertEqual((asked.end, asked.extension_end), (booking.end, self.at_hour(booking, 12)))
        self.assertEqual(len(self.notices(self.manager, "EXTENSION_REQUESTED")), 1)
        asked = self.extend(booking, 14)  # asking again replaces the requested end; 4 h is allowed, a Manager decides
        self.assertEqual(asked.extension_end, self.at_hour(booking, 14))
        self.refused("FORBIDDEN", self.service.review_extension, self.admin, booking.id, "APPROVED")
        approved = self.service.review_extension(self.manager, booking.id, "APPROVED")
        self.assertEqual((approved.end, approved.extension_end, approved.revision),
                         (self.at_hour(booking, 14), None, booking.revision + 1))
        self.assertIn("now ends at", self.notices(self.student, "EXTENSION_APPROVED")[0].body)
        self.refused("NO_EXTENSION_REQUEST", self.service.review_extension, self.manager, booking.id, "APPROVED")
        self.assertEqual([item.action for item in self.repo.list_audit() if item.entity_id == booking.id][-2:],
                         ["EXTENSION_REQUESTED", "BOOKING_EXTENDED"])

    def test_rejection_needs_a_reason_and_the_time_after_must_still_be_free(self):
        booking = self.approved(days=3, hour=10)
        self.approved(self.other, days=3, hour=15)  # 15:00-16:00
        self.now = booking.start + timedelta(minutes=10)
        self.refused("BOOKING_CONFLICT", self.extend, booking, 15, 30)
        self.refused("VALIDATION_ERROR", self.extend, booking, 11)
        self.refused("NOT_FOUND", self.extend, booking, 13, actor=self.other)
        self.refused("DURATION_LIMIT", self.extend, booking, 19)  # the room's longest booking is 8 h
        self.extend(booking, 13)
        self.refused("REASON_REQUIRED", self.service.review_extension, self.manager, booking.id, "REJECTED", " ")
        rejected = self.service.review_extension(self.manager, booking.id, "REJECTED", "Cleaning at 12:00")
        self.assertEqual((rejected.end, rejected.extension_end), (booking.end, None))
        self.assertIn("Cleaning at 12:00", self.notices(self.student, "EXTENSION_REJECTED")[0].body)
        # Someone books the time after while a request waits: approval is refused.
        self.extend(booking, 15)
        self.service._override_rule(min_advance_days=0)
        self.approved(self.other, days=3, hour=13)
        self.refused("BOOKING_CONFLICT", self.service.review_extension, self.manager, booking.id, "APPROVED")

    def test_a_manager_extends_at_once_and_sees_the_waiting_requests(self):
        booking = self.approved(days=3, hour=10)
        mine = self.request(self.manager, days=3, hour=14)  # a Manager booking is approved at once
        self.now = booking.start + timedelta(minutes=10)
        self.extend(booking, 12)
        overview = self.service.staff_overview(self.manager)
        self.assertEqual([item.id for item in overview["extension_requests"]], [booking.id])
        self.now = mine.start + timedelta(minutes=5)
        self.assertEqual(self.extend(mine, 16, actor=self.manager).end, self.at_hour(mine, 16))
        self.assertEqual(self.service.staff_overview(self.manager)["extension_requests"], [])  # its requested end passed
        self.refused("EXTENSION_EXPIRED", self.service.review_extension, self.manager, booking.id, "APPROVED")

    def test_an_extension_stays_visible_until_its_requested_end(self):
        booking = self.approved(days=3, hour=10)
        self.now = booking.start + timedelta(minutes=10)
        asked = self.extend(booking, 12)
        self.now = booking.end + timedelta(minutes=5)
        requests = self.service.staff_overview(self.manager)["extension_requests"]
        self.assertEqual([item.id for item in requests], [booking.id])
        approved = self.service.review_extension(self.manager, booking.id, "APPROVED")
        self.assertEqual(approved.end, asked.extension_end)

    def test_review_does_not_decide_a_replacement_the_manager_has_not_seen(self):
        booking = self.approved(days=3, hour=10)
        self.now = booking.start + timedelta(minutes=10)
        first = self.extend(booking, 12)
        replaced = self.extend(booking, 14)
        self.refused("EXTENSION_CHANGED", self.service.review_extension, self.manager, booking.id, "APPROVED",
                     expected_end=first.extension_end)
        self.assertEqual(self.repo.get_booking(booking.id), replaced)
        approved = self.service.review_extension(self.manager, booking.id, "APPROVED", expected_end=replaced.extension_end)
        self.assertEqual(approved.end, replaced.extension_end)


class MaintenanceNoticeTests(Sprint3Fixture, SimpleTestCase):
    def test_people_with_bookings_are_told_when_a_room_goes_out_of_service_and_reopens(self):
        booked = self.approved(days=3, hour=10)
        waiting = self.request(self.other, days=4, hour=10)
        self.service.set_resource_status(self.manager, self.room.id, "MAINTENANCE", "Water leak")
        out = self.notices(self.student, "RESOURCE_OUT_OF_SERVICE")
        self.assertEqual(len(out), 1)
        self.assertIn("Water leak", out[0].body)
        self.assertIn("kept for now", out[0].body)
        self.assertEqual(out[0].booking_id, booked.id)
        self.assertIn("cannot be approved", self.notices(self.other, "RESOURCE_OUT_OF_SERVICE")[0].body)
        self.assertEqual(self.repo.get_booking(booked.id).status, BookingStatus.APPROVED)  # bookings are kept

        self.service.set_resource_status(self.manager, self.room.id, "MAINTENANCE", "Still drying")  # reason only: no new notice
        self.assertEqual(len(self.notices(self.student, "RESOURCE_OUT_OF_SERVICE")), 1)

        self.service.set_resource_status(self.manager, self.room.id, "AVAILABLE")
        self.assertIn("goes ahead as planned", self.notices(self.student, "RESOURCE_REOPENED")[0].body)
        self.assertEqual(self.notices(self.other, "RESOURCE_REOPENED")[0].booking_id, waiting.id)

    def test_the_new_kinds_are_emailed_by_default(self):
        from django.conf import settings
        for kind in ("CHANGE_REQUESTED", "CHANGE_APPROVED", "CHANGE_REJECTED", "RESOURCE_OUT_OF_SERVICE", "RESOURCE_REOPENED"):
            self.assertIn(kind, settings.EMAIL_NOTIFICATION_KINDS)


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class ChangeRequestAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def test_owner_asks_for_a_new_time_and_both_bookings_show_the_link(self):
        created = self.verified.post("/api/v1/bookings/", self.payload(day_offset=3, hour=10), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        approved = self.admin.post(f"/api/v1/admin/bookings/{created.data['id']}/review/", {"decision": "APPROVED"}, format="json")
        self.assertEqual(approved.status_code, 200, approved.data)
        new_time = self.payload(day_offset=4, hour=14)
        response = self.verified.post(f"/api/v1/bookings/{created.data['id']}/change/",
                                      {"start": new_time["start"], "end": new_time["end"]}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["replaces_booking"]["id"], created.data["id"])
        self.assertEqual(response.data["purpose"], created.data["purpose"])
        old = self.verified.get(f"/api/v1/bookings/{created.data['id']}/")
        self.assertEqual(old.data["open_change"]["id"], response.data["id"])
        other = self.student.post(f"/api/v1/bookings/{created.data['id']}/change/",
                                  {"start": new_time["start"], "end": new_time["end"]}, format="json")
        self.assertEqual(other.status_code, 404)

    def test_extend_a_booking_in_progress(self):
        """2026-11-07: the person asks, a Manager approves."""
        payload = self.payload(day_offset=3, hour=10)
        created = self.verified.post("/api/v1/bookings/", payload, format="json")
        self.admin.post(f"/api/v1/admin/bookings/{created.data['id']}/review/", {"decision": "APPROVED"}, format="json")
        self.service.clock = lambda: datetime.fromisoformat(payload["start"]) + timedelta(minutes=5)
        later = self.payload(day_offset=3, hour=11)["end"]  # 12:00
        url = f"/api/v1/bookings/{created.data['id']}/extend/"
        response = self.verified.post(url, {"end": later}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(datetime.fromisoformat(response.data["extension_end"].replace("Z", "+00:00")), datetime.fromisoformat(later))
        self.assertEqual(response.data["end"], created.data["end"])
        self.assertEqual(self.verified.post(url, {"end": later, "start": later}, format="json").status_code, 400)
        self.assertEqual(self.admin.post(url + "review/", {"decision": "APPROVED"}, format="json").status_code, 403)
        self.assertEqual(self.manager.post(url + "review/", {"decision": "REJECTED"}, format="json").status_code, 400)
        decided = self.manager.post(url + "review/", {"decision": "APPROVED"}, format="json")
        self.assertEqual((decided.status_code, decided.data["extension_end"]), (200, None))
        self.assertEqual(datetime.fromisoformat(decided.data["end"].replace("Z", "+00:00")), datetime.fromisoformat(later))


class DayOverviewCountTests(Sprint3Fixture, SimpleTestCase):
    def test_lengths_longer_than_the_effective_slot_limit_are_counted_not_an_error(self):
        short = replace(self.room, id=str(uuid4()), name="Short room", max_booking_minutes=120)
        self.repo.save_resource(short)
        day = self.today + timedelta(days=3)
        overview = self.service.day_overview(self.student, day, duration_minutes=180)
        self.assertEqual([row["resource"].id for row in overview["results"]], [self.room.id])  # six 30-minute slots
        self.assertEqual(overview["too_long"], 1)

    def test_rows_hidden_as_not_bookable_are_counted_by_reason(self):
        newcomer = Principal(str(uuid4()), "z3333333", "Newcomer", Role.STUDENT, "z3333333@ad.unsw.edu.au")
        self.repo.save_principal(newcomer)
        day = self.today + timedelta(days=3)
        overview = self.service.day_overview(newcomer, day, duration_minutes=60, bookable_only=True)
        self.assertEqual((overview["count"], overview["not_bookable"]), (0, {"NOT_SUBMITTED": 1}))
        self.service.set_resource_status(self.manager, self.room.id, "MAINTENANCE", "Repairs")
        self.assertEqual(self.service.day_overview(self.student, day, bookable_only=True)["not_bookable"], {"MAINTENANCE": 1})
