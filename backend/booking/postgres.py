
import json
from contextlib import contextmanager
from dataclasses import asdict, fields
from enum import Enum
from uuid import UUID, uuid4

from django.db import connection, transaction
from psycopg.types.json import Jsonb

from .domain import (
    Announcement,  # Sprint 3 (1.19.0)
    AuditRecord, Booking, BookingSeries, BookingStatus, CalendarFeed, Notification, NotificationPreference,
    OutlookSyncRecord, Principal,
    QualificationRequirement, QualificationStatus, QualificationSubmission,
    Resource, ResourceKind, Role, StaffCredential, UnfreezeRequest, UnfreezeStatus,
    SITE_CONTACT_ID, SiteContact,  # Sprint 3 (1.16.0)
)
from .storage import StoredFile


_TABLES = {
    Principal: 'app_users',
    QualificationRequirement: 'qualification_requirement',
    Resource: 'bookable_resource',
    QualificationSubmission: 'qualification_submission',
    Booking: 'booking',
    AuditRecord: 'audit_record',
    OutlookSyncRecord: 'outlook_sync_record',
    StoredFile: 'stored_file',
    StaffCredential: 'staff_credential',
    Notification: 'notification',
    CalendarFeed: 'calendar_feed',
    UnfreezeRequest: 'unfreeze_request',
    BookingSeries: 'booking_series',
    SiteContact: 'site_contact',  # Sprint 3 (1.16.0)
    Announcement: 'announcement',  # Sprint 3 (1.19.0)
    NotificationPreference: 'notification_preference',  # Sprint 3 (2026-10-25)
}
# Sprint 3 (1.16.0): fields kept as JSON (jsonb) lists of objects rather than uuid[] arrays.
_JSON_LISTS = {(Resource, 'details')}
_ENUMS = {
    Principal: {'role': Role},
    Resource: {'kind': ResourceKind},
    QualificationSubmission: {'status': QualificationStatus},
    Booking: {'status': BookingStatus},
    UnfreezeRequest: {'status': UnfreezeStatus},
}
_ORDER = {
    Principal: 'id', Resource: 'id', QualificationRequirement: 'id',
    QualificationSubmission: 'storage_order', Booking: 'created_at, id',
    AuditRecord: 'at, id', OutlookSyncRecord: 'updated_at, booking_id',
    StoredFile: 'id', StaffCredential: 'principal_id',
    Notification: 'created_at DESC, id DESC', CalendarFeed: 'principal_id',
    UnfreezeRequest: 'created_at, id', BookingSeries: 'created_at, id',
    SiteContact: 'id',
    Announcement: 'created_at DESC, id DESC',  # Sprint 3 (1.19.0)
    NotificationPreference: 'category',
}
_KEYS = {OutlookSyncRecord: 'booking_id', StaffCredential: 'principal_id', CalendarFeed: 'principal_id'}
_WRITE_LOCK = 0x534D4152544C4142


def _uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _table(record_type):
    return '"public".' + connection.ops.quote_name(_TABLES[record_type])


def _columns(record_type):
    return tuple(field.name for field in fields(record_type))


def _decode(record_type, row):
    values = dict(zip(_columns(record_type), row, strict=True))
    for key, value in values.items():
        if (record_type, key) in _JSON_LISTS:
            # Sprint 3 (1.16.0): Django returns jsonb as text; the dataclass turns the objects back into records.
            values[key] = json.loads(value) if isinstance(value, str) else value
            continue
        if isinstance(value, UUID):
            values[key] = str(value)
        elif isinstance(value, list):  # uuid[] columns such as prerequisite_ids
            values[key] = tuple(str(item) for item in value)
    for key, enum in _ENUMS.get(record_type, {}).items():
        values[key] = enum(values[key])
    if record_type is AuditRecord and isinstance(values['details'], str):
        values['details'] = json.loads(values['details'])
    if record_type is StoredFile:
        values['data'] = bytes(values['data'])
    return record_type(**values)


def _encode(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if isinstance(value, dict):
        return Jsonb(value)
    return value


@contextmanager
def _atomic(resource_ids=(), student_ids=()):
    if connection.vendor != 'postgresql':
        raise RuntimeError('Configure Django DATABASES with the PostgreSQL backend first.')
    # atomic() uses a real transaction and savepoints when nested; Django keeps
    # default connections thread-local. File writes share this same transaction.
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [_WRITE_LOCK])
            for table, ids in (
                ('bookable_resource', resource_ids),
                ('app_users', student_ids),
            ):
                normalized = set()
                for raw_id in ids:
                    item = _uuid(raw_id)
                    if item is None:
                        raise ValueError('Lock identifiers must be UUIDs.')
                    normalized.add(item)
                for item in sorted(normalized):
                    cursor.execute(
                        f'SELECT id FROM public.{table} WHERE id = %s FOR UPDATE', [item]
                    )
                    cursor.fetchall()
        yield


