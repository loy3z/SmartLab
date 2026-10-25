"""HTTP views: auth (split from booking/views.py on 2026-10-25)."""

from ._common import *  # noqa: F401,F403 - shared imports, helpers and PublicView.

__all__ = ["HealthView", "AuthConfigView", "TestLoginView", "TestSessionView", "DemoRegisterView", "DemoLoginView", "StaffSignInView", "StaffActivateView", "MeView", "ChangePasswordView"]

class HealthView(PublicView):
    def get(self, request):
        return Response({"status": "ok", "service": "smartlab-sprint1", "demo_auth_enabled": settings.DEBUG and settings.ENABLE_DEMO_AUTH,
                         "persistence": "adapter", "outlook_sync": "enabled" if settings.OUTLOOK_ENABLED else "disabled"})

class AuthConfigView(PublicView):
    def get(self, request):
        demo = settings.DEBUG and settings.ENABLE_DEMO_AUTH
        return Response({"mode": "demo" if demo else "external_provider_required", "demo_auth_enabled": demo,
                         "demo_registration_enabled": demo, "sso_connected": False, "token_type": "Bearer",
                         # Admins and Managers sign in on the staff page with zID + password (prototype; uses the same token).
                         "staff_sign_in_enabled": demo, "test_console_enabled": test_console_enabled()})

class TestLoginView(PublicView):
    def post(self, request):
        require_test_console()
        validated(TestLoginSerializer, request.data)
        principal = test_identity(get_test_account(get_service()), Role.STUDENT, True)
        return Response(session_result(principal))

class TestSessionView(APIView):
    def post(self, request):
        require_test_console()
        if not isinstance(request.user, TestPrincipal):
            raise DomainError("FORBIDDEN", "Only the test account can change its test session.", 403)
        data = validated(TestSessionSerializer, request.data)
        principal = test_identity(request.user, data["role"], data["bypass_booking_rules"])
        get_service()._audit(principal.id, "TEST_SESSION_CHANGED", "principal", principal.id,
                             role=principal.role.value, bypass_booking_rules=principal.bypass_booking_rules)
        return Response(session_result(principal))

class DemoRegisterView(PublicView):
    def post(self, request):
        require_demo_mode()
        data = validated(DemoRegisterSerializer, request.data)
        service = get_service()
        with service.repo.atomic():
            if any(item.zid == data["zid"] for item in service.repo.list_principals()):
                raise DomainError("USER_ALREADY_EXISTS", "This demo zID already exists.", 409)
            principal = Principal(str(uuid4()), data["zid"], data["display_name"], Role.STUDENT,
                                  university_email=data["university_email"])
            service.repo.save_principal(principal)
            service._audit(principal.id, "DEMO_STUDENT_CREATED", "principal", principal.id)
        return Response(session_result(principal), status=status.HTTP_201_CREATED)

class DemoLoginView(PublicView):
    def post(self, request):
        require_demo_mode()
        data = validated(DemoLoginSerializer, request.data)
        principal = next((item for item in get_service().repo.list_principals() if item.zid == data["zid"] and item.active), None)
        if principal is None:
            raise DomainError("INVALID_DEMO_USER", "Create this demo student account first or use a seeded demo zID.", 401)
        if principal.is_staff:
            # University (student) sign-in is for students only; staff use the staff sign-in page.
            raise DomainError("USE_STAFF_SIGN_IN", "Admins and Managers sign in on the staff sign-in page.", 403)
        return Response(session_result(principal))

class StaffSignInView(PublicView):
    """Staff sign-in page: zID + password. The account's role decides Admin or Manager access."""
    def post(self, request):
        require_demo_mode()
        data = validated(StaffSignInSerializer, request.data)
        return Response(session_result(get_service().staff_sign_in(data["zid"], data["password"])))

class StaffActivateView(PublicView):
    """First staff sign-in: invite code from the Manager + a new password. Signs the user in."""
    def post(self, request):
        require_demo_mode()
        data = validated(StaffActivateSerializer, request.data)
        return Response(session_result(get_service().activate_staff(data["zid"], data["invite_code"], data["password"])))

class MeView(APIView):
    def get(self, request):
        return Response(json_value(request.user))

class ChangePasswordView(APIView):
    def post(self, request):
        data = validated(ChangePasswordSerializer, request.data)
        get_service().change_password(request.user, data["current_password"], data["new_password"])
        return Response({"changed": True})
