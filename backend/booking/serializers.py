from pathlib import Path
from datetime import datetime
from django.utils.dateparse import parse_datetime
from rest_framework import serializers

class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        unknown = set(data.keys()) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: ["Unknown field."] for key in sorted(unknown)})
        return super().to_internal_value(data)

class AwareDateTimeField(serializers.DateTimeField):
    def to_internal_value(self, value):
        try:
            parsed = value if isinstance(value, datetime) else parse_datetime(value)
        except (TypeError, ValueError):
            parsed = None
        if parsed is None or parsed.tzinfo is None or parsed.utcoffset() is None:
            raise serializers.ValidationError("Use an ISO 8601 timestamp with Z or a UTC offset.")
        return super().to_internal_value(value)

class DemoRegisterSerializer(StrictSerializer):
    zid = serializers.RegexField(r"^z[0-9]{7}$")
    display_name = serializers.CharField(max_length=120)
    university_email = serializers.EmailField(max_length=254)

class DemoLoginSerializer(StrictSerializer):
    zid = serializers.RegexField(r"^z[0-9]{7}$")

class TestLoginSerializer(StrictSerializer):
    login_id = serializers.ChoiceField(choices=["1"])

class TestSessionSerializer(StrictSerializer):
    role = serializers.ChoiceField(choices=["STUDENT", "ADMIN", "MANAGER"])
    bypass_booking_rules = serializers.BooleanField()

class StaffSignInSerializer(StrictSerializer):
    zid = serializers.RegexField(r"^[zZ][0-9]{7}$")
    password = serializers.CharField(max_length=128, trim_whitespace=False)

class StaffActivateSerializer(StrictSerializer):
    zid = serializers.RegexField(r"^[zZ][0-9]{7}$")
    invite_code = serializers.CharField(max_length=20)
    password = serializers.CharField(max_length=128, trim_whitespace=False)

class BookingCreateSerializer(StrictSerializer):
    resource_id = serializers.UUIDField()
    start = AwareDateTimeField()
    end = AwareDateTimeField()
    purpose = serializers.CharField(max_length=1000)
    # Admin/Manager only: book for someone else (the booking is theirs; created_by records the staff member).
    on_behalf_of_zid = serializers.RegexField(r"^[zZ]\d{7}$", required=False, allow_blank=True)
    # Sooner than the minimum advance window; a Manager must approve it.
    urgent = serializers.BooleanField(required=False, default=False)
    urgent_reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class PersonLookupSerializer(StrictSerializer):
    zid = serializers.RegexField(r"^[zZ]\d{7}$")


class AdditionalHoursCreateSerializer(StrictSerializer):
    resource_id = serializers.UUIDField()
    start = AwareDateTimeField()
    end = AwareDateTimeField()
    purpose = serializers.CharField(max_length=1000)
    on_behalf_of_zid = serializers.RegexField(r"^[zZ]\d{7}$", required=False, allow_blank=True)
    additional_hours_reason = serializers.CharField(max_length=1000)
    active_data_collection = serializers.BooleanField(required=False, default=False)
    data_collection_reason = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["active_data_collection"] and not attrs["data_collection_reason"].strip():
            raise serializers.ValidationError({"data_collection_reason": "Explain the ongoing data collection for Manager verification."})
        if not attrs["active_data_collection"] and attrs["data_collection_reason"].strip():
            raise serializers.ValidationError({"data_collection_reason": "Select active data collection when providing this explanation."})
        return attrs


class LongBookingCreateSerializer(StrictSerializer):
    resource_id = serializers.UUIDField()
    start = AwareDateTimeField()
    end = AwareDateTimeField()
    purpose = serializers.CharField(max_length=1000)
    on_behalf_of_zid = serializers.RegexField(r"^[zZ]\d{7}$", required=False, allow_blank=True)
    long_booking_reason = serializers.CharField(max_length=1000)


