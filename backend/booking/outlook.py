"""Microsoft Graph adapter. Booking authentication is independent of Graph OAuth.

Credentials (access tokens, refresh tokens, client secrets) never leave this module: errors carry a safe code
only, and nothing here logs or returns a token.
"""
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

# Delegated permission for the signed-in account's own calendar; offline_access returns a refresh token.
DELEGATED_SCOPE = "https://graph.microsoft.com/Calendars.ReadWrite offline_access"
INVITE_MODES = ("none", "allowlist", "all")
_EVENT_PATH = re.compile(r"/(?:me|users/[^/]+)/calendar(?:s/[^/]+)?/events(?:/[^/]+)?")
_CALENDAR_PATH = re.compile(r"/(?:me|users/[^/]+)/calendar(?:s/[^/]+)?")
_AUTHORITY = re.compile(r"[A-Za-z0-9.-]+")
_GRAPH_TIME = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?")
NOTICE = "Changes made in Outlook are not applied: manage this booking in SmartLab."


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
    ical_uid: str | None = None


@dataclass(frozen=True)
class EventSnapshot:
    """The fields the website owns. Anything else (notes, categories, reminders) may be edited freely."""
    start: datetime
    end: datetime
    subject: str
    location: str
    attendees: frozenset = field(default_factory=frozenset)
    cancelled: bool = False


def event_differences(expected: EventSnapshot, actual: EventSnapshot) -> list[str]:
    """Names of website-owned fields that differ in Outlook, in a fixed order."""
    names = []
    if actual.start != expected.start:
        names.append("start")
    if actual.end != expected.end:
        names.append("end")
    if actual.subject.strip() != expected.subject.strip():
        names.append("subject")
    if actual.location.strip() != expected.location.strip():
        names.append("location")
    if actual.attendees != expected.attendees:
        names.append("attendees")
    return names


class CalendarProvider(Protocol):
    @property
    def configured(self) -> bool: ...
    def target_path(self) -> str: ...
    def create_event(self, booking, student, resource, calendar_path: str, creator=None,
                     transaction_id: str | None = None) -> CalendarEvent: ...
    def update_event(self, booking, student, resource, calendar_path: str, event_id: str,
                     creator=None) -> CalendarEvent: ...
    def delete_event(self, calendar_path: str, event_id: str) -> None: ...
    def get_event(self, calendar_path: str, event_id: str) -> EventSnapshot: ...
    def expected_snapshot(self, booking, student, resource) -> EventSnapshot: ...
    def check_connection(self) -> dict: ...


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
            code = f"GRAPH_HTTP_{exc.code}"
            if exc.code == 400 and "login.microsoftonline.com" in url:
                # OAuth endpoint: only the standard error name is read (never the description or tokens).
                code = _oauth_error_code(exc)
            raise OutlookError(code, int(retry) if retry.isdigit() else 30) from None
        except (URLError, TimeoutError, OSError):
            raise OutlookError("GRAPH_NETWORK_ERROR") from None
        except (ValueError, UnicodeError):
            raise OutlookError("GRAPH_INVALID_RESPONSE") from None


def _oauth_error_code(exc):
    try:
        name = json.loads(exc.read(64 * 1024) or b"{}").get("error")
    except (ValueError, UnicodeError, OSError, AttributeError):
        name = None
    known = {"authorization_pending": "OAUTH_AUTHORIZATION_PENDING", "slow_down": "OAUTH_SLOW_DOWN",
             "expired_token": "OAUTH_CODE_EXPIRED", "authorization_declined": "OAUTH_DECLINED",
             "invalid_grant": "OUTLOOK_LOGIN_EXPIRED", "invalid_client": "OAUTH_INVALID_CLIENT",
             "unauthorized_client": "OAUTH_INVALID_CLIENT"}
    return known.get(name, "GRAPH_HTTP_400")


