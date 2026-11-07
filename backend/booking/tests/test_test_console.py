"""Sprint 3 (1.17.0): the opt-in test console is a signed session, not an editable user role or a request flag."""
from dataclasses import replace
from datetime import timedelta

from django.core import signing
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from booking.domain import BookingStatus, ResourceStatus, Role
from booking.tests.test_api import BookingAPIFixtureMixin, NOW
from booking.test_console import TEST_ACCOUNT_ID


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, ENABLE_TEST_CONSOLE=True, SEED_DEMO_DATA=True)
class TestConsoleAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.service.min_advance_days, self.service.max_advance_days = 7, 30
        self.result = self.client.post('/api/v1/auth/test-login/', {'login_id': '1'}, format='json')
        self.assertEqual(self.result.status_code, 200, self.result.data)
        self.tester = self.authorized(self.result.data['access_token'])

    def authorized(self, token):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return client

    def switch(self, role='STUDENT', bypass=True):
        response = self.tester.post('/api/v1/auth/test-session/',
                                    {'role': role, 'bypass_booking_rules': bypass}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return self.authorized(response.data['access_token'])

    def test_switches_roles_without_changing_the_stored_role_or_another_session(self):
        for role, path in [('ADMIN', '/api/v1/admin/bookings/'), ('MANAGER', '/api/v1/admin/users/'),
                           ('STUDENT', '/api/v1/dashboard/')]:
            session = self.switch(role)
            me = session.get('/api/v1/auth/me/')
            self.assertEqual((me.data['zid'], me.data['role'], me.data['test_account']), ('1', role, True))
            self.assertEqual(session.get(path).status_code, 200)
        self.assertEqual(self.tester.get('/api/v1/auth/me/').data['role'], 'STUDENT')
        self.assertEqual(self.service.repo.get_principal(TEST_ACCOUNT_ID).role, Role.STUDENT)
        self.assertEqual(self.tester.get('/api/v1/admin/users/').status_code, 403)

    def test_bypasses_training_windows_duration_opening_hours_freeze_and_weekly_limit(self):
        base = self.service.repo.get_principal(TEST_ACCOUNT_ID)
        self.service.repo.save_principal(replace(base, frozen_until=NOW + timedelta(days=365)))
        self.service._override_rule(max_slots_per_week=1)
        for offset, hour, minutes in [(1, 1, 540), (2, 2, 60), (3, 3, 60), (60, 4, 60)]:
            result = self.tester.post('/api/v1/bookings/', self.payload(day_offset=offset, hour=hour, minutes=minutes), format='json')
            self.assertEqual(result.status_code, 201, result.data)
            self.assertEqual(result.data['status'], 'APPROVED')
            self.assertEqual(result.data['reason_code'], 'TEST_OVERRIDE')
            self.assertEqual(result.data['attendance'], 'NOT_TRACKED')
            self.assertIsNone(result.data['review_due_at'])
        self.assertFalse(self.tester.get('/api/v1/auth/me/').data['booking_frozen'])
        self.assertIn('TEST_BOOKING_CREATED', [item.action for item in self.service.repo.list_audit()])

    def test_bypass_off_keeps_inductions_but_restores_windows_and_approval(self):
        normal = self.switch(bypass=False)
        availability = normal.get(f"/api/v1/resources/{self.room['id']}/availability/", {'date': '2026-10-06'})
        self.assertTrue(availability.data['can_request'])
        self.assertEqual(availability.data['qualification_status'], 'VERIFIED')
        self.assertFalse(availability.data.get('test_bypass', False))
        result = normal.post('/api/v1/bookings/', self.payload(day_offset=1), format='json')
        self.assertEqual(result.status_code, 400, result.data)
        result = normal.post('/api/v1/bookings/', self.payload(day_offset=8), format='json')
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data['status'], 'PENDING_APPROVAL')

    def test_all_inductions_are_permanent_fileless_and_survive_role_switches(self):
        required = {item.id for item in self.service.repo.list_requirements()}
        for role in ['STUDENT', 'ADMIN', 'MANAGER']:
            client = self.switch(role, bypass=False)
            records = client.get('/api/v1/qualifications/').data['results']
            self.assertEqual({item['requirement_id'] for item in records}, required)
            self.assertTrue(all(item['effective_status'] == 'VERIFIED' and item['valid_until'] is None
                                and item['file_url'] == '' for item in records))
            dashboard = client.get('/api/v1/dashboard/')
            self.assertEqual(len(dashboard.data['qualifications']), len(required))
            self.assertTrue(all(item['effective_status'] == 'VERIFIED' for item in dashboard.data['qualifications']))
        for resource in self.service.repo.list_resources():
            self.assertEqual(self.service.qualification_state(TEST_ACCOUNT_ID, resource,
                             NOW + timedelta(days=3650)), ('VERIFIED', True))
        self.assertFalse(self.student.get('/api/v1/qualifications/').data['results'])

    def test_existing_session_receives_new_requirements_without_duplicate_grants(self):
        manager = self.service.repo.get_principal('00000000-0000-0000-0000-000000000902')
        requirement = self.service.create_requirement(manager, {'name': 'New specialist induction'})
        response = self.tester.get('/api/v1/qualifications/')
        record = next(item for item in response.data['results'] if item['requirement_id'] == requirement.id)
        self.assertEqual(record['effective_status'], 'VERIFIED')
        self.assertIsNone(record['valid_until'])
        count = len(self.service.repo.list_submissions(student_id=TEST_ACCOUNT_ID))
        audit_count = len(self.service.repo.list_audit())
        for _ in range(3):
            self.assertEqual(self.tester.get('/api/v1/dashboard/').status_code, 200)
        self.assertEqual(len(self.service.repo.list_submissions(student_id=TEST_ACCOUNT_ID)), count)
        self.assertEqual(len(self.service.repo.list_audit()), audit_count)

    def test_conflicts_and_duplicates_are_not_overridden_and_retries_are_idempotent(self):
        data = self.payload(day_offset=8)
        first = self.tester.post('/api/v1/bookings/', data, format='json', HTTP_IDEMPOTENCY_KEY='test-once')
        retry = self.tester.post('/api/v1/bookings/', data, format='json', HTTP_IDEMPOTENCY_KEY='test-once')
        self.assertEqual((first.status_code, retry.status_code), (201, 200))
        self.assertEqual(first.data['id'], retry.data['id'])
        duplicate = self.tester.post('/api/v1/bookings/', data, format='json')
        self.assertEqual(duplicate.status_code, 409)
        held = self.verified.post('/api/v1/bookings/', self.payload(day_offset=9), format='json')
        self.assertEqual(held.status_code, 201, held.data)
        conflict = self.tester.post('/api/v1/bookings/', self.payload(day_offset=9), format='json')
        self.assertEqual(conflict.status_code, 409, conflict.data)
        self.assertEqual(conflict.data['error']['code'], 'BOOKING_CONFLICT')
        self.assertEqual(self.service.repo.get_booking(held.data['id']).status, BookingStatus.PENDING_APPROVAL)

    def test_urgent_shared_description_is_saved_and_directly_approved(self):
        data = {**self.payload(day_offset=1), 'purpose': 'Rerun the experiment before tomorrow’s deadline.',
                'urgent': True, 'urgent_reason': 'Rerun the experiment before tomorrow’s deadline.'}
        response = self.tester.post('/api/v1/bookings/', data, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], 'APPROVED')
        self.assertEqual(response.data['purpose'], response.data['urgent_reason'])

    def test_availability_and_day_overview_use_the_same_test_policy(self):
        self.service.set_resource_status(self.service.repo.get_principal('00000000-0000-0000-0000-000000000902'),
                                         self.room['id'], ResourceStatus.MAINTENANCE, 'Testing')
        response = self.tester.get(f"/api/v1/resources/{self.room['id']}/availability/",
                                   {'date': '2026-12-05', 'duration_minutes': 540})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['can_request'])
        self.assertTrue(response.data['test_bypass'])
        self.assertIsNone(response.data['latest_date'])
        self.assertEqual(response.data['review_window_minutes'], 0)
        overview = self.tester.get('/api/v1/resources/day-overview/',
                                   {'date': '2026-12-05', 'duration_minutes': 540, 'bookable_only': 'true'})
        self.assertEqual(overview.status_code, 200, overview.data)
        self.assertTrue(overview.data['test_bypass'])
        self.assertGreater(overview.data['count'], 0)

    def test_invalid_dates_are_still_rejected(self):
        data = self.payload(day_offset=1)
        data['end'] = data['start']
        self.assertEqual(self.tester.post('/api/v1/bookings/', data, format='json').status_code, 400)
        self.assertEqual(self.tester.post('/api/v1/bookings/', self.payload(day_offset=-1), format='json').status_code, 400)

    def test_ordinary_accounts_cannot_switch_roles_or_submit_override_fields(self):
        result = self.student.post('/api/v1/auth/test-session/', {'role': 'MANAGER', 'bypass_booking_rules': True}, format='json')
        self.assertEqual(result.status_code, 403)
        result = self.student.post('/api/v1/bookings/', {**self.payload(day_offset=8), 'bypass_booking_rules': True}, format='json')
        self.assertEqual(result.status_code, 400)
        result = self.student.post('/api/v1/bookings/', self.payload(day_offset=8), format='json')
        self.assertEqual(result.status_code, 403)
        self.assertEqual(result.data['error']['code'], 'QUALIFICATION_REQUIRED')
        for invalid in ['2', 'z1000001', '']:
            self.assertEqual(self.client.post('/api/v1/auth/test-login/', {'login_id': invalid}, format='json').status_code, 400)

    def test_disabling_any_required_gate_hides_login_and_invalidates_existing_test_sessions(self):
        for override in [{'ENABLE_TEST_CONSOLE': False}, {'DEBUG': False}, {'ENABLE_DEMO_AUTH': False},
                         {'AUTH_PROVIDER': 'booking.authentication.DisabledIdentityProvider'},
                         {'REPOSITORY_FACTORY': 'booking.postgres.PostgresRepository'}]:  # memory mode only
            with self.settings(**override):
                self.assertFalse(self.client.get('/api/v1/auth/config/').data['test_console_enabled'])
                self.assertEqual(self.client.post('/api/v1/auth/test-login/', {'login_id': '1'}, format='json').status_code, 404)
                self.assertEqual(self.tester.get('/api/v1/auth/me/').status_code, 401)

    def test_a_normal_signed_token_cannot_grant_access_to_the_reserved_account(self):
        token = signing.dumps({'sub': TEST_ACCOUNT_ID}, salt='smartlab.demo.auth')
        self.assertEqual(self.authorized(token).get('/api/v1/auth/me/').status_code, 401)
        tampered = self.result.data['access_token'] + 'changed'
        self.assertEqual(self.authorized(tampered).get('/api/v1/auth/me/').status_code, 401)

    def test_test_override_does_not_extend_to_bookings_for_someone_else(self):
        # An Admin: since 2026-11-06 a Manager overrides the rules for anyone (Manager override, not the test one).
        admin = self.switch('ADMIN')
        response = admin.post('/api/v1/bookings/', {**self.payload(day_offset=8), 'on_behalf_of_zid': 'z1000002'}, format='json')
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(response.data['error']['code'], 'QUALIFICATION_REQUIRED')

    def test_staff_series_bypass_is_self_only_and_preserves_conflicts(self):
        from booking.tests.test_api import SYDNEY
        first = (NOW.astimezone(SYDNEY) + timedelta(days=1)).date()
        body = {'resource_id': self.room['id'], 'weekdays': [first.isoweekday()], 'start_time': '01:00',
                'duration_minutes': 540, 'first_date': first.isoformat(),
                'last_date': (first + timedelta(weeks=20)).isoformat(), 'purpose': 'Test weekly series'}
        manager = self.switch('MANAGER')
        created = manager.post('/api/v1/bookings/series/', body, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(len(created.data['bookings']), 21)
        self.assertTrue(all(item['status'] == 'APPROVED' and item['attendance'] == 'NOT_TRACKED'
                            for item in created.data['bookings']))
        duplicate = manager.post('/api/v1/bookings/series/', body, format='json')
        self.assertEqual(duplicate.status_code, 409, duplicate.data)
        other = manager.post('/api/v1/bookings/series/preview/',
                             {**{key: value for key, value in body.items() if key != 'purpose'},
                              'on_behalf_of_zid': 'z1000002'}, format='json')
        self.assertEqual(other.status_code, 400, other.data)
        self.assertEqual(other.data['error']['code'], 'SERIES_TOO_LONG')

    def test_manager_can_move_own_test_booking_without_changing_conflict_protection(self):
        manager = self.switch('MANAGER')
        first = manager.post('/api/v1/bookings/', self.payload(day_offset=1), format='json')
        self.assertEqual(first.status_code, 201, first.data)
        path = f"/api/v1/bookings/{first.data['id']}/reschedule/"
        period = self.payload(day_offset=60, hour=1, minutes=540)
        moved = manager.post(path, {key: period[key] for key in ('start', 'end')}, format='json')
        self.assertEqual(moved.status_code, 200, moved.data)
        second = manager.post('/api/v1/bookings/', self.payload(day_offset=61), format='json')
        occupied = self.payload(day_offset=61)
        conflict = manager.post(path, {key: occupied[key] for key in ('start', 'end')}, format='json')
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(conflict.status_code, 409, conflict.data)

    def test_test_bookings_keep_website_notifications_without_external_delivery(self):
        from unittest.mock import Mock, patch
        from booking.notification_channels import deliver_new_notifications
        self.service.take_new_notification_ids()
        response = self.tester.post('/api/v1/bookings/', self.payload(day_offset=1), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(self.service.repo.list_notifications(TEST_ACCOUNT_ID))
        channel = Mock()
        with patch('booking.notification_channels.configured_channels', return_value=[channel]):
            self.service._notify(TEST_ACCOUNT_ID, 'TEST', 'Test notice', 'Do not deliver externally.')
            self.assertEqual(deliver_new_notifications(self.service), 0)
            channel.deliver.assert_not_called()
        self.assertFalse(self.service.repo.list_outlook_sync())

    def test_own_time_change_is_approved_and_releases_only_the_original_booking(self):
        first = self.tester.post('/api/v1/bookings/', self.payload(day_offset=1), format='json')
        self.assertEqual(first.status_code, 201, first.data)
        period = self.payload(day_offset=60, hour=1, minutes=540)
        response = self.tester.post(f"/api/v1/bookings/{first.data['id']}/change/",
                                    {key: period[key] for key in ('start', 'end')}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], 'APPROVED')
        self.assertEqual(response.data['replaces_id'], first.data['id'])
        self.assertEqual(self.service.repo.get_booking(first.data['id']).status, BookingStatus.CANCELLED)
