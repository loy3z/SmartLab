"""Outlook sync with the 17 Oct features. One-way only: the website is the only authority.

Client email, 17 Oct: one-way sync is fine for phase one, but Outlook changes must not bypass the system rules
and a change made in Outlook must never become an approved booking on the website. The system never reads the
calendar back while running, so neither can happen; a person may delete the event from their own calendar.
"""
import io
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from booking.domain import Booking, BookingStatus, Principal, Resource, ResourceKind, Role
from booking.outlook import (EventSnapshot, GraphTransport, MicrosoftGraphCalendar, OutlookError, event_differences,
                             finish_device_login, save_refresh_token, start_device_login)
from booking.tests.test_api import NOW, SYDNEY
from booking.tests import test_outlook as base  # module import: its test classes must not be collected twice
from booking.tests.test_outlook import FakeCalendar, FakeTransport


class SyncFixture(base.OutlookWorkflowTests):
    """Reuses the Outlook workflow fixture without running its tests again (they are switched off below)."""

    def event_id(self, booking_id):
        return self.service.repo.get_outlook_sync(booking_id).event_id

    def audit_actions(self, booking_id):
        return [item.action for item in self.service.repo.list_audit() if item.entity_id == booking_id]

    def booking_state(self, booking_id):
        booking = self.service.repo.get_booking(booking_id)
        return booking.status, booking.start, booking.end, booking.revision, booking.resource_id, booking.student_id


for _name in [name for name in vars(base.OutlookWorkflowTests) if name.startswith("test_")]:
    setattr(SyncFixture, _name, None)


