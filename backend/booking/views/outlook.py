"""HTTP views: outlook (split from booking/views.py on 2026-10-25)."""

from ._common import *  # noqa: F401,F403 - shared imports, helpers and PublicView.

__all__ = ["OutlookStatusView", "OutlookCheckView", "OutlookProcessView", "OutlookRetryView"]

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
