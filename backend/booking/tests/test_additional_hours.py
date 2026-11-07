"""Spare-capacity allocations retain booking safeguards and cannot bypass Manager review or queue order."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, time, timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, override_settings

from booking.domain import Booking, BookingStatus, Principal, Role
from booking.errors import DomainError
from booking.test_console import TEST_ACCOUNT_ID, test_identity as make_test_identity
from booking.tests.test_services import BookingFixtureMixin


class AdditionalHoursTests(BookingFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.service._override_rule(min_advance_days=7, max_advance_days=28)
        self.manager = Principal(str(uuid4()), "z9888888", "Manager", Role.MANAGER, "manager@example.test")
        self.manager2 = Principal(str(uuid4()), "z9777777", "Other manager", Role.MANAGER, "manager2@example.test")
        for person in (self.manager, self.manager2):
            self.repo.save_principal(person)
        for person in (self.student, self.other, self.admin, self.manager):
            self.qualification(person)
        self.zone = ZoneInfo(self.room.timezone)
        self.today = self.now.astimezone(self.zone).date()

    def at(self, days=1, hour=10, minutes=60):
        start = datetime.combine(self.today + timedelta(days=days), time(hour), self.zone)
        return start, start + timedelta(minutes=minutes)

    def extra(self, actor=None, days=1, hour=10, minutes=60, **kwargs):
        start, end = self.at(days, hour, minutes)
        return self.service.create_additional_hours_booking(actor or self.student, self.room.id, start, end,
                                                            "Research", "Need spare capacity", **kwargs)[0]

    def refused(self, code, call, *args, **kwargs):
        with self.assertRaises(DomainError) as denied:
            call(*args, **kwargs)
        self.assertEqual(denied.exception.code, code)
        return denied.exception

    def used_lab(self, person, resource=None, days=0, attendance="CHECKED_IN"):
        start, end = self.at(days, hour=8)
        booking = Booking(str(uuid4()), person.id, (resource or self.room).id, start, end, "Earlier lab use",
                          start - timedelta(days=1), BookingStatus.APPROVED, "MANUALLY_APPROVED",
                          attendance=attendance, checked_in_at=start if attendance == "CHECKED_IN" else None)
        self.repo.save_booking(booking)
        return booking

    def test_advance_request_never_reserves_or_auto_approves_and_expires_at_start(self):
        booking = self.extra(days=10)
        self.assertEqual((booking.status, booking.hold_until, booking.review_due_at),
                         (BookingStatus.PENDING_APPROVAL, None, None))
        self.assertFalse(booking.blocks_resource_at(self.now))
        self.assertEqual(self.repo.list_blocking_bookings(self.room.id, booking.start, booking.end, self.now), [])
        self.now += timedelta(days=2)
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.PENDING_APPROVAL)
        self.assertFalse(self.service.additional_hours_review(booking)["can_approve"])
        self.now = booking.start
        self.service.process_due_requests()
        self.assertEqual(self.repo.get_booking(booking.id).status, BookingStatus.EXPIRED)
        self.assertTrue(any(item.kind == "BOOKING_EXPIRED" for item in self.repo.list_notifications(self.student.id)))

    def test_exact_48_hour_boundary_and_configurable_approval_window(self):
        booking = self.extra(days=10)
        self.now = booking.start - timedelta(hours=48, microseconds=1)
        self.refused("ADDITIONAL_HOURS_TOO_EARLY", self.service.review_booking, self.manager, booking.id, "APPROVED")
        self.now += timedelta(microseconds=1)
        self.assertTrue(self.service.additional_hours_review(booking)["can_approve"])
        self.service._override_rule(additional_hours_approval_window_hours=24)
        self.refused("ADDITIONAL_HOURS_TOO_EARLY", self.service.review_booking, self.manager, booking.id, "APPROVED")
        self.now = booking.start - timedelta(hours=24)
        approved = self.service.review_booking(self.manager, booking.id, "APPROVED")
        self.assertEqual((approved.status, approved.reviewed_by), (BookingStatus.APPROVED, self.manager.id))
        self.assertFalse(self.service.additional_hours_review(approved)["can_approve"])

    def test_only_manager_may_review_and_neither_beneficiary_nor_creator_can_self_review(self):
        booking = self.extra()
        for decision in ("APPROVED", "REJECTED"):
            self.refused("FORBIDDEN", self.service.review_booking, self.admin, booking.id, decision, "Reason")
        own = self.extra(self.manager, hour=12)
        self.refused("SELF_REVIEW_FORBIDDEN", self.service.review_booking, self.manager, own.id, "APPROVED")
        created = self.extra(self.manager, hour=14, on_behalf_of_zid=self.other.zid)
        self.refused("SELF_REVIEW_FORBIDDEN", self.service.review_booking, self.manager, created.id, "REJECTED", "Reason")
        self.assertEqual(self.service.review_booking(self.manager2, created.id, "APPROVED").status, BookingStatus.APPROVED)

    def test_manager_can_reject_before_approval_window_and_reason_is_required(self):
        booking = self.extra(days=10)
        self.refused("REASON_REQUIRED", self.service.review_booking, self.manager, booking.id, "REJECTED")
        self.assertEqual(self.service.review_booking(self.manager, booking.id, "REJECTED", "No extra allocation").status,
                         BookingStatus.REJECTED)

    def test_pending_extra_does_not_block_normal_booking_and_approval_rechecks_capacity(self):
        extra = self.extra(days=8)
        ordinary = self.service.create_booking(self.other, self.room.id, extra.start, extra.end, "Normal request")[0]
        self.assertEqual(ordinary.status, BookingStatus.PENDING_APPROVAL)
        self.now = extra.start - timedelta(hours=48)
        # Keep a live ordinary hold while entering the extra approval window.
        self.repo.save_booking(replace(ordinary, hold_until=extra.start, review_due_at=extra.start))
        self.refused("ADDITIONAL_HOURS_NO_CAPACITY", self.service.review_booking, self.manager, extra.id, "APPROVED")
        ordinary = self.service.review_booking(self.admin, ordinary.id, "APPROVED")
        self.refused("ADDITIONAL_HOURS_NO_CAPACITY", self.service.review_booking, self.manager, extra.id, "APPROVED")
        self.service.cancel_booking(self.other, ordinary.id)
        self.assertEqual(self.service.review_booking(self.manager, extra.id, "APPROVED").status, BookingStatus.APPROVED)

    def test_base_weekly_allowance_is_independent_of_pending_and_approved_extras(self):
        self.service._override_rule(min_advance_days=0, max_slots_per_week=2)
        start, end = self.at(1, hour=8)
        ordinary = self.service.create_booking(self.student, self.room.id, start, end, "Base allowance")[0]
        extra = self.extra(days=2, minutes=180)
        self.assertIsNone(self.service._weekly_limit_violation(self.student.id, self.room, start, end, ordinary.id))
        self.service.review_booking(self.manager, extra.id, "APPROVED")
        self.assertIsNone(self.service._weekly_limit_violation(self.student.id, self.room, start, end, ordinary.id))
        start, end = self.at(3)
        self.refused("WEEKLY_LIMIT_REACHED", self.service.create_booking, self.student, self.room.id, start, end, "Another base hour")
        self.service.cancel_booking(self.student, ordinary.id)
        self.assertEqual(self.service.create_booking(self.student, self.room.id, start, end, "Base hour after cancellation")[0].status,
                         BookingStatus.PENDING_APPROVAL)

    def test_extras_count_toward_eight_future_bookings_and_approval_rechecks_limit(self):
        bookings = [self.extra(days=day) for day in range(1, 9)]
        self.refused("FUTURE_BOOKING_LIMIT_REACHED", self.extra, days=9)
        self.service._override_rule(max_active_future_bookings=7)
        self.refused("FUTURE_BOOKING_LIMIT_REACHED", self.service.review_booking, self.manager, bookings[0].id, "APPROVED")
        self.service.cancel_booking(self.student, bookings[-1].id)
        self.assertEqual(self.service.review_booking(self.manager, bookings[0].id, "APPROVED").status, BookingStatus.APPROVED)

    def test_day_28_and_three_hour_limits_remain_but_minimum_seven_days_does_not_apply(self):
        self.assertEqual(self.extra(days=1, minutes=180).status, BookingStatus.PENDING_APPROVAL)
        self.assertEqual(self.extra(days=28).status, BookingStatus.PENDING_APPROVAL)
        self.refused("BOOKING_TOO_FAR_AHEAD", self.extra, days=29)
        self.refused("DURATION_LIMIT", self.extra, days=2, minutes=210)
        self.refused("OUTSIDE_OPENING_HOURS", self.extra, days=2, hour=19, minutes=120)
        self.repo.save_resource(replace(self.room, max_booking_minutes=60))
        self.refused("DURATION_LIMIT", self.extra, days=3, minutes=90)

    def test_qualification_is_rechecked_at_approval(self):
        booking = self.extra(days=2)
        submission = self.repo.list_submissions(student_id=self.student.id)[0]
        self.repo.save_submission(replace(submission, valid_until=booking.end - timedelta(minutes=1)))
        self.refused("QUALIFICATION_REQUIRED", self.service.review_booking, self.manager, booking.id, "APPROVED")

    def test_no_use_priority_overtakes_standard_and_uses_actual_attendance_across_resources(self):
        other_resource = replace(self.room, id=str(uuid4()), name="Other laboratory")
        self.repo.save_resource(other_resource)
        self.used_lab(self.student, resource=other_resource)
        earlier = self.extra()
        self.now += timedelta(seconds=1)
        later = self.extra(self.other)
        self.assertEqual(self.service.additional_hours_review(earlier)["priority_group"], "STANDARD")
        self.assertEqual(self.service.additional_hours_review(later)["priority_reasons"], ["NO_USE_THIS_WEEK"])
        self.refused("ADDITIONAL_HOURS_QUEUE_PRIORITY", self.service.review_booking, self.manager, earlier.id, "APPROVED")
        self.service.review_booking(self.manager, later.id, "REJECTED", "Cannot attend")
        self.assertEqual(self.service.review_booking(self.manager, earlier.id, "APPROVED").status, BookingStatus.APPROVED)

    def test_active_collection_and_no_use_are_equal_priority_with_fifo_and_manager_confirmation(self):
        self.used_lab(self.student)
        earlier = self.extra(active_data_collection=True, data_collection_reason="The current experiment is collecting measurements")
        self.now += timedelta(seconds=1)
        later = self.extra(self.other)
        self.assertEqual(self.service.additional_hours_review(earlier)["priority_reasons"], ["ACTIVE_DATA_COLLECTION"])
        self.assertEqual(self.service.additional_hours_review(later)["queue_position"], 2)
        self.refused("ADDITIONAL_HOURS_QUEUE_PRIORITY", self.service.review_booking, self.manager, later.id, "APPROVED")
        self.refused("DATA_COLLECTION_CONFIRMATION_REQUIRED", self.service.review_booking, self.manager, earlier.id, "APPROVED")
        self.service.review_booking(self.manager, earlier.id, "APPROVED", confirm_active_data_collection=True)
        audit = next(item for item in self.repo.list_audit() if item.action == "ADDITIONAL_HOURS_APPROVED")
        self.assertEqual(audit.details["priority_reasons"], ["ACTIVE_DATA_COLLECTION"])
        self.assertTrue(audit.details["active_data_collection_confirmed"])
        self.assertEqual(audit.details["approval_window_hours"], 48)

    def test_invalid_claim_can_be_rejected_to_release_priority_and_non_overlaps_do_not_compete(self):
        self.used_lab(self.student)
        self.used_lab(self.other)
        claim = self.extra(active_data_collection=True, data_collection_reason="Claim to verify")
        self.now += timedelta(seconds=1)
        ordinary = self.extra(self.other)
        independent = self.extra(self.other, hour=14)
        self.assertTrue(self.service.additional_hours_review(independent)["can_approve"])
        self.refused("ADDITIONAL_HOURS_QUEUE_PRIORITY", self.service.review_booking, self.manager, ordinary.id, "APPROVED")
        self.service.review_booking(self.manager, claim.id, "REJECTED", "Collection not verified")
        self.assertTrue(self.service.additional_hours_review(ordinary)["can_approve"])

    def test_priority_ignores_other_weeks_and_no_shows_and_does_not_count_future_checkins(self):
        self.used_lab(self.student, days=-7)
        self.used_lab(self.student, attendance="NO_SHOW")
        self.used_lab(self.student, days=1)
        booking = self.extra(days=2)
        self.assertEqual(self.service.additional_hours_review(booking)["priority_reasons"], ["NO_USE_THIS_WEEK"])
        self.now = self.at(1, hour=9)[0]
        self.assertEqual(self.service.additional_hours_review(booking)["priority_reasons"], [])

    def test_idempotency_compares_claim_details_and_cannot_cross_normal_and_extra_endpoints(self):
        start, end = self.at(8)
        args = (self.student, self.room.id, start, end, "Research", "Need spare capacity")
        first, created = self.service.create_additional_hours_booking(*args, idempotency_key="extra-key")
        again, repeated = self.service.create_additional_hours_booking(*args, idempotency_key="extra-key")
        self.assertEqual((created, repeated, first.id), (True, False, again.id))
        self.refused("IDEMPOTENCY_CONFLICT", self.service.create_additional_hours_booking, *args,
                     idempotency_key="extra-key", active_data_collection=True, data_collection_reason="Different claim")
        self.refused("IDEMPOTENCY_CONFLICT", self.service.create_booking, self.student, self.room.id, start, end,
                     "Research", idempotency_key="extra-key")
        normal = self.service.create_booking(self.other, self.room.id, start, end, "Research", idempotency_key="normal-key")[0]
        self.refused("IDEMPOTENCY_CONFLICT", self.service.create_additional_hours_booking,
                     self.other, self.room.id, normal.start, normal.end, "Research", "Need spare capacity", idempotency_key="normal-key")

    def test_approved_grant_cannot_be_moved_through_reschedule_or_change(self):
        booking = self.extra()
        approved = self.service.review_booking(self.manager, booking.id, "APPROVED")
        start, end = self.at(2)
        self.refused("ADDITIONAL_HOURS_NEW_REQUEST_REQUIRED", self.service.reschedule_booking, self.manager, approved.id, start, end)
        self.refused("ADDITIONAL_HOURS_NEW_REQUEST_REQUIRED", self.service.request_time_change, self.student, approved.id, start, end)
        self.assertEqual(self.repo.get_booking(booking.id).start, booking.start)

    def test_availability_and_overview_distinguish_non_reserving_extra_requests(self):
        booking = self.extra()
        day = booking.start.astimezone(self.zone).date()
        ordinary = self.service.availability(self.other, self.room.id, day)
        extra = self.service.availability(self.other, self.room.id, day, additional_hours=True)
        self.assertEqual(ordinary["min_advance_days"], 7)
        self.assertEqual(extra["min_advance_days"], 0)
        self.assertEqual(extra["earliest_date"], self.today.isoformat())
        self.assertEqual(extra["latest_date"], (self.today + timedelta(days=28)).isoformat())
        self.assertTrue(all(item["available"] for item in extra["slots"]))
        overview = self.service.staff_overview(self.manager)
        self.assertEqual((overview["additional_hours_requests"], overview["additional_hours_ready"], overview["pending_bookings"]), (1, 1, 0))
        self.assertFalse(self.service.staff_overview(self.admin)["can_decide_additional_hours"])
        self.assertTrue(any(item.kind == "ADDITIONAL_HOURS_REQUEST" for item in self.repo.list_notifications(self.manager.id)))
        notice = next(item for item in self.repo.list_notifications(self.student.id) if item.kind == "BOOKING_SUBMITTED")
        self.assertNotIn("system decides", notice.body)

    @override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, ENABLE_TEST_CONSOLE=True)
    def test_test_console_bypass_does_not_apply_to_additional_hours(self):
        principal = replace(self.student, id=TEST_ACCOUNT_ID, zid="1")
        self.repo.save_principal(principal)
        self.qualification(principal)
        actor = make_test_identity(principal, "STUDENT", True)
        self.refused("DURATION_LIMIT", self.extra, actor, minutes=240)
        self.refused("BOOKING_TOO_FAR_AHEAD", self.extra, actor, days=29)
        booking = self.extra(actor)
        self.assertEqual(booking.status, BookingStatus.PENDING_APPROVAL)
        self.refused("INVALID_DURATION", self.service.availability, actor, self.room.id,
                     self.today + timedelta(days=1), duration_minutes=240, additional_hours=True)

    def test_concurrent_manager_approval_confirms_once(self):
        booking = self.extra()
        barrier = Barrier(2)

        def decide(actor):
            barrier.wait()
            try:
                return self.service.review_booking(actor, booking.id, "APPROVED").status
            except DomainError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(decide, (self.manager, self.manager2)))
        self.assertCountEqual(results, [BookingStatus.APPROVED, "REQUEST_NOT_REVIEWABLE"])
        self.assertEqual(sum(item.kind == "BOOKING_APPROVED" for item in self.repo.list_notifications(self.student.id)), 1)

    def test_response_context_keeps_queue_database_reads_linear(self):
        bookings, counts = [], []
        for size in (1, 10, 20):
            while len(bookings) < size:
                person = replace(self.student, id=str(uuid4()), zid=f"z{3000000 + len(bookings)}")
                self.repo.save_principal(person)
                self.qualification(person)
                self.now += timedelta(seconds=1)
                bookings.append(self.extra(person))
            context = {}
            with patch.object(self.repo, "list_bookings", wraps=self.repo.list_bookings) as listed, \
                    patch.object(self.repo, "list_blocking_bookings", wraps=self.repo.list_blocking_bookings) as blockers:
                metadata = [self.service.additional_hours_review(item, context=context) for item in bookings]
                counts.append((listed.call_count, blockers.call_count))
            self.assertEqual([item["queue_position"] for item in metadata], list(range(1, size + 1)))
        self.assertLessEqual(counts[1][0], 10 * counts[0][0])
        self.assertLessEqual(counts[2][0], 2 * counts[1][0] + 1)
        self.assertEqual([item[1] for item in counts], [1, 10, 20])

    def test_approval_never_reuses_a_previous_response_context(self):
        booking = self.extra()
        context = {}
        self.assertTrue(self.service.additional_hours_review(booking, context=context)["can_approve"])
        self.service._override_rule(min_advance_days=0)
        self.service.create_booking(self.other, self.room.id, booking.start, booking.end, "New ordinary hold")
        self.refused("ADDITIONAL_HOURS_NO_CAPACITY", self.service.review_booking, self.manager, booking.id, "APPROVED")
