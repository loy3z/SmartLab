"""Replace IdentityProvider for real SSO; no user-supplied role is trusted."""
from typing import Protocol
from django.conf import settings
from django.core import signing
from django.http import Http404
from django.utils.module_loading import import_string
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from .domain import Principal

class IdentityProvider(Protocol):
    def resolve_bearer(self, token: str) -> Principal: ...

def require_demo_mode():
    if not (settings.DEBUG and settings.ENABLE_DEMO_AUTH):
        raise Http404("Demo authentication is disabled.")

def issue_demo_token(principal):
    require_demo_mode()
    from .test_console import TEST_ACCOUNT_ID, TestPrincipal, require_test_console
    payload = {"sub": principal.id}
    if principal.id == TEST_ACCOUNT_ID:
        require_test_console()
        if not isinstance(principal, TestPrincipal):
            raise AuthenticationFailed("Use the test console sign-in.", code="INVALID_TOKEN")
        payload.update(test_console=True, test_role=principal.role.value,
                       test_bypass=principal.bypass_booking_rules)
    return signing.dumps(payload, salt="smartlab.demo.auth")

class DemoIdentityProvider:
    def resolve_bearer(self, token):
        if not (settings.DEBUG and settings.ENABLE_DEMO_AUTH):
            raise AuthenticationFailed("Configure a verified university SSO identity provider.", code="SSO_NOT_CONFIGURED")
        try:
            payload = signing.loads(token, salt="smartlab.demo.auth", max_age=settings.DEMO_TOKEN_TTL_SECONDS)
        except signing.SignatureExpired:
            raise AuthenticationFailed("The demo token has expired.", code="TOKEN_EXPIRED")
        except signing.BadSignature:
            raise AuthenticationFailed("Invalid token.", code="INVALID_TOKEN")
        from .runtime import get_service
        from .test_console import TEST_ACCOUNT_ID, test_console_enabled, test_identity
        principal = get_service().repo.get_principal(payload.get("sub", ""))
        if not principal or not principal.active:
            raise AuthenticationFailed("The user is inactive or unknown.", code="INVALID_TOKEN")
        if principal.id == TEST_ACCOUNT_ID or payload.get("test_console"):
            if not (principal.id == TEST_ACCOUNT_ID and payload.get("test_console") is True
                    and test_console_enabled() and isinstance(payload.get("test_bypass"), bool)):
                raise AuthenticationFailed("Test console is unavailable.", code="INVALID_TOKEN")
            try:
                return test_identity(principal, payload["test_role"], payload["test_bypass"])
            except (KeyError, ValueError):
                raise AuthenticationFailed("Invalid test session.", code="INVALID_TOKEN")
        return principal

class DisabledIdentityProvider:
    def resolve_bearer(self, token):
        raise AuthenticationFailed("University SSO is not configured.", code="SSO_NOT_CONFIGURED")

class SprintAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header:
            return None
        if len(header) != 2 or header[0].lower() != b"bearer":
            raise AuthenticationFailed("Use Authorization: Bearer <token>.", code="INVALID_TOKEN")
        try:
            token = header[1].decode("ascii")
        except UnicodeDecodeError:
            raise AuthenticationFailed("Invalid token.", code="INVALID_TOKEN")
        principal = import_string(settings.AUTH_PROVIDER)().resolve_bearer(token)
        if not principal.active:
            raise AuthenticationFailed("The account is inactive.", code="INACTIVE_USER")
        return principal, token

    def authenticate_header(self, request):
        return "Bearer"
