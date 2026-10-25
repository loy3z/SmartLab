"""Sprint 3: iCalendar (RFC 5545) text for a person's calendar subscription link.

Outlook, Google Calendar and Apple Calendar fetch the link themselves every few hours; the website stays the only
authority (the feed is read-only). Each booking keeps one UID, so a rescheduled booking replaces its old entry.
"""
from datetime import UTC

from .outlook import NOTICE


def _stamp(value):
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _text(value):
    return (str(value).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line):
    """Lines longer than 75 octets continue on the next line after a space (RFC 5545 3.1)."""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return [line]
    parts, current = [], b""
    for char in line:
        encoded = char.encode("utf-8")
        if len(current) + len(encoded) > (75 if not parts else 74):
            parts.append(current.decode("utf-8"))
            current = b""
        current += encoded
    parts.append(current.decode("utf-8"))
    return [parts[0]] + [" " + part for part in parts[1:]]


def render_calendar(name, events, now):
    """events: (booking, resource, student, creator) tuples of approved bookings."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SmartLab//Booking calendar//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{_text(name)}", "X-WR-TIMEZONE:Australia/Sydney",
             "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H"]
    for booking, resource, student, creator in events:
        details = [f"Booked for: {student.display_name}" if student else None,
                   f"Booked by: {creator.display_name} (on behalf)" if creator and student and creator.id != student.id else None,
                   "Urgent request approved by a Manager" if booking.urgent else None,
                   "Weekly series" if booking.series_id else None,
                   f"Booking reference: {booking.id}", "Managed by SmartLab. " + NOTICE]
        lines += ["BEGIN:VEVENT", f"UID:{booking.id}@smartlab", f"DTSTAMP:{_stamp(now)}",
                  f"DTSTART:{_stamp(booking.start)}", f"DTEND:{_stamp(booking.end)}",
                  f"SUMMARY:{_text('SmartLab booking: ' + (resource.name if resource else 'Resource'))}",
                  f"LOCATION:{_text(resource.location if resource else '')}",
                  f"DESCRIPTION:{_text(chr(10).join(item for item in details if item))}",
                  f"SEQUENCE:{max(booking.revision - 1, 0)}", "STATUS:CONFIRMED", "TRANSP:OPAQUE"]
        if booking.updated_at:
            lines.append(f"LAST-MODIFIED:{_stamp(booking.updated_at)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(folded for line in lines for folded in _fold(line)) + "\r\n"
