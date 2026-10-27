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
Emails are sent on a background thread (``EmailOutbox``), so the website does not wait for Gmail.
Configuration: ``backend/docs/email-setup.md``.
"""
import atexit
import logging
import threading
import time
from collections import deque

from django.conf import settings
from django.core.mail import EmailMessage, get_connection

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


def _ms(since):
    return round((time.monotonic() - since) * 1000)


class EmailOutbox:
    """Sends finished emails on one background thread per server process (2026-10-27, performance P1–P3).

    Connecting and signing in to Gmail takes about 1.9 s from the EC2 server, and every API request used to wait for
    it before answering. Now the request only queues the message. The thread sends everything that is waiting over
    one SMTP connection and logs each result. An email still queued when the process is killed is lost; on a normal
    shutdown (gunicorn restart, ``docker compose down``) the process first waits up to EMAIL_TIMEOUT seconds.
    """
    BATCH_WINDOW_SECONDS = 0.2  # emails from the same request arrive within this time and share one connection

    def __init__(self):
        self._items = deque()
        self._changed = threading.Condition()
        self._pending = 0  # queued or being sent
        self._thread = None

    def put(self, message: EmailMessage, notification_id) -> None:
        with self._changed:
            self._items.append((message, notification_id, time.monotonic()))
            self._pending += 1
            self._changed.notify_all()
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="smartlab-email", daemon=True)
                self._thread.start()

    def wait(self, timeout=None) -> bool:
        """Until every queued email has been sent or has failed; False when ``timeout`` seconds pass first."""
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._changed:
            while self._pending:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._changed.wait(remaining)
        return True

    def _run(self):
        while True:
            with self._changed:
                while not self._items:
                    self._changed.wait()
            time.sleep(self.BATCH_WINDOW_SECONDS)
            with self._changed:
                batch = list(self._items)
                self._items.clear()
            try:
                self._send(batch)
            except Exception:  # the thread must keep running for later emails
                logger.exception("Sending %d email(s) failed", len(batch))
            finally:
                with self._changed:
                    self._pending -= len(batch)
                    self._changed.notify_all()

    def _send(self, batch):
        started = time.monotonic()
        connection = get_connection(fail_silently=False)
        try:
            connection.open()
        except Exception:  # logged only: the booking changes are already saved
            logger.exception("Could not connect to the mail server; %d email(s) not sent (notifications %s)",
                             len(batch), ", ".join(str(item[1]) for item in batch))
            return
        logger.info("Mail server connection opened in %d ms for %d email(s)", _ms(started), len(batch))
        try:
            for message, notification_id, queued_at in batch:
                sending = time.monotonic()
                try:
                    connection.send_messages([message])
                except Exception:  # logged only: the booking change is already saved
                    logger.exception("Email to %s failed for notification %s", message.to[0], notification_id)
                    connection.close()  # the next email opens a fresh connection
                    continue
                logger.info("Email sent for notification %s to @%s: waited %d ms, sent in %d ms", notification_id,
                            message.to[0].rpartition("@")[2], round((sending - queued_at) * 1000), _ms(sending))
        finally:
            connection.close()


outbox = EmailOutbox()


@atexit.register
def _send_the_rest_before_exit():
    outbox.wait(settings.EMAIL_TIMEOUT)


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
        outbox.put(EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, [address]), notification.id)

    def wait(self, timeout=None) -> bool:
        return outbox.wait(timeout)
