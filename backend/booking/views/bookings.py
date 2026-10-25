"""HTTP views: bookings (split from booking/views.py on 2026-10-25)."""

from ._common import *  # noqa: F401,F403 - shared imports, helpers and PublicView.

__all__ = ["BookingListView", "my_bookings", "PersonLookupView", "BookingDetailView", "BookingCancelView", "BookingRescheduleView", "BookingChangeView", "DashboardView", "BookingCheckInView"]

class BookingListView(APIView):
    def get(self, request):
        service = get_service()
        service.process_due_requests()
        return Response(collection(my_bookings(service, request.user)))

    def post(self, request):
        service = get_service()
        service.require_booking_user(request.user)
        data = validated(BookingCreateSerializer, request.data)
        booking, created = service.create_booking(request.user, str(data["resource_id"]), data["start"], data["end"], data["purpose"],
                                                  request.headers.get("Idempotency-Key"),
                                                  on_behalf_of_zid=data.get("on_behalf_of_zid") or None,
                                                  urgent=data["urgent"], urgent_reason=data["urgent_reason"])
        booking, = sync_after_write(service, booking)
        return Response(json_value(booking), status=201 if created else 200)

def my_bookings(service, user):
    """Bookings for me plus those I created for other people, oldest first."""
    mine = {item.id: item for item in service.repo.list_bookings(student_id=user.id)}
    if user.role in (Role.ADMIN, Role.MANAGER):
        mine.update({item.id: item for item in service.repo.list_bookings() if item.created_by == user.id})
    return sorted(mine.values(), key=lambda item: (item.created_at, item.id))

class PersonLookupView(APIView):
    """Admin/Manager: check whom you are booking for before submitting."""
    def get(self, request):
        data = validated(PersonLookupSerializer, request.query_params)
        person = get_service().find_person(request.user, data["zid"])
        return Response({"id": person.id, "zid": person.zid, "display_name": person.display_name, "role": person.role.value})

class BookingDetailView(APIView):
    def get(self, request, booking_id):
        service = get_service()
        service.process_due_requests()
        return Response(json_value(service.booking_for(request.user, str(booking_id))))

class BookingCancelView(APIView):
    def post(self, request, booking_id):
        if request.data:
            raise DomainError("VALIDATION_ERROR", "The cancellation action does not accept extra fields.")
        service = get_service()
        booking = service.cancel_booking(request.user, str(booking_id))
        booking, = sync_after_write(service, booking)
        return Response(json_value(booking))

class BookingRescheduleView(APIView):
    def post(self, request, booking_id):
        data = validated(BookingRescheduleSerializer, request.data)
        service = get_service()
        booking = service.reschedule_booking(request.user, str(booking_id), data["start"], data["end"])
        booking, = sync_after_write(service, booking)
        return Response(json_value(booking))

class BookingChangeView(APIView):
    """Sprint 3 (1.16.0): the person a booking is for asks to move it (services/changes.py). Returns the new request;
    the old booking stays until it is approved."""
    def post(self, request, booking_id):
        data = validated(BookingRescheduleSerializer, request.data)
        service = get_service()
        booking, created = service.request_time_change(request.user, str(booking_id), data["start"], data["end"],
                                                       request.headers.get("Idempotency-Key"))
        booking, = sync_after_write(service, booking)
        return Response(json_value(booking), status=201 if created else 200)

class DashboardView(APIView):
    def get(self, request):
        service = get_service()
        service.process_due_requests()
        bookings = my_bookings(service, request.user)
        submissions = service.repo.list_submissions(student_id=request.user.id)
        counts = {item.value: sum(booking.status == item for booking in bookings) for item in BookingStatus}
        return Response({"bookings": json_value(bookings), "qualifications": [submission_json(item) for item in submissions], "counts": counts})

class BookingCheckInView(APIView):
    def post(self, request, booking_id):
        if request.data:
            raise DomainError("VALIDATION_ERROR", "Check-in does not accept extra fields.")
        return Response(json_value(get_service().check_in(request.user, str(booking_id))))
