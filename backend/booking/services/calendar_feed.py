"""Sprint 3: Calendar subscription link: each person's approved bookings as an iCalendar feed (see booking/ics.py).

The link contains a random token generated here; it is the only key to the feed, so a person can make a new one
at any time and the old link stops working. No Microsoft sign-in or permission is involved.
"""
import secrets
from dataclasses import replace
from datetime import timedelta

from ..domain import BookingStatus, CalendarFeed
from ..errors import DomainError

# Approved bookings that ended up to this long ago stay in the feed (so last week's entries do not vanish).
FEED_HISTORY = timedelta(days=60)


class CalendarFeedMixin:
    def calendar_feed(self, actor, reset=False):
        """The person's subscription token, created on first use. reset=True replaces it (the old link stops)."""
        self.require_booking_user(actor)
        with self.repo.atomic(student_ids=[actor.id]):
            feed = self.repo.get_calendar_feed(actor.id)
            if feed is None or reset:
                token = secrets.token_urlsafe(24)
                feed = (CalendarFeed(actor.id, token, self.now()) if feed is None
                        else replace(feed, token=token, created_at=self.now()))
                self.repo.save_calendar_feed(feed)
                if reset:
                    self._audit(actor.id, "CALENDAR_LINK_RESET", "principal", actor.id)
            return feed

    def calendar_feed_events(self, token):
        """(person, [(booking, resource, person, creator)]) for a subscription token; 404 for an unknown token."""
        feed = self.repo.get_calendar_feed_by_token(token) if token else None
        person = self.repo.get_principal(feed.principal_id) if feed else None
        if person is None or not person.active:
            raise DomainError("NOT_FOUND", "Calendar not found.", 404)
        self.process_due_requests()
        since = self.now() - FEED_HISTORY
        events = []
        for booking in sorted(self.repo.list_bookings(student_id=person.id), key=lambda item: (item.start, item.id)):
            if booking.status == BookingStatus.APPROVED and booking.end >= since:
                creator = self.repo.get_principal(booking.created_by) if booking.created_by else None
                events.append((booking, self.repo.get_resource(booking.resource_id), person, creator))
        return person, events