class BookingRescheduleSerializer(StrictSerializer):
    start = AwareDateTimeField()
    end = AwareDateTimeField()

class BookingExtendSerializer(StrictSerializer):  # 2026-11-06 (client, Week 8)
    end = AwareDateTimeField()

class QualificationCreateSerializer(StrictSerializer):
    requirement_id = serializers.UUIDField()
    title = serializers.CharField(max_length=160)
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    file = serializers.FileField()

    def validate_file(self, value):
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Maximum file size is 5 MiB.")
        data = value.read()
        value.seek(0)
        suffix = Path(value.name).suffix.lower()
        pdf = suffix == ".pdf" and value.content_type == "application/pdf" and data.startswith(b"%PDF-") and b"%%EOF" in data[-1024:]
        png = suffix == ".png" and value.content_type == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR" and data[-12:-8] == b"\x00\x00\x00\x00" and data[-8:-4] == b"IEND"
        jpeg = suffix in (".jpg", ".jpeg") and value.content_type == "image/jpeg" and data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")
        if not (pdf or png or jpeg):
            raise serializers.ValidationError("Upload a PDF, PNG or JPEG with matching file content and MIME type.")
        return value

class QualificationReviewSerializer(StrictSerializer):
    decision = serializers.ChoiceField(choices=["VERIFIED", "REJECTED"])
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)
    # No valid_until input: expiry is fixed by QUALIFICATION_VALIDITY_DAYS (Sprint 1 policy).

    def validate(self, attrs):
        if attrs["decision"] == "REJECTED" and not attrs["reason"].strip():
            raise serializers.ValidationError({"reason": "A rejection reason is required."})
        return attrs

class BookingReviewSerializer(StrictSerializer):
    decision = serializers.ChoiceField(choices=["APPROVED", "REJECTED"])
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)
    confirm_active_data_collection = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if attrs["decision"] == "REJECTED" and not attrs["reason"].strip():
            raise serializers.ValidationError({"reason": "A rejection reason is required."})
        return attrs

class DayOverviewQuerySerializer(StrictSerializer):
    date = serializers.DateField()
    duration_minutes = serializers.IntegerField(default=60, min_value=1, max_value=1440)
    kind = serializers.ChoiceField(choices=["ROOM", "EQUIPMENT"], required=False)
    room_id = serializers.UUIDField(required=False)
    category = serializers.CharField(max_length=60, required=False, allow_blank=True)
    q = serializers.CharField(max_length=100, required=False, allow_blank=True)
    bookable_only = serializers.BooleanField(required=False, default=False)
    free_at = serializers.TimeField(required=False, format="%H:%M", input_formats=["%H:%M"])


class AvailabilityQuerySerializer(StrictSerializer):
    date = serializers.DateField()
    duration_minutes = serializers.IntegerField(default=30, min_value=1, max_value=1440)
    exclude_booking_id = serializers.UUIDField(required=False)
    for_zid = serializers.RegexField(r"^[zZ]\d{7}$", required=False, allow_blank=True)
    urgent = serializers.BooleanField(required=False, default=False)
    additional_hours = serializers.BooleanField(required=False, default=False)
    long_booking = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if sum(bool(attrs[key]) for key in ("urgent", "additional_hours", "long_booking")) > 1:
            raise serializers.ValidationError("Choose only one of urgent, additional-hours or longer-booking availability.")
        return attrs


class OutlookProcessSerializer(StrictSerializer):
    limit = serializers.IntegerField(default=1, min_value=1, max_value=5)


class AuditQuerySerializer(StrictSerializer):
    resource_id = serializers.UUIDField(required=False)
    student_id = serializers.UUIDField(required=False)
    entity_type = serializers.ChoiceField(choices=["booking", "qualification", "resource", "principal"], required=False)
    entity_id = serializers.UUIDField(required=False)
    action = serializers.RegexField(r"^[A-Z][A-Z0-9_]{0,63}$", required=False)
    actor_id = serializers.RegexField(r"^(SYSTEM|[0-9a-fA-F-]{36})$", required=False)
    since = AwareDateTimeField(required=False)
    until = AwareDateTimeField(required=False)
    limit = serializers.IntegerField(default=100, min_value=1, max_value=500)
    offset = serializers.IntegerField(default=0, min_value=0)


