"""Durable email notification delivery through a system SMTP mailbox.

The booking transaction stores both the website notification and an ``EmailDelivery`` outbox row. API workers only
wake a background sender after commit; the scheduler also processes due rows. SMTP failures therefore never undo a
booking and no longer disappear on process restart.
"""

import logging
import os
import socket
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from django.conf import settings
from django.core.mail import EmailMessage, get_connection

from .domain import EmailDelivery, Notification, Principal

logger = logging.getLogger(__name__)

MODES = ("none", "allowlist", "redirect", "all")
RETRY_DELAYS_SECONDS = (60, 300, 900, 3600)


def email_mode():
    mode = (settings.EMAIL_MODE or "allowlist").strip().lower()
    return mode if mode in MODES else "none"


def _addresses(values):
    return {value.strip().lower() for value in values if value and value.strip()}


def choose_recipient(address):
    """Return the permitted destination, or None when the current safety mode skips it."""
    mode = email_mode()
    if mode == "all":
        return address
    if mode == "allowlist":
        return address if address.strip().lower() in _addresses(settings.EMAIL_ALLOWED_RECIPIENTS) else None
    if mode == "redirect":
        return settings.EMAIL_REDIRECT_TO.strip() or None
    return None


def booking_label(notification, service=None):
    """Build the optional resource/time suffix used in email subjects."""
    if not notification.booking_id:
        return ""
    try:
        if service is None:
            from .runtime import get_service
            service = get_service()
        booking = service.repo.get_booking(notification.booking_id)
        if booking is None:
            return ""
        resource = service.repo.get_resource(booking.resource_id)
        return f"{resource.name if resource else 'Resource'}, {service.describe_time(booking, resource)}"
    except Exception:
        logger.exception("Could not describe booking %s for an email subject", notification.booking_id)
        return ""


def site_link(notification):
    base = settings.SITE_URL.rstrip("/")
    return f"{base}/#{notification.link}" if notification.link else f"{base}/"


def compose(notification: Notification, recipient: Principal, sent_to: str, service=None):
    """Render a stable message snapshot before it enters the durable outbox."""
    label = booking_label(notification, service)
    subject = f"SmartLab: {notification.title}" + (f" – {label}" if label else "")
    lines = [f"Hi {recipient.display_name},", "", notification.body, "", f"Open SmartLab: {site_link(notification)}"]
    if sent_to.strip().lower() != recipient.university_email.strip().lower():
        lines += ["", f"(Demo redirect: this email was meant for {recipient.zid} <{recipient.university_email}>.)"]
    lines += ["", "This is an automatic message from SmartLab. Please do not reply."]
    return subject, "\n".join(lines)


def _error_text(exc):
    """Keep diagnostics useful without allowing an unbounded provider response into the database."""
    return f"{type(exc).__name__}: {exc}"[:500]


