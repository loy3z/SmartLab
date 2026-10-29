"""Sprint 3 (1.20.0): removing personal history preserves the shared booking and its consequences."""

from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from booking.domain import BookingStatus
from booking.tests.test_api import BookingAPIFixtureMixin
from booking.tests.test_sprint3 import Sprint3Fixture
from booking.views.bookings import my_bookings


class BookingHistoryTests(Sprint3Fixture, SimpleTestCase):
    def test_removal_is_personal_idempotent_and_keeps_reports_and_notifications(self):
        booking = self.request(self.manager, on_behalf_of_zid=self.student.zid)
        booking = self.service.cancel_booking(self.manager, booking.id)
        notices = self.repo.list_notifications(self.student.id)
        person = self.repo.get_principal(self.student.id)
        for _ in range(2):
            self.service.remove_booking_history(self.manager, booking.id)
        self.assertEqual(my_bookings(self.service, self.manager), [])
        self.assertEqual([b.id for b in my_bookings(self.service, self.student)], [booking.id])
        self.assertEqual(self.repo.get_booking(booking.id), booking)
        self.assertIn(booking, self.service.booking_report(self.manager))
        self.assertEqual(self.repo.list_notifications(self.student.id), notices)
        self.assertEqual(self.repo.get_principal(self.student.id), person)
        self.assertEqual(len([a for a in self.repo.list_audit() if a.action == 'BOOKING_HISTORY_REMOVED']), 1)
        self.service.remove_booking_history(self.student, booking.id)
        self.assertEqual(my_bookings(self.service, self.student), [])

    def test_all_roles_can_remove_their_own_terminal_history(self):
        source = self.request()
        for actor in (self.student, self.admin, self.manager):
            for status in (BookingStatus.CANCELLED, BookingStatus.REJECTED, BookingStatus.EXPIRED):
                with self.subTest(role=actor.role, status=status):
                    self.repo.save_booking(replace(source, student_id=actor.id, created_by=actor.id, status=status))
                    self.service.remove_booking_history(actor, source.id)
                    self.assertEqual(my_bookings(self.service, actor), [])

    def test_future_and_ongoing_active_bookings_cannot_be_removed(self):
        source = self.approved()
        for status in (BookingStatus.APPROVED, BookingStatus.PENDING_APPROVAL, BookingStatus.WAITLISTED,
                       BookingStatus.WAITING_QUALIFICATION):
            self.repo.save_booking(replace(source, status=status))
            self.refused('BOOKING_NOT_HISTORY', self.service.remove_booking_history, self.student, source.id)
        self.repo.save_booking(source)
        self.now = source.start
        self.refused('BOOKING_NOT_HISTORY', self.service.remove_booking_history, self.student, source.id)
        self.now = source.end
        self.service.remove_booking_history(self.student, source.id)
        self.assertEqual(my_bookings(self.service, self.student), [])

    def test_staff_cannot_remove_unrelated_history_and_failed_audit_rolls_back(self):
        booking = self.service.cancel_booking(self.student, self.request().id)
        for actor in (self.other, self.admin, self.manager):
            self.refused('NOT_FOUND', self.service.remove_booking_history, actor, booking.id)
        with patch.object(self.service, '_audit', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.service.remove_booking_history(self.student, booking.id)
        self.assertEqual([b.id for b in my_bookings(self.service, self.student)], [booking.id])

    def test_completed_no_show_stays_in_usage_and_preserves_account_and_calendar(self):
        booking = self.approved()
        self.now = booking.end + timedelta(minutes=1)
        self.service.process_due_requests()
        before = self.repo.get_booking(booking.id)
        person = self.repo.get_principal(self.student.id)
        feed = self.service.calendar_feed(self.student)
        events = self.service.calendar_feed_events(feed.token)
        self.service.remove_booking_history(self.student, booking.id)
        self.assertEqual(before.attendance, 'NO_SHOW')
        self.assertEqual(self.repo.get_booking(booking.id), before)
        self.assertEqual(self.repo.get_principal(self.student.id), person)
        self.assertEqual(self.service.calendar_feed_events(feed.token), events)
        self.assertIn(before, self.service.booking_report(self.manager))


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, AUTH_PROVIDER='booking.authentication.DemoIdentityProvider',
                   SEED_DEMO_DATA=True, OUTLOOK_ENABLED=False)
class BookingHistoryAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def test_remove_hides_both_personal_endpoints_but_keeps_staff_records(self):
        booking = self.create_approved()
        url = f"/api/v1/bookings/{booking['id']}/remove-from-history/"
        self.assertEqual(self.verified.post(url, {}, format='json').status_code, 409)
        self.assertEqual(self.manager.post(url, {}, format='json').status_code, 404)
        self.verified.post(f"/api/v1/bookings/{booking['id']}/cancel/", {}, format='json')
        self.assertEqual(self.verified.post(url, {'user_id': 'someone'}, format='json').status_code, 400)
        for _ in range(2):
            self.assertEqual(self.verified.post(url, {}, format='json').status_code, 204)
        self.assertEqual(self.items(self.verified.get('/api/v1/bookings/')), [])
        dashboard = self.verified.get('/api/v1/dashboard/').data
        self.assertEqual(dashboard['bookings'], [])
        self.assertEqual(dashboard['counts']['CANCELLED'], 0)
        records = self.items(self.manager.get('/api/v1/admin/bookings/?status=ALL'))
        self.assertIn(booking['id'], [b['id'] for b in records])
        self.assertEqual(self.client.post(url, {}, format='json').status_code, 401)
