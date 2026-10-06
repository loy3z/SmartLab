import json
from django.conf import settings
from django.http import JsonResponse
from django.urls import include, path

def schema(request):
    with (settings.BASE_DIR / "docs" / "openapi.json").open(encoding="utf-8") as source:
        return JsonResponse(json.load(source))

urlpatterns = [path("api/v1/", include("booking.urls")), path("api/schema/", schema)]
