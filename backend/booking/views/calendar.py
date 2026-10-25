"""HTTP views: calendar (split from booking/views.py on 2026-10-25)."""

from ._common import *  # noqa: F401,F403 - shared imports, helpers and PublicView.

__all__ = ["calendar_link_json", "CalendarLinkView", "CalendarLinkResetView", "CalendarFeedView"]

def calendar_link_json(feed):
    return {"path": f"/api/v1/calendar/{feed.token}.ics", "created_at": json_value(feed.created_at)}

class CalendarLinkView(APIView):
    """The signed-in person's secret calendar subscription address (created on first use)."""
    def get(self, request):
        return Response(calendar_link_json(get_service().calendar_feed(request.user)))

class CalendarLinkResetView(APIView):
    """Make a new address; the old one stops working at once."""
    def post(self, request):
        return Response(calendar_link_json(get_service().calendar_feed(request.user, reset=True)))

class CalendarFeedView(PublicView):
    """iCalendar feed read by Outlook / Google / Apple Calendar. The token in the address is the only key."""
    def get(self, request, token):
        service = get_service()
        person, events = service.calendar_feed_events(token)
        body = render_calendar(f"SmartLab bookings ({person.display_name})", events, service.now())
        response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = 'inline; filename="smartlab-bookings.ics"'
        response["Cache-Control"] = "no-store"
        return response


# Sprint 3: notifications ------------------------------------------------------------------------------------
