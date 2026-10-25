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
from .authentication import issue_demo_token, require_demo_mode
from .domain import Booking, BookingStatus, Principal, QualificationStatus, ResourceKind, Role
from .exceptions import DomainError
from .runtime import get_service
from .serializers import (AvailabilityQuerySerializer, DayOverviewQuerySerializer, BookingCreateSerializer, BookingRescheduleSerializer, BookingReviewSerializer,
                          DemoLoginSerializer, DemoRegisterSerializer, StaffActivateSerializer, StaffSignInSerializer, QualificationCreateSerializer, QualificationReviewSerializer,
                          OutlookProcessSerializer, BookingPolicySerializer, AuditQuerySerializer,
                          UserListQuerySerializer, UserUpdateSerializer, ManagerCreateSerializer, ResourceStatusSerializer,
                          AdminBookingQuerySerializer, StaffCreateSerializer, PrerequisiteSerializer,
                          PersonLookupSerializer, NotificationQuerySerializer, UnfreezeRequestSerializer,
                          UnfreezeReviewSerializer, UnfreezeListQuerySerializer, UnfreezeSerializer,
                          SeriesPlanSerializer, SeriesCreateSerializer, ResourceFieldsSerializer,
                          ResourceCreateSerializer, UsageReportQuerySerializer, ChangePasswordSerializer,
                          RequirementFieldsSerializer, RequirementUpdateSerializer, SiteContactSerializer)  # Sprint 3 (1.16.0)
from .ics import render_calendar
from .test_console import (TestPrincipal, get_test_account, require_test_console,
                           test_console_enabled, test_identity, TEST_ACCOUNT_ID, booking_rules_bypassed)
from .serializers import TestLoginSerializer, TestSessionSerializer

def json_value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, (time, date)):
        return value.isoformat()
    if is_dataclass(value):
        result = json_value(asdict(value))
        if isinstance(value, Booking):
            service = get_service()
            result["outlook_sync"] = service.calendar_sync.describe(value)
            result["hold_active"] = value.hold_is_active(service.now())
            result["blocks_slot"] = value.blocks_resource_at(service.now())
            result["waitlist_position"] = waitlist_position(service, value)
            # Who the booking is for and who created it (staff may book on behalf of someone).
            result["booked_for"] = person_brief(service, value.student_id)
            result["created_by_user"] = person_brief(service, value.created_by) if value.created_by else None
            result["on_behalf"] = bool(value.created_by and value.created_by != value.student_id)
            result.update(json_value(service.check_in_state(value)))  # Sprint 3: check-in button state
            # Sprint 3 (1.16.0): change requests. On a change request: the booking it would replace. On an approved
            # booking: its open change request (pending or waitlisted), if any.
            old = service.repo.get_booking(value.replaces_id) if value.replaces_id else None
            result["replaces_booking"] = ({"id": old.id, "start": json_value(old.start), "end": json_value(old.end),
                                           "status": old.status.value} if old else None)
            change = service.open_change_for(value) if value.status == BookingStatus.APPROVED else None
            result["open_change"] = ({"id": change.id, "start": json_value(change.start), "end": json_value(change.end),
                                      "status": change.status.value} if change else None)
        if isinstance(value, Principal):  # Sprint 3: booking freeze
            result["booking_frozen"] = value.frozen_at(get_service().now()) and not booking_rules_bypassed(value)
        return result
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value

def person_brief(service, principal_id):
    person = service.repo.get_principal(str(principal_id))
    return ({"id": person.id, "zid": person.zid, "display_name": person.display_name, "role": person.role.value}
            if person else None)

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

