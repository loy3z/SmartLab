"""Sprint 3 (1.16.0): "Today" page for Admins and Managers: what needs doing first, in one call.

Everything here is a count or a short list taken from the same records the other staff pages use, so each card can
link to the page that handles it. Nothing is changed by reading it (apart from the usual time processing).
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..domain import BookingStatus, QualificationStatus, ResourceStatus, Role, UnfreezeStatus
from .base import ACTIVE_REQUEST_STATUSES, UNDECIDED_STATUSES

DUE_SOON_HOURS = 6   # pending requests whose review window ends within this many hours are listed first
LIST_LIMIT = 10      # longest list shown on a card; the full list is on the linked page
_SYDNEY = ZoneInfo("Australia/Sydney")


class OverviewMixin:
    def staff_overview(self, actor):
        """Counts and short lists for the staff home page.

        - pending_inductions: evidence waiting for review.
        - pending_bookings / urgent_requests / waitlisted: undecided booking requests (urgent ones only a Manager decides).
        - due_soon: pending requests whose review window ends within DUE_SOON_HOURS, soonest first.
        - unfreeze_requests: people asking for their booking freeze to be lifted.
        - out_of_service: resources under maintenance or closed, with how many future bookings or requests they still have.
        - today: approved bookings starting today (Sydney), in time order; missed_today counts those marked as missed.
        - changes_waiting: change requests (people asking to move a booking) still undecided.
        """
        self.require_staff(actor)
        self.process_due_requests()
        now = self.now()
        local_today = now.astimezone(_SYDNEY).date()
        day_start = datetime.combine(local_today, time(0), _SYDNEY)
        day_end = day_start + timedelta(days=1)
        # 2026-10-29 (load test S5): read every undecided request, approved bookings that have not ended and
        # today's approved bookings, instead of every booking ever made. Each count below still applies its own checks.
        bookings = list({item.id: item for query in (
            self.repo.list_bookings(statuses=UNDECIDED_STATUSES),
            self.repo.list_bookings(statuses=[BookingStatus.APPROVED], end_from=now),
            self.repo.list_bookings(statuses=[BookingStatus.APPROVED], start_from=day_start, start_to=day_end),
        ) for item in query}.values())
        undecided = [item for item in bookings if item.status == BookingStatus.PENDING_APPROVAL]
        due_limit = now + timedelta(hours=DUE_SOON_HOURS)
        due_soon = sorted((item for item in undecided if item.review_due_at and item.review_due_at <= due_limit),
                          key=lambda item: (item.review_due_at, item.id))
        today = sorted((item for item in bookings if item.status == BookingStatus.APPROVED and day_start <= item.start < day_end),
                       key=lambda item: (item.start, item.id))
        out_of_service = []
        for resource in sorted(self.repo.list_resources(), key=lambda item: item.name.casefold()):
            if not resource.active or resource.status == ResourceStatus.AVAILABLE:
                continue
            affected = sum(1 for item in bookings if item.resource_id == resource.id
                           and item.status in ACTIVE_REQUEST_STATUSES and item.end > now)
            out_of_service.append({"resource": resource, "affected_bookings": affected})
        return {
            "role": actor.role.value,
            "pending_inductions": sum(1 for item in self.repo.list_submissions() if item.status == QualificationStatus.PENDING),
            "pending_bookings": sum(1 for item in undecided if not item.urgent),
            "urgent_requests": sum(1 for item in undecided if item.urgent),
            "waitlisted": sum(1 for item in bookings if item.status == BookingStatus.WAITLISTED),
            "changes_waiting": sum(1 for item in bookings if item.replaces_id and item.status in (
                BookingStatus.PENDING_APPROVAL, BookingStatus.WAITLISTED)),
            "due_soon": due_soon[:LIST_LIMIT],
            "due_soon_hours": DUE_SOON_HOURS,
            "unfreeze_requests": sum(1 for item in self.repo.list_unfreeze_requests() if item.status == UnfreezeStatus.PENDING),
            "out_of_service": out_of_service,
            "today": today[:LIST_LIMIT],
            "today_count": len(today),
            "missed_today": sum(1 for item in today if item.attendance == "NO_SHOW"),
            "can_decide_urgent": actor.role == Role.MANAGER,
        }
