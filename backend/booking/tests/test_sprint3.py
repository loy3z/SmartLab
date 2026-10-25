"""Sprint 3: calendar subscription link, website notifications, check-in with booking freeze, weekly limit, weekly series."""

from dataclasses import replace
from datetime import datetime, time, timedelta
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from booking.domain import BookingStatus, Principal, QualificationStatus, ResourceStatus, Role, UnfreezeStatus
from booking.exceptions import DomainError
from booking.ics import render_calendar
from booking.notification_channels import reset_channels
from booking.tests.test_api import NOW, SYDNEY, BookingAPIFixtureMixin
from booking.tests.test_services import BookingFixtureMixin


class Sprint3Fixture(BookingFixtureMixin):
    def setUp(self):
        super().setUp()
        self.manager = Principal(str(uuid4()), "z9888888", "Manager", Role.MANAGER, "z9888888@ad.unsw.edu.au")
        self.repo.save_principal(self.manager)
        self.qualification(self.student)
        self.qualification(self.other)
        self.today = self.now.astimezone(SYDNEY).date()

    def at(self, days, hour=10, minutes=60):
        start = datetime.combine(self.today + timedelta(days=days), time(hour), SYDNEY)
        return start, start + timedelta(minutes=minutes)

    def request(self, actor=None, days=3, hour=10, resource=None, **extra):
        start, end = self.at(days, hour)
        return self.service.create_booking(actor or self.student, (resource or self.room).id, start, end,
                                           "Practical session", **extra)[0]

    def approved(self, actor=None, days=3, hour=10, **extra):
        return self.service.review_booking(self.admin, self.request(actor, days, hour, **extra).id, "APPROVED")

    def refused(self, code, call, *args, **kwargs):
        with self.assertRaises(DomainError) as denied:
            call(*args, **kwargs)
        self.assertEqual(denied.exception.code, code)
        return denied.exception

    def notices(self, person, kind=None):
        return [item for item in self.repo.list_notifications(person.id) if kind is None or item.kind == kind]