def _select(record_type, where='', params=()):
    names = ', '.join(connection.ops.quote_name(name) for name in _columns(record_type))
    query = f'SELECT {names} FROM {_table(record_type)}'
    if where:
        query += ' WHERE ' + where
    query += ' ORDER BY ' + _ORDER[record_type]
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return [_decode(record_type, row) for row in cursor.fetchall()]


def _get(record_type, record_id):
    record_id = _uuid(record_id)
    if record_id is None:
        return None
    key = _KEYS.get(record_type, 'id')
    rows = _select(record_type, f'{key} = %s', [record_id])
    return rows[0] if rows else None


def _filtered(record_type, **filters):
    clauses, params = [], []
    for key, value in filters.items():
        if value is not None:
            normalized = _uuid(value)
            if normalized is None:
                return []
            clauses.append(connection.ops.quote_name(key) + ' = %s')
            params.append(normalized)
    return _select(record_type, ' AND '.join(clauses), params)


def _insert(record, upsert=False):
    record_type = type(record)
    names = _columns(record_type)
    quote = connection.ops.quote_name
    columns = ', '.join(quote(name) for name in names)
    placeholders = ', '.join(['%s'] * len(names))
    query = f'INSERT INTO {_table(record_type)} ({columns}) VALUES ({placeholders})'
    if upsert:
        key = _KEYS.get(record_type, 'id')
        assignments = ', '.join(
            f'{quote(name)} = EXCLUDED.{quote(name)}' for name in names if name != key
        )
        query += f' ON CONFLICT ({quote(key)}) DO UPDATE SET {assignments}'
    with _atomic():
        with connection.cursor() as cursor:
            cursor.execute(query, [Jsonb([asdict(item) for item in getattr(record, name)]) if (record_type, name) in _JSON_LISTS
                                   else _encode(getattr(record, name)) for name in names])