def waitlist_position(service, booking):
    """1-based place among waitlisted requests that overlap this one on the same resource."""
    if booking.status != BookingStatus.WAITLISTED:
        return None
    ahead = [item for item in service.repo.list_bookings(resource_id=booking.resource_id)
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

class HealthView(PublicView):
    def get(self, request):
        return Response({"status": "ok", "service": "smartlab-sprint1", "demo_auth_enabled": settings.DEBUG and settings.ENABLE_DEMO_AUTH,
                         "persistence": "adapter", "outlook_sync": "enabled" if settings.OUTLOOK_ENABLED else "disabled"})

class AuthConfigView(PublicView):
    def get(self, request):
        demo = settings.DEBUG and settings.ENABLE_DEMO_AUTH
        return Response({"mode": "demo" if demo else "external_provider_required", "demo_auth_enabled": demo,
                         "demo_registration_enabled": demo, "sso_connected": False, "token_type": "Bearer",
                         # Admins and Managers sign in on the staff page with zID + password (prototype; uses the same token).
                         "staff_sign_in_enabled": demo, "test_console_enabled": test_console_enabled()})

class TestLoginView(PublicView):
    def post(self, request):
        require_test_console()
        validated(TestLoginSerializer, request.data)
        principal = test_identity(get_test_account(get_service()), Role.STUDENT, True)
        return Response(session_result(principal))

class TestSessionView(APIView):
    def post(self, request):
        require_test_console()
        if not isinstance(request.user, TestPrincipal):
            raise DomainError("FORBIDDEN", "Only the test account can change its test session.", 403)
        data = validated(TestSessionSerializer, request.data)
        principal = test_identity(request.user, data["role"], data["bypass_booking_rules"])
        get_service()._audit(principal.id, "TEST_SESSION_CHANGED", "principal", principal.id,
                             role=principal.role.value, bypass_booking_rules=principal.bypass_booking_rules)
        return Response(session_result(principal))

class DemoRegisterView(PublicView):
    def post(self, request):
        require_demo_mode()
        data = validated(DemoRegisterSerializer, request.data)
        service = get_service()
        with service.repo.atomic():
            if any(item.zid == data["zid"] for item in service.repo.list_principals()):
                raise DomainError("USER_ALREADY_EXISTS", "This demo zID already exists.", 409)
            principal = Principal(str(uuid4()), data["zid"], data["display_name"], Role.STUDENT,
                                  university_email=data["university_email"])
            service.repo.save_principal(principal)
            service._audit(principal.id, "DEMO_STUDENT_CREATED", "principal", principal.id)
        return Response(session_result(principal), status=status.HTTP_201_CREATED)

class DemoLoginView(PublicView):
    def post(self, request):
        require_demo_mode()
        data = validated(DemoLoginSerializer, request.data)
        principal = next((item for item in get_service().repo.list_principals() if item.zid == data["zid"] and item.active), None)
        if principal is None:
            raise DomainError("INVALID_DEMO_USER", "Create this demo student account first or use a seeded demo zID.", 401)
        if principal.is_staff:
            # University (student) sign-in is for students only; staff use the staff sign-in page.
            raise DomainError("USE_STAFF_SIGN_IN", "Admins and Managers sign in on the staff sign-in page.", 403)
        return Response(session_result(principal))

class StaffSignInView(PublicView):
    """Staff sign-in page: zID + password. The account's role decides Admin or Manager access."""
    def post(self, request):
        require_demo_mode()
        data = validated(StaffSignInSerializer, request.data)
        return Response(session_result(get_service().staff_sign_in(data["zid"], data["password"])))

class StaffActivateView(PublicView):
    """First staff sign-in: invite code from the Manager + a new password. Signs the user in."""
    def post(self, request):
        require_demo_mode()
        data = validated(StaffActivateSerializer, request.data)
        return Response(session_result(get_service().activate_staff(data["zid"], data["invite_code"], data["password"])))

class MeView(APIView):
    def get(self, request):
        return Response(json_value(request.user))

class ResourceListView(APIView):
    def get(self, request):
        records = [item for item in get_service().repo.list_resources() if item.active]
        kind = request.query_params.get("kind")
        if kind:
            if kind not in ResourceKind._value2member_map_:
                raise DomainError("VALIDATION_ERROR", "kind must be ROOM or EQUIPMENT.")
            records = [item for item in records if item.kind.value == kind]
        category = request.query_params.get("category", "").strip()
        if category:
            records = [item for item in records if item.category == category]
        query = request.query_params.get("q", "").strip().casefold()
        if query:
            records = [item for item in records if query in f"{item.name} {item.location} {item.category or ''}".casefold()]
        return Response(collection(records))

class DayOverviewView(APIView):
    """Booking page day grid: free and taken times of every matching resource on one day."""
    def get(self, request):
        data = validated(DayOverviewQuerySerializer, request.query_params)
        result = get_service().day_overview(
            request.user, data["date"], data["duration_minutes"], kind=data.get("kind"),
            room_id=str(data["room_id"]) if data.get("room_id") else None, category=data.get("category") or None,
            query=data.get("q"), bookable_only=data["bookable_only"], free_at=data.get("free_at"))
        return Response(json_value(result))

class ResourceDetailView(APIView):
    def get(self, request, resource_id):
        return Response(json_value(get_service().resource(str(resource_id))))

class RequirementListView(APIView):
    def get(self, request):
        return Response(collection(get_service().repo.list_requirements()))

class AvailabilityView(APIView):
    def get(self, request, resource_id):
        data = validated(AvailabilityQuerySerializer, request.query_params)
        result = get_service().availability(request.user, str(resource_id), data["date"], data["duration_minutes"],
                                            data.get("exclude_booking_id"), data.get("for_zid") or None, data["urgent"])
        return Response(json_value(result))

class QualificationListView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        return Response(collection(get_service().repo.list_submissions(student_id=request.user.id), submission_json))

    def post(self, request):
        get_service().require_booking_user(request.user)
        data = validated(QualificationCreateSerializer, request.data)
        file = data["file"]
        record = get_service().submit_qualification(request.user, str(data["requirement_id"]), data["title"], data["notes"], file.read(), file.name, file.content_type)
        return Response(submission_json(record), status=status.HTTP_201_CREATED)

class QualificationDetailView(APIView):
    def get(self, request, submission_id):
        return Response(submission_json(get_service().submission_for(request.user, str(submission_id))))

class QualificationFileView(APIView):
    def get(self, request, submission_id):
        service = get_service()
        submission = service.submission_for(request.user, str(submission_id))
        file = service.storage.get(submission.file_id)
        if not file:
            raise DomainError("NOT_FOUND", "Evidence file not found.", 404)
        response = FileResponse(io.BytesIO(file.data), as_attachment=True, filename=file.original_name, content_type=file.content_type)
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

class BookingListView(APIView):
    def get(self, request):
        service = get_service()
        service.process_due_requests()
        return Response(collection(my_bookings(service, request.user)))

    def post(self, request):
        service = get_service()
        service.require_booking_user(request.user)
        data = validated(BookingCreateSerializer, request.data)
        booking, created = service.create_booking(request.user, str(data["resource_id"]), data["start"], data["end"], data["purpose"],
                                                  request.headers.get("Idempotency-Key"),
                                                  on_behalf_of_zid=data.get("on_behalf_of_zid") or None,
                                                  urgent=data["urgent"], urgent_reason=data["urgent_reason"])
        booking, = sync_after_write(service, booking)
        return Response(json_value(booking), status=201 if created else 200)

def my_bookings(service, user):
    """Bookings for me plus those I created for other people, oldest first."""
    mine = {item.id: item for item in service.repo.list_bookings(student_id=user.id)}
    if user.role in (Role.ADMIN, Role.MANAGER):
        mine.update({item.id: item for item in service.repo.list_bookings() if item.created_by == user.id})
    return sorted(mine.values(), key=lambda item: (item.created_at, item.id))

class PersonLookupView(APIView):
    """Admin/Manager: check whom you are booking for before submitting."""
    def get(self, request):
        data = validated(PersonLookupSerializer, request.query_params)
        person = get_service().find_person(request.user, data["zid"])
        return Response({"id": person.id, "zid": person.zid, "display_name": person.display_name, "role": person.role.value})

class BookingDetailView(APIView):
    def get(self, request, booking_id):
        service = get_service()
        service.process_due_requests()
        return Response(json_value(service.booking_for(request.user, str(booking_id))))

class BookingCancelView(APIView):
    def post(self, request, booking_id):
        if request.data:
            raise DomainError("VALIDATION_ERROR", "The cancellation action does not accept extra fields.")
        service = get_service()
        booking = service.cancel_booking(request.user, str(booking_id))
        booking, = sync_after_write(service, booking)
        return Response(json_value(booking))

class BookingRescheduleView(APIView):
    def post(self, request, booking_id):
        data = validated(BookingRescheduleSerializer, request.data)
        service = get_service()
        booking = service.reschedule_booking(request.user, str(booking_id), data["start"], data["end"])
        booking, = sync_after_write(service, booking)
        return Response(json_value(booking))

class BookingChangeView(APIView):
    """Sprint 3 (1.16.0): the person a booking is for asks to move it (services/changes.py). Returns the new request;
    the old booking stays until it is approved."""
    def post(self, request, booking_id):
        data = validated(BookingRescheduleSerializer, request.data)
        service = get_service()
        booking, created = service.request_time_change(request.user, str(booking_id), data["start"], data["end"],
                                                       request.headers.get("Idempotency-Key"))
        booking, = sync_after_write(service, booking)
        return Response(json_value(booking), status=201 if created else 200)

class DashboardView(APIView):
    def get(self, request):
        service = get_service()
        service.process_due_requests()
        bookings = my_bookings(service, request.user)
        submissions = service.repo.list_submissions(student_id=request.user.id)
        counts = {item.value: sum(booking.status == item for booking in bookings) for item in BookingStatus}
        return Response({"bookings": json_value(bookings), "qualifications": [submission_json(item) for item in submissions], "counts": counts})

class AdminQualificationListView(APIView):
    def get(self, request):
        service = get_service()
        service.require_staff(request.user)
        requested = request.query_params.get("status", "PENDING")
        if requested not in QualificationStatus._value2member_map_:
            raise DomainError("VALIDATION_ERROR", "Use PENDING, VERIFIED or REJECTED.")
        records = [item for item in service.repo.list_submissions() if item.status.value == requested]
        people = {item.id: item for item in service.repo.list_principals()}

        def staff_submission_json(record):
            # Reviewers need to know whose evidence it is, not only the internal id.
            result = submission_json(record)
            person = people.get(record.student_id)
            result["student"] = ({"id": person.id, "zid": person.zid, "display_name": person.display_name,
                                  "university_email": person.university_email} if person else None)
            return result

        return Response(collection(records, staff_submission_json))

class AdminQualificationReviewView(APIView):
    def post(self, request, submission_id):
        service = get_service()
        service.require_staff(request.user)
        data = validated(QualificationReviewSerializer, request.data)
        record, bookings = service.review_qualification(request.user, str(submission_id), data["decision"], data["reason"])
        bookings = sync_after_write(service, *bookings)
        return Response({"submission": submission_json(record), "updated_bookings": json_value(bookings)})

def staff_booking_rows(service, user, params):
    data = validated(AdminBookingQuerySerializer, params)
    records = service.booking_report(user, data["status"], data.get("resource_id"), data.get("student_id"),
                                     data.get("since"), data.get("until"), data.get("q"))
    people = {item.id: item for item in service.repo.list_principals()}
    resources = {item.id: item for item in service.repo.list_resources()}
    return records, people, resources

def staff_booking_json(booking, people, resources):
    """Booking plus who booked it and what, for Admin/Manager lists and printouts."""
    result = json_value(booking)
    person, resource = people.get(booking.student_id), resources.get(booking.resource_id)
    result["student"] = ({"id": person.id, "zid": person.zid, "display_name": person.display_name,
                          "university_email": person.university_email} if person else None)
    result["resource_name"] = resource.name if resource else None
    result["resource_kind"] = resource.kind.value if resource else None
    return result

class AdminBookingListView(APIView):
    """Admin/Manager booking list. Defaults to the manual-approval queue; status=ALL lists everything."""
    def get(self, request):
        service = get_service()
        service.require_staff(request.user)
        records, people, resources = staff_booking_rows(service, request.user, request.query_params)
        return Response(collection(records, lambda item: staff_booking_json(item, people, resources)))

class AdminBookingExportView(APIView):
    """Admin/Manager (Sprint 3: Admins too, for Booking Records): the same filters as the list (default status=ALL),
    as a CSV file for printing or Excel."""
    def get(self, request):
        service = get_service()
        service.require_staff(request.user)
        params = request.query_params.copy()
        params.setdefault("status", "ALL")
        records, people, resources = staff_booking_rows(service, request.user, params)
        zone = ZoneInfo(settings.TIME_ZONE)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Booking ID", "Status", "Reason", "Resource", "Type", "Date", "Start", "End", "Minutes",
                         "Student zID", "Student name", "Student email", "Purpose", "Submitted", "Decided by", "Decision reason",
                         "Created by", "Urgent", "Urgent reason", "Weekly series", "Attendance"])  # last two: Sprint 3
        for item in records:
            person, resource = people.get(item.student_id), resources.get(item.resource_id)
            local = ZoneInfo(resource.timezone) if resource else zone
            start, end = item.start.astimezone(local), item.end.astimezone(local)
            reviewer = people.get(item.reviewed_by) if item.reviewed_by else None
            writer.writerow([item.id, item.status.value, item.reason_code or "", resource.name if resource else item.resource_id,
                             resource.kind.value if resource else "", start.date().isoformat(), start.strftime("%H:%M"),
                             end.strftime("%H:%M"), int((item.end - item.start).total_seconds() // 60),
                             person.zid if person else "", person.display_name if person else "",
                             person.university_email if person else "", _csv_safe(item.purpose),
                             item.created_at.astimezone(local).strftime("%Y-%m-%d %H:%M"),
                             reviewer.zid if reviewer else (item.reviewed_by or ""), _csv_safe(item.decision_reason or ""),
                             creator.zid if (creator := people.get(item.created_by)) else (item.created_by or ""),
                             "Yes" if item.urgent else "", _csv_safe(item.urgent_reason or ""),
                             "Yes" if item.series_id else "", item.attendance or ""])
        response = HttpResponse("\ufeff" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="bookings.csv"'
        return response

def _csv_safe(text):
    """Stop spreadsheet apps from treating user text as a formula."""
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text

class AdminResourceStatusView(APIView):
    """Manager only: AVAILABLE / MAINTENANCE / CLOSED. Existing bookings are kept and listed for follow-up."""
    def patch(self, request, resource_id):
        service = get_service()
        service.require_manager(request.user)
        data = validated(ResourceStatusSerializer, request.data)
        resource, affected = service.set_resource_status(request.user, str(resource_id), data["status"], data["reason"])
        sync_after_write(service)
        people = {item.id: item for item in service.repo.list_principals()}
        resources = {resource.id: resource}
        return Response({"resource": json_value(resource),
                         "affected_bookings": [staff_booking_json(item, people, resources) for item in affected]})

def audit_json(record, principals):
    result = json_value(record)
    person = principals.get(record.actor_id)
    result["actor"] = ({"id": person.id, "zid": person.zid, "display_name": person.display_name, "role": person.role.value}
                       if person else None)
    return result

class AdminAuditListView(APIView):
    """Audit trail of requests, approvals, changes and cancellations (Admin/Manager)."""
    def get(self, request):
        service = get_service()
        service.require_staff(request.user)
        data = validated(AuditQuerySerializer, request.query_params)
        total, records = service.audit_trail(request.user, **data)
        principals = {item.id: item for item in service.repo.list_principals()}
        return Response({"count": total, "limit": data["limit"], "offset": data["offset"],
                         "results": [audit_json(item, principals) for item in records]})

def user_json(service, user):
    """A person plus their induction status (students) and whether they are staff."""
    result = json_value(user)
    result["is_staff"] = user.is_staff
    result.update(service.staff_access(user))
    inductions = service.induction_summary(user.id)
    result["inductions"] = json_value(inductions)
    result["induction_status"] = "VERIFIED" if all(item["status"] == "VERIFIED" for item in inductions) else "INCOMPLETE"
    return result

class AdminStaffCreateView(APIView):
    """Manager only ("Add staff"): create an Admin or Manager account. Students are never promoted to staff."""
    def post(self, request):
        service = get_service()
        service.require_manager(request.user)
        data = validated(StaffCreateSerializer, request.data)
        created = service.create_staff(request.user, data["zid"], data["display_name"], data["university_email"], data["role"])
        return Response(user_json(service, created), status=status.HTTP_201_CREATED)

class RequirementDetailView(APIView):
    """Manager only: set which inductions must be verified first (e.g. Advanced needs General).

    Sprint 3 (1.16.0): also changes the name, description and guidance texts; send any of them."""
    def patch(self, request, requirement_id):
        service = get_service()
        service.require_manager(request.user)
        data = validated(RequirementUpdateSerializer, request.data)
        prerequisites = data.pop("prerequisite_ids", None)
        updated = service.repo.get_requirement(str(requirement_id))
        if data:
            updated = service.update_requirement(request.user, str(requirement_id), data)
        if prerequisites is not None:
            updated = service.set_prerequisites(request.user, str(requirement_id), [str(item) for item in prerequisites])
        if updated is None:
            raise DomainError("NOT_FOUND", "Qualification requirement not found.", 404)
        return Response(json_value(updated))

class RequirementCreateView(APIView):
    """Sprint 3 (1.16.0), Manager only: add an induction type."""
    def post(self, request):
        data = validated(RequirementFieldsSerializer, request.data)
        return Response(json_value(get_service().create_requirement(request.user, data)), status=201)

class SiteContactView(APIView):
    """Sprint 3 (1.16.0): the lab's contact details. Anyone signed in reads them; a Manager changes them."""
    def get(self, request):
        return Response(json_value(get_service().site_contact()))

    def patch(self, request):
        data = validated(SiteContactSerializer, request.data)
        return Response(json_value(get_service().update_site_contact(request.user, data)))

class StaffOverviewView(APIView):
    """Sprint 3 (1.16.0), Admin and Manager: the "Today" page (services/overview.py)."""
    def get(self, request):
        return Response(json_value(get_service().staff_overview(request.user)))

class AdminManagerCreateView(APIView):
    """Manager only ("Add manager"): kept for existing clients; same as Add staff with role MANAGER."""
    def post(self, request):
        service = get_service()
        service.require_manager(request.user)
        data = validated(ManagerCreateSerializer, request.data)
        created = service.create_manager(request.user, data["zid"], data["display_name"], data["university_email"])
        return Response(user_json(service, created), status=status.HTTP_201_CREATED)

class AdminUserListView(APIView):
    """Manager only: students (read only) and staff (roles and account status)."""
    def get(self, request):
        service = get_service()
        service.require_manager(request.user)
        data = validated(UserListQuerySerializer, request.query_params)
        users = service.list_users(request.user, data.get("role"), data["active"], data["q"])
        return Response(collection(users, lambda item: user_json(service, item)))

class AdminUserDetailView(APIView):
    def patch(self, request, user_id):
        service = get_service()
        service.require_manager(request.user)
        data = validated(UserUpdateSerializer, request.data)
        return Response(user_json(service, service.update_user(request.user, str(user_id), data.get("role"), data.get("active"))))

class AdminUserResetAccessView(APIView):
    """Manager only: clear a staff member's password and issue a new invite code."""
    def post(self, request, user_id):
        service = get_service()
        service.require_manager(request.user)
        return Response(user_json(service, service.reset_staff_access(request.user, str(user_id))))

class AdminBookingReviewView(APIView):
    def post(self, request, booking_id):
        service = get_service()
        service.require_staff(request.user)
        data = validated(BookingReviewSerializer, request.data)
        booking = service.review_booking(request.user, str(booking_id), data["decision"], data["reason"])
        booking, = sync_after_write(service, booking)
        return Response(json_value(booking))

class ProcessDueView(APIView):
    def post(self, request):
        service = get_service()
        service.require_staff(request.user)
        if request.data:
            raise DomainError("VALIDATION_ERROR", "The processing action does not accept a client-supplied clock.")
        changed = service.process_due_requests()
        sync_after_write(service)  # automatically approved bookings go to Outlook straight away
        changed = [service.repo.get_booking(item.id) for item in changed]
        return Response({"processed_count": len(changed), "updated_bookings": json_value(changed)})


class OutlookStatusView(APIView):
    def get(self, request):
        service = get_service()
        service.require_staff(request.user)
        sync = service.calendar_sync
        provider = sync.provider
        # Reading this page never calls Microsoft: use POST check/ to test the connection.
        return Response(json_value({
            "enabled": sync.enabled, "configured": provider.configured,
            "mode": getattr(provider, "mode", "adapter"), "direction": "system_to_outlook",
            "invite_mode": getattr(provider, "invite_mode", None), "last_check": sync.last_check, **sync.overview(),
            "sync_records": collection(sync.repo.list_outlook_sync())}))


class OutlookCheckView(APIView):
    def post(self, request):
        service = get_service()
        service.require_staff(request.user)
        if request.data:
            raise DomainError("VALIDATION_ERROR", "The connection check does not accept fields.")
        return Response(json_value(service.calendar_sync.check_connection()))


class OutlookProcessView(APIView):
    def post(self, request):
        service = get_service()
        service.require_staff(request.user)
        data = validated(OutlookProcessSerializer, request.data)
        processed = service.calendar_sync.process_pending(data["limit"])
        return Response({"processed_count": len(processed), "results": json_value(processed)})


class OutlookRetryView(APIView):
    def post(self, request, booking_id):
        service = get_service()
        service.require_staff(request.user)
        if request.data:
            raise DomainError("VALIDATION_ERROR", "The retry action does not accept extra fields.")
        booking = service.booking_for(request.user, str(booking_id))
        service.calendar_sync.retry(booking)
        return Response(json_value(booking))


def policy_json(resource):
    return {"resource_id": resource.id, "pending_hold_minutes": resource.pending_hold_minutes}

class ResourceBookingPolicyView(APIView):
    """Manager only (Admins approve and review; rules belong to Managers)."""
    def get(self, request, resource_id):
        service = get_service()
        service.require_manager(request.user)
        return Response(policy_json(service.resource(str(resource_id))))

    def patch(self, request, resource_id):
        service = get_service()
        service.require_manager(request.user)
        data = validated(BookingPolicySerializer, request.data)
        resource = service.set_booking_policy(request.user, str(resource_id), data["pending_hold_minutes"])
        return Response(policy_json(resource))


# Sprint 3: calendar subscription link ------------------------------------------------------------------------

def calendar_link_json(feed):
    return {"path": f"/api/v1/calendar/{feed.token}.ics", "created_at": json_value(feed.created_at)}

class CalendarLinkView(APIView):
    """The signed-in person's secret calendar subscription address (created on first use)."""
    def get(self, request):
        return Response(calendar_link_json(get_service().calendar_feed(request.user)))

class CalendarLinkResetView(APIView):
    """Make a new address; the old one stops working at once."""
    def post(self, request):
        return Response(calendar_link_json(get_service().calendar_feed(request.user, reset=True)))

class CalendarFeedView(PublicView):
    """iCalendar feed read by Outlook / Google / Apple Calendar. The token in the address is the only key."""
    def get(self, request, token):
        service = get_service()
        person, events = service.calendar_feed_events(token)
        body = render_calendar(f"SmartLab bookings ({person.display_name})", events, service.now())
        response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = 'inline; filename="smartlab-bookings.ics"'
        response["Cache-Control"] = "no-store"
        return response


# Sprint 3: notifications ------------------------------------------------------------------------------------

class NotificationListView(APIView):
    def get(self, request):
        service = get_service()
        service.process_due_requests()
        data = validated(NotificationQuerySerializer, request.query_params)
        items, unread = service.list_notifications(request.user, data["unread"], data["limit"])
        return Response({"count": len(items), "unread_count": unread, "results": json_value(items)})

class NotificationReadView(APIView):
    def post(self, request, notification_id):
        return Response(json_value(get_service().mark_notification_read(request.user, str(notification_id))))

class NotificationReadAllView(APIView):
    def post(self, request):
        return Response({"updated": get_service().mark_all_notifications_read(request.user)})


# Sprint 3: check-in and booking freeze ----------------------------------------------------------------------

class BookingCheckInView(APIView):
    def post(self, request, booking_id):
        if request.data:
            raise DomainError("VALIDATION_ERROR", "Check-in does not accept extra fields.")
        return Response(json_value(get_service().check_in(request.user, str(booking_id))))

def unfreeze_json(service, item):
    result = json_value(item)
    person = service.repo.get_principal(item.principal_id)
    result["person"] = ({**person_brief(service, person.id), "frozen_until": json_value(person.frozen_until),
                         "booking_frozen": person.frozen_at(service.now())} if person else None)
    result["decided_by_user"] = person_brief(service, item.decided_by) if item.decided_by else None
    return result

class MyUnfreezeRequestsView(APIView):
    def get(self, request):
        service = get_service()
        return Response(collection(service.my_unfreeze_requests(request.user), lambda item: unfreeze_json(service, item)))

    def post(self, request):
        service = get_service()
        data = validated(UnfreezeRequestSerializer, request.data)
        created = service.request_unfreeze(request.user, data["reason"])
        return Response(unfreeze_json(service, created), status=status.HTTP_201_CREATED)

class AdminUnfreezeRequestListView(APIView):
    def get(self, request):
        service = get_service()
        service.process_due_requests()
        data = validated(UnfreezeListQuerySerializer, request.query_params)
        items = service.list_unfreeze_requests(request.user, data.get("status"))
        return Response(collection(items, lambda item: unfreeze_json(service, item)))

class AdminUnfreezeReviewView(APIView):
    def post(self, request, request_id):
        service = get_service()
        data = validated(UnfreezeReviewSerializer, request.data)
        return Response(unfreeze_json(service, service.review_unfreeze(request.user, str(request_id), data["decision"], data["reason"])))

class AdminFrozenUsersView(APIView):
    """Admin/Manager: everyone whose booking is frozen now, with any waiting unfreeze request."""
    def get(self, request):
        service = get_service()
        service.require_staff(request.user)
        service.process_due_requests()
        now = service.now()
        pending = {item.principal_id: item for item in service.list_unfreeze_requests(request.user, "PENDING")}
        people = sorted((item for item in service.repo.list_principals() if item.frozen_at(now)), key=lambda item: item.frozen_until)
        return Response(collection(people, lambda item: {**json_value(item), "pending_request":
                                                         unfreeze_json(service, pending[item.id]) if item.id in pending else None}))

class AdminUserUnfreezeView(APIView):
    def post(self, request, user_id):
        service = get_service()
        data = validated(UnfreezeSerializer, request.data)
        return Response(json_value(service.unfreeze(request.user, str(user_id), data["reason"])))


# Sprint 3: weekly series (staff) ----------------------------------------------------------------------------

def series_json(series, bookings):
    return {**json_value(series), "weekdays": [int(item) for item in series.weekdays.split(",") if item],
            "bookings": json_value(bookings)}

def _series_args(data):
    return dict(resource_id=str(data["resource_id"]), weekdays=data["weekdays"], start_time=data["start_time"],
                duration_minutes=data["duration_minutes"], first_date=data["first_date"], last_date=data["last_date"],
                on_behalf_of_zid=data.get("on_behalf_of_zid") or None)

class SeriesPreviewView(APIView):
    def post(self, request):
        data = validated(SeriesPlanSerializer, request.data)
        return Response(json_value(get_service().preview_series(request.user, **_series_args(data))))

class SeriesCreateView(APIView):
    def post(self, request):
        service = get_service()
        data = validated(SeriesCreateSerializer, request.data)
        series, bookings = service.create_series(request.user, purpose=data["purpose"], skip_dates=data["skip_dates"],
                                                 **_series_args(data))
        bookings = sync_after_write(service, *bookings)
        return Response(series_json(series, bookings), status=status.HTTP_201_CREATED)

class SeriesDetailView(APIView):
    def get(self, request, series_id):
        service = get_service()
        service.process_due_requests()
        return Response(series_json(*service.series_detail(request.user, str(series_id))))

class SeriesCancelView(APIView):
    def post(self, request, series_id):
        if request.data:
            raise DomainError("VALIDATION_ERROR", "The cancellation action does not accept extra fields.")
        service = get_service()
        series, cancelled = service.cancel_series(request.user, str(series_id))
        sync_after_write(service, *cancelled)
        return Response(series_json(*service.series_detail(request.user, series.id)))


# Sprint 3: resource setup (Manager) -------------------------------------------------------------------------

def changed_resource_json(service, resource, outside):
    """The saved resource plus the future bookings that no longer fit its rules (kept until a Manager acts)."""
    people = {booking.student_id: service.repo.get_principal(booking.student_id) for booking, _ in outside}
    return {"resource": json_value(resource),
            "bookings_outside_rules": [{**staff_booking_json(booking, people, {resource.id: resource}), "problem": code}
                                       for booking, code in outside]}

class AdminResourceListView(APIView):
    """GET: every resource including archived ones. POST: add a room or equipment."""
    def get(self, request):
        return Response(collection(get_service().list_all_resources(request.user)))

    def post(self, request):
        service = get_service()
        data = validated(ResourceCreateSerializer, request.data)
        kind = data.pop("kind")
        return Response(json_value(service.create_resource(request.user, kind, data)), status=status.HTTP_201_CREATED)

class AdminResourceDetailView(APIView):
    """PATCH: change the fields sent; the kind cannot change."""
    def patch(self, request, resource_id):
        service = get_service()
        if "kind" in request.data:
            raise DomainError("KIND_IS_FIXED", "A room cannot become equipment or the other way round. Add a new resource instead.", 409)
        data = validated(ResourceFieldsSerializer, request.data)
        resource, outside = service.update_resource(request.user, str(resource_id), data)
        return Response(changed_resource_json(service, resource, outside))

class AdminResourceArchiveView(APIView):
    def post(self, request, resource_id):
        if request.data:
            raise DomainError("VALIDATION_ERROR", "This action does not accept fields.")
        return Response(json_value(get_service().archive_resource(request.user, str(resource_id))))

class AdminResourceRestoreView(APIView):
    def post(self, request, resource_id):
        if request.data:
            raise DomainError("VALIDATION_ERROR", "This action does not accept fields.")
        return Response(json_value(get_service().restore_resource(request.user, str(resource_id))))


# Sprint 3: usage report (Manager) -----------------------------------------------------------------------------

class AdminUsageReportView(APIView):
    def get(self, request):
        data = validated(UsageReportQuerySerializer, request.query_params)
        return Response(json_value(get_service().usage_report(request.user, data["first_date"], data["last_date"])))


# Sprint 3: staff change their own password --------------------------------------------------------------------

class ChangePasswordView(APIView):
    def post(self, request):
        data = validated(ChangePasswordSerializer, request.data)
        get_service().change_password(request.user, data["current_password"], data["new_password"])
        return Response({"changed": True})
