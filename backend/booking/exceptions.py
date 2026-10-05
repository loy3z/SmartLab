from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from .errors import DomainError

def exception_handler(exc, context):
    if isinstance(exc, DomainError):
        return Response({"error": {"code": exc.code, "message": exc.message, "details": exc.details}}, status=exc.status)
    response = drf_exception_handler(exc, context)
    if response is not None:
        data = response.data
        detail = data.get("detail") if isinstance(data, dict) else None
        defaults = {400: "VALIDATION_ERROR", 401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 413: "FILE_TOO_LARGE", 415: "UNSUPPORTED_MEDIA_TYPE"}
        code = str(getattr(detail, "code", defaults.get(response.status_code, "API_ERROR"))).upper()
        message = str(detail) if detail else "Check the request fields."
        response.data = {"error": {"code": code, "message": message, "details": data if not detail else {}}}
        return response
    return Response({"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred.", "details": {}}}, status=500)
