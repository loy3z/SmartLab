import csv
import io
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, time
from enum import Enum
from uuid import uuid4
from zoneinfo import ZoneInfo
from django.conf import settings
from django.http import FileResponse, HttpResponse
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from ..authentication import issue_demo_token, require_demo_mode
from ..domain import Booking, BookingStatus, Principal, QualificationStatus, ResourceKind, Role
from ..exceptions import DomainError
from ..runtime import get_service
from ..serializers import (AvailabilityQuerySerializer, DayOverviewQuerySerializer, BookingCreateSerializer, BookingRescheduleSerializer, BookingReviewSerializer,
                          DemoLoginSerializer, DemoRegisterSerializer, StaffActivateSerializer, StaffSignInSerializer, QualificationCreateSerializer, QualificationReviewSerializer,
                          OutlookProcessSerializer, BookingPolicySerializer, AuditQuerySerializer,
                          UserListQuerySerializer, UserUpdateSerializer, ManagerCreateSerializer, ResourceStatusSerializer,
                          AdminBookingQuerySerializer, StaffCreateSerializer, PrerequisiteSerializer,
                          PersonLookupSerializer, NotificationQuerySerializer, UnfreezeRequestSerializer,
                          UnfreezeReviewSerializer, UnfreezeListQuerySerializer, UnfreezeSerializer,
                          SeriesPlanSerializer, SeriesCreateSerializer, ResourceFieldsSerializer,
                          ResourceCreateSerializer, UsageReportQuerySerializer, ChangePasswordSerializer,
                          RequirementFieldsSerializer, RequirementUpdateSerializer, SiteContactSerializer)  # Sprint 3 (1.16.0)
from ..ics import render_calendar
from ..test_console import (TestPrincipal, get_test_account, require_test_console,
                           test_console_enabled, test_identity, TEST_ACCOUNT_ID, booking_rules_bypassed)
from ..serializers import TestLoginSerializer, TestSessionSerializer, AdditionalHoursCreateSerializer, LongBookingCreateSerializer
from ..services.base import UNDECIDED_STATUSES  # 2026-10-29 (load test S2)

_UNSET = object()

def json_value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, (time, date)):
        return value.isoformat()
    if isinstance(value, Booking):
        return booking_json(value)
    if is_dataclass(value):
        result = json_value(asdict(value))
        if isinstance(value, Principal):  # Sprint 3: booking freeze
            result["booking_frozen"] = value.frozen_at(get_service().now()) and not booking_rules_bypassed(value)
        return result
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value

def person_brief(service, principal_id, person=_UNSET):
    if person is _UNSET:
        person = service.repo.get_principal(str(principal_id))
    return ({"id": person.id, "zid": person.zid, "display_name": person.display_name, "role": person.role.value}
            if person else None)

def booking_json(value, lookups=None):
    """A booking plus what the pages show with it. lookups: a BookingListLookups for long staff lists, otherwise
    everything is looked up one query at a time (2026-10-29, load test S2: the output is the same either way)."""
    service = get_service()
    lookups = lookups or _SingleLookups(service)
    result = json_value(asdict(value))
    result["outlook_sync"] = lookups.outlook(value)
    result["hold_active"] = value.hold_is_active(service.now())
    result["blocks_slot"] = value.blocks_resource_at(service.now())
    result["waitlist_position"] = lookups.waitlist_position(value)
    # Who the booking is for and who created it (staff may book on behalf of someone).
    result["booked_for"] = person_brief(service, value.student_id, lookups.person(value.student_id))
    result["created_by_user"] = person_brief(service, value.created_by, lookups.person(value.created_by)) if value.created_by else None
    result["on_behalf"] = bool(value.created_by and value.created_by != value.student_id)
    result["additional_hours_review"] = json_value(lookups.additional_hours_review(value)) if value.additional_hours else None
    result.update(json_value(service.check_in_state(value)))  # Sprint 3: check-in button state
    # Sprint 3 (1.16.0): change requests. On a change request: the booking it would replace. On an approved
    # booking: its open change request (pending or waitlisted), if any.
    old = lookups.booking(value.replaces_id) if value.replaces_id else None
    result["replaces_booking"] = ({"id": old.id, "start": json_value(old.start), "end": json_value(old.end),
                                   "status": old.status.value} if old else None)
    change = lookups.open_change(value) if value.status == BookingStatus.APPROVED else None
    result["open_change"] = ({"id": change.id, "start": json_value(change.start), "end": json_value(change.end),
                              "status": change.status.value} if change else None)
    return result

