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

class DemoLoginSerializer(StrictSerializer):
    zid = serializers.RegexField(r"^z[0-9]{7}$")

class BookingCreateSerializer(StrictSerializer):
    resource_id = serializers.UUIDField()
    start = AwareDateTimeField()
    end = AwareDateTimeField()
    purpose = serializers.CharField(max_length=1000)

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
    valid_until = AwareDateTimeField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        if attrs["decision"] == "REJECTED" and not attrs["reason"].strip():
            raise serializers.ValidationError({"reason": "A rejection reason is required."})
        return attrs

class BookingReviewSerializer(StrictSerializer):
    decision = serializers.ChoiceField(choices=["APPROVED", "REJECTED"])
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)

    def validate(self, attrs):
        if attrs["decision"] == "REJECTED" and not attrs["reason"].strip():
            raise serializers.ValidationError({"reason": "A rejection reason is required."})
        return attrs

class AvailabilityQuerySerializer(StrictSerializer):
    date = serializers.DateField()
    duration_minutes = serializers.IntegerField(default=30, min_value=1, max_value=1440)
