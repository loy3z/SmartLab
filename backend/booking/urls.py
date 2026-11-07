from django.urls import path, re_path
from . import views

urlpatterns = [
    # Sprint 3 (1.19.0): manual staff announcements and authenticated reads.
    path("announcements/", views.AnnouncementListView.as_view()),
    path("announcements/<uuid:announcement_id>/", views.AnnouncementDetailView.as_view()),
    path("announcements/<uuid:announcement_id>/remove/", views.AnnouncementRemoveView.as_view()),
    path("health/", views.HealthView.as_view()),
    path("auth/config/", views.AuthConfigView.as_view()),
    path("auth/test-login/", views.TestLoginView.as_view()),
    path("auth/test-session/", views.TestSessionView.as_view()),
    path("auth/demo-register/", views.DemoRegisterView.as_view()),
    path("auth/demo-login/", views.DemoLoginView.as_view()),
    path("auth/staff-sign-in/", views.StaffSignInView.as_view()),
    path("auth/staff-activate/", views.StaffActivateView.as_view()),
    path("auth/change-password/", views.ChangePasswordView.as_view()),  # Sprint 3
    path("auth/me/", views.MeView.as_view()),
    path("resources/", views.ResourceListView.as_view()),
    path("resources/day-overview/", views.DayOverviewView.as_view()),
    path("resources/<uuid:resource_id>/", views.ResourceDetailView.as_view()),
    path("resources/<uuid:resource_id>/availability/", views.AvailabilityView.as_view()),
    path("qualification-requirements/", views.RequirementListView.as_view()),
    path("admin/qualification-requirements/<uuid:requirement_id>/", views.RequirementDetailView.as_view()),
    path("admin/qualification-requirements/", views.RequirementCreateView.as_view()),  # Sprint 3 (1.16.0)
    path("site/contact/", views.SiteContactView.as_view()),  # Sprint 3 (1.16.0): GET anyone, PATCH Manager
    path("admin/overview/", views.StaffOverviewView.as_view()),  # Sprint 3 (1.16.0)
    path("qualifications/", views.QualificationListView.as_view()),
    path("qualifications/<uuid:submission_id>/", views.QualificationDetailView.as_view()),
    path("qualifications/<uuid:submission_id>/file/", views.QualificationFileView.as_view()),
    path("bookings/", views.BookingListView.as_view()),
    path("bookings/additional-hours/", views.AdditionalHoursBookingView.as_view()),
    path("bookings/long-bookings/", views.LongBookingView.as_view()),
    path("people/lookup/", views.PersonLookupView.as_view()),
    path("bookings/series/preview/", views.SeriesPreviewView.as_view()),  # Sprint 3
    path("bookings/series/", views.SeriesCreateView.as_view()),  # Sprint 3
    path("bookings/series/<uuid:series_id>/", views.SeriesDetailView.as_view()),  # Sprint 3
    path("bookings/series/<uuid:series_id>/cancel/", views.SeriesCancelView.as_view()),  # Sprint 3
    path("bookings/<uuid:booking_id>/", views.BookingDetailView.as_view()),
    path("bookings/<uuid:booking_id>/check-in/", views.BookingCheckInView.as_view()),  # Sprint 3
    path("bookings/<uuid:booking_id>/cancel/", views.BookingCancelView.as_view()),
    path("bookings/<uuid:booking_id>/remove-from-history/", views.BookingHistoryRemoveView.as_view()),  # Sprint 3 (1.20.0)
    path("bookings/<uuid:booking_id>/reschedule/", views.BookingRescheduleView.as_view()),
    path("bookings/<uuid:booking_id>/change/", views.BookingChangeView.as_view()),  # Sprint 3 (1.16.0)
    path("bookings/<uuid:booking_id>/extend/", views.BookingExtendView.as_view()),  # 2026-11-06 (client, Week 8)
    path("dashboard/", views.DashboardView.as_view()),
    path("calendar/link/", views.CalendarLinkView.as_view()),  # Sprint 3
    path("calendar/link/reset/", views.CalendarLinkResetView.as_view()),  # Sprint 3
    re_path(r"^calendar/(?P<token>[A-Za-z0-9_-]{16,64})\.ics$", views.CalendarFeedView.as_view()),  # Sprint 3
    path("notifications/", views.NotificationListView.as_view()),  # Sprint 3
    path("notifications/preferences/", views.NotificationPreferencesView.as_view()),  # Sprint 3 (2026-10-25)
    path("notifications/read-all/", views.NotificationReadAllView.as_view()),  # Sprint 3
    path("notifications/<uuid:notification_id>/read/", views.NotificationReadView.as_view()),  # Sprint 3
    path("account/unfreeze-requests/", views.MyUnfreezeRequestsView.as_view()),  # Sprint 3
    path("admin/unfreeze-requests/", views.AdminUnfreezeRequestListView.as_view()),  # Sprint 3
    path("admin/unfreeze-requests/<uuid:request_id>/review/", views.AdminUnfreezeReviewView.as_view()),  # Sprint 3
    path("admin/frozen-users/", views.AdminFrozenUsersView.as_view()),  # Sprint 3
    path("admin/users/<uuid:user_id>/unfreeze/", views.AdminUserUnfreezeView.as_view()),  # Sprint 3
    path("admin/qualifications/", views.AdminQualificationListView.as_view()),
    path("admin/qualifications/<uuid:submission_id>/review/", views.AdminQualificationReviewView.as_view()),
    path("admin/bookings/", views.AdminBookingListView.as_view()),
    path("admin/bookings/export/", views.AdminBookingExportView.as_view()),
    path("admin/reports/usage/", views.AdminUsageReportView.as_view()),  # Sprint 3
    path("admin/resources/", views.AdminResourceListView.as_view()),  # Sprint 3
    path("admin/resources/<uuid:resource_id>/", views.AdminResourceDetailView.as_view()),  # Sprint 3
    path("admin/resources/<uuid:resource_id>/archive/", views.AdminResourceArchiveView.as_view()),  # Sprint 3
    path("admin/resources/<uuid:resource_id>/restore/", views.AdminResourceRestoreView.as_view()),  # Sprint 3
    path("admin/resources/<uuid:resource_id>/status/", views.AdminResourceStatusView.as_view()),
    path("admin/bookings/<uuid:booking_id>/review/", views.AdminBookingReviewView.as_view()),
    path("admin/audit/", views.AdminAuditListView.as_view()),
    path("admin/users/", views.AdminUserListView.as_view()),
    path("admin/users/<uuid:user_id>/", views.AdminUserDetailView.as_view()),
    path("admin/users/<uuid:user_id>/reset-access/", views.AdminUserResetAccessView.as_view()),
    path("admin/users/managers/", views.AdminManagerCreateView.as_view()),
    path("admin/users/staff/", views.AdminStaffCreateView.as_view()),
    path("admin/process-due/", views.ProcessDueView.as_view()),
    path("admin/resources/<uuid:resource_id>/booking-policy/", views.ResourceBookingPolicyView.as_view()),
    path("admin/outlook/", views.OutlookStatusView.as_view()),
    path("admin/outlook/process/", views.OutlookProcessView.as_view()),
    path("admin/outlook/check/", views.OutlookCheckView.as_view()),
    path("admin/bookings/<uuid:booking_id>/outlook-retry/", views.OutlookRetryView.as_view()),
]
