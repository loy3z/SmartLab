"""Client approval flow: every request is pending first; an Admin decides within the review window
(default 24 hours, holding the slot), otherwise the system approves it if it still follows the rules
and rejects it if not. Later requests for the same time queue in submission order.
"""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, override_settings
from django.utils.dateparse import parse_datetime

from booking.domain import BookingStatus, Principal, QualificationStatus, QualificationSubmission, Role
from booking.exceptions import DomainError
from booking.tests.test_api import NOW, BookingAPIFixtureMixin
from booking.tests.test_outlook import FakeCalendar
from booking.tests.test_services import BookingFixtureMixin

SYDNEY = ZoneInfo("Australia/Sydney")


class ApprovalFlowServiceTests(BookingFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.manager = Principal(str(uuid4()), "z9888888", "Manager", Role.MANAGER, "z9888888@ad.unsw.edu.au")
        self.repo.save_principal(self.manager)
        self.a, self.b = self.student, self.other
        self.c, self.d = self.make_student("z3333333"), self.make_student("z4444444")
        for person in (self.a, self.b, self.c, self.d):
            self.qualification(person)

    def make_student(self, zid):
        principal = Principal(str(uuid4()), zid, zid, Role.STUDENT, f"{zid}@ad.unsw.edu.au")
        self.repo.save_principal(principal)
        return principal

    def book(self, principal=None, **overrides):
        # Requests arrive one after another; queue order follows submission time.
        booking = super().book(principal, **overrides)
        self.now += timedelta(seconds=1)
        return booking

    def get(self, booking):
        return self.repo.get_booking(booking.id)

    def state(self, booking):
        current = self.get(booking)
        return current.status, current.reason_code

    def test_first_request_holds_the_slot_for_the_review_window_and_later_ones_queue(self):
        first = self.book(self.a)
        self.assertEqual((first.status, first.reason_code), (BookingStatus.PENDING_APPROVAL, "AWAITING_REVIEW"))
        self.assertEqual(first.hold_until, first.created_at + timedelta(hours=24))
        later = [self.book(person) for person in (self.b, self.c)]
        self.assertEqual([self.state(item) for item in later], [(BookingStatus.WAITLISTED, "TEMPORARY_HOLD_CONFLICT")] * 2)
        with self.assertRaises(DomainError) as denied:
            self.service.review_booking(self.admin, later[0].id, "APPROVED")
        self.assertEqual(denied.exception.code, "REQUEST_WAITLISTED")

    def test_unreviewed_request_is_approved_when_the_window_ends_and_the_queue_stays_as_backup(self):
        first, waiting = self.book(self.a), self.book(self.b)
        self.now = first.review_due_at
        self.service.process_due_requests()
        self.assertEqual(self.state(first), (BookingStatus.APPROVED, "AUTO_APPROVED_AFTER_REVIEW_WINDOW"))
        self.assertEqual(self.get(first).reviewed_by, "SYSTEM")
        self.assertEqual(self.state(waiting)[0], BookingStatus.WAITLISTED)

    def test_freed_time_goes_to_the_next_request_as_a_new_pending_request(self):
        first, second, third = self.book(self.a), self.book(self.b), self.book(self.c)
        self.service.review_booking(self.admin, first.id, "REJECTED", "Not a teaching activity")
        promoted = self.get(second)
        self.assertEqual((promoted.status, promoted.reason_code), (BookingStatus.PENDING_APPROVAL, "PROMOTED_FROM_WAITLIST"))
        self.assertEqual(promoted.hold_until, self.now + timedelta(hours=24))  # a fresh review window, not an approval
        self.assertEqual(self.state(third)[0], BookingStatus.WAITLISTED)
        self.now = promoted.review_due_at
        self.service.process_due_requests()
        self.assertEqual(self.state(second), (BookingStatus.APPROVED, "AUTO_APPROVED_AFTER_REVIEW_WINDOW"))

    def test_cancelling_an_approved_booking_promotes_the_queue_in_submission_order(self):
        first = self.book(self.a)
        second, third = self.book(self.b), self.book(self.c)
        self.service.review_booking(self.admin, first.id, "APPROVED")
        self.service.cancel_booking(self.a, first.id)
        self.assertEqual([self.state(second)[0], self.state(third)[0]], [BookingStatus.PENDING_APPROVAL, BookingStatus.WAITLISTED])

    def test_staff_can_cancel_an_approved_booking_after_review_and_the_next_request_moves_up(self):
        first, waiting = self.book(self.a), self.book(self.b)
        self.now = first.review_due_at
        self.service.process_due_requests()  # approved over the weekend without anyone looking
        cancelled = self.service.cancel_booking(self.manager, first.id)
        self.assertEqual(cancelled.reason_code, "CANCELLED_BY_STAFF")
        self.assertEqual(self.state(waiting), (BookingStatus.PENDING_APPROVAL, "PROMOTED_FROM_WAITLIST"))

    def test_window_end_rejects_an_ineligible_holder_and_passes_the_time_on(self):
        first, waiting = self.book(self.a), self.book(self.b)
        self.qualification(self.a, valid_until=self.now - timedelta(seconds=1))  # the holder's induction expired
        self.now = first.review_due_at
        self.service.process_due_requests()
        self.assertEqual(self.state(first), (BookingStatus.REJECTED, "AUTO_REJECTED_QUALIFICATION"))
        self.assertEqual(self.state(waiting)[0], BookingStatus.PENDING_APPROVAL)

    def test_promotion_rejects_requests_without_a_current_qualification(self):
        first, second, third = self.book(self.a), self.book(self.b), self.book(self.c)
        self.qualification(self.b, status=QualificationStatus.PENDING)  # B uploaded new evidence, not yet reviewed
        self.service.cancel_booking(self.a, first.id)
        self.assertEqual(self.state(second), (BookingStatus.REJECTED, "QUALIFICATION_REQUIRED"))
        self.assertEqual(self.state(third)[0], BookingStatus.PENDING_APPROVAL)

    def test_rejecting_an_induction_rejects_that_persons_undecided_requests(self):
        first, waiting = self.book(self.a), self.book(self.b)
        submission = self.qualification(self.a, status=QualificationStatus.PENDING)
        self.service.review_qualification(self.admin, submission.id, "REJECTED", "Wrong certificate")
        self.assertEqual(self.state(first), (BookingStatus.REJECTED, "QUALIFICATION_REJECTED"))
        self.assertEqual(self.get(first).decision_reason, "Wrong certificate")
        self.assertEqual(self.state(waiting)[0], BookingStatus.PENDING_APPROVAL)

    def test_freed_time_goes_to_the_earliest_request_that_fits(self):
        first = self.book(self.a, start=self.start, end=self.start + timedelta(hours=2))
        wide = self.book(self.b, start=self.start, end=self.start + timedelta(hours=3))  # also overlaps the C+1h booking
        self.service.review_booking(self.admin, first.id, "APPROVED")
        blocker = self.book(self.d, start=self.start + timedelta(hours=2), end=self.start + timedelta(hours=3))
        self.service.review_booking(self.admin, blocker.id, "APPROVED")
        fits = self.book(self.c, start=self.start, end=self.start + timedelta(hours=1))
        self.service.cancel_booking(self.a, first.id)
        self.assertEqual(self.state(wide)[0], BookingStatus.WAITLISTED)
        self.assertEqual(self.state(fits)[0], BookingStatus.PENDING_APPROVAL)

    def test_waitlisted_requests_expire_at_start(self):
        self.book(self.a)
        waiting = self.book(self.b)
        self.now = self.start
        self.service.process_due_requests()
        self.assertEqual(self.state(waiting), (BookingStatus.EXPIRED, "START_TIME_PASSED"))

    def test_rescheduling_frees_the_old_slot_for_the_queue(self):
        first, waiting = self.book(self.a), self.book(self.b)
        self.service.review_booking(self.admin, first.id, "APPROVED")
        later = self.start + timedelta(hours=3)
        self.service.reschedule_booking(self.a, first.id, later, later + timedelta(hours=1))
        self.assertEqual(self.state(waiting)[0], BookingStatus.PENDING_APPROVAL)

    def test_staff_do_not_book(self):
        """Admins and Managers are staff: they review and manage, they do not book."""
        for staff in (replace(self.c, role=Role.ADMIN), self.manager, self.admin):
            self.repo.save_principal(staff)
            with self.subTest(role=staff.role), self.assertRaises(DomainError) as denied:
                self.book(staff)
            self.assertEqual(denied.exception.code, "FORBIDDEN")

    def test_adjacent_periods_and_other_resources_do_not_conflict(self):
        first = self.book(self.a)
        after = self.book(self.b, start=self.end, end=self.end + timedelta(hours=1))
        before = self.book(self.c, start=self.start - timedelta(hours=1), end=self.start)
        other_room = replace(self.room, id=str(uuid4()), name="Second laboratory")
        self.repo.save_resource(other_room)
        elsewhere = self.book(self.d, resource_id=other_room.id)
        self.assertEqual([item.status for item in (first, after, before, elsewhere)], [BookingStatus.PENDING_APPROVAL] * 4)

    def test_rejecting_a_waitlisted_request_keeps_everyone_elses_order(self):
        first = self.book(self.a)
        second, third, fourth = (self.book(person) for person in (self.b, self.c, self.d))
        self.service.review_booking(self.admin, third.id, "REJECTED", "Duplicate request")
        self.assertEqual(self.state(first)[0], BookingStatus.PENDING_APPROVAL)
        self.service.cancel_booking(self.a, first.id)
        self.assertEqual([self.state(item)[0] for item in (second, third, fourth)],
                         [BookingStatus.PENDING_APPROVAL, BookingStatus.REJECTED, BookingStatus.WAITLISTED])

    def test_review_window_is_capped_at_the_start_and_an_undecided_request_expires_then(self):
        self.service.min_advance_days = 0
        soon = self.now + timedelta(hours=3)
        start = soon.astimezone(SYDNEY).replace(minute=0, second=0, microsecond=0)
        if not 8 <= start.hour < 19:  # keep inside opening hours whatever the fixture clock is
            start = (start + timedelta(days=1)).replace(hour=10)
            self.now = start - timedelta(hours=3)
        booking = self.book(self.a, start=start, end=start + timedelta(hours=1))
        self.assertEqual(booking.review_due_at, start)
        self.now = start
        self.service.process_due_requests()
        self.assertEqual(self.state(booking), (BookingStatus.EXPIRED, "START_TIME_PASSED"))

    def test_parallel_requests_create_only_one_pending_request(self):
        import threading
        barrier, results = threading.Barrier(4), []

        def request(person):
            barrier.wait()
            results.append(self.service.create_booking(person, self.room.id, self.start, self.end, "Race")[0].status)

        threads = [threading.Thread(target=request, args=(person,)) for person in (self.a, self.b, self.c, self.d)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(item.value for item in results), ["PENDING_APPROVAL"] + ["WAITLISTED"] * 3)

    def test_promotions_are_audited(self):
        first, second = self.book(self.a), self.book(self.b)
        self.service.cancel_booking(self.a, first.id)
        actions = [(item.action, item.actor_id) for item in self.repo.list_audit() if item.entity_id == second.id]
        self.assertIn(("BOOKING_PROMOTED", "SYSTEM"), actions)

    def test_manager_sets_the_review_window_for_new_requests_only(self):
        first = self.book(self.a)
        updated = self.service.set_booking_policy(self.manager, self.room.id, 60)
        self.assertEqual(updated.pending_hold_minutes, 60)
        self.assertEqual(self.get(first).hold_until, first.created_at + timedelta(hours=24))
        later = self.book(self.b, start=self.end, end=self.end + timedelta(hours=1))
        self.assertEqual(later.hold_until, later.created_at + timedelta(minutes=60))
        for actor, value in ((self.admin, 60), (self.a, 60), (self.manager, 0), (self.manager, 20161), (self.manager, True)):
            with self.subTest(actor=actor.zid, value=value), self.assertRaises(DomainError):
                self.service.set_booking_policy(actor, self.room.id, value)

    def test_reads_and_idempotent_retries_do_not_renew_the_window(self):
        first = super().book(self.a, idempotency_key="retry-1")
        self.now += timedelta(hours=1)
        again = super().book(self.a, idempotency_key="retry-1")
        self.service.availability(self.a, self.room.id, self.start.date(), 60)
        self.assertEqual((again.id, self.get(first).hold_until), (first.id, first.hold_until))


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True, OUTLOOK_ENABLED=False)
class ApprovalFlowAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def slots(self, client):
        day = parse_datetime(self.payload()["start"]).astimezone(SYDNEY).date().isoformat()
        response = client.get(f"/api/v1/resources/{self.room['id']}/availability/", {"date": day, "duration_minutes": 60})
        self.assertEqual(response.status_code, 200, response.data)
        expected = parse_datetime(self.payload()["start"])
        return response.data, next(item for item in response.data["slots"] if parse_datetime(item["start"]) == expected)

    def test_new_request_is_pending_with_a_24_hour_review_window(self):
        created = self.create_booking()
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual((created.data["status"], created.data["reason_code"]), ("PENDING_APPROVAL", "AWAITING_REVIEW"))
        self.assertEqual(parse_datetime(created.data["hold_until"]), NOW + timedelta(hours=24))
        self.assertEqual(created.data["review_due_at"], created.data["hold_until"])
        self.assertEqual(created.data["outlook_sync"]["status"], "NOT_REQUIRED")
        queue = self.items(self.admin.get("/api/v1/admin/bookings/"))
        self.assertEqual([item["id"] for item in queue], [created.data["id"]])

    def test_availability_shows_the_held_slot_and_who_may_request(self):
        held = self.create_booking().data
        data, mine = self.slots(self.verified)
        self.assertEqual((mine["reason_code"], mine["held_by_me"], mine["hold_until"]), ("TEMPORARILY_HELD", True, held["hold_until"]))
        self.assertEqual((data["can_request"], data["review_window_minutes"]), (True, 1440))
        data, theirs = self.slots(self.student)  # z1000002 has no induction
        self.assertEqual((theirs["held_by_me"], data["can_request"], data["qualification_status"]), (False, False, "NOT_SUBMITTED"))

    def test_student_with_induction_under_review_cannot_request_yet(self):
        submission = self.submit()
        refused = self.create_booking(self.student)
        self.assert_error(refused, 403)
        self.assertEqual((refused.data["error"]["code"], refused.data["error"]["details"]["qualification_status"]),
                         ("QUALIFICATION_REQUIRED", "PENDING"))
        self.admin.post(f"/api/v1/admin/qualifications/{submission['id']}/review/", {"decision": "VERIFIED"}, format="json")
        self.assertEqual(self.create_booking(self.student).data["status"], "PENDING_APPROVAL")

    def test_window_end_is_applied_on_the_next_request_to_the_server(self):
        created = self.create_booking().data
        self.service.clock = lambda: NOW + timedelta(hours=24)
        decided = self.verified.get(f"/api/v1/bookings/{created['id']}/").data
        self.assertEqual((decided["status"], decided["reason_code"], decided["reviewed_by"]),
                         ("APPROVED", "AUTO_APPROVED_AFTER_REVIEW_WINDOW", "SYSTEM"))

    def test_manager_policy_endpoint(self):
        url = f"/api/v1/admin/resources/{self.room['id']}/booking-policy/"
        self.assert_error(self.admin.get(url), 403)  # rules belong to Managers; Admins approve
        self.assertEqual(self.manager.get(url).data, {"resource_id": self.room["id"], "pending_hold_minutes": 1440})
        self.assert_error(self.admin.patch(url, {"pending_hold_minutes": 60}, format="json"), 403)
        self.assertEqual(self.manager.patch(url, {"pending_hold_minutes": 60}, format="json").data["pending_hold_minutes"], 60)
        for body in ({}, {"pending_hold_minutes": 0}, {"pending_hold_minutes": 60, "auto_approve_max_minutes": 120}):
            with self.subTest(body=body):
                self.assert_error(self.manager.patch(url, body, format="json"), 400)

    def test_waitlist_position_and_staff_cannot_book(self):
        first = self.create_booking().data
        other = next(item for item in self.service.repo.list_principals() if item.zid == "z1000003")
        self.service.repo.save_submission(QualificationSubmission(
            str(uuid4()), other.id, self.requirement_id, "Certificate", "", "file", NOW,
            status=QualificationStatus.VERIFIED, reviewed_by="seed", reviewed_at=NOW))
        queued = self.create_booking(self.login("z1000003"))
        self.assertEqual((queued.status_code, queued.data["status"], queued.data["waitlist_position"]), (201, "WAITLISTED", 1))
        self.verified.post(f"/api/v1/bookings/{first['id']}/cancel/", {}, format="json")
        moved = self.admin.get("/api/v1/admin/bookings/").data["results"]
        self.assertEqual([(item["id"], item["reason_code"]) for item in moved], [(queued.data["id"], "PROMOTED_FROM_WAITLIST")])
        for staff in (self.admin, self.manager):
            with self.subTest(staff=staff):
                self.assert_error(self.create_booking(staff, self.payload(hour=14)), 403)


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True, OUTLOOK_ENABLED=True, OUTLOOK_SYNC_ON_WRITE=True)
class ApprovalFlowOutlookTests(BookingAPIFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.provider = FakeCalendar()
        self.service.calendar_sync.provider = self.provider

    def test_only_an_approved_booking_reaches_outlook(self):
        created = self.create_booking().data
        self.assertEqual(self.provider.creates, [])
        approved = self.admin.post(f"/api/v1/admin/bookings/{created['id']}/review/", {"decision": "APPROVED"}, format="json").data
        self.assertEqual(approved["outlook_sync"]["status"], "SYNCED")
        self.assertEqual([call[0] for call in self.provider.creates], [created["id"]])

    def test_automatic_approval_is_pushed_to_outlook_on_the_next_write(self):
        created = self.create_booking().data
        self.service.clock = lambda: NOW + timedelta(hours=24)
        self.create_booking(payload=self.payload(hour=15))  # any later write processes due requests and syncs them
        self.assertIn(created["id"], [call[0] for call in self.provider.creates])
