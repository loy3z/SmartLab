"""Real Graph request shape plus booking/outbox integration, without live credentials."""
import io
import json
import tempfile
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from booking.calendar_sync import CalendarSyncService
from booking.domain import BookingStatus
from booking.outlook import CalendarEvent, GraphTransport, MicrosoftGraphCalendar, OutlookError
from booking.runtime import reset_runtime
from booking.tests.test_api import NOW, PNG, SYDNEY


class FakeCalendar:
    configured = True
    mode = "test_adapter"

    def __init__(self):
        self.creates, self.updates, self.deletes = [], [], []
        self.error = None
        self.on_create = None

    def target_path(self):
        return "/me/calendar/events"

    def create_event(self, booking, student, resource, path):
        self.creates.append((booking.id, student.university_email, resource.id, path))
        if self.on_create:
            self.on_create()
        if self.error:
            raise self.error
        return CalendarEvent("event-" + booking.id, "https://outlook.live.com/calendar/item/demo", "ical-" + booking.id)

    def update_event(self, booking, student, resource, path, event_id):
        self.updates.append((booking.id, student.university_email, resource.id, path, event_id))
        if self.error:
            raise self.error
        return CalendarEvent(event_id, "https://outlook.live.com/calendar/item/demo", "ical-" + booking.id)

    def delete_event(self, path, event_id):
        if self.error:
            raise self.error
        self.deletes.append((path, event_id))


class FakeTransport:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def request(self, method, url, headers=None, json_body=None, form_body=None):
        self.calls.append((method, url, headers, json_body, form_body))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True,
                   OUTLOOK_ENABLED=True, OUTLOOK_SYNC_ON_WRITE=True)
