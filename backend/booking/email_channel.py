"""Sprint 3: email delivery channel for notifications (system Gmail mailbox over SMTP).

How it fits in (nothing in the booking rules changes):

1. A service creates a Notification record as before (it shows under the bell on the website).
2. After the request, ``deliver_new_notifications`` hands each new notification to every configured channel.
3. This channel turns the notification into one plain-text email to the person's university address.

Which notifications are emailed: the kinds in ``EMAIL_NOTIFICATION_KINDS`` (request received, approved, rejected,
expired, promoted from the waitlist, rescheduled, cancelled by staff, reminders, booked for you).

Who actually receives it depends on ``EMAIL_MODE``, so a demo never mails real students by accident:

- ``none``: send nothing (the channel is on but silent).
- ``allowlist`` (default): send only to the addresses in ``EMAIL_ALLOWED_RECIPIENTS``; skip everyone else.
- ``redirect``: send every email to ``EMAIL_REDIRECT_TO`` instead; the body says who it was meant for.
- ``all``: send to the person's university email.

Problems (wrong password, no network, Gmail limits) are logged and never undo the booking change.
Configuration: ``backend/docs/email-setup.md``.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail

from .domain import Notification, Principal

logger = logging.getLogger(__name__)

MODES = ("none", "allowlist", "redirect", "all")


def email_mode():
    mode = (settings.EMAIL_MODE or "allowlist").strip().lower()
    return mode if mode in MODES else "none"  # an unknown mode sends nothing rather than guessing


def _addresses(values):
    return {value.strip().lower() for value in values if value and value.strip()}


def choose_recipient(address):
    """Where an email meant for ``address`` goes under the current mode, or None when it is skipped."""
    mode = email_mode()
    if mode == "all":
        return address
    if mode == "allowlist":
        return address if address.strip().lower() in _addresses(settings.EMAIL_ALLOWED_RECIPIENTS) else None
    if mode == "redirect":
        return settings.EMAIL_REDIRECT_TO.strip() or None
    return None


def booking_label(notification):
    """Like "Lab Room 1, Mon 3 Nov 2025, 10:00–11:00" for the subject line; empty without a booking."""
    if not notification.booking_id:
        return ""
    try:
        from .runtime import get_service  # late import: the channel is loaded while the service is being built
        service = get_service()
        booking = service.repo.get_booking(notification.booking_id)
        if booking is None:
            return ""
        resource = service.repo.get_resource(booking.resource_id)
        return f"{resource.name if resource else 'Resource'}, {service.describe_time(booking, resource)}"
    except Exception:  # the subject is still useful without the label
        logger.exception("Could not describe booking %s for an email subject", notification.booking_id)
        return ""


def site_link(notification):
    """Full address of the page the notification points to (the web app uses hash routes: /#/bookings)."""
    base = settings.SITE_URL.rstrip("/")
    return f"{base}/#{notification.link}" if notification.link else f"{base}/"


def compose(notification: Notification, recipient: Principal, sent_to: str):
    """Subject and body of the email. Kept separate so tests and the docs can show exactly what is sent."""
    label = booking_label(notification)
    subject = f"SmartLab: {notification.title}" + (f" – {label}" if label else "")
    lines = [f"Hi {recipient.display_name},", "", notification.body, "", f"Open SmartLab: {site_link(notification)}"]
    if sent_to.strip().lower() != recipient.university_email.strip().lower():
        lines += ["", f"(Demo redirect: this email was meant for {recipient.zid} <{recipient.university_email}>.)"]
    lines += ["", "This is an automatic message from SmartLab. Please do not reply."]
    return subject, "\n".join(lines)


class EmailChannel:
    """NotificationChannel that emails selected notifications. Turned on by EMAIL_ENABLED=true."""
    name = "email"

    def deliver(self, notification: Notification, recipient: Principal) -> None:
        if notification.kind not in settings.EMAIL_NOTIFICATION_KINDS:
            return
        address = choose_recipient(recipient.university_email)
        if not address:
            logger.info("Email skipped for %s (%s): EMAIL_MODE=%s", recipient.zid, notification.kind, email_mode())
            return
        subject, body = compose(notification, recipient, address)
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [address], fail_silently=False)
        except Exception:  # logged only: the booking change is already saved
            logger.exception("Email to %s failed for notification %s", address, notification.id)
