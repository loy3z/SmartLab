"""HTTP views: bookings (split from booking/views.py on 2026-10-25)."""

from ._common import *  # noqa: F401,F403 - shared imports, helpers and PublicView.

__all__ = ["BookingListView", "AdditionalHoursBookingView", "LongBookingView", "my_bookings", "PersonLookupView", "BookingDetailView", "BookingCancelView", "BookingRescheduleView", "BookingChangeView", "DashboardView", "BookingCheckInView", "BookingHistoryRemoveView"]

class BookingListView(APIView):
    def get(self, request):
        service = get_service()
        service.process_due_requests()
        bookings = my_bookings(service, request.user)
        lookups = BookingListLookups(service, bookings)
        return Response(collection(bookings, lambda item: booking_json(item, lookups)))

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

class AdditionalHoursBookingView(APIView):
    """Separate weekly allowance: unheld requests awaiting a Manager's explicit decision."""
    def post(self, request):
        service = get_service()
        service.require_booking_user(request.user)
        data = validated(AdditionalHoursCreateSerializer, request.data)
        booking, created = service.create_additional_hours_booking(
            request.user, str(data["resource_id"]), data["start"], data["end"], data["purpose"],
            data["additional_hours_reason"], request.headers.get("Idempotency-Key"),
            on_behalf_of_zid=data.get("on_behalf_of_zid") or None,
            active_data_collection=data["active_data_collection"], data_collection_reason=data["data_collection_reason"],
        )
        booking, = sync_after_write(service, booking)
        return Response(json_value(booking), status=201 if created else 200)


class LongBookingView(APIView):
    """A separate request to exceed the ordinary duration cap, requiring a Manager's decision."""
    def post(self, request):
        service = get_service()
        service.require_booking_user(request.user)
        data = validated(LongBookingCreateSerializer, request.data)
        booking, created = service.create_long_booking(
            request.user, str(data["resource_id"]), data["start"], data["end"], data["purpose"],
            data["long_booking_reason"], request.headers.get("Idempotency-Key"),
            on_behalf_of_zid=data.get("on_behalf_of_zid") or None,
        )
        booking, = sync_after_write(service, booking)
        return Response(json_value(booking), status=201 if created else 200)


def my_bookings(service, user):
    """Bookings for me plus those I created for other people, oldest first."""
    mine = {item.id: item for item in service.repo.list_bookings(student_id=user.id)}
    if user.role in (Role.ADMIN, Role.MANAGER):
        # 2026-10-29 (load test S5): filter in the repository instead of reading every booking.
        mine.update({item.id: item for item in service.repo.list_bookings(created_by=user.id) if item.created_by == user.id})
    # Sprint 3 (1.20.0): personal lists and Dashboard share visibility; reports keep the original rows.
    hidden = service.repo.hidden_booking_ids(user.id)
    return sorted((item for item in mine.values() if item.id not in hidden), key=lambda item: (item.created_at, item.id))


class BookingHistoryRemoveView(APIView):
    """Sprint 3 (1.20.0): remove only the caller's personal history entry, idempotently."""
    def post(self, request, booking_id):
        if request.data:
            raise DomainError("VALIDATION_ERROR", "The history removal action does not accept extra fields.")
        get_service().remove_booking_history(request.user, str(booking_id))
        return Response(status=204)

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
        lookups = BookingListLookups(service, bookings)
        return Response({"bookings": [booking_json(item, lookups) for item in bookings],
                         "qualifications": [submission_json(item) for item in submissions], "counts": counts,
                         "week_hours": service.week_hours(request.user.id)})  # 2026-11-03: hours left this week

class BookingCheckInView(APIView):
    def post(self, request, booking_id):
        if request.data:
            raise DomainError("VALIDATION_ERROR", "Check-in does not accept extra fields.")
        return Response(json_value(get_service().check_in(request.user, str(booking_id))))