class OutlookWorkflowTests(SimpleTestCase):
    def setUp(self):
        self.service = reset_runtime()
        self.service.clock = lambda: NOW
        self.provider = FakeCalendar()
        self.sync = self.service.calendar_sync
        self.sync.provider = self.provider
        self.client = self.login("z1000001")
        self.student = self.login("z1000002")
        self.admin = self.login("z9000001")
        self.room = self.service.repo.list_resources()[0]
        for item in self.service.repo.list_submissions():
            self.service.repo.save_submission(replace(item, valid_until=None))

    def login(self, zid):
        client = APIClient()
        result = client.post("/api/v1/auth/demo-login/", {"zid": zid}, format="json")
        client.credentials(HTTP_AUTHORIZATION="Bearer " + result.data["access_token"])
        return client

    def payload(self, days=3):
        start = (NOW.astimezone(SYDNEY) + timedelta(days=days)).replace(hour=12, minute=0)
        return {"resource_id": self.room.id, "start": start.isoformat(),
                "end": (start + timedelta(hours=1)).isoformat(), "purpose": "Private student purpose"}

    def create(self, client=None, **headers):
        return (client or self.client).post("/api/v1/bookings/", self.payload(), format="json", **headers)

    def submit(self):
        response = self.student.post("/api/v1/qualifications/", {
            "requirement_id": self.room.required_qualification_id, "title": "Induction",
            "file": SimpleUploadedFile("induction.png", PNG, content_type="image/png")}, format="multipart")
        self.assertEqual(response.status_code, 201)
        return response.data["id"]

    def test_auto_approval_creates_exactly_one_event_and_returns_sync_state(self):
        first = self.create(HTTP_IDEMPOTENCY_KEY="outlook-demo-1")
        second = self.create(HTTP_IDEMPOTENCY_KEY="outlook-demo-1")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["outlook_sync"]["status"], "SYNCED")
        self.assertEqual(len(self.provider.creates), 1)
        self.assertEqual(self.client.get(f"/api/v1/bookings/{first.data['id']}/").data["outlook_sync"]["status"], "SYNCED")
        self.assertEqual(self.client.get("/api/v1/dashboard/").data["bookings"][0]["outlook_sync"]["status"], "SYNCED")

    def test_pending_request_is_not_written_but_qualification_auto_approval_is(self):
        submission_id = self.submit()
        booking = self.create(self.student)
        self.assertEqual(booking.data["status"], "WAITING_QUALIFICATION")
        self.assertEqual(booking.data["outlook_sync"]["status"], "NOT_REQUIRED")
        self.assertEqual(self.provider.creates, [])
        reviewed = self.admin.post(f"/api/v1/admin/qualifications/{submission_id}/review/", {"decision": "VERIFIED"}, format="json")
        self.assertEqual(reviewed.status_code, 200)
        self.assertEqual(reviewed.data["updated_bookings"][0]["outlook_sync"]["status"], "SYNCED")
        self.assertEqual(len(self.provider.creates), 1)

    def test_manual_approval_is_also_written(self):
        submission_id = self.submit()
        self.service.wait_hours = 96
        booking = self.create(self.student)
        self.assertEqual(booking.data["status"], "PENDING_APPROVAL")
        self.admin.post(f"/api/v1/admin/qualifications/{submission_id}/review/", {"decision": "VERIFIED"}, format="json")
        self.assertEqual(self.provider.creates, [])
        result = self.admin.post(f"/api/v1/admin/bookings/{booking.data['id']}/review/", {"decision": "APPROVED"}, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["outlook_sync"]["status"], "SYNCED")

    def test_cancellation_deletes_original_event_once(self):
        booking = self.create().data
        path = f"/api/v1/bookings/{booking['id']}/cancel/"
        result = self.client.post(path, {}, format="json")
        self.client.post(path, {}, format="json")
        self.assertEqual(result.data["status"], "CANCELLED")
        self.assertEqual(result.data["outlook_sync"]["action"], "DELETE")
        self.assertEqual(result.data["outlook_sync"]["status"], "SYNCED")
        self.assertIsNone(result.data["outlook_sync"]["web_link"])
        self.assertEqual(len(self.provider.deletes), 1)

    def test_reschedule_updates_the_existing_event_and_preserves_its_identity(self):
        booking = self.create().data
        original = self.service.repo.get_outlook_sync(booking["id"])
        new_start = (NOW.astimezone(SYDNEY) + timedelta(days=4)).replace(hour=14, minute=0)
        result = self.client.post(f"/api/v1/bookings/{booking['id']}/reschedule/", {
            "start": new_start.isoformat(),
            "end": (new_start + timedelta(hours=1)).isoformat(),
        }, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["revision"], 2)
        self.assertEqual(result.data["reason_code"], "RESCHEDULED_BY_USER")
        self.assertEqual(result.data["outlook_sync"]["action"], "UPDATE")
        self.assertEqual(result.data["outlook_sync"]["status"], "SYNCED")
        self.assertEqual(len(self.provider.creates), 1)
        self.assertEqual(len(self.provider.updates), 1)
        self.assertEqual(self.provider.updates[0][-1], original.event_id)
        self.assertEqual(self.service.repo.get_outlook_sync(booking["id"]).event_id, original.event_id)

    def test_failed_reschedule_sync_keeps_new_booking_time_and_retry_updates_event(self):
        booking = self.create().data
        original = self.service.repo.get_outlook_sync(booking["id"])
        self.provider.error = OutlookError("GRAPH_NETWORK_ERROR")
        new_start = (NOW.astimezone(SYDNEY) + timedelta(days=5)).replace(hour=15, minute=0)
        moved = self.client.post(f"/api/v1/bookings/{booking['id']}/reschedule/", {
            "start": new_start.isoformat(),
            "end": (new_start + timedelta(hours=1)).isoformat(),
        }, format="json")
        self.assertEqual(moved.status_code, 200)
        self.assertEqual(moved.data["status"], "APPROVED")
        self.assertEqual(moved.data["outlook_sync"]["status"], "FAILED")
        self.assertEqual(moved.data["outlook_sync"]["action"], "UPDATE")
        self.provider.error = None
        retried = self.admin.post(f"/api/v1/admin/bookings/{booking['id']}/outlook-retry/", {}, format="json")
        self.assertEqual(retried.data["outlook_sync"]["status"], "SYNCED")
        self.assertEqual(len(self.provider.creates), 1)
        self.assertEqual(len(self.provider.updates), 2)
        self.assertTrue(all(call[-1] == original.event_id for call in self.provider.updates))

    def test_graph_failure_preserves_approved_booking_and_retry_recovers(self):
        self.provider.error = OutlookError("GRAPH_HTTP_429", retry_after=120)
        booking = self.create().data
        self.assertEqual(booking["status"], "APPROVED")
        self.assertEqual(booking["outlook_sync"]["status"], "FAILED")
        self.assertEqual(booking["outlook_sync"]["last_error"], "GRAPH_HTTP_429")
        self.assertEqual(self.create().data["status"], "PENDING_APPROVAL")
        record = self.service.repo.get_outlook_sync(booking["id"])
        self.assertEqual(record.next_attempt_at, NOW + timedelta(seconds=120))
        self.sync.process_pending()
        self.assertEqual(len(self.provider.creates), 1)
        self.provider.error = None
        result = self.admin.post(f"/api/v1/admin/bookings/{booking['id']}/outlook-retry/", {}, format="json")
        self.assertEqual(result.data["outlook_sync"]["status"], "SYNCED")
        self.assertEqual(self.provider.creates[0][0], self.provider.creates[1][0])

    @override_settings(OUTLOOK_SYNC_ON_WRITE=False)
    def test_cancel_before_processing_does_not_create_an_event(self):
        booking = self.create().data
        self.client.post(f"/api/v1/bookings/{booking['id']}/cancel/", {}, format="json")
        self.sync.process_pending()
        self.assertEqual(self.provider.creates, [])
        self.assertEqual(self.provider.deletes, [])
        self.assertEqual(self.service.repo.get_outlook_sync(booking["id"]).status, "SYNCED")

    def test_cancellation_during_create_deletes_the_late_event(self):
        def cancel_during_http():
            record = self.service.repo.list_bookings()[0]
            self.service.cancel_booking(self.service.repo.get_principal(record.student_id), record.id)
        self.provider.on_create = cancel_during_http
        result = self.create()
        self.assertEqual(result.data["status"], "CANCELLED")
        record = self.service.repo.get_outlook_sync(result.data["id"])
        self.assertEqual(record.action, "DELETE")
        self.assertEqual(record.status, "SYNCED")
        self.assertEqual(len(self.provider.creates), 1)
        self.assertEqual(len(self.provider.deletes), 1)

    def test_unknown_create_outcome_is_recovered_before_cancellation(self):
        self.provider.error = OutlookError("GRAPH_NETWORK_ERROR")
        booking = self.create().data
        self.provider.error = None
        self.client.post(f"/api/v1/bookings/{booking['id']}/cancel/", {}, format="json")
        self.assertEqual(len(self.provider.creates), 2)
        self.assertEqual(self.provider.creates[0][0], self.provider.creates[1][0])
        self.assertEqual(len(self.provider.deletes), 1)

    def test_failed_delete_keeps_cancelled_booking_and_original_event_for_retry(self):
        booking = self.create().data
        original = self.service.repo.get_outlook_sync(booking["id"])
        self.provider.error = OutlookError("GRAPH_NETWORK_ERROR")
        result = self.client.post(f"/api/v1/bookings/{booking['id']}/cancel/", {}, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["status"], "CANCELLED")
        failed = self.service.repo.get_outlook_sync(booking["id"])
        self.assertEqual(failed.status, "FAILED")
        self.assertEqual(failed.event_id, original.event_id)
        self.provider.error = None
        retried = self.admin.post(f"/api/v1/admin/bookings/{booking['id']}/outlook-retry/", {}, format="json")
        self.assertEqual(retried.data["outlook_sync"]["status"], "SYNCED")
        self.assertEqual(len(self.provider.creates), 1)
        self.assertEqual(len(self.provider.deletes), 1)

    def test_missing_outlook_configuration_is_visible_without_failing_booking(self):
        self.sync.provider = MicrosoftGraphCalendar()
        result = self.create()
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.data["status"], "APPROVED")
        self.assertEqual(result.data["outlook_sync"]["last_error"], "OUTLOOK_NOT_CONFIGURED")

    def test_other_worker_cannot_claim_an_in_progress_event(self):
        other_worker = CalendarSyncService(self.service.repo, self.provider, enabled=True, clock=lambda: NOW)
        def try_duplicate():
            other_worker.process_booking(self.service.repo.list_bookings()[0].id)
        self.provider.on_create = try_duplicate
        self.create()
        self.assertEqual(len(self.provider.creates), 1)

    def test_outbox_rolls_back_with_booking_transaction(self):
        payload = self.payload()
        actor = self.service.repo.get_principal(self.client.get("/api/v1/auth/me/").data["id"])
        with self.assertRaises(RuntimeError):
            with self.service.repo.atomic():
                from django.utils.dateparse import parse_datetime
                self.service.create_booking(actor, self.room.id, parse_datetime(payload["start"]), parse_datetime(payload["end"]), "Test")
                raise RuntimeError("Rollback")
        self.assertEqual(self.service.repo.list_bookings(), [])
        self.assertEqual(self.service.repo.list_outlook_sync(), [])

    def test_outlook_management_endpoints_are_staff_only(self):
        booking = self.create().data
        paths = [("get", "/api/v1/admin/outlook/"), ("post", "/api/v1/admin/outlook/process/"),
                 ("post", f"/api/v1/admin/bookings/{booking['id']}/outlook-retry/")]
        for method, path in paths:
            self.assertEqual(getattr(self.student, method)(path).status_code, 403)
            self.assertEqual(getattr(APIClient(), method)(path).status_code, 401)
        info = self.admin.get("/api/v1/admin/outlook/")
        self.assertEqual(info.status_code, 200)
        self.assertNotIn("token", json.dumps(info.data).lower())
        self.assertEqual(self.admin.post("/api/v1/admin/outlook/process/", {"limit": 100}, format="json").status_code, 400)

    @override_settings(OUTLOOK_ENABLED=False)
    def test_disabled_integration_keeps_the_original_booking_workflow(self):
        self.service = reset_runtime()
        self.service.clock = lambda: NOW
        booking = self.create().data
        self.assertEqual(booking["outlook_sync"]["status"], "DISABLED")
        self.assertEqual(self.provider.creates, [])