class PostgresRepository:
    def atomic(self, resource_ids=(), student_ids=()):
        return _atomic(resource_ids, student_ids)

    def get_resource(self, resource_id):
        return _get(Resource, resource_id)

    def list_resources(self):
        return _select(Resource)

    def save_resource(self, resource):
        _insert(resource, upsert=True)

    def get_principal(self, principal_id):
        return _get(Principal, principal_id)

    def list_principals(self):
        return _select(Principal)

    def save_principal(self, principal):
        _insert(principal, upsert=True)

    def get_requirement(self, requirement_id):
        return _get(QualificationRequirement, requirement_id)

    def list_requirements(self):
        return _select(QualificationRequirement)

    def save_requirement(self, requirement):
        _insert(requirement, upsert=True)

    def get_submission(self, submission_id):
        return _get(QualificationSubmission, submission_id)

    def list_submissions(self, student_id=None, requirement_id=None):
        return _filtered(QualificationSubmission, student_id=student_id, requirement_id=requirement_id)

    def save_submission(self, submission):
        _insert(submission, upsert=True)

    def get_booking(self, booking_id):
        return _get(Booking, booking_id)

    def list_bookings(self, student_id=None, resource_id=None, *, statuses=None, start_from=None, start_to=None,
                      end_from=None, due_by=None, created_by=None, unmarked=False):
        """2026-10-29 (load test R1): the same keyword filters as repository.booking_matches, applied in SQL so only
        the rows a caller may need are read and decoded."""
        clauses, params = [], []
        for column, value in (('student_id', student_id), ('resource_id', resource_id), ('created_by', created_by)):
            if value is not None:
                if (normalized := _uuid(value)) is None:
                    return []
                clauses.append(f'{column} = %s')
                params.append(normalized)
        if statuses is not None:
            clauses.append('status = ANY(%s)')
            params.append([_encode(status) for status in statuses])
        for condition, value in (('"start" >= %s', start_from), ('"start" <= %s', start_to),
                                 ('"end" >= %s', end_from)):
            if value is not None:
                clauses.append(condition)
                params.append(value)
        if due_by is not None:
            clauses.append('("start" <= %s OR review_due_at <= %s)')
            params += [due_by, due_by]
        if unmarked:
            clauses.append('attendance IS NULL')
        return _select(Booking, ' AND '.join(clauses), params)

    def save_booking(self, booking):
        _insert(booking, upsert=True)

    # Sprint 3 (1.20.0): personal history visibility survives sessions and adapter instances.
    def hidden_booking_ids(self, principal_id):
        with connection.cursor() as cursor:
            cursor.execute('SELECT booking_id FROM public.booking_history_removal WHERE principal_id = %s',
                           [principal_id])
            return {str(row[0]) for row in cursor.fetchall()}

    def hide_booking(self, principal_id, booking_id, at):
        with connection.cursor() as cursor:
            cursor.execute('''INSERT INTO public.booking_history_removal(principal_id, booking_id, removed_at)
                              VALUES (%s, %s, %s) ON CONFLICT (principal_id, booking_id) DO NOTHING''',
                           [principal_id, booking_id, at])

    def list_blocking_bookings(self, resource_id, start, end, at, exclude_id=None):
        resource_id = _uuid(resource_id)
        if resource_id is None:
            return []
        where = '''resource_id = %s AND "start" < %s AND "end" > %s
            AND (status = 'APPROVED' OR
                 (status IN ('WAITING_QUALIFICATION', 'PENDING_APPROVAL') AND hold_until > %s))'''
        params = [resource_id, end, start, at]
        if exclude_id is not None and (normalized := _uuid(exclude_id)) is not None:
            where += ' AND id <> %s'
            params.append(normalized)
        return _select(Booking, where, params)

    def append_audit(self, record):
        # Never UPSERT or UPDATE an audit entry.
        _insert(record)

    def list_audit(self):
        return _select(AuditRecord)

    def get_outlook_sync(self, booking_id):
        return _get(OutlookSyncRecord, booking_id)

    def list_outlook_sync(self):
        return _select(OutlookSyncRecord)

    def save_outlook_sync(self, record):
        _insert(record, upsert=True)

    def get_credential(self, principal_id):
        return _get(StaffCredential, principal_id)

    def save_credential(self, credential):
        _insert(credential, upsert=True)

    # Sprint 3 records ------------------------------------------------------------------------------------

    def save_notification(self, notification):
        _insert(notification, upsert=True)

    def get_notification(self, notification_id):
        return _get(Notification, notification_id)

    def list_notifications(self, recipient_id):
        return _filtered(Notification, recipient_id=recipient_id)

    def list_booking_notifications(self, kind, booking_ids):
        # 2026-10-29 (load test S1): one query for reminder de-duplication instead of one per booking.
        ids = [normalized for item in booking_ids if (normalized := _uuid(item)) is not None]
        if not ids:
            return []
        return _select(Notification, 'kind = %s AND booking_id = ANY(%s::uuid[])', [kind, ids])

    # Sprint 3 (2026-10-25): notification category choices.
    def save_notification_preference(self, preference):
        _insert(preference, upsert=True)

    def list_notification_preferences(self, principal_id):
        return _filtered(NotificationPreference, principal_id=principal_id)

    # Sprint 3 (1.19.0): same record contract as the memory adapter.
    def save_announcement(self, announcement):
        _insert(announcement, upsert=True)

    def get_announcement(self, announcement_id):
        return _get(Announcement, announcement_id)

    def list_announcements(self):
        return _filtered(Announcement)

    def get_calendar_feed(self, principal_id):
        return _get(CalendarFeed, principal_id)

    def get_calendar_feed_by_token(self, token):
        if not isinstance(token, str) or not token:
            return None
        rows = _select(CalendarFeed, 'token = %s', [token])
        return rows[0] if rows else None

    def save_calendar_feed(self, feed):
        _insert(feed, upsert=True)

    def save_unfreeze_request(self, request):
        _insert(request, upsert=True)

    def get_unfreeze_request(self, request_id):
        return _get(UnfreezeRequest, request_id)

    def list_unfreeze_requests(self, principal_id=None):
        return _filtered(UnfreezeRequest, principal_id=principal_id)

    def save_series(self, series):
        _insert(series, upsert=True)

    def get_series(self, series_id):
        return _get(BookingSeries, series_id)

    # Sprint 3 (1.16.0)
    def get_site_contact(self):
        return _get(SiteContact, SITE_CONTACT_ID)

    def save_site_contact(self, contact):
        _insert(contact, upsert=True)


class PostgresFileStorage:
    def save(self, data, original_name, content_type, owner_id):
        content = bytes(data)
        record = StoredFile(str(uuid4()), original_name, content_type, len(content), str(owner_id), content)
        _insert(record)
        return record

    def get(self, file_id):
        return _get(StoredFile, file_id)

    def delete(self, file_id):
        normalized = _uuid(file_id)
        if normalized is None:
            return
        # Missing files are harmless, including cleanup after a rolled-back upload.
        # The existing FK protects files still referenced by evidence submissions.
        with _atomic():
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM public.stored_file WHERE id = %s', [normalized])