def _write_private(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(text)
    os.replace(temporary, path)


def _graph_time(value):
    """Graph returns {"dateTime": "2026-10-08T00:00:00.0000000", "timeZone": "UTC"} with Prefer outlook.timezone."""
    if not isinstance(value, dict) or not isinstance(value.get("dateTime"), str):
        raise OutlookError("GRAPH_INVALID_EVENT_RESPONSE")
    if (value.get("timeZone") or "UTC").upper() not in ("UTC", "ETC/UTC", "COORDINATED UNIVERSAL TIME"):
        raise OutlookError("GRAPH_INVALID_EVENT_RESPONSE")
    match = _GRAPH_TIME.fullmatch(value["dateTime"].strip())
    if not match:
        raise OutlookError("GRAPH_INVALID_EVENT_RESPONSE")
    return datetime.fromisoformat(match.group(1)).replace(tzinfo=UTC)


class MicrosoftGraphCalendar:
    """Writes to one organiser calendar (/me for a delegated personal account, or a named mailbox).

    Credentials, in order of preference:
      1. OUTLOOK_ACCESS_TOKEN (environment) - a temporary delegated token
      2. device-code login (public client + refresh token file) - renews itself
      3. a token file saved by ``manage.py outlook_token`` - a temporary delegated token (about one hour)
      4. application credentials (tenant/client/secret) for a Microsoft 365 mailbox
    """

    def __init__(self, access_token="", token_file="", tenant_id="", client_id="", client_secret="",
                 mailbox="", calendar_id="", timeout=8, transport=None, invite_mode="allowlist",
                 allowed_attendees=(), public_client_id="", authority="common", refresh_token_file=""):
        self.access_token, self.token_file = access_token, token_file
        self.tenant_id, self.client_id, self.client_secret = tenant_id, client_id, client_secret
        self.mailbox, self.calendar_id = mailbox, calendar_id
        self.public_client_id, self.authority, self.refresh_token_file = public_client_id, authority, refresh_token_file
        if invite_mode not in INVITE_MODES:
            raise ValueError(f"invite_mode must be one of {', '.join(INVITE_MODES)}.")
        self.invite_mode = invite_mode
        self.allowed_attendees = frozenset(item.strip().casefold() for item in allowed_attendees if item and item.strip())
        self.transport = transport or GraphTransport(timeout)
        self._cached_token, self._expires_at = None, 0
        self._lock = RLock()

    # -- credentials -------------------------------------------------------------------------------------

    def _refresh_configured(self):
        return bool(self.public_client_id and self.refresh_token_file and Path(self.refresh_token_file).is_file())

    @property
    def mode(self):
        if self.access_token:
            return "delegated_token"
        if self._refresh_configured():
            return "delegated_refresh"
        if self.token_file and Path(self.token_file).is_file():
            return "delegated_token"
        return "application" if self.tenant_id and self.client_id and self.client_secret else "unconfigured"

    @property
    def configured(self):
        if self.mode in ("delegated_token", "delegated_refresh"):
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
        if self._refresh_configured():
            return self._refreshed_token()
        if self.token_file and Path(self.token_file).is_file():
            try:
                token = Path(self.token_file).read_text(encoding="utf-8").strip()
            except OSError:
                raise OutlookError("OUTLOOK_NOT_CONFIGURED") from None
            if not token or "\n" in token or "\r" in token:
                raise OutlookError("OUTLOOK_INVALID_TOKEN_FILE")
            return token
        if not self.configured or not _AUTHORITY.fullmatch(self.tenant_id):
            raise OutlookError("OUTLOOK_NOT_CONFIGURED")
        with self._lock:
            if self._cached_token and time.monotonic() < self._expires_at:
                return self._cached_token
            result = self.transport.request("POST", f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
                form_body={"client_id": self.client_id, "client_secret": self.client_secret,
                           "grant_type": "client_credentials", "scope": "https://graph.microsoft.com/.default"})
            return self._remember(result)

    def _remember(self, result):
        if not isinstance(result, dict) or not isinstance(result.get("access_token"), str) or not result["access_token"]:
            raise OutlookError("GRAPH_INVALID_TOKEN_RESPONSE")
        try:
            lifetime = max(0, int(result.get("expires_in", 0)) - 60)
        except (TypeError, ValueError):
            raise OutlookError("GRAPH_INVALID_TOKEN_RESPONSE") from None
        self._cached_token = result["access_token"]
        self._expires_at = time.monotonic() + lifetime
        return self._cached_token

    def _refreshed_token(self):
        with self._lock:
            if self._cached_token and time.monotonic() < self._expires_at:
                return self._cached_token
            if not _AUTHORITY.fullmatch(self.authority or ""):
                raise OutlookError("OUTLOOK_NOT_CONFIGURED")
            try:
                saved = json.loads(Path(self.refresh_token_file).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise OutlookError("OUTLOOK_INVALID_TOKEN_FILE") from None
            refresh = saved.get("refresh_token") if isinstance(saved, dict) else None
            if not isinstance(refresh, str) or not refresh:
                raise OutlookError("OUTLOOK_INVALID_TOKEN_FILE")
            if saved.get("client_id") not in (None, self.public_client_id):
                raise OutlookError("OUTLOOK_LOGIN_EXPIRED")  # saved for another app registration: sign in again
            try:
                result = self.transport.request(
                    "POST", f"https://login.microsoftonline.com/{self.authority}/oauth2/v2.0/token",
                    form_body={"client_id": self.public_client_id, "grant_type": "refresh_token",
                               "refresh_token": refresh, "scope": DELEGATED_SCOPE})
            except OutlookError as exc:
                if exc.code in ("GRAPH_HTTP_400", "GRAPH_HTTP_401", "OAUTH_INVALID_CLIENT"):
                    raise OutlookError("OUTLOOK_LOGIN_EXPIRED") from None
                raise
            token = self._remember(result)
            # Microsoft may rotate the refresh token; keep the newest one.
            if isinstance(result.get("refresh_token"), str) and result["refresh_token"] != refresh:
                save_refresh_token(self.refresh_token_file, self.public_client_id, result["refresh_token"])
            return token

    def _request(self, method, path, body=None, query=None):
        if not (_EVENT_PATH.fullmatch(path) or _CALENDAR_PATH.fullmatch(path)):
            raise OutlookError("OUTLOOK_INVALID_CALENDAR_PATH")
        # Read times back in UTC so they compare exactly with the booking.
        headers = {"Authorization": f"Bearer {self._token()}",
                   "Prefer": 'IdType="ImmutableId", outlook.timezone="UTC"'}
        url = "https://graph.microsoft.com/v1.0" + path + ("?" + urlencode(query) if query else "")
        try:
            return self.transport.request(method, url, headers, json_body=body)
        except OutlookError as exc:
            if exc.code == "GRAPH_HTTP_401":
                self._cached_token, self._expires_at = None, 0
            raise

    # -- event content -----------------------------------------------------------------------------------

    def invites(self, person):
        """Whether this person gets a meeting invitation (OUTLOOK_INVITE_MODE / OUTLOOK_ALLOWED_ATTENDEES)."""
        if not person or not person.university_email or self.invite_mode == "none":
            return False
        return self.invite_mode == "all" or person.university_email.strip().casefold() in self.allowed_attendees

    @staticmethod
    def subject(resource):
        return f"SmartLab booking: {resource.name}"

    def _event_body(self, booking, student, resource, creator=None, transaction_id=None):
        lines = [f"Booked for: {student.display_name}"]
        if creator and creator.id != student.id:
            lines.append(f"Booked by: {creator.display_name} (on behalf)")
        if getattr(booking, "urgent", False):
            lines.append("Urgent request approved by a Manager")
        lines += [f"Booking reference: {booking.id}", "Managed by SmartLab. " + NOTICE]
        body = {
            "subject": self.subject(resource),
            "body": {"contentType": "text", "content": "\n".join(lines)},
            "start": {"dateTime": booking.start.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds"), "timeZone": "UTC"},
            "end": {"dateTime": booking.end.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds"), "timeZone": "UTC"},
            "location": {"displayName": resource.location},
            "showAs": "busy",
            "isReminderOn": True,
            "reminderMinutesBeforeStart": 15,
            "attendees": ([{"emailAddress": {"address": student.university_email, "name": student.display_name},
                            "type": "required"}] if self.invites(student) else []),
        }
        if transaction_id:
            body["transactionId"] = transaction_id
        return body

    def expected_snapshot(self, booking, student, resource):
        return EventSnapshot(booking.start.astimezone(UTC).replace(microsecond=0),
                             booking.end.astimezone(UTC).replace(microsecond=0),
                             self.subject(resource), resource.location or "",
                             frozenset([student.university_email.strip().casefold()]) if self.invites(student) else frozenset())

    @staticmethod
    def _event_from_response(result, fallback_id=None):
        event_id = result.get("id") if isinstance(result, dict) else None
        if not isinstance(event_id, str) or not event_id:
            event_id = fallback_id
        if not event_id:
            raise OutlookError("GRAPH_INVALID_EVENT_RESPONSE")
        link = result.get("webLink") if isinstance(result, dict) else None
        if not isinstance(link, str) or not link.startswith(("https://outlook.live.com/", "https://outlook.office365.com/", "https://outlook.office.com/")):
            link = None
        ical_uid = result.get("iCalUId") if isinstance(result, dict) else None
        if not isinstance(ical_uid, str) or not ical_uid:
            ical_uid = None
        return CalendarEvent(event_id, link, ical_uid)

    # -- Graph operations --------------------------------------------------------------------------------

    def create_event(self, booking, student, resource, calendar_path, creator=None, transaction_id=None):
        # transactionId makes a retried POST return the same event instead of a duplicate.
        body = self._event_body(booking, student, resource, creator, transaction_id or booking.id)
        result = self._request("POST", calendar_path, body)
        return self._event_from_response(result)

    def update_event(self, booking, student, resource, calendar_path, event_id, creator=None):
        result = self._request("PATCH", calendar_path + "/" + quote(event_id, safe=""),
                               self._event_body(booking, student, resource, creator))
        return self._event_from_response(result, fallback_id=event_id)

    def delete_event(self, calendar_path, event_id):
        try:
            self._request("DELETE", calendar_path + "/" + quote(event_id, safe=""))
        except OutlookError as exc:
            if exc.code != "GRAPH_HTTP_404":
                raise

    def get_event(self, calendar_path, event_id):
        """Read the event back. Raises OutlookError("GRAPH_HTTP_404") when it no longer exists."""
        result = self._request("GET", calendar_path + "/" + quote(event_id, safe=""),
                               query={"$select": "subject,start,end,location,attendees,isCancelled"})
        if not isinstance(result, dict):
            raise OutlookError("GRAPH_INVALID_EVENT_RESPONSE")
        location = result.get("location") if isinstance(result.get("location"), dict) else {}
        attendees = set()
        for item in result.get("attendees") or []:
            address = ((item or {}).get("emailAddress") or {}).get("address") if isinstance(item, dict) else None
            if isinstance(address, str) and address.strip():
                attendees.add(address.strip().casefold())
        return EventSnapshot(_graph_time(result.get("start")), _graph_time(result.get("end")),
                             result.get("subject") if isinstance(result.get("subject"), str) else "",
                             location.get("displayName") if isinstance(location.get("displayName"), str) else "",
                             frozenset(attendees), bool(result.get("isCancelled")))

    def check_connection(self):
        """Read the target calendar once: proves the credentials and permission work."""
        result = self._request("GET", self.target_path()[:-len("/events")], query={"$select": "name,owner,canEdit"})
        if not isinstance(result, dict):
            raise OutlookError("GRAPH_INVALID_RESPONSE")
        if result.get("canEdit") is False:
            raise OutlookError("OUTLOOK_CALENDAR_READ_ONLY")
        owner = result.get("owner") if isinstance(result.get("owner"), dict) else {}
        return {"calendar_name": result.get("name") if isinstance(result.get("name"), str) else None,
                "owner": owner.get("address") if isinstance(owner.get("address"), str) else None}


# -- device-code sign-in (public client: no client secret) ----------------------------------------------------

def save_refresh_token(path, client_id, refresh_token):
    _write_private(path, json.dumps({"client_id": client_id, "refresh_token": refresh_token}))


def start_device_login(client_id, authority="common", transport=None):
    if not client_id or not _AUTHORITY.fullmatch(authority or ""):
        raise OutlookError("OUTLOOK_NOT_CONFIGURED")
    result = (transport or GraphTransport(15)).request(
        "POST", f"https://login.microsoftonline.com/{authority}/oauth2/v2.0/devicecode",
        form_body={"client_id": client_id, "scope": DELEGATED_SCOPE})
    needed = ("device_code", "user_code", "verification_uri")
    if not isinstance(result, dict) or not all(isinstance(result.get(name), str) and result[name] for name in needed):
        raise OutlookError("GRAPH_INVALID_TOKEN_RESPONSE")
    return result


def finish_device_login(client_id, authority, device_code, interval=5, expires_in=900, transport=None, sleep=time.sleep):
    """Poll until the person signs in. Returns the token response (never print it)."""
    transport = transport or GraphTransport(15)
    deadline = time.monotonic() + max(30, int(expires_in))
    interval = max(1, int(interval))
    while time.monotonic() < deadline:
        sleep(interval)
        try:
            result = transport.request(
                "POST", f"https://login.microsoftonline.com/{authority}/oauth2/v2.0/token",
                form_body={"client_id": client_id, "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                           "device_code": device_code})
        except OutlookError as exc:
            if exc.code == "OAUTH_AUTHORIZATION_PENDING":
                continue
            if exc.code == "OAUTH_SLOW_DOWN":
                interval += 5
                continue
            raise
        if not isinstance(result, dict) or not isinstance(result.get("refresh_token"), str) or not result["refresh_token"]:
            raise OutlookError("GRAPH_INVALID_TOKEN_RESPONSE")
        return result
    raise OutlookError("OAUTH_CODE_EXPIRED")


def make_graph_calendar():
    from django.conf import settings
    return MicrosoftGraphCalendar(access_token=settings.OUTLOOK_ACCESS_TOKEN, token_file=settings.OUTLOOK_TOKEN_FILE,
        tenant_id=settings.OUTLOOK_TENANT_ID, client_id=settings.OUTLOOK_CLIENT_ID,
        client_secret=settings.OUTLOOK_CLIENT_SECRET, mailbox=settings.OUTLOOK_MAILBOX,
        calendar_id=settings.OUTLOOK_CALENDAR_ID, timeout=settings.OUTLOOK_HTTP_TIMEOUT_SECONDS,
        invite_mode=settings.OUTLOOK_INVITE_MODE, allowed_attendees=settings.OUTLOOK_ALLOWED_ATTENDEES,
        public_client_id=settings.OUTLOOK_PUBLIC_CLIENT_ID, authority=settings.OUTLOOK_AUTHORITY,
        refresh_token_file=settings.OUTLOOK_REFRESH_TOKEN_FILE)