class GraphAdapterTests(SimpleTestCase):
    def fixture(self):
        from booking.domain import Booking, Principal, Resource, ResourceKind, Role
        start = NOW + timedelta(days=3)
        booking = Booking("booking-reference", "student-private-id", "resource", start, start + timedelta(hours=1),
            "Private purpose", NOW, BookingStatus.APPROVED, "AUTO_APPROVED")
        student = Principal("student-private-id", "z1234567", "Example Student", Role.STUDENT,
                            university_email="student@example.edu")
        resource = Resource("resource", "Lab Room 1", ResourceKind.ROOM, "Building A", "Demo")
        return booking, student, resource

    def test_personal_account_posts_real_graph_payload_without_student_private_data(self):
        transport = FakeTransport([{"id": "event-id", "webLink": "https://outlook.live.com/calendar/item/event"}])
        provider = MicrosoftGraphCalendar(access_token="example-access-token", transport=transport)
        booking, student, resource = self.fixture()
        event = provider.create_event(booking, student, resource, provider.target_path())
        method, url, headers, body, _ = transport.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://graph.microsoft.com/v1.0/me/calendar/events")
        self.assertEqual(headers["Authorization"], "Bearer example-access-token")
        self.assertEqual(body["transactionId"], booking.id)
        self.assertEqual(body["start"], {"dateTime": "2026-10-08T00:00:00", "timeZone": "UTC"})
        self.assertEqual(len(body["attendees"]), 1)
        self.assertEqual(body["attendees"][0]["emailAddress"]["address"], student.university_email)
        self.assertEqual(body["attendees"][0]["type"], "required")
        self.assertEqual(body["subject"], "SmartLab booking: Lab Room 1")
        self.assertEqual(body["location"]["displayName"], "Building A")
        self.assertNotIn(booking.student_id, json.dumps(body))
        self.assertNotIn(booking.purpose, json.dumps(body))
        self.assertEqual(event.id, "event-id")

    def test_application_credentials_use_default_scope_cache_and_named_mailbox(self):
        transport = FakeTransport([{"access_token": "app-token", "expires_in": 3600}, {"id": "event1"}, {"id": "event2"}])
        provider = MicrosoftGraphCalendar(token_file="missing-local-token-file", tenant_id="tenant.example",
            client_id="example-client", client_secret="example-secret", mailbox="lab@example.com", calendar_id="a/b", transport=transport)
        self.assertTrue(provider.configured)
        self.assertEqual(provider.mode, "application")
        booking, student, resource = self.fixture()
        provider.create_event(booking, student, resource, provider.target_path())
        provider.create_event(booking, student, resource, provider.target_path())
        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(transport.calls[0][4]["scope"], "https://graph.microsoft.com/.default")
        self.assertEqual(transport.calls[1][1], "https://graph.microsoft.com/v1.0/users/lab%40example.com/calendars/a%2Fb/events")

    def test_reschedule_patches_the_existing_graph_event(self):
        transport = FakeTransport([{"id": "event/with+characters", "iCalUId": "ical-uid"}])
        provider = MicrosoftGraphCalendar(access_token="example-token", transport=transport)
        booking, student, resource = self.fixture()
        event = provider.update_event(booking, student, resource, provider.target_path(), "event/with+characters")
        method, url, _, body, _ = transport.calls[0]
        self.assertEqual(method, "PATCH")
        self.assertTrue(url.endswith("/events/event%2Fwith%2Bcharacters"))
        self.assertNotIn("transactionId", body)
        self.assertEqual(len(body["attendees"]), 1)
        self.assertEqual(body["attendees"][0]["emailAddress"]["address"], student.university_email)
        self.assertEqual(event.id, "event/with+characters")
        self.assertEqual(event.ical_uid, "ical-uid")

    def test_deleted_or_missing_event_cancellation_is_idempotent(self):
        transport = FakeTransport([OutlookError("GRAPH_HTTP_404")])
        provider = MicrosoftGraphCalendar(access_token="example-token", transport=transport)
        provider.delete_event(provider.target_path(), "event/with+characters")
        self.assertTrue(transport.calls[0][1].endswith("event%2Fwith%2Bcharacters"))

    def test_invalid_response_is_not_reported_as_a_synced_event(self):
        provider = MicrosoftGraphCalendar(access_token="example-token", transport=FakeTransport([{}]))
        booking, student, resource = self.fixture()
        with self.assertRaisesRegex(OutlookError, "GRAPH_INVALID_EVENT_RESPONSE"):
            provider.create_event(booking, student, resource, provider.target_path())

    def test_token_file_can_be_replaced_without_restarting_server(self):
        with tempfile.TemporaryDirectory() as directory:
            token_path = Path(directory) / "token"
            token_path.write_text("first-token", encoding="utf-8")
            transport = FakeTransport([{"id": "first"}, {"id": "second"}])
            provider = MicrosoftGraphCalendar(token_file=str(token_path), transport=transport)
            booking, student, resource = self.fixture()
            provider.create_event(booking, student, resource, provider.target_path())
            token_path.write_text("second-token", encoding="utf-8")
            provider.create_event(booking, student, resource, provider.target_path())
            self.assertEqual(transport.calls[1][2]["Authorization"], "Bearer second-token")

    def test_http_errors_redact_bodies_and_preserve_retry_after(self):
        transport = GraphTransport()
        with patch.object(transport.opener, "open", side_effect=HTTPError("https://graph.microsoft.com", 429, "raw secret",
                {"Retry-After": "120"}, io.BytesIO(b'{"secret":"do-not-return"}'))):
            with self.assertRaises(OutlookError) as caught:
                transport.request("POST", "https://graph.microsoft.com/v1.0/me/calendar/events")
        self.assertEqual(str(caught.exception), "GRAPH_HTTP_429")
        self.assertEqual(caught.exception.retry_after, 120)

    def test_http_transport_serializes_and_sends_the_graph_request(self):
        transport = GraphTransport()
        with patch.object(transport.opener, "open") as opened:
            opened.return_value.__enter__.return_value.read.return_value = b'{"id":"event-from-http"}'
            result = transport.request("POST", "https://graph.microsoft.com/v1.0/me/calendar/events",
                {"Authorization": "Bearer example-token"}, json_body={"transactionId": "booking-id"})
            request = opened.call_args.args[0]
            self.assertEqual(request.get_method(), "POST")
            self.assertEqual(request.get_header("Authorization"), "Bearer example-token")
            self.assertEqual(json.loads(request.data), {"transactionId": "booking-id"})
            self.assertEqual(result["id"], "event-from-http")

    def test_missing_credentials_produce_a_safe_configuration_error(self):
        provider = MicrosoftGraphCalendar()
        booking, student, resource = self.fixture()
        with self.assertRaisesRegex(OutlookError, "OUTLOOK_NOT_CONFIGURED"):
            provider.create_event(booking, student, resource, provider.target_path())

    @override_settings(DEBUG=False)
    def test_token_helper_cannot_run_in_production(self):
        with self.assertRaises(CommandError):
            call_command("outlook_token", stdout=io.StringIO())

    @override_settings(DEBUG=True, OUTLOOK_ACCESS_TOKEN="")
    def test_token_helper_saves_only_to_ignored_local_path(self):
        with tempfile.TemporaryDirectory() as directory:
            token_path = Path(directory) / ".local" / "outlook-token"
            with override_settings(BASE_DIR=Path(directory), OUTLOOK_TOKEN_FILE=str(token_path)):
                output = io.StringIO()
                with patch("booking.management.commands.outlook_token.getpass.getpass", return_value="example-token"):
                    call_command("outlook_token", stdout=output)
                self.assertEqual(token_path.read_text(encoding="utf-8"), "example-token")
                self.assertNotIn("example-token", output.getvalue())

    @override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
    def test_separate_worker_refuses_process_local_memory_repository(self):
        reset_runtime()
        with self.assertRaisesRegex(CommandError, "process-local"):
            call_command("process_outlook", stdout=io.StringIO())
