"""HTTP views: notifications (split from booking/views.py on 2026-10-25)."""

from django.conf import settings  # Sprint 3 (1.19.0): site email capability.
from ..serializers import NotificationPreferencesSerializer  # Sprint 3 (1.19.0)
from ._common import *  # noqa: F401,F403 - shared imports, helpers and PublicView.

__all__ = ["NotificationListView", "NotificationReadView", "NotificationReadAllView", "NotificationPreferencesView"]

class NotificationListView(APIView):
    def get(self, request):
        service = get_service()
        service.process_due_requests()
        data = validated(NotificationQuerySerializer, request.query_params)
        items, unread = service.list_notifications(request.user, data["unread"], data["limit"])
        return Response({"count": len(items), "unread_count": unread, "results": json_value(items)})

class NotificationPreferencesView(APIView):
    """Sprint 3 (1.19.0): independent bell/email settings for the signed-in person."""

    def get(self, request):
        return Response({"results": get_service().notification_preferences(request.user), "email_available": bool(settings.EMAIL_ENABLED)})

    def put(self, request):
        data = validated(NotificationPreferencesSerializer, request.data)
        return Response({"results": get_service().save_notification_preferences(request.user, data["preferences"]), "email_available": bool(settings.EMAIL_ENABLED)})

class NotificationReadView(APIView):
    def post(self, request, notification_id):
        return Response(json_value(get_service().mark_notification_read(request.user, str(notification_id))))

class NotificationReadAllView(APIView):
    def post(self, request):
        return Response({"updated": get_service().mark_all_notifications_read(request.user)})
