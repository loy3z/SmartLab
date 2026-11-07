"""HTTP views: admin (split from booking/views.py on 2026-10-25)."""

from ._common import *  # noqa: F401,F403 - shared imports, helpers and PublicView.

__all__ = ["AdminQualificationListView", "AdminQualificationReviewView", "staff_booking_rows", "staff_booking_json", "AdminBookingListView", "AdminBookingExportView", "_csv_safe", "AdminResourceStatusView", "audit_json", "AdminAuditListView", "user_json", "AdminStaffCreateView", "AdminManagerCreateView", "AdminUserListView", "AdminUserDetailView", "AdminUserResetAccessView", "AdminBookingReviewView", "changed_resource_json", "AdminResourceListView", "AdminResourceDetailView", "AdminResourceInternalInfoView", "AdminResourceArchiveView", "AdminResourceRestoreView", "AdminUsageReportView"]

class AdminQualificationListView(APIView):
    def get(self, request):
        service = get_service()
        service.require_staff(request.user)
        requested = request.query_params.get("status", "PENDING")
        if requested not in QualificationStatus._value2member_map_:
            raise DomainError("VALIDATION_ERROR", "Use PENDING, VERIFIED or REJECTED.")
        records = [item for item in service.repo.list_submissions() if item.status.value == requested]
        people = {item.id: item for item in service.repo.list_principals()}

        def staff_submission_json(record):
            # Reviewers need to know whose evidence it is, not only the internal id.
            result = submission_json(record)
            person = people.get(record.student_id)
            result["student"] = ({"id": person.id, "zid": person.zid, "display_name": person.display_name,
                                  "university_email": person.university_email} if person else None)
            return result

        return Response(collection(records, staff_submission_json))

class AdminQualificationReviewView(APIView):
    def post(self, request, submission_id):
        service = get_service()
        service.require_staff(request.user)
        data = validated(QualificationReviewSerializer, request.data)
        record, bookings = service.review_qualification(request.user, str(submission_id), data["decision"], data["reason"])
        bookings = sync_after_write(service, *bookings)
        return Response({"submission": submission_json(record), "updated_bookings": json_value(bookings)})

def staff_booking_rows(service, user, params):
    data = validated(AdminBookingQuerySerializer, params)
    records = service.booking_report(user, data["status"], data.get("resource_id"), data.get("student_id"),
                                     data.get("since"), data.get("until"), data.get("q"))
    people = {item.id: item for item in service.repo.list_principals()}
    resources = {item.id: item for item in service.repo.list_resources()}
    return records, people, resources

def staff_booking_json(booking, people, resources, lookups=None):
    """Booking plus who booked it and what, for Admin/Manager lists and printouts.

    lookups (2026-10-29, load test S2): a BookingListLookups shared by the whole list, so each row adds no queries.
    """
    result = booking_json(booking, lookups)
    person, resource = people.get(booking.student_id), resources.get(booking.resource_id)
    result["student"] = ({"id": person.id, "zid": person.zid, "display_name": person.display_name,
                          "university_email": person.university_email} if person else None)
    result["resource_name"] = resource.name if resource else None
    result["resource_kind"] = resource.kind.value if resource else None
    return result

class AdminBookingListView(APIView):
    """Admin/Manager booking list. Defaults to the manual-approval queue; status=ALL lists everything."""
    def get(self, request):
        service = get_service()
        service.require_staff(request.user)
        records, people, resources = staff_booking_rows(service, request.user, request.query_params)
        lookups = BookingListLookups(service, records, people)
        return Response(collection(records, lambda item: staff_booking_json(item, people, resources, lookups)))