class CalendarFeedTests(Sprint3Fixture, SimpleTestCase):
    def test_link_is_created_once_and_a_reset_stops_the_old_link(self):
        first = self.service.calendar_feed(self.student)
        self.assertEqual(self.service.calendar_feed(self.student).token, first.token)
        self.assertGreaterEqual(len(first.token), 32)
        renewed = self.service.calendar_feed(self.student, reset=True)
        self.assertNotEqual(renewed.token, first.token)
        self.refused("NOT_FOUND", self.service.calendar_feed_events, first.token)
        self.assertEqual(self.service.calendar_feed_events(renewed.token)[0].id, self.student.id)

    def test_feed_has_only_the_persons_approved_bookings_with_a_stable_uid(self):
        mine = self.approved(self.student, days=3)
        self.request(self.student, days=4)  # still pending: not in the calendar
        self.approved(self.other, days=5)   # someone else's
        token = self.service.calendar_feed(self.student).token
        _, events = self.service.calendar_feed_events(token)
        self.assertEqual([item[0].id for item in events], [mine.id])
        start, end = self.at(3, 14)
        moved = self.service.reschedule_booking(self.manager, mine.id, start, end)
        text = render_calendar("SmartLab", self.service.calendar_feed_events(token)[1], self.now)
        self.assertIn(f"UID:{mine.id}@smartlab", text)
        self.assertIn("SEQUENCE:1", text)
        self.assertIn(moved.start.strftime("DTSTART:%Y%m%dT%H%M%SZ"), text)
        self.service.cancel_booking(self.student, mine.id)
        self.assertEqual(self.service.calendar_feed_events(token)[1], [])

    def test_ics_text_is_escaped_and_folded(self):
        booking = self.approved(self.student)
        resource = replace(self.room, name="Lab, room; A\\B " + "x" * 120)
        text = render_calendar("Name, with comma", [(booking, resource, self.student, None)], self.now)
        self.assertTrue(text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n"))
        self.assertIn("X-WR-CALNAME:Name\\, with comma", text)
        self.assertIn("Lab\\, room\\; A\\\\B", text.replace("\r\n ", ""))
        self.assertTrue(all(len(line.encode()) <= 75 for line in text.split("\r\n")))

    def test_inactive_person_has_no_feed(self):
        token = self.service.calendar_feed(self.student).token
        self.repo.save_principal(replace(self.student, active=False))
        self.refused("NOT_FOUND", self.service.calendar_feed_events, token)


class NotificationTests(Sprint3Fixture, SimpleTestCase):
    def test_review_decisions_notify_the_person_booked_for(self):
        approved = self.approved(self.student, days=3)
        self.assertEqual(sorted(item.kind for item in self.notices(self.student)), ["BOOKING_APPROVED", "BOOKING_SUBMITTED"])
        self.assertIn("Laboratory", self.notices(self.student, "BOOKING_APPROVED")[0].body)
        self.assertEqual(self.notices(self.student, "BOOKING_APPROVED")[0].booking_id, approved.id)
        rejected = self.request(self.student, days=4)
        self.service.review_booking(self.admin, rejected.id, "REJECTED", "Room needed for an exam")
        notice = self.notices(self.student, "BOOKING_REJECTED")[0]
        self.assertIn("Room needed for an exam", notice.body)
        # Admins are not told about ordinary new requests (they have the review queue).
        self.assertEqual(self.notices(self.admin), [])

    def test_promotion_reschedule_and_staff_cancel_are_notified_but_own_cancel_is_not(self):
        first = self.request(self.student, days=3)
        queued = self.request(self.other, days=3)
        self.assertEqual(queued.status, BookingStatus.WAITLISTED)
        self.service.cancel_booking(self.student, first.id)
        self.assertEqual([item.kind for item in self.notices(self.student)], ["BOOKING_SUBMITTED"])  # no notice for own cancel
        self.assertEqual(sorted(item.kind for item in self.notices(self.other)), ["BOOKING_PROMOTED", "BOOKING_SUBMITTED"])
        self.assertIn("waitlist", self.notices(self.other, "BOOKING_SUBMITTED")[0].body)
        approved = self.service.review_booking(self.admin, queued.id, "APPROVED")
        start, end = self.at(3, 15)
        self.service.reschedule_booking(self.manager, approved.id, start, end)
        self.assertIn("was", self.notices(self.other, "BOOKING_RESCHEDULED")[0].body)
        self.service.cancel_booking(self.admin, approved.id)
        self.assertEqual(len(self.notices(self.other, "BOOKING_CANCELLED")), 1)

    def test_automatic_decision_is_notified(self):
        booking = self.request(self.student, days=3)
        self.now = booking.review_due_at + timedelta(minutes=1)
        self.service.process_due_requests()
        notice = self.notices(self.student, "BOOKING_APPROVED")[0]
        self.assertIn("automatically", notice.body)

    def test_booking_for_someone_urgent_and_induction_notices(self):
        self.qualification(self.admin)
        self.request(self.admin, days=3, on_behalf_of_zid=self.student.zid)
        self.assertEqual(self.notices(self.student, "BOOKING_CREATED_FOR_YOU")[0].body.split(" booked")[0], "Administrator")
        self.service.min_advance_days, self.service.max_advance_days = 7, 30
        self.request(self.other, days=2, urgent=True, urgent_reason="Thesis deadline")
        urgent = self.notices(self.manager, "URGENT_REQUEST")
        self.assertEqual(len(urgent), 1)
        self.assertIn("Thesis deadline", urgent[0].body)
        self.assertEqual(urgent[0].link, "/admin/bookings")
        newcomer = Principal(str(uuid4()), "z3333333", "Third student", Role.STUDENT, "z3333333@ad.unsw.edu.au")
        self.repo.save_principal(newcomer)
        evidence = self.qualification(newcomer, status=QualificationStatus.PENDING)
        self.service.review_qualification(self.admin, evidence.id, "REJECTED", "Blurry scan")
        notice = self.notices(newcomer, "QUALIFICATION_REJECTED")[0]
        self.assertEqual(notice.link, "/induction")
        self.assertIn("Blurry scan", notice.body)

    def test_reading_notifications(self):
        self.approved(self.student, days=3)
        self.service.review_booking(self.admin, self.request(self.student, days=4).id, "REJECTED", "No")
        items, unread = self.service.list_notifications(self.student)
        self.assertEqual((len(items), unread), (4, 4))  # two "Request received" and two decisions
        self.service.mark_notification_read(self.student, items[0].id)
        self.assertEqual(self.service.list_notifications(self.student)[1], 3)
        self.assertEqual(len(self.service.list_notifications(self.student, unread_only=True)[0]), 3)
        self.refused("NOT_FOUND", self.service.mark_notification_read, self.other, items[1].id)
        self.assertEqual(self.service.mark_all_notifications_read(self.student), 3)
        self.assertEqual(self.service.list_notifications(self.student)[1], 0)


class AttendanceTests(Sprint3Fixture, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.service._override_rule(max_advance_days=60, max_bookings_per_week=20)

    def miss(self, booking):
        self.now = booking.start + timedelta(minutes=31)
        self.service.process_due_requests()
        return self.repo.get_booking(booking.id)

    def test_check_in_window(self):
        booking = self.approved(self.student, days=3)
        self.now = booking.start - timedelta(minutes=16)
        self.refused("CHECK_IN_NOT_OPEN", self.service.check_in, self.student, booking.id)
        self.refused("NOT_FOUND", self.service.check_in, self.other, booking.id)
        self.now = booking.start + timedelta(minutes=5)
        self.assertTrue(self.service.check_in_state(self.repo.get_booking(booking.id))["check_in_open"])
        checked = self.service.check_in(self.student, booking.id)
        self.assertEqual((checked.attendance, checked.checked_in_at), ("CHECKED_IN", self.now))
        self.assertEqual(self.service.check_in(self.student, booking.id).checked_in_at, checked.checked_in_at)
        self.assertEqual(self.miss(booking).attendance, "CHECKED_IN")
        self.assertEqual(self.repo.get_principal(self.student.id).no_show_count, 0)
        late = self.approved(self.student, days=5)
        self.now = late.start + timedelta(minutes=30)
        self.refused("CHECK_IN_CLOSED", self.service.check_in, self.student, late.id)

    def test_missed_booking_is_counted_and_notified(self):
        booking = self.approved(self.student, days=3)
        self.assertEqual(self.miss(booking).attendance, "NO_SHOW")
        self.assertEqual(self.repo.get_principal(self.student.id).no_show_count, 1)
        self.assertIn("1 of 4", self.notices(self.student, "NO_SHOW_RECORDED")[0].body)
        self.service.process_due_requests()  # counted once
        self.assertEqual(self.repo.get_principal(self.student.id).no_show_count, 1)

    def test_resource_under_maintenance_is_not_a_missed_booking(self):
        booking = self.approved(self.student, days=3)
        self.repo.save_resource(replace(self.room, status=ResourceStatus.MAINTENANCE, status_reason="Repair"))
        self.assertEqual(self.miss(booking).attendance, "EXCUSED")
        self.assertEqual(self.repo.get_principal(self.student.id).no_show_count, 0)

    def test_fourth_missed_booking_freezes_and_cancels_later_bookings(self):
        missed = [self.approved(self.student, days=day) for day in (1, 2, 3, 4)]
        later = self.approved(self.student, days=20)
        pending = self.request(self.student, days=21)
        held = self.request(self.other, days=22)
        queued = self.request(self.student, days=22)
        waiting_other = self.request(self.other, days=20)  # queued behind the student's approved booking
        self.assertEqual((queued.status, waiting_other.status), (BookingStatus.WAITLISTED, BookingStatus.WAITLISTED))
        for booking in missed[:3]:
            self.miss(booking)
        self.assertEqual(self.repo.get_principal(self.student.id).no_show_count, 3)
        self.miss(missed[3])
        person = self.repo.get_principal(self.student.id)
        self.assertEqual((person.no_show_count, person.frozen_until), (0, self.now + timedelta(days=30)))
        for item in (later, pending, queued):
            current = self.repo.get_booking(item.id)
            self.assertEqual((current.status, current.reason_code), (BookingStatus.CANCELLED, "ACCOUNT_FROZEN"))
        self.assertIn(self.repo.get_booking(held.id).status, (BookingStatus.PENDING_APPROVAL, BookingStatus.APPROVED))
        self.assertEqual(self.repo.get_booking(waiting_other.id).status, BookingStatus.PENDING_APPROVAL)  # freed time
        self.assertEqual(len(self.notices(self.student, "ACCOUNT_FROZEN")), 1)
        self.assertEqual(self.notices(self.student, "BOOKING_CANCELLED"), [])
        # Frozen: nobody can book for this person, but a frozen staff member keeps reviewing rights.
        self.refused("ACCOUNT_FROZEN", self.request, self.student, days=40)
        self.refused("ACCOUNT_FROZEN", self.request, self.admin, days=40, on_behalf_of_zid=self.student.zid)
        self.assertFalse(self.service.availability(self.student, self.room.id, self.today + timedelta(days=40), 60)["can_request"])
        self.now += timedelta(days=31)
        self.assertEqual(self.request(self.student, days=40).status, BookingStatus.PENDING_APPROVAL)

    def test_frozen_staff_can_still_review(self):
        self.repo.save_principal(replace(self.admin, frozen_until=self.now + timedelta(days=5)))
        admin = self.repo.get_principal(self.admin.id)
        booking = self.request(self.student, days=3)
        self.assertEqual(self.service.review_booking(admin, booking.id, "APPROVED").status, BookingStatus.APPROVED)
        self.qualification(self.admin)
        self.refused("ACCOUNT_FROZEN", self.request, admin, days=4)

    def test_unfreeze_request_flow(self):
        self.refused("NOT_FROZEN", self.service.request_unfreeze, self.student, "Please")
        self.repo.save_principal(replace(self.student, frozen_until=self.now + timedelta(days=30)))
        request = self.service.request_unfreeze(self.student, "I was ill and could not cancel")
        self.refused("UNFREEZE_ALREADY_REQUESTED", self.service.request_unfreeze, self.student, "Again")
        self.refused("REASON_REQUIRED", self.service.review_unfreeze, self.admin, request.id, "REJECTED", " ")
        self.refused("FORBIDDEN", self.service.list_unfreeze_requests, self.other)
        self.assertEqual([item.id for item in self.service.list_unfreeze_requests(self.admin, "PENDING")], [request.id])
        rejected = self.service.review_unfreeze(self.admin, request.id, "REJECTED", "Too many missed bookings")
        self.assertEqual(rejected.status, UnfreezeStatus.REJECTED)
        self.assertIn("Too many", self.notices(self.student, "UNFREEZE_REJECTED")[0].body)
        self.refused("ALREADY_REVIEWED", self.service.review_unfreeze, self.admin, request.id, "APPROVED")
        second = self.service.request_unfreeze(self.student, "Medical certificate attached")
        self.service.review_unfreeze(self.manager, second.id, "APPROVED")
        self.assertFalse(self.repo.get_principal(self.student.id).frozen_at(self.now))
        self.assertEqual(len(self.notices(self.student, "UNFREEZE_APPROVED")), 1)

    def test_staff_cannot_decide_their_own_request_but_can_unfreeze_directly(self):
        self.repo.save_principal(replace(self.admin, frozen_until=self.now + timedelta(days=30)))
        admin = self.repo.get_principal(self.admin.id)
        request = self.service.request_unfreeze(admin, "Missed during exam week")
        self.refused("SELF_REVIEW_FORBIDDEN", self.service.review_unfreeze, admin, request.id, "APPROVED")
        self.refused("SELF_MODIFICATION_FORBIDDEN", self.service.unfreeze, admin, admin.id)
        self.service.unfreeze(self.manager, admin.id, "Lifted")
        self.assertIsNone(self.repo.get_principal(admin.id).frozen_until)
        self.assertEqual(self.repo.get_unfreeze_request(request.id).status, UnfreezeStatus.APPROVED)
        self.refused("NOT_FROZEN", self.service.unfreeze, self.manager, admin.id)


class WeeklyLimitTests(Sprint3Fixture, SimpleTestCase):
    def test_at_most_three_bookings_in_one_week(self):
        # 2030-01-07 is a Monday (UTC); Sydney days 1-6 ahead are in the same Monday-Sunday week.
        first, second, third = (self.request(self.student, days=day) for day in (1, 2, 3))
        error = self.refused("WEEKLY_LIMIT_REACHED", self.request, self.student, days=4)
        self.assertEqual((error.details["limit"], error.details["count"]), (3, 3))
        self.service.cancel_booking(self.student, first.id)
        self.assertEqual(self.request(self.student, days=4).status, BookingStatus.PENDING_APPROVAL)
        # A waitlisted request counts too.
        self.request(self.other, days=5)
        self.service.cancel_booking(self.student, second.id)
        self.assertEqual(self.request(self.student, days=5).status, BookingStatus.WAITLISTED)
        self.refused("WEEKLY_LIMIT_REACHED", self.request, self.student, days=6)
        self.assertEqual(third.status, BookingStatus.PENDING_APPROVAL)

    def test_staff_booking_counts_for_the_person_booked_for_and_next_week_is_separate(self):
        self.qualification(self.admin)
        for day in (1, 2, 3):
            self.request(self.admin, days=day, on_behalf_of_zid=self.student.zid)
        self.refused("WEEKLY_LIMIT_REACHED", self.request, self.student, days=4)
        self.service.max_advance_days = 30
        week_day = self.today.isoweekday()
        next_monday = 8 - week_day
        self.assertEqual(self.request(self.student, days=next_monday).status, BookingStatus.PENDING_APPROVAL)

    def test_reschedule_into_a_full_week_is_refused(self):
        self.service.max_advance_days = 30
        week_day = self.today.isoweekday()
        moved = self.approved(self.student, days=8 - week_day + 2)  # next week
        for day in (1, 2, 3):
            self.request(self.student, days=day)
        start, end = self.at(4)
        self.refused("WEEKLY_LIMIT_REACHED", self.service.reschedule_booking, self.manager, moved.id, start, end)


class SeriesTests(Sprint3Fixture, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.qualification(self.admin)
        self.service.max_advance_days = 14  # one-off bookings; a series may go further
        self.monday = self.today + timedelta(days=(7 - self.today.weekday()) % 7 or 7)

    def plan(self, actor=None, **extra):
        arguments = dict(resource_id=self.room.id, weekdays=[1, 3], start_time=time(9), duration_minutes=60,
                         first_date=self.monday, last_date=self.monday + timedelta(weeks=6, days=-1))
        arguments.update(extra)
        return actor or self.admin, arguments

    def test_only_staff_create_series(self):
        actor, arguments = self.plan(self.student)
        self.refused("FORBIDDEN", self.service.preview_series, actor, **arguments)

    def test_preview_marks_problem_dates_and_create_approves_the_rest_at_once(self):
        start = datetime.combine(self.monday + timedelta(days=2), time(9), SYDNEY)  # first Wednesday
        taken = self.service.review_booking(self.admin, self.service.create_booking(
            self.other, self.room.id, start, start + timedelta(hours=1), "Other")[0].id, "APPROVED")
        actor, arguments = self.plan(on_behalf_of_zid=self.student.zid)
        preview = self.service.preview_series(actor, **arguments)
        self.assertEqual(len(preview["occurrences"]), 12)  # 6 weeks x Mon/Wed, beyond the 7-day window
        problems = [item for item in preview["occurrences"] if not item["available"]]
        self.assertEqual([(item["date"], item["reason_code"]) for item in problems],
                         [((self.monday + timedelta(days=2)).isoformat(), "BOOKING_CONFLICT")])
        self.refused("SERIES_CONFLICT", self.service.create_series, actor, purpose="Weekly lab", **arguments)
        series, bookings = self.service.create_series(actor, purpose="Weekly lab",
                                                      skip_dates=[problems[0]["date"]], **arguments)
        self.assertEqual(len(bookings), 11)
        self.assertTrue(all(item.status == BookingStatus.APPROVED and item.series_id == series.id
                            and item.student_id == self.student.id and item.created_by == self.admin.id for item in bookings))
        self.assertEqual(self.repo.get_booking(taken.id).status, BookingStatus.APPROVED)
        self.assertEqual(len(self.notices(self.student, "SERIES_CREATED_FOR_YOU")), 1)
        self.assertIn("(1 h)", self.notices(self.student, "SERIES_CREATED_FOR_YOU")[0].body)
        self.assertEqual(self.notices(self.student, "BOOKING_APPROVED"), [])
        # Series bookings do not count towards the weekly limit.
        self.assertEqual(self.request(self.student, days=1).status, BookingStatus.PENDING_APPROVAL)

    def test_series_rules(self):
        actor, arguments = self.plan(last_date=self.monday + timedelta(weeks=14))
        self.refused("SERIES_TOO_LONG", self.service.preview_series, actor, **arguments)
        actor, arguments = self.plan(first_date=self.monday, last_date=self.monday, weekdays=[2])
        self.refused("SERIES_EMPTY", self.service.preview_series, actor, **arguments)
        actor, arguments = self.plan(start_time=time(19, 30))
        preview = self.service.preview_series(actor, **arguments)
        self.assertEqual({item["reason_code"] for item in preview["occurrences"]}, {"OUTSIDE_OPENING_HOURS"})
        self.repo.save_principal(replace(self.student, frozen_until=self.now + timedelta(days=3)))
        actor, arguments = self.plan(on_behalf_of_zid=self.student.zid)
        self.refused("ACCOUNT_FROZEN", self.service.preview_series, actor, **arguments)

    def test_induction_must_cover_each_date(self):
        submission = next(item for item in self.repo.list_submissions(student_id=self.admin.id))
        self.repo.save_submission(replace(submission, valid_until=datetime.combine(self.monday + timedelta(days=10), time(12), SYDNEY)))
        actor, arguments = self.plan()
        preview = self.service.preview_series(actor, **arguments)
        self.assertEqual([item["available"] for item in preview["occurrences"]][:5], [True, True, True, True, False])
        self.assertEqual(preview["occurrences"][4]["reason_code"], "QUALIFICATION_REQUIRED")

    def test_cancel_series_keeps_past_dates(self):
        actor, arguments = self.plan()
        series, bookings = self.service.create_series(actor, purpose="Weekly lab", **arguments)
        # Sprint 3: the staff member's own series is confirmed once (emailed when email is on).
        self.assertEqual([item.kind for item in self.notices(self.admin)], ["SERIES_CREATED"])
        self.now = bookings[1].start + timedelta(hours=2)
        self.service.check_in_state(bookings[0])
        _, cancelled = self.service.cancel_series(self.admin, series.id)
        self.assertEqual(len(cancelled), len(bookings) - 2)
        detail = self.service.series_detail(self.admin, series.id)[1]
        self.assertEqual([item.status for item in detail[:2]], [BookingStatus.APPROVED] * 2)
        self.refused("NOT_FOUND", self.service.series_detail, self.other, series.id)


class RecordingChannel:
    name = "recording"
    sent = []

    def deliver(self, notification, recipient):
        RecordingChannel.sent.append((notification.kind, recipient.zid))


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class Sprint3APITests(BookingAPIFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.service._override_rule(max_advance_days=60)

    def create(self, client, **payload_args):
        response = client.post("/api/v1/bookings/", self.payload(**payload_args), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_calendar_link_and_public_feed(self):
        link = self.verified.get("/api/v1/calendar/link/")
        self.assertEqual(link.status_code, 200)
        self.assertTrue(link.data["path"].startswith("/api/v1/calendar/") and link.data["path"].endswith(".ics"))
        booking = self.create(self.verified)
        self.assertEqual(self.admin.post(f"/api/v1/admin/bookings/{booking['id']}/review/", {"decision": "APPROVED"},
                                         format="json").status_code, 200)
        feed = self.client.get(link.data["path"])  # no Authorization header: calendar apps cannot send one
        self.assertEqual(feed.status_code, 200)
        self.assertEqual(feed["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn(f"UID:{booking['id']}@smartlab", feed.content.decode())
        reset = self.verified.post("/api/v1/calendar/link/reset/", {}, format="json")
        self.assertNotEqual(reset.data["path"], link.data["path"])
        self.assertEqual(self.client.get(link.data["path"]).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/calendar/link/").status_code, 401)

    def test_notifications_api(self):
        booking = self.create(self.verified)
        self.admin.post(f"/api/v1/admin/bookings/{booking['id']}/review/", {"decision": "REJECTED", "reason": "Exam"}, format="json")
        listed = self.verified.get("/api/v1/notifications/")
        self.assertEqual((listed.status_code, listed.data["unread_count"], listed.data["count"]), (200, 2, 2))
        item = next(entry for entry in listed.data["results"] if entry["kind"] == "BOOKING_REJECTED")
        self.assertEqual((item["link"], item["read_at"]), ("/bookings", None))
        self.assertEqual(self.student.post(f"/api/v1/notifications/{item['id']}/read/", {}, format="json").status_code, 404)
        read = self.verified.post(f"/api/v1/notifications/{item['id']}/read/", {}, format="json")
        self.assertIsNotNone(read.data["read_at"])
        self.assertEqual(self.verified.post("/api/v1/notifications/read-all/", {}, format="json").data, {"updated": 1})
        self.assertEqual(self.verified.get("/api/v1/notifications/?unread=true").data["count"], 0)

    def test_extra_channels_receive_new_notifications_after_the_request(self):
        RecordingChannel.sent = []
        with override_settings(NOTIFICATION_CHANNELS=["booking.tests.test_sprint3.RecordingChannel"]):
            reset_channels()
            try:
                booking = self.create(self.verified)
                self.admin.post(f"/api/v1/admin/bookings/{booking['id']}/review/", {"decision": "APPROVED"}, format="json")
            finally:
                reset_channels()
        self.assertEqual(RecordingChannel.sent, [("BOOKING_SUBMITTED", "z1000001"), ("BOOKING_APPROVED", "z1000001")])

    def test_check_in_and_booking_fields(self):
        booking = self.create(self.verified)
        approved = self.admin.post(f"/api/v1/admin/bookings/{booking['id']}/review/", {"decision": "APPROVED"}, format="json").data
        self.assertEqual((approved["check_in_open"], approved["attendance"]), (False, None))
        start = datetime.fromisoformat(approved["start"].replace("Z", "+00:00"))
        self.service.clock = lambda: start + timedelta(minutes=1)
        detail = self.verified.get(f"/api/v1/bookings/{booking['id']}/").data
        self.assertTrue(detail["check_in_open"])
        self.assertEqual(self.admin.post(f"/api/v1/bookings/{booking['id']}/check-in/", {}, format="json").status_code, 404)
        checked = self.verified.post(f"/api/v1/bookings/{booking['id']}/check-in/", {}, format="json")
        self.assertEqual((checked.status_code, checked.data["attendance"], checked.data["check_in_open"]), (200, "CHECKED_IN", False))
        me = self.verified.get("/api/v1/auth/me/").data
        self.assertEqual((me["no_show_count"], me["frozen_until"], me["booking_frozen"]), (0, None, False))

    def test_unfreeze_api(self):
        person = next(item for item in self.service.repo.list_principals() if item.zid == "z1000001")
        self.service.repo.save_principal(replace(person, frozen_until=NOW + timedelta(days=10)))
        refused = self.verified.post("/api/v1/bookings/", self.payload(), format="json")
        self.assertEqual((refused.status_code, refused.data["error"]["code"]), (403, "ACCOUNT_FROZEN"))
        created = self.verified.post("/api/v1/account/unfreeze-requests/", {"reason": "Sick"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(self.verified.get("/api/v1/account/unfreeze-requests/").data["count"], 1)
        self.assertEqual(self.student.get("/api/v1/admin/unfreeze-requests/").status_code, 403)
        frozen = self.items(self.admin.get("/api/v1/admin/frozen-users/"))
        self.assertEqual([(item["zid"], item["pending_request"]["id"]) for item in frozen], [("z1000001", created.data["id"])])
        pending = self.items(self.admin.get("/api/v1/admin/unfreeze-requests/?status=PENDING"))
        self.assertEqual(pending[0]["person"]["zid"], "z1000001")
        decided = self.admin.post(f"/api/v1/admin/unfreeze-requests/{created.data['id']}/review/", {"decision": "APPROVED"}, format="json")
        self.assertEqual((decided.status_code, decided.data["status"]), (200, "APPROVED"))
        self.assertEqual(self.items(self.admin.get("/api/v1/admin/frozen-users/")), [])
        self.service.repo.save_principal(replace(self.service.repo.get_principal(person.id), frozen_until=NOW + timedelta(days=3)))
        lifted = self.manager.post(f"/api/v1/admin/users/{person.id}/unfreeze/", {"reason": "OK"}, format="json")
        self.assertEqual((lifted.status_code, lifted.data["booking_frozen"]), (200, False))

    def test_series_api(self):
        today = NOW.astimezone(SYDNEY).date()
        first = today + timedelta(days=7 - today.weekday())
        body = {"resource_id": self.room["id"], "weekdays": [2, 4], "start_time": "09:00", "duration_minutes": 60,
                "first_date": first.isoformat(), "last_date": (first + timedelta(weeks=3, days=-1)).isoformat(),
                "on_behalf_of_zid": "z1000001"}
        self.assertEqual(self.verified.post("/api/v1/bookings/series/preview/", body, format="json").status_code, 403)
        preview = self.admin.post("/api/v1/bookings/series/preview/", body, format="json")
        self.assertEqual((preview.status_code, len(preview.data["occurrences"]), preview.data["available_count"]), (200, 6, 6))
        created = self.admin.post("/api/v1/bookings/series/", {**body, "purpose": "Weekly lab"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual((created.data["weekdays"], len(created.data["bookings"])), ([2, 4], 6))
        self.assertTrue(all(item["status"] == "APPROVED" and item["series_id"] == created.data["id"]
                            for item in created.data["bookings"]))
        detail = self.verified.get(f"/api/v1/bookings/series/{created.data['id']}/")
        self.assertEqual(detail.status_code, 200)
        cancelled = self.admin.post(f"/api/v1/bookings/series/{created.data['id']}/cancel/", {}, format="json")
        self.assertEqual({item["status"] for item in cancelled.data["bookings"]}, {"CANCELLED"})
        bad = self.admin.post("/api/v1/bookings/series/preview/", {**body, "weekdays": [8]}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_weekly_limit_api_error(self):
        for day in (1, 2, 3):
            self.create(self.verified, day_offset=day)
        refused = self.verified.post("/api/v1/bookings/", self.payload(day_offset=4), format="json")
        self.assertEqual((refused.status_code, refused.data["error"]["code"]), (409, "WEEKLY_LIMIT_REACHED"))
        self.assertEqual(refused.data["error"]["details"]["limit"], 3)
