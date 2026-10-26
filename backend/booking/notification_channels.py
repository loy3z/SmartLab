"""Sprint 3: Where notifications are delivered besides the website.

Every notification is stored first (the website shows it under the bell). Extra channels then send the same
notification somewhere else after the request's database transaction has finished. None is configured today.

To add one later (for example Outlook mail through Microsoft Graph ``sendMail`` from a system mailbox, or
plain email):

1. Write a class with a ``name`` and ``deliver(notification, recipient)``. It must not raise for ordinary
   delivery problems; log them instead, because the booking change has already been saved.
2. List its dotted path in the ``NOTIFICATION_CHANNELS`` environment variable.

No booking code changes: services only create Notification records.
"""
import logging
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string

from .domain import Notification, Principal
from .test_console import TEST_ACCOUNT_ID

logger = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    name: str

    def deliver(self, notification: Notification, recipient: Principal) -> None:
        """Send one stored notification to its recipient (e.g. as an email)."""


_channels = None


def configured_channels():
    global _channels
    if _channels is None:
        _channels = [import_string(path)() for path in settings.NOTIFICATION_CHANNELS]
    return _channels


def reset_channels():
    """Tests: read NOTIFICATION_CHANNELS again."""
    global _channels
    _channels = None


def deliver_new_notifications(service):
    """Send the notifications created during this request (or command run) through the extra channels."""
    ids = service.take_new_notification_ids()
    channels = configured_channels()
    if not ids or not channels:
        return 0
    sent = 0
    for notification_id in ids:
        notification = service.repo.get_notification(notification_id)
        recipient = service.repo.get_principal(notification.recipient_id) if notification else None
        if notification is None or not notification.email or recipient is None or recipient.id == TEST_ACCOUNT_ID:  # Sprint 3 (1.19.0)
            continue
        for channel in channels:
            try:
                channel.deliver(notification, recipient)
                sent += 1
            except Exception:  # one channel failing must not undo a saved booking change
                logger.exception("Notification channel %s failed for %s", getattr(channel, "name", channel), notification_id)
    return sent
