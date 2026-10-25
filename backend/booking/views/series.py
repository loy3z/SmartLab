"""HTTP views: series (split from booking/views.py on 2026-10-25)."""

from ._common import *  # noqa: F401,F403 - shared imports, helpers and PublicView.

__all__ = ["series_json", "_series_args", "SeriesPreviewView", "SeriesCreateView", "SeriesDetailView", "SeriesCancelView"]

def series_json(series, bookings):
    return {**json_value(series), "weekdays": [int(item) for item in series.weekdays.split(",") if item],
            "bookings": json_value(bookings)}

def _series_args(data):
    return dict(resource_id=str(data["resource_id"]), weekdays=data["weekdays"], start_time=data["start_time"],
                duration_minutes=data["duration_minutes"], first_date=data["first_date"], last_date=data["last_date"],
                on_behalf_of_zid=data.get("on_behalf_of_zid") or None)

class SeriesPreviewView(APIView):
    def post(self, request):
        data = validated(SeriesPlanSerializer, request.data)
        return Response(json_value(get_service().preview_series(request.user, **_series_args(data))))

class SeriesCreateView(APIView):
    def post(self, request):
        service = get_service()
        data = validated(SeriesCreateSerializer, request.data)
        series, bookings = service.create_series(request.user, purpose=data["purpose"], skip_dates=data["skip_dates"],
                                                 **_series_args(data))
        bookings = sync_after_write(service, *bookings)
        return Response(series_json(series, bookings), status=status.HTTP_201_CREATED)

class SeriesDetailView(APIView):
    def get(self, request, series_id):
        service = get_service()
        service.process_due_requests()
        return Response(series_json(*service.series_detail(request.user, str(series_id))))

class SeriesCancelView(APIView):
    def post(self, request, series_id):
        if request.data:
            raise DomainError("VALIDATION_ERROR", "The cancellation action does not accept extra fields.")
        service = get_service()
        series, cancelled = service.cancel_series(request.user, str(series_id))
        sync_after_write(service, *cancelled)
        return Response(series_json(*service.series_detail(request.user, series.id)))


# Sprint 3: resource setup (Manager) -------------------------------------------------------------------------