class NewFeatureSyncTests(SyncFixture):

    def test_booking_on_behalf_invites_the_beneficiary_and_names_the_staff_creator(self):
        payload = {**self.payload(), "on_behalf_of_zid": "z1000001"}
        created = self.manager.post("/api/v1/bookings/", payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        # 2026-11-06 (client, Week 8): a Manager's booking is approved at once, so it reaches Outlook straight away.
        self.assertEqual(created.data["outlook_sync"]["status"], "SYNCED")
        booking_id, attendee, _, _ = self.provider.creates[0]
        self.assertEqual(booking_id, created.data["id"])
        self.assertEqual(attendee, "z1000001@ad.unsw.edu.au")  # the person the booking is for
        self.assertEqual(self.provider.creators, ["z9000002"])  # who created it, named in the event text

    def test_urgent_request_reaches_outlook_only_after_a_manager_approves_it(self):
        self.service.min_advance_days = 7
        start = (NOW.astimezone(SYDNEY) + timedelta(days=2)).replace(hour=12, minute=0)
        created = self.client.post("/api/v1/bookings/", {
            "resource_id": self.room.id, "start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat(),
            "purpose": "Rerun", "urgent": True, "urgent_reason": "Thesis deadline"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(self.approve(created.data["id"]).status_code, 403)  # an Admin cannot decide it
        self.assertEqual(self.provider.creates, [])
        approved = self.manager.post(f"/api/v1/admin/bookings/{created.data['id']}/review/",
                                     {"decision": "APPROVED"}, format="json")
        self.assertEqual(approved.data["outlook_sync"]["status"], "SYNCED")
        self.assertEqual([call[0] for call in self.provider.creates], [created.data["id"]])

    def test_manager_reschedule_moves_the_same_event(self):
        booking = self.create_approved()
        event_id = self.event_id(booking["id"])
        new_start = (NOW.astimezone(SYDNEY) + timedelta(days=5)).replace(hour=9, minute=0)
        moved = self.manager.post(f"/api/v1/bookings/{booking['id']}/reschedule/", {
            "start": new_start.isoformat(), "end": (new_start + timedelta(hours=1)).isoformat()}, format="json")
        self.assertEqual(moved.status_code, 200, moved.data)
        self.assertEqual(self.provider.events[event_id].start, new_start.astimezone(UTC))
        self.assertEqual(len(self.provider.creates), 1)

    def test_process_due_endpoint_pushes_automatic_approvals_straight_away(self):
        created = self.create().data
        self.service.clock = lambda: NOW + timedelta(hours=24)
        response = self.admin.post("/api/v1/admin/process-due/", {}, format="json")
        self.assertEqual(response.data["updated_bookings"][0]["outlook_sync"]["status"], "SYNCED")
        self.assertEqual([call[0] for call in self.provider.creates], [created["id"]])

    def test_bookings_that_already_ended_are_not_written_when_sync_is_turned_on(self):
        self.sync.enabled = False
        booking = self.create_approved()
        self.sync.enabled = True
        self.service.clock = lambda: NOW + timedelta(days=10)
        self.sync.process_pending()
        self.assertEqual(self.provider.creates, [])
        self.assertIsNone(self.service.repo.get_outlook_sync(booking["id"]))


class OneWayTests(SyncFixture):
    def test_reschedule_writes_an_event_the_person_deleted_again_at_the_new_time(self):
        booking = self.create_approved()
        old_event = self.event_id(booking["id"])
        self.provider.outlook_delete(old_event)
        new_start = (NOW.astimezone(SYDNEY) + timedelta(days=5)).replace(hour=9, minute=0)
        moved = self.manager.post(f"/api/v1/bookings/{booking['id']}/reschedule/", {
            "start": new_start.isoformat(), "end": (new_start + timedelta(hours=1)).isoformat()}, format="json")
        self.assertEqual(moved.data["outlook_sync"]["status"], "SYNCED")
        new_event = self.event_id(booking["id"])
        self.assertNotEqual(new_event, old_event)
        self.assertEqual(self.provider.events[new_event].start, new_start.astimezone(UTC))
        self.assertEqual(self.provider.transaction_ids[0], booking["id"])
        self.assertNotEqual(self.provider.transaction_ids[1], booking["id"])  # not a retry of the deleted event
        self.assertIn("OUTLOOK_EVENT_RECREATED", self.audit_actions(booking["id"]))

    def test_deleting_or_editing_the_event_in_outlook_is_left_alone(self):
        booking = self.create_approved()
        event_id = self.event_id(booking["id"])
        self.provider.outlook_edit(event_id, subject="My own title")
        before = self.booking_state(booking["id"])
        self.sync.process_pending()
        self.admin.get("/api/v1/admin/outlook/")
        self.admin.post("/api/v1/admin/outlook/process/", {"limit": 5}, format="json")
        self.assertEqual(self.provider.reads, [])  # the calendar is never read back
        self.assertEqual(self.provider.events[event_id].subject, "My own title")
        self.assertEqual(len(self.provider.creates) + len(self.provider.updates), 1)
        self.assertEqual(self.booking_state(booking["id"]), before)
        self.provider.outlook_delete(event_id)
        self.sync.process_pending()
        self.assertEqual(len(self.provider.creates), 1)  # not written again by itself

    def test_nothing_done_in_outlook_becomes_a_booking(self):
        self.create_approved()
        count = len(self.service.repo.list_bookings())
        self.provider.events["made-in-outlook"] = EventSnapshot(NOW, NOW + timedelta(hours=1), "My own booking", "Lab")
        self.sync.process_pending()
        self.assertEqual(len(self.service.repo.list_bookings()), count)

    def test_check_and_restore_endpoints_no_longer_exist(self):
        booking = self.create_approved()
        self.assertEqual(self.admin.post("/api/v1/admin/outlook/verify/", {}, format="json").status_code, 404)
        self.assertEqual(self.admin.post(f"/api/v1/admin/bookings/{booking['id']}/outlook-restore/", {}, format="json").status_code, 404)

    def test_connection_check_and_status_are_staff_only(self):
        ok = self.admin.post("/api/v1/admin/outlook/check/", {}, format="json")
        self.assertEqual((ok.status_code, ok.data["ok"], ok.data["owner"]), (200, True, "organiser@example.test"))
        self.provider.read_error = OutlookError("GRAPH_HTTP_401")
        expired = self.admin.post("/api/v1/admin/outlook/check/", {}, format="json").data
        self.assertEqual((expired["ok"], expired["code"]), (False, "TOKEN_EXPIRED"))
        self.provider.read_error = None
        self.create_approved()
        status = self.admin.get("/api/v1/admin/outlook/").data
        self.assertEqual(status["last_check"]["code"], "TOKEN_EXPIRED")
        self.assertEqual(status["summary"], {"total": 1, "synced": 1, "pending": 0, "failed": 0})
        self.assertEqual(status["items"][0]["sync"]["status"], "SYNCED")
        self.assertNotIn("drift_status", status["items"][0]["sync"])
        self.assertEqual(self.client.post("/api/v1/admin/outlook/check/", {}, format="json").status_code, 403)
        self.assertEqual(self.admin.post("/api/v1/admin/outlook/check/", {"x": 1}, format="json").status_code, 400)

    def test_failures_are_listed_first_with_their_error(self):
        first = self.create_approved()
        self.provider.error = OutlookError("GRAPH_HTTP_401")
        second = self.client.post("/api/v1/bookings/", self.payload(days=4), format="json").data
        self.approve(second["id"])
        status = self.admin.get("/api/v1/admin/outlook/").data
        self.assertEqual([item["booking_id"] for item in status["items"]], [second["id"], first["id"]])
        self.assertEqual(status["items"][0]["sync"]["last_error"], "GRAPH_HTTP_401")
        self.assertEqual(status["summary"]["failed"], 1)


def _fixture():
    booking = Booking("11111111-1111-4111-8111-111111111111", "student-private-id", "resource",
                      datetime(2026, 10, 8, tzinfo=UTC), datetime(2026, 10, 8, 1, tzinfo=UTC),
                      "Private purpose", NOW, BookingStatus.APPROVED, "AUTO_APPROVED", urgent=True)
    student = Principal("student-private-id", "z1234567", "Example Student", Role.STUDENT, "Student@Example.edu")
    staff = Principal("staff-id", "z7654321", "Example Manager", Role.MANAGER, "manager@example.edu")
    resource = Resource("resource", "Lab Room 1", ResourceKind.ROOM, "Building A", "Demo")
    return booking, student, staff, resource


class GraphReadBackTests(SimpleTestCase):
    def test_invitations_go_only_to_listed_addresses_by_default(self):
        booking, student, staff, resource = _fixture()
        for kwargs, expected in (({}, 0), ({"allowed_attendees": ["student@example.edu"]}, 1),
                                 ({"invite_mode": "none", "allowed_attendees": ["student@example.edu"]}, 0),
                                 ({"invite_mode": "all"}, 1)):
            transport = FakeTransport([{"id": "event"}])
            provider = MicrosoftGraphCalendar(access_token="token", transport=transport, **kwargs)
            provider.create_event(booking, student, resource, provider.target_path())
            self.assertEqual(len(transport.calls[0][3]["attendees"]), expected, kwargs)
        with self.assertRaises(ValueError):
            MicrosoftGraphCalendar(invite_mode="everyone")

    def test_event_text_names_both_people_and_says_outlook_changes_do_not_count(self):
        booking, student, staff, resource = _fixture()
        transport = FakeTransport([{"id": "event"}])
        provider = MicrosoftGraphCalendar(access_token="token", transport=transport)
        provider.create_event(booking, student, resource, provider.target_path(), creator=staff, transaction_id="tx-2")
        body = transport.calls[0][3]
        text = body["body"]["content"]
        for expected in ("Booked for: Example Student", "Booked by: Example Manager (on behalf)", "Urgent request",
                         "Changes made in Outlook are not applied"):
            self.assertIn(expected, text)
        self.assertEqual(body["transactionId"], "tx-2")
        self.assertNotIn(booking.student_id, json.dumps(body))
        self.assertNotIn(booking.purpose, json.dumps(body))

    def test_reads_event_back_in_utc_and_compares_owned_fields(self):
        booking, student, staff, resource = _fixture()
        transport = FakeTransport([{
            "id": "event", "subject": "SmartLab booking: Lab Room 1", "isCancelled": False,
            "start": {"dateTime": "2026-10-08T02:00:00.0000000", "timeZone": "UTC"},
            "end": {"dateTime": "2026-10-08T03:00:00.0000000", "timeZone": "UTC"},
            "location": {"displayName": "Building A"},
            "attendees": [{"emailAddress": {"address": "Student@example.edu"}}]}])
        provider = MicrosoftGraphCalendar(access_token="token", transport=transport, invite_mode="all")
        actual = provider.get_event(provider.target_path(), "event/1")
        method, url, headers, _, _ = transport.calls[0]
        self.assertEqual(method, "GET")
        self.assertTrue(url.startswith("https://graph.microsoft.com/v1.0/me/calendar/events/event%2F1?%24select="))
        self.assertIn('outlook.timezone="UTC"', headers["Prefer"])
        self.assertEqual(event_differences(provider.expected_snapshot(booking, student, resource), actual), ["start", "end"])
        self.assertEqual(actual.attendees, frozenset(["student@example.edu"]))

    def test_unexpected_time_zone_is_an_error_not_a_difference(self):
        provider = MicrosoftGraphCalendar(access_token="token", transport=FakeTransport([{
            "start": {"dateTime": "2026-10-08T13:00:00", "timeZone": "AUS Eastern Standard Time"},
            "end": {"dateTime": "2026-10-08T14:00:00", "timeZone": "AUS Eastern Standard Time"}}]))
        with self.assertRaisesRegex(OutlookError, "GRAPH_INVALID_EVENT_RESPONSE"):
            provider.get_event(provider.target_path(), "event")

    def test_missing_event_raises_not_found(self):
        provider = MicrosoftGraphCalendar(access_token="token", transport=FakeTransport([OutlookError("GRAPH_HTTP_404")]))
        with self.assertRaisesRegex(OutlookError, "GRAPH_HTTP_404"):
            provider.get_event(provider.target_path(), "event")

    def test_connection_check_reads_the_calendar_itself(self):
        transport = FakeTransport([{"name": "Calendar", "owner": {"address": "me@example.com"}, "canEdit": True},
                                   {"name": "Shared", "canEdit": False}])
        provider = MicrosoftGraphCalendar(access_token="token", transport=transport)
        self.assertEqual(provider.check_connection(), {"calendar_name": "Calendar", "owner": "me@example.com"})
        self.assertTrue(transport.calls[0][1].startswith("https://graph.microsoft.com/v1.0/me/calendar?"))
        with self.assertRaisesRegex(OutlookError, "OUTLOOK_CALENDAR_READ_ONLY"):
            provider.check_connection()


class DeviceSignInTests(SimpleTestCase):
    def test_refresh_token_renews_access_and_keeps_the_rotated_token(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "refresh"
            save_refresh_token(path, "client-1", "refresh-1")
            transport = FakeTransport([{"access_token": "access-1", "expires_in": 3600, "refresh_token": "refresh-2"},
                                       {"id": "event"}, {"id": "event"}])
            provider = MicrosoftGraphCalendar(public_client_id="client-1", refresh_token_file=str(path), transport=transport)
            self.assertEqual((provider.mode, provider.configured), ("delegated_refresh", True))
            booking, student, _, resource = _fixture()
            provider.create_event(booking, student, resource, provider.target_path())
            provider.create_event(booking, student, resource, provider.target_path())  # cached access token
            token_call = transport.calls[0]
            self.assertEqual(token_call[1], "https://login.microsoftonline.com/common/oauth2/v2.0/token")
            self.assertEqual((token_call[4]["grant_type"], token_call[4]["refresh_token"]), ("refresh_token", "refresh-1"))
            self.assertEqual(transport.calls[1][2]["Authorization"], "Bearer access-1")
            self.assertEqual(len(transport.calls), 3)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["refresh_token"], "refresh-2")

    def test_expired_sign_in_is_reported_as_login_expired(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "refresh"
            save_refresh_token(path, "client-1", "refresh-1")
            provider = MicrosoftGraphCalendar(public_client_id="client-1", refresh_token_file=str(path),
                                              transport=FakeTransport([OutlookError("OUTLOOK_LOGIN_EXPIRED")]))
            booking, student, _, resource = _fixture()
            with self.assertRaisesRegex(OutlookError, "OUTLOOK_LOGIN_EXPIRED"):
                provider.create_event(booking, student, resource, provider.target_path())
            other = MicrosoftGraphCalendar(public_client_id="client-2", refresh_token_file=str(path), transport=FakeTransport([]))
            with self.assertRaisesRegex(OutlookError, "OUTLOOK_LOGIN_EXPIRED"):
                other.create_event(booking, student, resource, other.target_path())

    def test_oauth_error_names_are_read_without_the_description(self):
        transport = GraphTransport()
        body = io.BytesIO(b'{"error":"authorization_pending","error_description":"secret detail"}')
        with patch.object(transport.opener, "open", side_effect=HTTPError(
                "https://login.microsoftonline.com/common/oauth2/v2.0/token", 400, "Bad Request", {}, body)):
            with self.assertRaises(OutlookError) as caught:
                transport.request("POST", "https://login.microsoftonline.com/common/oauth2/v2.0/token", form_body={})
        self.assertEqual(caught.exception.code, "OAUTH_AUTHORIZATION_PENDING")

    def test_device_code_flow_waits_for_the_person_to_sign_in(self):
        transport = FakeTransport([{"device_code": "device", "user_code": "ABCD-EFGH",
                                    "verification_uri": "https://microsoft.com/devicelogin", "interval": 1},
                                   OutlookError("OAUTH_AUTHORIZATION_PENDING"),
                                   {"access_token": "access", "refresh_token": "refresh", "expires_in": 3600}])
        started = start_device_login("client-1", "consumers", transport)
        self.assertEqual(transport.calls[0][4]["scope"], "https://graph.microsoft.com/Calendars.ReadWrite offline_access")
        result = finish_device_login("client-1", "consumers", started["device_code"], 1, 60, transport, sleep=lambda _: None)
        self.assertEqual(result["refresh_token"], "refresh")
        self.assertEqual(transport.calls[2][4]["grant_type"], "urn:ietf:params:oauth:grant-type:device_code")

    def test_login_command_saves_the_refresh_token_without_printing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".local" / "outlook-refresh-token"
            started = {"device_code": "device", "user_code": "ABCD-EFGH", "verification_uri": "https://microsoft.com/devicelogin"}
            with override_settings(OUTLOOK_PUBLIC_CLIENT_ID="client-1", OUTLOOK_REFRESH_TOKEN_FILE=str(path), OUTLOOK_ACCESS_TOKEN=""), \
                    patch("booking.management.commands.outlook_login.start_device_login", return_value=started), \
                    patch("booking.management.commands.outlook_login.finish_device_login",
                          return_value={"access_token": "secret-access", "refresh_token": "secret-refresh"}):
                output = io.StringIO()
                call_command("outlook_login", stdout=output)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")),
                             {"client_id": "client-1", "refresh_token": "secret-refresh"})
            self.assertIn("ABCD-EFGH", output.getvalue())
            self.assertNotIn("secret", output.getvalue())

    @override_settings(OUTLOOK_PUBLIC_CLIENT_ID="")
    def test_login_command_needs_a_client_id(self):
        with self.assertRaisesRegex(CommandError, "OUTLOOK_PUBLIC_CLIENT_ID"):
            call_command("outlook_login", stdout=io.StringIO())


_live_calendar = None


def make_live_fake():
    return _live_calendar


class LiveCheckCommandTests(SimpleTestCase):
    def test_live_check_runs_every_step_and_removes_its_event(self):
        global _live_calendar
        _live_calendar = FakeCalendar()
        output = io.StringIO()
        with override_settings(OUTLOOK_PROVIDER_FACTORY="booking.tests.test_outlook_features.make_live_fake"):
            call_command("outlook_live_check", stdout=output)
        text = output.getvalue()
        self.assertEqual(text.count("PASS"), 5, text)
        self.assertIn("All live Outlook checks passed.", text)
        self.assertEqual(_live_calendar.events, {})
        self.assertEqual(_live_calendar.invite_mode, "none")

    def test_live_check_reports_a_failed_graph_call_and_cleans_up(self):
        global _live_calendar
        _live_calendar = FakeCalendar()

        def broken(path, event_id):
            raise OutlookError("GRAPH_HTTP_403")
        _live_calendar.get_event = broken
        output = io.StringIO()
        with override_settings(OUTLOOK_PROVIDER_FACTORY="booking.tests.test_outlook_features.make_live_fake"):
            with self.assertRaisesRegex(CommandError, "failed"):
                call_command("outlook_live_check", stdout=output)
        self.assertIn("FAIL  Microsoft Graph call  - GRAPH_HTTP_403", output.getvalue())
        self.assertEqual(_live_calendar.events, {})
