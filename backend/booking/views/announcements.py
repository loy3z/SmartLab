"""Sprint 3 (1.19.0): authenticated announcement reads and staff-only manual writes."""
from rest_framework import serializers

from ._common import APIView, Response, collection, get_service, json_value, validated
from ..serializers import StrictSerializer


class AnnouncementFields(StrictSerializer):
    title = serializers.CharField(max_length=120)
    body = serializers.CharField(max_length=1000)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class AnnouncementQuery(StrictSerializer):
    include_ended = serializers.BooleanField(required=False, default=False)


def announcement_json(item):
    result = json_value(item)
    person = get_service().repo.get_principal(item.created_by)
    result['author'] = {'id': item.created_by, 'display_name': person.display_name if person else 'Former staff member',
                        'role': item.author_role}
    result['active'] = item.removed_at is None and (item.expires_at is None or item.expires_at > get_service().now())
    return result


class AnnouncementListView(APIView):
    def get(self, request):
        data = validated(AnnouncementQuery, request.query_params)
        return Response(collection(get_service().list_announcements(request.user, **data), announcement_json))

    def post(self, request):
        service = get_service()
        service.require_staff(request.user)
        data = validated(AnnouncementFields, request.data)
        return Response(announcement_json(service.create_announcement(request.user, **data)), status=201)


class AnnouncementDetailView(APIView):
    def patch(self, request, announcement_id):
        service = get_service()
        service.require_staff(request.user)
        serializer = AnnouncementFields(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(announcement_json(service.update_announcement(request.user, str(announcement_id), serializer.validated_data)))


class AnnouncementRemoveView(APIView):
    def post(self, request, announcement_id):
        service = get_service()
        service.require_staff(request.user)
        validated(StrictSerializer, request.data)
        return Response(announcement_json(service.remove_announcement(request.user, str(announcement_id))))
