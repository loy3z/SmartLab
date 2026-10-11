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
from .serializers import (AvailabilityQuerySerializer, BookingCreateSerializer, BookingRescheduleSerializer, BookingReviewSerializer,
                          DemoLoginSerializer, DemoRegisterSerializer, QualificationCreateSerializer, QualificationReviewSerializer,
                          OutlookProcessSerializer, BookingPolicySerializer, AuditQuerySerializer,
                          UserListQuerySerializer, UserUpdateSerializer, ManagerCreateSerializer, ResourceStatusSerializer,
                          AdminBookingQuerySerializer)

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
        return result
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value

def submission_json(record):
    result = json_value(record)
    result["effective_status"] = "EXPIRED" if record.status == QualificationStatus.VERIFIED and record.valid_until and record.valid_until <= get_service().now() else record.status.value
    result["file_url"] = f"/api/v1/qualifications/{record.id}/file/"
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
                         "demo_registration_enabled": demo, "sso_connected": False, "token_type": "Bearer"})

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
        return Response(session_result(principal))

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
        query = request.query_params.get("q", "").strip().casefold()
        if query:
            records = [item for item in records if query in f"{item.name} {item.location}".casefold()]
        return Response(collection(records))

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
                                            data.get("exclude_booking_id"))
        return Response(json_value(result))

class QualificationListView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        return Response(collection(get_service().repo.list_submissions(student_id=request.user.id), submission_json))

    def post(self, request):
        get_service().require_student(request.user)
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
        return Response(collection(service.repo.list_bookings(student_id=request.user.id)))

    def post(self, request):
        service = get_service()
        service.require_student(request.user)
        data = validated(BookingCreateSerializer, request.data)
        booking, created = service.create_booking(request.user, str(data["resource_id"]), data["start"], data["end"], data["purpose"], request.headers.get("Idempotency-Key"))
        booking, = sync_after_write(service, booking)
        return Response(json_value(booking), status=201 if created else 200)

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

class DashboardView(APIView):
    def get(self, request):
        service = get_service()
        service.process_due_requests()
        bookings = service.repo.list_bookings(student_id=request.user.id)
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
        return Response(collection(records, submission_json))

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
                                     data.get("since"), data.get("until"))
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
    """Manager only: the same filters as the list (default status=ALL), as a CSV file for printing or Excel."""
    def get(self, request):
        service = get_service()
        service.require_manager(request.user)
        params = request.query_params.copy()
        params.setdefault("status", "ALL")
        records, people, resources = staff_booking_rows(service, request.user, params)
        zone = ZoneInfo(settings.TIME_ZONE)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Booking ID", "Status", "Reason", "Resource", "Type", "Date", "Start", "End", "Minutes",
                         "Student zID", "Student name", "Student email", "Purpose", "Submitted", "Decided by", "Decision reason"])
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
                             reviewer.zid if reviewer else (item.reviewed_by or ""), _csv_safe(item.decision_reason or "")])
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
    """A person plus their induction status, so the Manager can see who may become an administrator."""
    result = json_value(user)
    inductions = service.induction_summary(user.id)
    result["inductions"] = json_value(inductions)
    result["induction_status"] = "VERIFIED" if all(item["status"] == "VERIFIED" for item in inductions) else "INCOMPLETE"
    return result

class AdminManagerCreateView(APIView):
    """Manager only ("Add manager"): the only way to create a Manager account."""
    def post(self, request):
        service = get_service()
        service.require_manager(request.user)
        data = validated(ManagerCreateSerializer, request.data)
        created = service.create_manager(request.user, data["zid"], data["display_name"], data["university_email"])
        return Response(user_json(service, created), status=status.HTTP_201_CREATED)

class AdminUserListView(APIView):
    """Manager only: staff and user list for nominating roles."""
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
        return Response({"processed_count": len(changed), "updated_bookings": json_value(changed)})


class OutlookStatusView(APIView):
    def get(self, request):
        service = get_service()
        service.require_staff(request.user)
        sync = service.calendar_sync
        return Response({"enabled": sync.enabled, "configured": sync.provider.configured,
                         "mode": getattr(sync.provider, "mode", "adapter"), "direction": "system_to_outlook",
                         "sync_records": collection(sync.repo.list_outlook_sync())})


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
    return {"resource_id": resource.id, "pending_hold_minutes": resource.pending_hold_minutes,
            "auto_approve_max_minutes": resource.auto_approve_max_minutes}

class ResourceBookingPolicyView(APIView):
    def get(self, request, resource_id):
        service = get_service()
        service.require_staff(request.user)
        return Response(policy_json(service.resource(str(resource_id))))

    def patch(self, request, resource_id):
        service = get_service()
        service.require_manager(request.user)
        data = validated(BookingPolicySerializer, request.data)
        resource = service.set_booking_policy(request.user, str(resource_id), data.get("pending_hold_minutes"),
                                              data.get("auto_approve_max_minutes"))
        return Response(policy_json(resource))
