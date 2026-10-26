"""Sprint 3 (1.19.0): shared Memory/PostgreSQL acceptance cases and HTTP permissions."""
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from booking.domain import Principal, QualificationRequirement, Resource, ResourceKind, Role
from booking.errors import DomainError
from booking.notification_channels import deliver_new_notifications
from booking.repository import MemoryRepository
from booking.services import BookingService
from booking.storage import MemoryFileStorage
from booking.tests.test_api import BookingAPIFixtureMixin


class Acceptance119:
    """The same service contract is exercised against both actual repository adapters."""
    def setup_119(self, repo, storage):
        self.repo = repo
        self.now = datetime(2030, 1, 7, tzinfo=UTC)
        self.service = BookingService(repo, storage, clock=lambda: self.now)
        self.student, self.admin, self.manager, self.other_admin = [
            Principal(str(uuid4()), f'z{uuid4().int % 10000000:07d}', name, role, 'test@example.test')
            for name, role in [('Student', Role.STUDENT), ('Admin', Role.ADMIN),
                               ('Manager', Role.MANAGER), ('Other admin', Role.ADMIN)]
        ]
        for person in [self.student, self.admin, self.manager, self.other_admin]:
            repo.save_principal(person)
        requirement = QualificationRequirement(str(uuid4()), 'Training', '')
        repo.save_requirement(requirement)
        self.room = Resource(str(uuid4()), 'Lab Room 1', ResourceKind.ROOM, 'Lab', '',
                             required_qualification_id=requirement.id, opening_time=time(8), closing_time=time(20))
        repo.save_resource(self.room)
        self.service.take_new_notification_ids()

    def denied(self, fn, *args, **kwargs):
        with self.assertRaises(DomainError) as error:
            fn(*args, **kwargs)
        self.assertEqual(error.exception.status, 403)

    def test_channel_combinations_are_independent_and_hidden_records_stay_hidden(self):
        for in_app, email in [(True, True), (True, False), (False, True), (False, False)]:
            with self.subTest(in_app=in_app, email=email):
                self.service.save_notification_preferences(self.student, {'bookings': {'in_app': in_app, 'email': email}})
                notice = self.service._notify(self.student.id, 'BOOKING_SUBMITTED', 'Request received', 'Details')
                channel = Mock()
                with patch('booking.notification_channels.configured_channels', return_value=[channel]):
                    deliver_new_notifications(self.service)
                self.assertEqual(channel.deliver.call_count, int(email))
                visible, unread = self.service.list_notifications(self.student)
                self.assertEqual(bool(notice and notice.id in [item.id for item in visible]), in_app)
                if notice:
                    self.assertEqual((notice.in_app, notice.email), (in_app, email))
                else:
                    self.assertFalse(in_app or email)
        self.service.save_notification_preferences(self.student, {'bookings': {'in_app': True}})
        visible, unread = self.service.list_notifications(self.student)
        self.assertEqual(len(visible), 2)
        self.assertEqual(unread, 2)
        hidden = next(item for item in self.repo.list_notifications(self.student.id) if not item.in_app)
        with self.assertRaises(DomainError):
            self.service.mark_notification_read(self.student, hidden.id)
        self.service.mark_all_notifications_read(self.student)
        self.assertIsNone(self.repo.get_notification(hidden.id).read_at)

    def test_partial_preferences_defaults_isolation_and_urgent_notice(self):
        self.service.save_notification_preferences(self.student, {'bookings': {'in_app': False}})
        saved = self.service.notification_preferences(self.student)
        self.assertEqual(saved[0], {'category': 'bookings', 'in_app': False, 'email': True})
        self.service.save_notification_preferences(self.student, {'bookings': {'email': False}})
        self.assertFalse(self.service.notification_preferences(self.student)[0]['in_app'])
        self.assertTrue(all(item['in_app'] and item['email'] for item in self.service.notification_preferences(self.admin)))
        self.service.save_notification_preferences(self.manager, {cat: {'in_app': False, 'email': False}
                                                                 for cat in ['bookings', 'reminders', 'induction', 'account', 'resources']})
        notice = self.service._notify(self.manager.id, 'URGENT_REQUEST', 'Urgent request', 'Review')
        self.assertTrue(notice.in_app and notice.email)

    def test_announcements_expiry_order_history_and_no_notifications(self):
        first = self.service.create_announcement(self.admin, 'First', 'Body')
        self.now += timedelta(seconds=1)
        second = self.service.create_announcement(self.manager, 'Second', 'Message', self.now + timedelta(hours=1))
        self.assertEqual([item.id for item in self.service.list_announcements(self.student)], [second.id, first.id])
        self.assertEqual(self.repo.get_announcement(first.id).created_by, self.admin.id)
        self.assertEqual(self.repo.list_notifications(self.student.id), [])
        self.assertEqual(self.service.take_new_notification_ids(), [])
        self.now += timedelta(hours=2)
        self.assertEqual([item.id for item in self.service.list_announcements(self.student)], [first.id])
        self.service.remove_announcement(self.manager, first.id)
        self.assertEqual(self.service.list_announcements(self.student), [])
        self.assertGreaterEqual(len(self.service.list_announcements(self.admin, include_ended=True)), 2)
        self.denied(self.service.list_announcements, self.student, include_ended=True)

    def test_removal_time_must_be_in_the_future(self):
        # Review 1.19.0 R1: a past "Remove at" used to publish an announcement that no home page showed.
        for when in [self.now, self.now - timedelta(minutes=1)]:
            with self.subTest(when=when):
                with self.assertRaises(DomainError) as error:
                    self.service.create_announcement(self.admin, 'Notice', 'Details', when)
                self.assertEqual(error.exception.code, 'VALIDATION_ERROR')
        self.assertEqual(self.repo.list_announcements(), [])
        item = self.service.create_announcement(self.admin, 'Notice', 'Details', self.now + timedelta(hours=1))
        with self.assertRaises(DomainError):
            self.service.update_announcement(self.admin, item.id, {'expires_at': self.now - timedelta(minutes=1)})
        self.assertEqual(self.repo.get_announcement(item.id).expires_at, self.now + timedelta(hours=1))
        self.assertIsNone(self.service.update_announcement(self.admin, item.id, {'expires_at': None}).expires_at)

    def test_manual_announcement_ownership_matrix_and_audit(self):
        for author in [self.admin, self.manager, self.other_admin]:
            for actor in [self.student, self.admin, self.manager, self.other_admin]:
                with self.subTest(author=author.display_name, actor=actor.display_name):
                    item = self.service.create_announcement(author, 'Notice', 'Details')
                    if actor.id == author.id:
                        self.assertEqual(self.service.update_announcement(actor, item.id, {'title': 'Updated'}).title, 'Updated')
                    else:
                        self.denied(self.service.update_announcement, actor, item.id, {'body': 'Changed'})
                    if actor.id == author.id or actor.role == Role.MANAGER:
                        self.assertIsNotNone(self.service.remove_announcement(actor, item.id).removed_at)
                    else:
                        self.denied(self.service.remove_announcement, actor, item.id)
        self.denied(self.service.create_announcement, self.student, 'Title', 'Body')
        self.assertTrue({'ANNOUNCEMENT_CREATED', 'ANNOUNCEMENT_UPDATED', 'ANNOUNCEMENT_REMOVED'} <=
                        {item.action for item in self.repo.list_audit()})

    def test_status_announcement_upsert_expected_back_reopen_and_equipment(self):
        back = self.now + timedelta(hours=2)
        for resource in [self.room, replace(self.room, id=str(uuid4()), name='Microscope', kind=ResourceKind.EQUIPMENT)]:
            self.repo.save_resource(resource)
            self.denied(self.service.set_resource_status, self.admin, resource.id, 'MAINTENANCE', 'Repair')
            self.service.set_resource_status(self.manager, resource.id, 'MAINTENANCE', 'Repair', expected_back=back)
            notice = next(item for item in self.service.list_announcements(self.student) if item.resource_id == resource.id)
            self.assertEqual((notice.kind, notice.expected_back, notice.author_role), ('RESOURCE_STATUS', back, 'MANAGER'))
            self.service.set_resource_status(self.manager, resource.id, 'MAINTENANCE', 'Repair continues', expected_back=back)
            changed = next(item for item in self.service.list_announcements(self.student) if item.resource_id == resource.id)
            self.assertEqual((changed.id, changed.body), (notice.id, 'Repair continues'))
            self.service.set_resource_status(self.manager, resource.id, 'CLOSED', 'New reason', expected_back=back)
            current = next(item for item in self.service.list_announcements(self.student) if item.resource_id == resource.id)
            self.assertEqual(current.id, notice.id)
            self.assertEqual(current.body, 'New reason')
            self.assertEqual(current.title, f'{resource.name} is closed')
            self.denied(self.service.update_announcement, self.manager, current.id, {'title': 'Forged'})
            self.denied(self.service.remove_announcement, self.manager, current.id)
            self.now = back + timedelta(hours=1)
            self.assertIn(current.id, [item.id for item in self.service.list_announcements(self.student)])
            self.service.set_resource_status(self.manager, resource.id, 'AVAILABLE')
            self.assertNotIn(current.id, [item.id for item in self.service.list_announcements(self.student)])

    def test_status_and_announcement_roll_back_together(self):
        original = self.repo.save_announcement
        def fail_after_write(record):
            original(record)
            raise DomainError('TEST_FAILURE', 'Rollback')
        with patch.object(self.repo, 'save_announcement', side_effect=fail_after_write):
            with self.assertRaises(DomainError):
                self.service.set_resource_status(self.manager, self.room.id, 'CLOSED', 'Repair')
        self.assertEqual(self.repo.get_resource(self.room.id).status.value, 'AVAILABLE')
        self.assertFalse([item for item in self.repo.list_announcements() if item.resource_id == self.room.id])


