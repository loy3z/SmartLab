"""HTTP views: unfreeze (split from booking/views.py on 2026-10-25)."""

from ._common import *  # noqa: F401,F403 - shared imports, helpers and PublicView.

__all__ = ["unfreeze_json", "MyUnfreezeRequestsView", "AdminUnfreezeRequestListView", "AdminUnfreezeReviewView", "AdminFrozenUsersView", "AdminUserUnfreezeView"]

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