class EmailDeliveryService:
    """Transactional outbox scheduling, leasing, SMTP delivery and bounded retry."""

    def __init__(self, booking_service, clock=None, worker_id=None):
        self.booking_service = booking_service
        self.repo = booking_service.repo
        self.clock = clock or (lambda: datetime.now(UTC))
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
        self._schedule_lock = threading.Lock()
        self._last_created_at = None

    def now(self):
        return self.clock().astimezone(UTC)

    @staticmethod
    def enabled():
        return "booking.email_channel.EmailChannel" in settings.NOTIFICATION_CHANNELS

    def schedule(self, notification):
        """Called inside the business transaction so the notification and outbox row commit together."""
        from .test_console import TEST_ACCOUNT_ID
        if (not self.enabled() or not notification.email
                or notification.recipient_id == TEST_ACCOUNT_ID
                or notification.kind not in settings.EMAIL_NOTIFICATION_KINDS):
            return None
        existing = self.repo.get_email_delivery(notification.id)
        if existing is not None:
            return existing
        recipient = self.repo.get_principal(notification.recipient_id)
        if recipient is None:
            return None
        address = choose_recipient(recipient.university_email)
        if not address:
            logger.info("Email skipped for %s (%s): EMAIL_MODE=%s", recipient.zid,
                        notification.kind, email_mode())
            return None
        subject, body = compose(notification, recipient, address, self.booking_service)
        # Keep FIFO order stable even when tests freeze the business clock and create several notices at once.
        with self._schedule_lock:
            now = self.now()
            if self._last_created_at is not None and now <= self._last_created_at:
                now = self._last_created_at + timedelta(microseconds=1)
            self._last_created_at = now
        delivery = EmailDelivery(notification.id, address, subject, body, "PENDING", now, now)
        self.repo.save_email_delivery(delivery)
        return delivery

    def process_pending(self, limit=50):
        if not self.enabled() or limit <= 0:
            return []
        now = self.now()
        claimed = self.repo.claim_email_deliveries(
            now, limit, self.worker_id, now + timedelta(seconds=settings.EMAIL_LEASE_SECONDS))
        if not claimed:
            return []
        connection = get_connection(fail_silently=False)
        started = time.monotonic()
        try:
            connection.open()
        except Exception as exc:
            logger.exception("Could not connect to the mail server; %d durable email(s) will retry", len(claimed))
            for delivery in claimed:
                self._failed(delivery, exc)
            return [self.repo.get_email_delivery(item.notification_id) for item in claimed]
        logger.info("Mail server connection opened in %d ms for %d durable email(s)",
                    round((time.monotonic() - started) * 1000), len(claimed))
        try:
            for delivery in claimed:
                sending = time.monotonic()
                try:
                    count = connection.send_messages([
                        EmailMessage(delivery.subject, delivery.body, settings.DEFAULT_FROM_EMAIL,
                                     [delivery.recipient_email])
                    ])
                    if count != 1:
                        raise RuntimeError("SMTP backend did not confirm delivery")
                except Exception as exc:
                    logger.exception("Email failed for notification %s", delivery.notification_id)
                    self._failed(delivery, exc)
                    continue
                self._succeeded(delivery)
                waited = max(0, round((self.now() - delivery.created_at).total_seconds() * 1000))
                logger.info("Email sent for notification %s to @%s: waited %d ms, sent in %d ms",
                            delivery.notification_id,
                            delivery.recipient_email.rpartition("@")[2],
                            waited,
                            round((time.monotonic() - sending) * 1000))
        finally:
            connection.close()
        return [self.repo.get_email_delivery(item.notification_id) for item in claimed]

    def _save_if_owned(self, claimed, **changes):
        """Ignore a stale worker whose lease expired and was recovered by another process."""
        with self.repo.atomic():
            latest = self.repo.get_email_delivery(claimed.notification_id)
            if (latest is None or latest.status != "IN_PROGRESS"
                    or latest.worker_id != self.worker_id or latest.attempts != claimed.attempts):
                return latest
            latest = replace(latest, updated_at=self.now(), **changes)
            self.repo.save_email_delivery(latest)
            return latest

    def _succeeded(self, claimed):
        now = self.now()
        return self._save_if_owned(claimed, status="SENT", sent_at=now, next_attempt_at=None,
                                   lease_until=None, worker_id=None, last_error=None)

    def _failed(self, claimed, exc):
        terminal = claimed.attempts >= settings.EMAIL_MAX_ATTEMPTS
        delay_index = min(max(claimed.attempts - 1, 0), len(RETRY_DELAYS_SECONDS) - 1)
        next_attempt = None if terminal else self.now() + timedelta(seconds=RETRY_DELAYS_SECONDS[delay_index])
        return self._save_if_owned(claimed, status="FAILED" if terminal else "RETRY",
                                   next_attempt_at=next_attempt, lease_until=None, worker_id=None,
                                   last_error=_error_text(exc))


class EmailOutbox:
    """Fast post-commit wake-up for the durable queue; PostgreSQL remains the source of truth."""

    BATCH_WINDOW_SECONDS = 0.2

    def __init__(self):
        self._changed = threading.Condition()
        self._queued_wakeups = 0
        self._active_wakeups = 0
        self._thread = None

    def put(self, _notification_id) -> None:
        with self._changed:
            self._queued_wakeups += 1
            self._changed.notify_all()
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="smartlab-email", daemon=True)
                self._thread.start()

    def wait(self, timeout=None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._changed:
            while self._queued_wakeups or self._active_wakeups:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._changed.wait(remaining)
        return True

    def _run(self):
        while True:
            with self._changed:
                while not self._queued_wakeups:
                    self._changed.wait()
            time.sleep(self.BATCH_WINDOW_SECONDS)
            with self._changed:
                wakeups = self._queued_wakeups
                self._queued_wakeups = 0
                self._active_wakeups += wakeups
            try:
                from .runtime import get_service
                get_service().email_delivery.process_pending(max(settings.EMAIL_BATCH_SIZE, wakeups))
            except Exception:
                logger.exception("Durable email worker failed; the scheduler will recover leased work")
            finally:
                with self._changed:
                    self._active_wakeups -= wakeups
                    self._changed.notify_all()


outbox = EmailOutbox()


class EmailChannel:
    """Post-commit notification channel that wakes the durable SMTP worker."""

    name = "email"

    def deliver(self, notification: Notification, _recipient: Principal) -> None:
        # The durable row was already written in the transaction. A missing row means the kind/address was skipped.
        from .runtime import get_service
        if get_service().repo.get_email_delivery(notification.id) is not None:
            outbox.put(notification.id)

    def wait(self, timeout=None) -> bool:
        return outbox.wait(timeout)
