"""The additional-hours workflow is separate, authenticated and Manager-controlled at the API boundary."""
from datetime import datetime, timedelta

from django.test import SimpleTestCase, override_settings

from booking.runtime import reset_runtime
from booking.tests.test_api import BookingAPIFixtureMixin, NOW, SYDNEY


@override_settings(DEBUG=True, ENABLE_DEMO_AUTH=True, SEED_DEMO_DATA=True)
class AdditionalHoursAPITests(BookingAPIFixtureMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.now = NOW
        self.service.clock = lambda: self.now
        self.service.min_advance_days, self.service.max_advance_days = 7, 28

    def additional_payload(self, **overrides):
        return {**self.payload(day_offset=3), "additional_hours_reason": "Finish a repeat experiment using spare capacity.",
                **overrides}

    def create_additional(self, client=None, payload=None, key=None):
        return (client or self.verified).post(
            "/api/v1/bookings/additional-hours/", payload or self.additional_payload(), format="json",
            **({"HTTP_IDEMPOTENCY_KEY": key} if key else {}))

    def review(self, booking_id, client=None, decision="APPROVED", **extra):
        return (client or self.manager).post(f"/api/v1/admin/bookings/{booking_id}/review/",
                                             {"decision": decision, **extra}, format="json")

    def test_separate_endpoint_validates_reasons_and_rejects_client_privilege_fields(self):
        self.assertEqual(self.create_additional(self.client).status_code, 401)
        self.assertEqual(self.create_additional(self.student).status_code, 403)
        for changes in ({"additional_hours_reason": " "}, {"active_data_collection": True},
                        {"data_collection_reason": "An unselected claim"}, {"approved": True},
                        {"priority_group": "PRIORITY"}, {"urgent": True}, {"additional_hours": True}):
            with self.subTest(changes=changes):
                response = self.create_additional(payload=self.additional_payload(**changes))
                self.assertEqual(response.status_code, 400, response.data)
        normal = self.verified.post("/api/v1/bookings/",
                                    {**self.payload(day_offset=8), "additional_hours": True}, format="json")
        self.assertEqual(normal.status_code, 400, normal.data)

    def test_request_is_unheld_and_idempotency_cannot_change_request_kind_or_reason(self):
        created = self.create_additional(key="extra-request")
        self.assertEqual(created.status_code, 201, created.data)
        booking = created.data
        self.assertEqual(booking["status"], "PENDING_APPROVAL")
        self.assertTrue(booking["additional_hours"])
        self.assertIsNone(booking["hold_until"])
        self.assertIsNone(booking["review_due_at"])
        self.assertFalse(booking["hold_active"])
        self.assertFalse(booking["blocks_slot"])
        review = booking["additional_hours_review"]
        self.assertEqual(review["approval_window_hours"], 48)
        self.assertEqual(review["blocker_code"], "ADDITIONAL_HOURS_TOO_EARLY")
        self.assertIn("NO_USE_THIS_WEEK", review["priority_reasons"])
        replay = self.create_additional(key="extra-request")
        self.assertEqual((replay.status_code, replay.data["id"]), (200, booking["id"]))
        changed = self.create_additional(payload=self.additional_payload(additional_hours_reason="Different reason"), key="extra-request")
        self.assertEqual((changed.status_code, changed.data["error"]["code"]), (409, "IDEMPOTENCY_CONFLICT"))
        normal = self.verified.post("/api/v1/bookings/", self.payload(day_offset=3), format="json",
                                    HTTP_IDEMPOTENCY_KEY="extra-request")
        self.assertEqual((normal.status_code, normal.data["error"]["code"]), (409, "IDEMPOTENCY_CONFLICT"))

    def test_manager_checks_window_and_confirms_collection_claim_at_approval(self):
        created = self.create_additional(payload=self.additional_payload(
            active_data_collection=True, data_collection_reason="Continue the experiment currently collecting samples."))
        self.assertEqual(created.status_code, 201, created.data)
        booking = created.data
        for client in (self.admin, self.verified):
            denied = self.review(booking["id"], client, confirm_active_data_collection=True)
            self.assertEqual(denied.status_code, 403, denied.data)
        too_early = self.review(booking["id"], confirm_active_data_collection=True)
        self.assertEqual((too_early.status_code, too_early.data["error"]["code"]), (409, "ADDITIONAL_HOURS_TOO_EARLY"))
        start = datetime.fromisoformat(booking["start"].replace("Z", "+00:00"))
        self.now = start - timedelta(hours=48)
        unconfirmed = self.review(booking["id"])
        self.assertEqual((unconfirmed.status_code, unconfirmed.data["error"]["code"]),
                         (400, "DATA_COLLECTION_CONFIRMATION_REQUIRED"))
        approved = self.review(booking["id"], confirm_active_data_collection=True)
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(approved.data["status"], "APPROVED")
        self.assertTrue(approved.data["blocks_slot"])
        self.assertFalse(approved.data["additional_hours_review"]["can_approve"])
        audit = next(item for item in self.service.repo.list_audit()
                     if item.entity_id == booking["id"] and item.action == "ADDITIONAL_HOURS_APPROVED")
        self.assertTrue(audit.details["active_data_collection_confirmed"])

    def test_on_behalf_requires_staff_and_creator_cannot_review(self):
        body = self.additional_payload(on_behalf_of_zid="z1000001")
        self.assertEqual(self.create_additional(self.student, body).status_code, 403)
        created = self.create_additional(self.manager, body)
        self.assertEqual(created.status_code, 201, created.data)
        denied = self.review(created.data["id"], decision="REJECTED", reason="Cannot review my own request")
        self.assertEqual((denied.status_code, denied.data["error"]["code"]), (403, "SELF_REVIEW_FORBIDDEN"))

    def test_unreviewed_request_never_auto_approves_and_expires_at_start(self):
        created = self.create_additional(payload={**self.additional_payload(), **self.payload(day_offset=8)})
        self.assertEqual(created.status_code, 201, created.data)
        booking = created.data
        start = datetime.fromisoformat(booking["start"].replace("Z", "+00:00"))
        self.now += timedelta(days=2)
        pending = self.verified.get(f"/api/v1/bookings/{booking['id']}/")
        self.assertEqual(pending.data["status"], "PENDING_APPROVAL")
        self.now = start
        expired = self.verified.get(f"/api/v1/bookings/{booking['id']}/")
        self.assertEqual(expired.data["status"], "EXPIRED")
        self.assertFalse(expired.data["blocks_slot"])

    def test_availability_allows_short_notice_but_keeps_duration_and_maximum_window(self):
        path = f"/api/v1/resources/{self.room['id']}/availability/"
        today = NOW.astimezone(SYDNEY).date()
        normal = self.verified.get(path, {"date": today.isoformat()})
        self.assertEqual(normal.data["min_advance_days"], 7)
        extra = self.verified.get(path, {"date": today.isoformat(), "additional_hours": "true"})
        self.assertEqual(extra.status_code, 200, extra.data)
        self.assertEqual((extra.data["min_advance_days"], extra.data["max_advance_days"]), (0, 28))
        self.assertEqual(extra.data["earliest_date"], today.isoformat())
        self.assertEqual(extra.data["additional_hours_approval_window_hours"], 48)
        self.assertEqual(extra.data["max_booking_minutes"], 180)
        for values in ({"duration_minutes": 240}, {"urgent": "true"}):
            with self.subTest(values=values):
                denied = self.verified.get(path, {"date": today.isoformat(), "additional_hours": "true", **values})
                self.assertEqual(denied.status_code, 400, denied.data)
        denied = self.create_additional(payload={**self.additional_payload(), **self.payload(day_offset=29)})
        self.assertEqual((denied.status_code, denied.data["error"]["code"]), (400, "BOOKING_TOO_FAR_AHEAD"))

    def test_extra_grant_cannot_be_moved_using_normal_change_or_reschedule(self):
        created = self.create_additional(payload={**self.additional_payload(), **self.payload(day_offset=1)})
        self.assertEqual(created.status_code, 201, created.data)
        booking = created.data
        approved = self.review(booking["id"])
        self.assertEqual(approved.status_code, 200, approved.data)
        new = self.payload(day_offset=2)
        for action, client in (("change", self.verified), ("reschedule", self.manager)):
            with self.subTest(action=action):
                denied = client.post(f"/api/v1/bookings/{booking['id']}/{action}/",
                                     {"start": new["start"], "end": new["end"]}, format="json")
                self.assertEqual((denied.status_code, denied.data["error"]["code"]),
                                 (409, "ADDITIONAL_HOURS_NEW_REQUEST_REQUIRED"))

    def test_approval_window_is_configurable_and_endpoint_is_documented(self):
        with override_settings(ADDITIONAL_HOURS_APPROVAL_WINDOW_HOURS=24):
            self.assertEqual(reset_runtime().rules().additional_hours_approval_window_hours, 24)
        schema = self.client.get("/api/schema/").json()
        self.assertIn("/api/v1/bookings/additional-hours/", schema["paths"])
