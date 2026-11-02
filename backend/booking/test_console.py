"""Sprint 3 (1.17.0): the local test account 1 (development only). Session overrides never change stored roles.

Switched on only when all five conditions hold (``test_console_enabled``): DEBUG, ENABLE_DEMO_AUTH,
ENABLE_TEST_CONSOLE, the demo identity provider, and the in-memory store. The last one (Loy, 2026-10-25) keeps
test bookings out of the PostgreSQL database, so they never appear in real records, reports or the Today page and
never take a real time slot; restarting the backend throws them away.
"""
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo
from uuid import NAMESPACE_URL, uuid5

from django.conf import settings
from django.http import Http404

from .domain import Booking, BookingStatus, Principal, QualificationStatus, QualificationSubmission, Role
from .errors import DomainError

TEST_ACCOUNT_ID = "00000000-0000-0000-0000-000000000999"
MEMORY_REPOSITORY = "booking.repository.MemoryRepository"


def test_console_enabled():
    return bool(settings.DEBUG and settings.ENABLE_DEMO_AUTH
                and settings.ENABLE_TEST_CONSOLE
                and settings.AUTH_PROVIDER == "booking.authentication.DemoIdentityProvider"
                and settings.REPOSITORY_FACTORY == MEMORY_REPOSITORY)  # Sprint 3 (1.17.0): memory mode only


def require_test_console():
    if not test_console_enabled():
        raise Http404("Test console is disabled.")


@dataclass(frozen=True)
class TestPrincipal(Principal):
    test_account: bool = True
    bypass_booking_rules: bool = False  # every caller sets it; off is the safe default


def test_identity(principal, role, bypass):
    values = asdict(principal)
    values.update(role=Role(role), test_account=True, bypass_booking_rules=bool(bypass))
    return TestPrincipal(**values)


def booking_rules_bypassed(actor, beneficiary_id=None):
    return (test_console_enabled() and isinstance(actor, TestPrincipal)
            and actor.id == TEST_ACCOUNT_ID and actor.active and actor.bypass_booking_rules
            and (beneficiary_id is None or beneficiary_id == actor.id))


def get_test_account(service):
    require_test_console()
    with service.repo.atomic(student_ids=[TEST_ACCOUNT_ID]):
        principal = service.repo.get_principal(TEST_ACCOUNT_ID)
        if principal is None:
            if any(person.zid == "1" for person in service.repo.list_principals()):
                raise DomainError("TEST_ACCOUNT_CONFLICT", "Login ID 1 is already in use.", 409)
            principal = Principal(TEST_ACCOUNT_ID, "1", "Test account 1", Role.STUDENT,
                                  "test-account@smartlab.invalid")
            service.repo.save_principal(principal)
            service._audit(principal.id, "TEST_ACCOUNT_CREATED", "principal", principal.id)
        if principal.zid != "1" or not principal.active:
            raise DomainError("TEST_ACCOUNT_UNAVAILABLE", "The test account is inactive or unavailable.", 403)
        _grant_test_inductions(service)
        return principal


def _grant_test_inductions(service):
    """Sprint 3: account 1 owns every induction permanently, including newly added requirements.

    Called only after the local-memory test-console gate and identity checks, under its account lock.
    Batch-read this account's records once. Grants have no evidence file: they are explicit test access,
    not uploaded certificates. Repeated reads do not create more submissions or audit records.
    """
    latest = {}
    for record in service.repo.list_submissions(student_id=TEST_ACCOUNT_ID):
        previous = latest.get(record.requirement_id)
        if previous is None or record.submitted_at >= previous.submitted_at:
            latest[record.requirement_id] = record
    for requirement in service.repo.list_requirements():
        previous = latest.get(requirement.id)
        if previous and previous.status == QualificationStatus.VERIFIED and previous.valid_until is None:
            continue
        now = service.now()
        record = QualificationSubmission(
            str(uuid5(NAMESPACE_URL, f"smartlab:test-induction:{requirement.id}")),
            TEST_ACCOUNT_ID, requirement.id, "Automatic test-account access",
            "Granted automatically to local test account 1. No training evidence is required.",
            "", max(now, previous.submitted_at) if previous else now,
            status=QualificationStatus.VERIFIED, reviewed_by=TEST_ACCOUNT_ID, reviewed_at=now,
            valid_until=None,
        )
        service.repo.save_submission(record)
        service._audit(TEST_ACCOUNT_ID, "TEST_INDUCTION_GRANTED", "qualification", record.id,
                       requirement_id=requirement.id)


