"""Sprint 3: usage report for Admins and Managers (how much each room and piece of equipment is used).

For a range of local dates, one row per resource (archived ones too, if they had bookings):
- approved: approved bookings starting in the range, and booked_hours, their total length;
- open_hours: opening hours in the range, and utilisation = booked_hours / open_hours;
- attendance of approved bookings that already happened: checked_in, no_show, excused, not_tracked, and
  attendance_rate = checked_in / (checked_in + no_show) (None when nothing could be counted yet);
- cancelled and rejected: requests in the range that did not go ahead.
Only reads data; nothing is changed.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..domain import BookingStatus
from ..errors import DomainError

MAX_REPORT_DAYS = 366


def _hours(minutes):
    return round(minutes / 60, 2)


class ReportsMixin:
    def usage_report(self, actor, first_date, last_date):
        self.require_staff(actor)  # Admins and Managers (Booking Records page)
        if last_date < first_date or (last_date - first_date).days >= MAX_REPORT_DAYS:
            raise DomainError("VALIDATION_ERROR", f"Choose a range of 1 to {MAX_REPORT_DAYS} days, ending on or after its start.")
        self.process_due_requests()
        days = (last_date - first_date).days + 1
        rows, totals = [], dict(approved=0, booked_minutes=0, open_minutes=0, checked_in=0, no_show=0, excused=0,
                                not_tracked=0, cancelled=0, rejected=0)
        resources = {item.id: item for item in self.repo.list_resources()}
        for resource in sorted(resources.values(), key=lambda item: (item.kind.value != "ROOM", item.name.casefold())):
            zone = ZoneInfo(resource.timezone)
            start = datetime.combine(first_date, time(0), zone)
            end = start + timedelta(days=days)
            in_range = [item for item in self.repo.list_bookings(resource_id=resource.id) if start <= item.start < end]
            if not resource.active and not in_range:
                continue  # archived and unused in this range
            approved = [item for item in in_range if item.status == BookingStatus.APPROVED]
            happened = [item for item in approved if item.end <= self.now()]
            row = dict(
                approved=len(approved),
                booked_minutes=sum((item.end - item.start).total_seconds() / 60 for item in approved),
                open_minutes=days * ((resource.closing_time.hour * 60 + resource.closing_time.minute)
                                     - (resource.opening_time.hour * 60 + resource.opening_time.minute)),
                checked_in=sum(1 for item in happened if item.attendance == "CHECKED_IN"),
                no_show=sum(1 for item in happened if item.attendance == "NO_SHOW"),
                excused=sum(1 for item in happened if item.attendance == "EXCUSED"),
                not_tracked=sum(1 for item in happened if item.attendance in (None, "NOT_TRACKED")),
                cancelled=sum(1 for item in in_range if item.status == BookingStatus.CANCELLED),
                rejected=sum(1 for item in in_range if item.status == BookingStatus.REJECTED),
            )
            for key in totals:
                totals[key] += row[key]
            room = resources.get(resource.room_id) if resource.room_id else None
            rows.append({"resource_id": resource.id, "name": resource.name, "kind": resource.kind.value,
                         "category": resource.category, "room_name": room.name if room else None, "active": resource.active,
                         **self._usage_figures(row)})
        return {"first_date": first_date, "last_date": last_date, "days": days, "results": rows,
                "totals": self._usage_figures(totals)}

    @staticmethod
    def _usage_figures(row):
        counted = row["checked_in"] + row["no_show"]
        return {"approved": row["approved"], "booked_hours": _hours(row["booked_minutes"]), "open_hours": _hours(row["open_minutes"]),
                "utilisation": round(row["booked_minutes"] / row["open_minutes"], 3) if row["open_minutes"] else None,
                "checked_in": row["checked_in"], "no_show": row["no_show"], "excused": row["excused"],
                "not_tracked": row["not_tracked"], "attendance_rate": round(row["checked_in"] / counted, 3) if counted else None,
                "cancelled": row["cancelled"], "rejected": row["rejected"]}
