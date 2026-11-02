"""HTTP views: resources (split from booking/views.py on 2026-10-25)."""

from ._common import *  # noqa: F401,F403 - shared imports, helpers and PublicView.

__all__ = ["ResourceListView", "DayOverviewView", "ResourceDetailView", "RequirementListView", "AvailabilityView", "QualificationListView", "QualificationDetailView", "QualificationFileView", "RequirementDetailView", "RequirementCreateView", "policy_json", "ResourceBookingPolicyView"]


def resource_json(service, resource):
    """Public resource data plus the effective normal-booking slot policy."""
    value = json_value(resource)
    max_slots, slot_minutes, maximum = service._normal_booking_limit(resource)
    value.update(
        booking_slot_minutes=slot_minutes,
        max_booking_slots=max_slots,
        selection_step_minutes=service._selection_step_minutes(resource),
        effective_max_booking_minutes=maximum,
    )
    return value

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
        service = get_service()
        return Response({"count": len(records), "results": [resource_json(service, item) for item in records]})

class DayOverviewView(APIView):
    """Booking page day grid: free and taken times of every matching resource on one day."""
    def get(self, request):
        data = validated(DayOverviewQuerySerializer, request.query_params)
        service = get_service()
        result = service.day_overview(
            request.user, data["date"], data["duration_minutes"], kind=data.get("kind"),
            room_id=str(data["room_id"]) if data.get("room_id") else None, category=data.get("category") or None,
            query=data.get("q"), bookable_only=data["bookable_only"], free_at=data.get("free_at"))
        for row in result["results"]:
            row["resource"] = resource_json(service, row["resource"])
        return Response(json_value(result))

class ResourceDetailView(APIView):
    def get(self, request, resource_id):
        service = get_service()
        return Response(resource_json(service, service.resource(str(resource_id))))

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
