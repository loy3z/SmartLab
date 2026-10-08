import io
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, time
from enum import Enum
from uuid import uuid4
from django.conf import settings
from django.http import FileResponse
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
                          OutlookProcessSerializer, BookingPolicySerializer)

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
    # The domain transaction has returned before any external HTTP call.
    if settings.OUTLOOK_SYNC_ON_WRITE:
        for booking in bookings:
            service.calendar_sync.process_booking(booking.id)
    return tuple(service.repo.get_booking(booking.id) for booking in bookings)

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
        result = get_service().availability(request.user, str(resource_id), data["date"], data["duration_minutes"])
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
        record, bookings = service.review_qualification(request.user, str(submission_id), data["decision"], data["reason"], data["valid_until"])
        bookings = sync_after_write(service, *bookings)
        return Response({"submission": submission_json(record), "updated_bookings": json_value(bookings)})

class AdminBookingListView(APIView):
    def get(self, request):
        service = get_service()
        service.require_staff(request.user)
        service.process_due_requests()
        requested = request.query_params.get("status", "PENDING_APPROVAL")
        if requested not in BookingStatus._value2member_map_:
            raise DomainError("VALIDATION_ERROR", "Unknown booking status.")
        records = [item for item in service.repo.list_bookings() if item.status.value == requested]
        return Response(collection(records))

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


class ResourceBookingPolicyView(APIView):
    def get(self, request, resource_id):
        service = get_service()
        service.require_staff(request.user)
        resource = service.resource(str(resource_id))
        return Response({"resource_id": resource.id, "pending_hold_minutes": resource.pending_hold_minutes})

    def patch(self, request, resource_id):
        service = get_service()
        if not request.user.active or request.user.role != Role.MANAGER:
            raise DomainError("FORBIDDEN", "Only an active Manager may configure booking policies.", 403)
        data = validated(BookingPolicySerializer, request.data)
        resource = service.set_pending_hold_minutes(request.user, str(resource_id), data["pending_hold_minutes"])
        return Response({"resource_id": resource.id, "pending_hold_minutes": resource.pending_hold_minutes})