class UserListQuerySerializer(StrictSerializer):
    role = serializers.ChoiceField(choices=["STUDENT", "ADMIN", "MANAGER"], required=False)
    active = serializers.BooleanField(required=False, allow_null=True, default=None)
    q = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")


class UserUpdateSerializer(StrictSerializer):
    role = serializers.ChoiceField(choices=["STUDENT", "ADMIN", "MANAGER"], required=False)
    active = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide role and/or active.")
        return attrs


class BookingPolicySerializer(StrictSerializer):
    pending_hold_minutes = serializers.IntegerField(min_value=1, max_value=20160)


class ResourceStatusSerializer(StrictSerializer):
    expected_back = serializers.DateTimeField(required=False, allow_null=True, default=None)  # Sprint 3 (1.19.0)
    status = serializers.ChoiceField(choices=["AVAILABLE", "MAINTENANCE", "CLOSED"])
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)


class ManagerCreateSerializer(StrictSerializer):
    zid = serializers.RegexField(r"^[zZ]\d{7}$")
    display_name = serializers.CharField(max_length=120)
    university_email = serializers.EmailField(max_length=254)


class StaffCreateSerializer(ManagerCreateSerializer):
    role = serializers.ChoiceField(choices=["ADMIN", "MANAGER"])


class PrerequisiteSerializer(StrictSerializer):
    prerequisite_ids = serializers.ListField(child=serializers.UUIDField(), max_length=20, allow_empty=True)


class RequirementFieldsSerializer(StrictSerializer):
    """Sprint 3 (1.16.0): induction texts a Manager writes. Limits are checked again in qualifications.py."""
    name = serializers.CharField(required=False, max_length=120)
    description = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    how_to_complete = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    accepted_evidence = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    reviewer = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    contact = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class RequirementUpdateSerializer(RequirementFieldsSerializer):
    """Sprint 3 (1.16.0): PATCH takes the texts and/or prerequisite_ids (as before)."""
    prerequisite_ids = serializers.ListField(child=serializers.UUIDField(), max_length=20, allow_empty=True, required=False)


class SiteContactSerializer(StrictSerializer):
    """Sprint 3 (1.16.0): the lab's contact details (every field optional; blank clears it)."""
    email = serializers.CharField(required=False, allow_blank=True, max_length=200)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=60)
    hours = serializers.CharField(required=False, allow_blank=True, max_length=200)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class ResourceDetailSerializer(StrictSerializer):
    """Sprint 3 (1.16.0): one "label: value" line on a resource."""
    label = serializers.CharField(allow_blank=True, max_length=40)
    value = serializers.CharField(allow_blank=True, max_length=200)


BOOKING_STATUS_VALUES = ["WAITING_QUALIFICATION", "PENDING_APPROVAL", "WAITLISTED", "APPROVED", "REJECTED", "CANCELLED", "EXPIRED"]


class AdminBookingQuerySerializer(StrictSerializer):
    """status: one status, a comma-separated list, or ALL."""
    status = serializers.CharField(required=False, default="PENDING_APPROVAL", max_length=200)
    resource_id = serializers.UUIDField(required=False)
    student_id = serializers.UUIDField(required=False)
    since = AwareDateTimeField(required=False)
    until = AwareDateTimeField(required=False)
    # Sprint 3 (Booking Records): part of the zID or name of the person booked for, or of whoever created it.
    q = serializers.CharField(required=False, allow_blank=True, max_length=100)

    def validate_status(self, value):
        if value.strip().upper() == "ALL":
            return None
        values = [item.strip() for item in value.split(",") if item.strip()]
        unknown = [item for item in values if item not in BOOKING_STATUS_VALUES]
        if not values or unknown:
            raise serializers.ValidationError("Use ALL or booking statuses separated by commas.")
        return values

    def validate(self, attrs):
        if attrs.get("since") and attrs.get("until") and attrs["since"] >= attrs["until"]:
            raise serializers.ValidationError({"until": "until must be later than since."})
        return attrs


