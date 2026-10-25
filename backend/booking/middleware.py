import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse

class CorsMiddleware:
    """Explicit development origins; authentication uses Bearer, not cookies."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get("Origin")
        permitted = origin in settings.CORS_ALLOWED_ORIGINS
        if request.method == "OPTIONS" and request.headers.get("Access-Control-Request-Method"):
            response = HttpResponse(status=204 if permitted else 403)
        else:
            response = self.get_response(request)
        if request.path.startswith("/api/") and response.status_code >= 400 and "application/json" not in response.get("Content-Type", ""):
            codes = {400: "BAD_REQUEST", 403: "FORBIDDEN", 404: "NOT_FOUND", 413: "FILE_TOO_LARGE", 500: "INTERNAL_ERROR"}
            response = JsonResponse({"error": {"code": codes.get(response.status_code, "API_ERROR"),
                                              "message": "The API request could not be completed.", "details": {}}}, status=response.status_code)
        if permitted:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Idempotency-Key"
            response["Access-Control-Expose-Headers"] = "Content-Disposition"
            response["Vary"] = "Origin"
        return response


class NotificationDeliveryMiddleware:
    """Sprint 3: after each API request, send its new notifications through extra channels (booking/notification_channels.py).

    Runs after the view, so the database transaction that stored the notifications has finished. Always clears the
    per-request list, even when no channel is configured.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            try:
                from .notification_channels import deliver_new_notifications
                from .runtime import get_service
                deliver_new_notifications(get_service())
            except Exception:  # delivery problems never change the API response
                logging.getLogger(__name__).exception("Notification delivery failed")
        return response