class _SingleLookups:
    """What booking_json needs, one query at a time (a single booking or a person's own short list)."""
    def __init__(self, service):
        self.service = service
        self.additional_hours_context = {}

    def additional_hours_review(self, booking):
        return self.service.additional_hours_review(booking, context=self.additional_hours_context)

    def person(self, principal_id):
        return self.service.repo.get_principal(str(principal_id))

    def booking(self, booking_id):
        return self.service.repo.get_booking(booking_id)

    def open_change(self, booking):
        return self.service.open_change_for(booking)

    def waitlist_position(self, booking):
        return waitlist_position(self.service, booking)

    def outlook(self, booking):
        return self.service.calendar_sync.describe(booking)

class BookingListLookups(_SingleLookups):
    """2026-10-29 (load test S2): everything booking_json needs for a long staff list, read once.

    Before, each booking cost about two more queries (people, the replaced booking, open change requests, the
    waitlist), so Booking Records ran 9000+ queries for 5000 bookings. Undecided requests are few, so they are read
    once to answer the change-request and waitlist questions; a replaced booking outside the list is still read alone.
    """
    def __init__(self, service, bookings, people=None):
        super().__init__(service)
        repo = service.repo
        self.people = people if people is not None else {item.id: item for item in repo.list_principals()}
        undecided = repo.list_bookings(statuses=UNDECIDED_STATUSES)
        self.bookings = {item.id: item for item in undecided}
        self.bookings.update((item.id, item) for item in bookings)
        self.changes, self.waitlists = {}, {}
        for item in undecided:  # repository order: open_change_for takes the first match
            if item.replaces_id:
                self.changes.setdefault((item.student_id, item.replaces_id), item)
            if item.status == BookingStatus.WAITLISTED:
                self.waitlists.setdefault(item.resource_id, []).append(item)
        sync = service.calendar_sync
        self.outlook_records = ({item.booking_id: item for item in repo.list_outlook_sync()}
                                if sync is not None and sync.enabled else None)

    def person(self, principal_id):
        return self.people.get(str(principal_id))

    def booking(self, booking_id):
        return self.bookings[booking_id] if booking_id in self.bookings else super().booking(booking_id)

    def open_change(self, booking):
        return self.changes.get((booking.student_id, booking.id))

    def waitlist_position(self, booking):
        return waitlist_position(self.service, booking, self.waitlists.get(booking.resource_id, []))

    def outlook(self, booking):
        return self.service.calendar_sync.describe(booking, self.outlook_records)

def submission_json(record):
    result = json_value(record)
    result["effective_status"] = "EXPIRED" if record.status == QualificationStatus.VERIFIED and record.valid_until and record.valid_until <= get_service().now() else record.status.value
    # Sprint 3 (1.17.1): automatic test-account grants have no evidence attachment.
    result["file_url"] = f"/api/v1/qualifications/{record.id}/file/" if record.file_id else ""
    return result

def collection(records, converter=json_value):
    records = list(records)
    return {"count": len(records), "results": [converter(item) for item in records]}

def validated(serializer_cls, data):
    serializer = serializer_cls(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data

def sync_after_write(service, *bookings):
    # The domain transaction has returned before any external HTTP call. Bookings approved by
    # automatic waitlist promotion during this request are synchronised as well.
    ids = [booking.id for booking in bookings]
    promoted = [item for item in service.take_promoted_ids() if item not in ids]
    if settings.OUTLOOK_SYNC_ON_WRITE:
        for booking_id in ids + promoted:
            record = service.repo.get_booking(booking_id)
            if record and record.student_id != TEST_ACCOUNT_ID:
                service.calendar_sync.process_booking(booking_id)
    return tuple(service.repo.get_booking(booking.id) for booking in bookings)

def waitlist_position(service, booking, candidates=None):
    """1-based place among waitlisted requests that overlap this one on the same resource.

    candidates (2026-10-29, load test S2): that resource's waitlisted requests, already read for a whole list.
    """
    if booking.status != BookingStatus.WAITLISTED:
        return None
    if candidates is None:
        candidates = service.repo.list_bookings(resource_id=booking.resource_id, statuses=[BookingStatus.WAITLISTED])
    ahead = [item for item in candidates
             if item.status == BookingStatus.WAITLISTED and item.id != booking.id
             and (item.created_at, item.id) < (booking.created_at, booking.id)
             and item.start < booking.end and booking.start < item.end]
    return len(ahead) + 1

def session_result(principal):
    return {"access_token": issue_demo_token(principal), "token_type": "Bearer", "expires_in": settings.DEMO_TOKEN_TTL_SECONDS,
            "user": json_value(principal), "mode": "demo"}

class PublicView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