class AdminBookingExportView(APIView):
    """Admin/Manager (Sprint 3: Admins too, for Booking Records): the same filters as the list (default status=ALL),
    as a CSV file for printing or Excel."""
    def get(self, request):
        service = get_service()
        service.require_staff(request.user)
        params = request.query_params.copy()
        params.setdefault("status", "ALL")
        records, people, resources = staff_booking_rows(service, request.user, params)
        zone = ZoneInfo(settings.TIME_ZONE)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Booking ID", "Status", "Reason", "Resource", "Type", "Date", "Start", "End", "Minutes",
                         "Student zID", "Student name", "Student email", "Purpose", "Submitted", "Decided by", "Decision reason",
                         "Created by", "Urgent", "Urgent reason", "Weekly series", "Attendance"])  # last two: Sprint 3
        for item in records:
            person, resource = people.get(item.student_id), resources.get(item.resource_id)
            local = ZoneInfo(resource.timezone) if resource else zone
            start, end = item.start.astimezone(local), item.end.astimezone(local)
            reviewer = people.get(item.reviewed_by) if item.reviewed_by else None
            writer.writerow([item.id, item.status.value, item.reason_code or "", resource.name if resource else item.resource_id,
                             resource.kind.value if resource else "", start.date().isoformat(), start.strftime("%H:%M"),
                             end.strftime("%H:%M"), int((item.end - item.start).total_seconds() // 60),
                             person.zid if person else "", person.display_name if person else "",
                             person.university_email if person else "", _csv_safe(item.purpose),
                             item.created_at.astimezone(local).strftime("%Y-%m-%d %H:%M"),
                             reviewer.zid if reviewer else (item.reviewed_by or ""), _csv_safe(item.decision_reason or ""),
                             creator.zid if (creator := people.get(item.created_by)) else (item.created_by or ""),
                             "Yes" if item.urgent else "", _csv_safe(item.urgent_reason or ""),
                             "Yes" if item.series_id else "", item.attendance or ""])
        response = HttpResponse("\ufeff" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="bookings.csv"'
        return response

def _csv_safe(text):
    """Stop spreadsheet apps from treating user text as a formula."""
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text

class AdminResourceStatusView(APIView):
    """Manager only: AVAILABLE / MAINTENANCE / CLOSED. Existing bookings are kept and listed for follow-up."""
    def patch(self, request, resource_id):
        service = get_service()
        service.require_manager(request.user)
        data = validated(ResourceStatusSerializer, request.data)
        # Sprint 3 (1.19.0): optional recovery estimate belongs to the status announcement.
        resource, affected = service.set_resource_status(request.user, str(resource_id), data["status"], data["reason"], expected_back=data["expected_back"])
        sync_after_write(service)
        people = {item.id: item for item in service.repo.list_principals()}
        resources = {resource.id: resource}
        lookups = BookingListLookups(service, affected, people)
        return Response({"resource": json_value(resource),
                         "affected_bookings": [staff_booking_json(item, people, resources, lookups) for item in affected]})

def audit_json(record, principals):
    result = json_value(record)
    person = principals.get(record.actor_id)
    result["actor"] = ({"id": person.id, "zid": person.zid, "display_name": person.display_name, "role": person.role.value}
                       if person else None)
    return result

class AdminAuditListView(APIView):
    """Audit trail of requests, approvals, changes and cancellations (Admin/Manager)."""
    def get(self, request):
        service = get_service()
        service.require_staff(request.user)
        data = validated(AuditQuerySerializer, request.query_params)
        total, records = service.audit_trail(request.user, **data)
        principals = {item.id: item for item in service.repo.list_principals()}
        return Response({"count": total, "limit": data["limit"], "offset": data["offset"],
                         "results": [audit_json(item, principals) for item in records]})

def user_json(service, user):
    """A person plus their induction status (students) and whether they are staff."""
    result = json_value(user)
    result["is_staff"] = user.is_staff
    result.update(service.staff_access(user))
    inductions = service.induction_summary(user.id)
    result["inductions"] = json_value(inductions)
    result["induction_status"] = "VERIFIED" if all(item["status"] == "VERIFIED" for item in inductions) else "INCOMPLETE"
    return result

class AdminStaffCreateView(APIView):
    """Manager only ("Add staff"): create an Admin or Manager account. Students are never promoted to staff."""
    def post(self, request):
        service = get_service()
        service.require_manager(request.user)
        data = validated(StaffCreateSerializer, request.data)
        created = service.create_staff(request.user, data["zid"], data["display_name"], data["university_email"], data["role"])
        return Response(user_json(service, created), status=status.HTTP_201_CREATED)

class AdminManagerCreateView(APIView):
    """Manager only ("Add manager"): kept for existing clients; same as Add staff with role MANAGER."""
    def post(self, request):
        service = get_service()
        service.require_manager(request.user)
        data = validated(ManagerCreateSerializer, request.data)
        created = service.create_manager(request.user, data["zid"], data["display_name"], data["university_email"])
        return Response(user_json(service, created), status=status.HTTP_201_CREATED)

class AdminUserListView(APIView):
    """Manager only: students (read only) and staff (roles and account status)."""
    def get(self, request):
        service = get_service()
        service.require_manager(request.user)
        data = validated(UserListQuerySerializer, request.query_params)
        users = service.list_users(request.user, data.get("role"), data["active"], data["q"])
        return Response(collection(users, lambda item: user_json(service, item)))

class AdminUserDetailView(APIView):
    def patch(self, request, user_id):
        service = get_service()
        service.require_manager(request.user)
        data = validated(UserUpdateSerializer, request.data)
        return Response(user_json(service, service.update_user(request.user, str(user_id), data.get("role"), data.get("active"))))

class AdminUserResetAccessView(APIView):
    """Manager only: clear a staff member's password and issue a new invite code."""
    def post(self, request, user_id):
        service = get_service()
        service.require_manager(request.user)
        return Response(user_json(service, service.reset_staff_access(request.user, str(user_id))))

class AdminBookingReviewView(APIView):
    def post(self, request, booking_id):
        service = get_service()
        service.require_staff(request.user)
        data = validated(BookingReviewSerializer, request.data)
        booking = service.review_booking(request.user, str(booking_id), data["decision"], data["reason"],
                                         confirm_active_data_collection=data["confirm_active_data_collection"])
        booking, = sync_after_write(service, booking)
        return Response(json_value(booking))

def changed_resource_json(service, resource, outside):
    """The saved resource plus the future bookings that no longer fit its rules (kept until a Manager acts)."""
    lookups = BookingListLookups(service, [booking for booking, _ in outside]) if outside else None
    people = lookups.people if lookups else {}
    return {"resource": json_value(resource),
            "bookings_outside_rules": [{**staff_booking_json(booking, people, {resource.id: resource}, lookups), "problem": code}
                                       for booking, code in outside]}

class AdminResourceListView(APIView):
    """GET: every resource including archived ones. POST: add a room or equipment."""
    def get(self, request):
        return Response(collection(get_service().list_all_resources(request.user)))

    def post(self, request):
        service = get_service()
        data = validated(ResourceCreateSerializer, request.data)
        kind = data.pop("kind")
        return Response(json_value(service.create_resource(request.user, kind, data)), status=status.HTTP_201_CREATED)

class AdminResourceDetailView(APIView):
    """PATCH: change the fields sent; the kind cannot change."""
    def patch(self, request, resource_id):
        service = get_service()
        if "kind" in request.data:
            raise DomainError("KIND_IS_FIXED", "A room cannot become equipment or the other way round. Add a new resource instead.", 409)
        data = validated(ResourceFieldsSerializer, request.data)
        resource, outside = service.update_resource(request.user, str(resource_id), data)
        return Response(changed_resource_json(service, resource, outside))

class AdminResourceInternalInfoView(APIView):
    """2026-11-07 (client, Week 8), Manager only: GET or PATCH the internal details of a resource."""
    def get(self, request, resource_id):
        return Response(json_value(get_service().resource_internal_info(request.user, str(resource_id))))

    def patch(self, request, resource_id):
        data = validated(ResourceInternalInfoSerializer, request.data)
        return Response(json_value(get_service().update_resource_internal_info(request.user, str(resource_id), data)))

class AdminResourceArchiveView(APIView):
    def post(self, request, resource_id):
        if request.data:
            raise DomainError("VALIDATION_ERROR", "This action does not accept fields.")
        return Response(json_value(get_service().archive_resource(request.user, str(resource_id))))

class AdminResourceRestoreView(APIView):
    def post(self, request, resource_id):
        if request.data:
            raise DomainError("VALIDATION_ERROR", "This action does not accept fields.")
        return Response(json_value(get_service().restore_resource(request.user, str(resource_id))))


# Sprint 3: usage report (Manager) -----------------------------------------------------------------------------

class AdminUsageReportView(APIView):
    def get(self, request):
        data = validated(UsageReportQuerySerializer, request.query_params)
        return Response(json_value(get_service().usage_report(request.user, data["first_date"], data["last_date"])))


# Sprint 3: staff change their own password --------------------------------------------------------------------
