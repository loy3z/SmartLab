"""Microsoft Graph adapter. Booking authentication is independent of Graph OAuth."""
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from threading import RLock
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


class OutlookError(Exception):
    """Safe error code only: Graph bodies can contain credentials or user data."""

    def __init__(self, code, retry_after=30):
        self.code = code
        self.retry_after = max(1, min(int(retry_after), 3600))
        super().__init__(code)


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    web_link: str | None = None


class CalendarProvider(Protocol):
    @property
    def configured(self) -> bool: ...
    def target_path(self) -> str: ...
    def create_event(self, booking, resource, calendar_path: str) -> CalendarEvent: ...
    def delete_event(self, calendar_path: str, event_id: str) -> None: ...


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward OAuth credentials/Bearer headers to redirected hosts.
        return None


class GraphTransport:
    def __init__(self, timeout=8):
        self.timeout = timeout
        self.opener = build_opener(NoRedirects())

    def request(self, method, url, headers=None, json_body=None, form_body=None):
        headers = dict(headers or {})
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif form_body is not None:
            data = urlencode(form_body).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            with self.opener.open(Request(url, data=data, headers=headers, method=method), timeout=self.timeout) as response:
                body = response.read(1024 * 1024 + 1)
                if len(body) > 1024 * 1024:
                    raise OutlookError("GRAPH_INVALID_RESPONSE")
                return json.loads(body) if body else {}
        except HTTPError as exc:
            retry = exc.headers.get("Retry-After", "30") if exc.headers else "30"
            raise OutlookError(f"GRAPH_HTTP_{exc.code}", int(retry) if retry.isdigit() else 30) from None
        except (URLError, TimeoutError, OSError):
            raise OutlookError("GRAPH_NETWORK_ERROR") from None
        except (ValueError, UnicodeError):
            raise OutlookError("GRAPH_INVALID_RESPONSE") from None


class MicrosoftGraphCalendar:
    def __init__(self, access_token="", token_file="", tenant_id="", client_id="", client_secret="",
                 mailbox="", calendar_id="", timeout=8, transport=None):
        self.access_token, self.token_file = access_token, token_file
        self.tenant_id, self.client_id, self.client_secret = tenant_id, client_id, client_secret
        self.mailbox, self.calendar_id = mailbox, calendar_id
        self.transport = transport or GraphTransport(timeout)
        self._cached_token, self._expires_at = None, 0
        self._lock = RLock()

    @property
    def mode(self):
        if self.access_token or (self.token_file and Path(self.token_file).is_file()):
            return "delegated_token"
        return "application" if self.tenant_id and self.client_id and self.client_secret else "unconfigured"

    @property
    def configured(self):
        if self.access_token:
            return True
        if self.token_file and Path(self.token_file).is_file():
            return True
        return bool(self.tenant_id and self.client_id and self.client_secret and self.mailbox)

    def target_path(self):
        # /me is valid for a delegated personal-account token, never app-only.
        root = f"/users/{quote(self.mailbox, safe='')}" if self.mailbox else "/me"
        calendar = f"/calendars/{quote(self.calendar_id, safe='')}" if self.calendar_id else "/calendar"
        return root + calendar + "/events"

    def _token(self):
        if self.access_token:
            return self.access_token
        if self.token_file and Path(self.token_file).is_file():
            try:
                token = Path(self.token_file).read_text(encoding="utf-8").strip()
            except OSError:
                raise OutlookError("OUTLOOK_NOT_CONFIGURED") from None
            if not token or "\n" in token or "\r" in token:
                raise OutlookError("OUTLOOK_INVALID_TOKEN_FILE")
            return token
        if not self.configured or not re.fullmatch(r"[A-Za-z0-9.-]+", self.tenant_id):
            raise OutlookError("OUTLOOK_NOT_CONFIGURED")
        with self._lock:
            if self._cached_token and time.monotonic() < self._expires_at:
                return self._cached_token
            result = self.transport.request("POST", f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
                form_body={"client_id": self.client_id, "client_secret": self.client_secret,
                           "grant_type": "client_credentials", "scope": "https://graph.microsoft.com/.default"})
            if not isinstance(result, dict) or not isinstance(result.get("access_token"), str) or not result["access_token"]:
                raise OutlookError("GRAPH_INVALID_TOKEN_RESPONSE")
            try:
                lifetime = max(0, int(result.get("expires_in", 0)) - 60)
            except (TypeError, ValueError):
                raise OutlookError("GRAPH_INVALID_TOKEN_RESPONSE") from None
            self._cached_token = result["access_token"]
            self._expires_at = time.monotonic() + lifetime
            return self._cached_token

    def _request(self, method, path, body=None):
        if not re.fullmatch(r"/(?:me|users/[^/]+)/calendar(?:s/[^/]+)?/events(?:/[^/]+)?", path):
            raise OutlookError("OUTLOOK_INVALID_CALENDAR_PATH")
        headers = {"Authorization": f"Bearer {self._token()}", "Prefer": 'IdType="ImmutableId"'}
        try:
            return self.transport.request(method, "https://graph.microsoft.com/v1.0" + path, headers, json_body=body)
        except OutlookError as exc:
            if exc.code == "GRAPH_HTTP_401":
                self._cached_token, self._expires_at = None, 0
            raise

    def create_event(self, booking, resource, calendar_path):
        body = {
            "subject": f"SmartLab booking: {resource.name}",
            "body": {"contentType": "text", "content": f"Booking reference: {booking.id}\nManaged by SmartLab."},
            "start": {"dateTime": booking.start.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds"), "timeZone": "UTC"},
            "end": {"dateTime": booking.end.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds"), "timeZone": "UTC"},
            "location": {"displayName": resource.location},
            "showAs": "busy",
            "transactionId": booking.id,
            "isReminderOn": True,
            "reminderMinutesBeforeStart": 15,
        }
        result = self._request("POST", calendar_path, body)
        if not isinstance(result, dict) or not isinstance(result.get("id"), str) or not result["id"]:
            raise OutlookError("GRAPH_INVALID_EVENT_RESPONSE")
        link = result.get("webLink")
        if not isinstance(link, str) or not link.startswith(("https://outlook.live.com/", "https://outlook.office365.com/", "https://outlook.office.com/")):
            link = None
        return CalendarEvent(result["id"], link)

    def delete_event(self, calendar_path, event_id):
        try:
            self._request("DELETE", calendar_path + "/" + quote(event_id, safe=""))
        except OutlookError as exc:
            if exc.code != "GRAPH_HTTP_404":
                raise


def make_graph_calendar():
    from django.conf import settings
    return MicrosoftGraphCalendar(access_token=settings.OUTLOOK_ACCESS_TOKEN, token_file=settings.OUTLOOK_TOKEN_FILE,
        tenant_id=settings.OUTLOOK_TENANT_ID, client_id=settings.OUTLOOK_CLIENT_ID,
        client_secret=settings.OUTLOOK_CLIENT_SECRET, mailbox=settings.OUTLOOK_MAILBOX,
        calendar_id=settings.OUTLOOK_CALENDAR_ID, timeout=settings.OUTLOOK_HTTP_TIMEOUT_SECONDS)