class Memory119Tests(Acceptance119, SimpleTestCase):
    def setUp(self):
        self.setup_119(MemoryRepository(), MemoryFileStorage())


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class API119Tests(BookingAPIFixtureMixin, SimpleTestCase):
    def test_preferences_contract_email_availability_and_partial_save(self):
        with self.settings(EMAIL_ENABLED=False):
            response = self.student.get('/api/v1/notifications/preferences/')
            self.assertFalse(response.data['email_available'])
        with self.settings(EMAIL_ENABLED=True):
            self.assertTrue(self.student.get('/api/v1/notifications/preferences/').data['email_available'])
        response = self.student.put('/api/v1/notifications/preferences/', {'preferences': {'bookings': {'in_app': False}}}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['results'][0], {'category': 'bookings', 'in_app': False, 'email': True})
        invalid = self.student.put('/api/v1/notifications/preferences/', {'preferences': {'bookings': {'email': False}, 'bad': {'email': True}}}, format='json')
        self.assertEqual(invalid.status_code, 400)
        self.assertTrue(self.student.get('/api/v1/notifications/preferences/').data['results'][0]['email'])

    def test_write_permissions_reserved_kind_and_creator_signature(self):
        created = self.admin.post('/api/v1/announcements/', {'title': 'Notice', 'body': 'Details'}, format='json')
        self.assertEqual(created.status_code, 201)
        announcement_id = created.data['id']
        self.assertEqual(created.data['author']['role'], 'ADMIN')
        self.assertIn('display_name', created.data['author'])
        for method, path, body in [('post', '/api/v1/announcements/', {'title': 'x', 'body': 'x'}),
                                   ('patch', f'/api/v1/announcements/{announcement_id}/', {'title': 'x'}),
                                   ('post', f'/api/v1/announcements/{announcement_id}/remove/', {})]:
            self.assertEqual(getattr(self.student, method)(path, body, format='json').status_code, 403)
            self.assertEqual(getattr(self.student, method)(path, {'kind': 'RESOURCE_STATUS'}, format='json').status_code, 403)
        for staff in [self.admin, self.manager]:
            self.assertEqual(staff.post('/api/v1/announcements/', {'title': 'x', 'body': 'x', 'kind': 'RESOURCE_STATUS'}, format='json').status_code, 400)
            self.assertEqual(staff.patch(f'/api/v1/announcements/{announcement_id}/', {'kind': 'RESOURCE_STATUS'}, format='json').status_code, 400)
        manager_notice = self.manager.post('/api/v1/announcements/', {'title': 'Manager notice', 'body': 'Details'}, format='json')
        self.assertEqual(manager_notice.status_code, 201)
        manager_path = f"/api/v1/announcements/{manager_notice.data['id']}/"
        self.assertEqual(self.admin.patch(manager_path, {'title': 'Changed'}, format='json').status_code, 403)
        self.assertEqual(self.admin.post(manager_path + 'remove/', {}, format='json').status_code, 403)
        self.assertEqual(self.manager.patch(f'/api/v1/announcements/{announcement_id}/', {'title': 'Changed'}, format='json').status_code, 403)
        self.assertEqual(self.manager.post(f'/api/v1/announcements/{announcement_id}/remove/', {}, format='json').status_code, 200)
        self.assertEqual(self.student.get('/api/v1/announcements/?include_ended=true').status_code, 403)
        self.assertEqual(self.student.get('/api/v1/announcements/').status_code, 200)
