from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.HealthView.as_view()),
    path("auth/config/", views.AuthConfigView.as_view()),
    path("auth/demo-register/", views.DemoRegisterView.as_view()),
    path("auth/demo-login/", views.DemoLoginView.as_view()),
    path("auth/me/", views.MeView.as_view()),
    path("resources/", views.ResourceListView.as_view()),
    path("resources/<uuid:resource_id>/", views.ResourceDetailView.as_view()),
    path("resources/<uuid:resource_id>/availability/", views.AvailabilityView.as_view()),
    path("qualification-requirements/", views.RequirementListView.as_view()),
    path("qualifications/", views.QualificationListView.as_view()),
    path("qualifications/<uuid:submission_id>/", views.QualificationDetailView.as_view()),
    path("qualifications/<uuid:submission_id>/file/", views.QualificationFileView.as_view()),
    path("bookings/", views.BookingListView.as_view()),
    path("bookings/<uuid:booking_id>/", views.BookingDetailView.as_view()),
    path("bookings/<uuid:booking_id>/cancel/", views.BookingCancelView.as_view()),
    path("dashboard/", views.DashboardView.as_view()),
    path("admin/qualifications/", views.AdminQualificationListView.as_view()),
    path("admin/qualifications/<uuid:submission_id>/review/", views.AdminQualificationReviewView.as_view()),
    path("admin/bookings/", views.AdminBookingListView.as_view()),
    path("admin/bookings/<uuid:booking_id>/review/", views.AdminBookingReviewView.as_view()),
    path("admin/process-due/", views.ProcessDueView.as_view()),
]