def test_period_violation(service, resource, start, end):
    if not resource.active:
        return DomainError("RESOURCE_UNAVAILABLE", "Restore this resource before booking it.", 409)
    if start >= end or start <= service.now():
        return DomainError("INVALID_TIME", "Use a future start time and an end later than start.")
    if end - start > timedelta(days=1):
        return DomainError("INVALID_TIME", "Choose a test booking of up to 24 hours.")
    return None


def create_test_booking(service, actor, resource, booking_id, start, end, purpose, urgent, reason, replaces):
    """Approve the test account's own booking at once, skipping lab policy (window, induction, opening hours,
    maintenance, length, weekly limit, freeze). Still enforced: an active resource, a future start, at most 24 h,
    no duplicate and no clash with another booking or held time. Called inside the normal transaction."""
    error = test_period_violation(service, resource, start, end)
    if error:
        raise error
    replaced_id = replaces.id if replaces else None
    service._reject_duplicate_request(actor.id, resource.id, start, end, replaced_id)
    if service._overlaps(resource.id, start, end, also_exclude=replaced_id):
        raise DomainError("BOOKING_CONFLICT", "Test overrides cannot displace an existing booking or held time.", 409)
    now = service.now()
    booking = Booking(booking_id, actor.id, resource.id, start, end, purpose.strip(), now,
                      BookingStatus.APPROVED, "TEST_OVERRIDE", reviewed_by=actor.id, reviewed_at=now,
                      updated_at=now, created_by=actor.id, urgent=bool(urgent), urgent_reason=reason or None,
                      replaces_id=replaced_id, attendance="NOT_TRACKED")
    service._save_booking(booking)
    service._audit(actor.id, "TEST_BOOKING_CREATED", "booking", booking.id,
                   role=actor.role.value, bypass_booking_rules=True, urgent=bool(urgent))
    service._notify(actor.id, "BOOKING_APPROVED", "Test booking approved",
                     f"{service._booking_label(booking)} was approved using test overrides.", booking)
    return booking, True


def test_availability(service, actor, resource, day, duration_minutes, exclude):
    if not resource.active:
        raise DomainError("RESOURCE_UNAVAILABLE", "Restore this resource before booking it.", 409)
    if duration_minutes < 1 or duration_minutes > 1440 or duration_minutes % resource.slot_minutes:
        raise DomainError("INVALID_DURATION", "Choose time steps of this resource, up to 24 hours.")
    zone = ZoneInfo(resource.timezone)
    opening = datetime.combine(day, time.min, zone)
    # The next local midnight, not "+24 h": a daylight-saving day is 23 or 25 hours long.
    closing = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(UTC)
    cursor = opening.astimezone(UTC)
    slots = []
    own = [item for item in service.repo.list_bookings(student_id=actor.id, resource_id=resource.id)
           if item.id != exclude and item.status in (BookingStatus.APPROVED, BookingStatus.PENDING_APPROVAL,
                                                     BookingStatus.WAITING_QUALIFICATION, BookingStatus.WAITLISTED)]
    while cursor + timedelta(minutes=duration_minutes) <= closing:
        end = cursor + timedelta(minutes=duration_minutes)
        blockers = service._overlaps(resource.id, cursor, end, exclude)
        reason = ("START_TIME_PASSED" if cursor <= service.now() else
                  "BOOKED" if any(item.status == BookingStatus.APPROVED for item in blockers) else
                  "TEMPORARILY_HELD" if blockers else None)
        slots.append({"start": cursor, "end": end, "available": reason is None, "reason_code": reason,
                      "hold_until": max((item.hold_until for item in blockers if item.hold_until), default=None),
                      "held_by_me": bool(blockers) and all(item.student_id == actor.id for item in blockers),
                      "requested_by_me": any(cursor < item.end and item.start < end for item in own)})
        cursor += timedelta(minutes=resource.slot_minutes)
    return {"resource_id": resource.id, "date": day.isoformat(), "timezone": resource.timezone,
            "duration_minutes": duration_minutes, "slots": slots, **test_window(service),
            "resource_status": resource.status.value, "status_reason": resource.status_reason,
            "review_window_minutes": 0,
            "can_request": True, "qualification_status": "VERIFIED", "frozen_until": None,
            "missing_prerequisite_id": None, "test_bypass": True, "max_booking_minutes": 1440,
            "booking_slot_minutes": 30, "max_booking_slots": 48,
            "selection_step_minutes": resource.slot_minutes,
            "booking_for": {"id": actor.id, "zid": actor.zid, "display_name": actor.display_name,
                            "role": actor.role.value}, "urgent": False}


def test_window(service):
    return {"earliest_date": service.now().astimezone(ZoneInfo("Australia/Sydney")).date().isoformat(),
            "latest_date": None, "min_advance_days": 0, "max_advance_days": 0, "test_bypass": True}
