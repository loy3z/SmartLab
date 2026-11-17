"""Who is making this request. Every API request passes through here before it reaches a view.

The request carries ``Authorization: Bearer <token>``. ``SprintAuthentication`` hands the token to the identity
provider named in the AUTH_PROVIDER setting, which answers with the person (a ``Principal``) or refuses.

No role supplied by the user is trusted: a token only identifies the person, and the role and the active flag are
read from the stored account on every request. Deactivating an account therefore stops its next request.

To connect real university SSO:
1. Write a class with ``resolve_bearer(token)`` that verifies the university's token, finds or creates the
   stored account for that zID, and returns it (role from the stored account, never from the token).
2. Set AUTH_PROVIDER to that class.
3. Set ENABLE_DEMO_AUTH=false, which switches off demo sign-in and demo tokens. Staff password sign-in issues
   the same demo tokens, so decide at the same time how staff sign in.
"""
from typing import Protocol
from django.conf import settings
from django.core import signing
from django.http import Http404
from django.utils.module_loading import import_string
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from .domain import Principal

class IdentityProvider(Protocol):
    """What an identity provider must do: turn a bearer token into the person, or raise AuthenticationFailed."""
    def resolve_bearer(self, token: str) -> Principal: ...

def require_demo_mode():
    """Demo sign-in exists only when both DEBUG and ENABLE_DEMO_AUTH are on; otherwise its endpoints answer 404."""
    if not (settings.DEBUG and settings.ENABLE_DEMO_AUTH):
        raise Http404("Demo authentication is disabled.")

def issue_demo_token(principal):
    """The token given after a demo or staff sign-in: the person's id, signed with the server's secret key.

    It holds no role. The local test account also carries the role and rule bypass chosen for that session.
    """
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
    """Reads the tokens made by ``issue_demo_token``. Stands in for university SSO until it is connected."""

    def resolve_bearer(self, token):
        if not (settings.DEBUG and settings.ENABLE_DEMO_AUTH):
            raise AuthenticationFailed("Configure a verified university SSO identity provider.", code="SSO_NOT_CONFIGURED")
        try:
            payload = signing.loads(token, salt="smartlab.demo.auth", max_age=settings.DEMO_TOKEN_TTL_SECONDS)
        except signing.SignatureExpired:
            raise AuthenticationFailed("The demo token has expired.", code="TOKEN_EXPIRED")
        except signing.BadSignature:
            raise AuthenticationFailed("Invalid token.", code="INVALID_TOKEN")
        # The signature is good: look the person up, so the role and active flag are today's, not the token's.
        from .runtime import get_service
        from .test_console import TEST_ACCOUNT_ID, get_test_account, test_console_enabled, test_identity
        service = get_service()
        principal = service.repo.get_principal(payload.get("sub", ""))
        if not principal or not principal.active:
            raise AuthenticationFailed("The user is inactive or unknown.", code="INVALID_TOKEN")
        # The local test account (development only; never enabled in deployment).
        if principal.id == TEST_ACCOUNT_ID or payload.get("test_console"):
            if not (principal.id == TEST_ACCOUNT_ID and payload.get("test_console") is True
                    and test_console_enabled() and isinstance(payload.get("test_bypass"), bool)):
                raise AuthenticationFailed("Test console is unavailable.", code="INVALID_TOKEN")
            try:
                identity = test_identity(principal, payload["test_role"], payload["test_bypass"])
            except (KeyError, ValueError):
                raise AuthenticationFailed("Invalid test session.", code="INVALID_TOKEN")
            # Sprint 3: active test sessions also receive any inductions added after sign-in.
            get_test_account(service)
            return identity
        return principal

class DisabledIdentityProvider:
    """Refuses every token. For a deployment that must not accept demo tokens while SSO is not connected yet."""

    def resolve_bearer(self, token):
        raise AuthenticationFailed("University SSO is not configured.", code="SSO_NOT_CONFIGURED")

class SprintAuthentication(BaseAuthentication):
    """The entry point Django REST Framework calls for every request (DEFAULT_AUTHENTICATION_CLASSES)."""

    def authenticate(self, request):
        """Returns (person, token), or None when no Authorization header was sent (a view that needs a person answers 401)."""
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
        """Makes a missing or bad token a 401 with ``WWW-Authenticate: Bearer`` rather than a 403."""
        return "Bearer"