# Sprint 3 -------------------------------------------------------------------------------------------------------

class NotificationQuerySerializer(StrictSerializer):
    unread = serializers.BooleanField(required=False, default=False)
    limit = serializers.IntegerField(required=False, default=50, min_value=1, max_value=200)


class NotificationPreferencesSerializer(StrictSerializer):
    """Sprint 3 (1.19.0): {"preferences": {"bookings": {"in_app": true, "email": false}}}."""
    # Sprint 3 (1.19.0): independent channel choices, with partial updates.
    preferences = serializers.DictField(child=serializers.DictField(child=serializers.BooleanField(), allow_empty=False), allow_empty=False)


class UnfreezeRequestSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=1000)


class UnfreezeReviewSerializer(BookingReviewSerializer):
    pass


class UnfreezeListQuerySerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=["PENDING", "APPROVED", "REJECTED"], required=False)


class UnfreezeSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class SeriesPlanSerializer(StrictSerializer):
    resource_id = serializers.UUIDField()
    # ISO weekdays: 1 = Monday ... 7 = Sunday.
    weekdays = serializers.ListField(child=serializers.IntegerField(min_value=1, max_value=7), min_length=1, max_length=7)
    start_time = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"])
    duration_minutes = serializers.IntegerField(min_value=1, max_value=1440)
    first_date = serializers.DateField()
    last_date = serializers.DateField()
    on_behalf_of_zid = serializers.RegexField(r"^[zZ]\d{7}$", required=False, allow_blank=True)


class SeriesCreateSerializer(SeriesPlanSerializer):
    purpose = serializers.CharField(max_length=1000)
    skip_dates = serializers.ListField(child=serializers.DateField(), required=False, default=list, max_length=400)


class ResourceFieldsSerializer(StrictSerializer):
    """Manager resource setup. Every field is optional here; the service applies the rules (resources.py)."""
    name = serializers.CharField(required=False, max_length=120)
    location = serializers.CharField(required=False, max_length=120)
    description = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    required_qualification_id = serializers.UUIDField(required=False)
    room_id = serializers.UUIDField(required=False, allow_null=True)
    category = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=60)
    slot_minutes = serializers.IntegerField(required=False)
    max_booking_minutes = serializers.IntegerField(required=False)
    opening_time = serializers.TimeField(required=False)
    closing_time = serializers.TimeField(required=False)
    pending_hold_minutes = serializers.IntegerField(required=False)
    # Sprint 3 (1.16.0): rooms' capacity and free "label: value" details.
    capacity = serializers.IntegerField(required=False, allow_null=True)
    details = serializers.ListField(child=ResourceDetailSerializer(), required=False, max_length=50)

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        for field in ("required_qualification_id", "room_id"):
            if values.get(field) is not None:
                values[field] = str(values[field])
        return values


class ResourceCreateSerializer(ResourceFieldsSerializer):
    kind = serializers.ChoiceField(choices=["ROOM", "EQUIPMENT"])


class UsageReportQuerySerializer(StrictSerializer):
    """Sprint 3: local dates of the usage report (both included)."""
    first_date = serializers.DateField()
    last_date = serializers.DateField()


class ChangePasswordSerializer(StrictSerializer):
    """Sprint 3: staff change their own password."""
    current_password = serializers.CharField(max_length=128, trim_whitespace=False)
    new_password = serializers.CharField(max_length=128, trim_whitespace=False)
