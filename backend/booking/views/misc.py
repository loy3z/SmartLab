"""HTTP views: misc (split from booking/views.py on 2026-10-25)."""

from ._common import *  # noqa: F401,F403 - shared imports, helpers and PublicView.

__all__ = ["SiteContactView", "StaffOverviewView", "ProcessDueView"]

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
