"""API-only configuration. No application database is provisioned here."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
ENABLE_DEMO_AUTH = os.getenv("ENABLE_DEMO_AUTH", "false").lower() == "true"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY; use DEBUG=true only for local development.")
    SECRET_KEY = secrets.token_urlsafe(48)
ALLOWED_HOSTS = [x.strip() for x in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if x.strip()]
INSTALLED_APPS = ["rest_framework", "booking"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "booking.middleware.CorsMiddleware", "django.middleware.common.CommonMiddleware"]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.dummy"}}
USE_TZ = True
TIME_ZONE = "Australia/Sydney"
LANGUAGE_CODE = "en-au"
APPEND_SLASH = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["booking.authentication.SprintAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "booking.exceptions.exception_handler",
}
AUTH_PROVIDER = os.getenv("AUTH_PROVIDER", "booking.authentication.DemoIdentityProvider")
REPOSITORY_FACTORY = os.getenv("REPOSITORY_FACTORY", "booking.repository.MemoryRepository")
FILE_STORAGE_FACTORY = os.getenv("FILE_STORAGE_FACTORY", "booking.storage.MemoryFileStorage")
SEED_DEMO_DATA = DEBUG and os.getenv("SEED_DEMO_DATA", "true").lower() == "true"
DEMO_TOKEN_TTL_SECONDS = 3600
APPROVAL_WAIT_HOURS = float(os.getenv("APPROVAL_WAIT_HOURS", "24"))
if APPROVAL_WAIT_HOURS < 0:
    raise ValueError("APPROVAL_WAIT_HOURS must be nonnegative")
# A first pending request holds its slot this long; afterwards it joins the waitlist and is promoted
# only once qualified. A Manager may change it per resource (up to 20160, which effectively holds until decided).
DEFAULT_PENDING_HOLD_MINUTES = int(os.getenv("DEFAULT_PENDING_HOLD_MINUTES", "30"))
# Sprint 1 fixed policy: verified induction lasts one term, counted in days from approval.
# A demo value, not a client-confirmed rule; see README "资格来源与有效期".
QUALIFICATION_VALIDITY_DAYS = int(os.getenv("QUALIFICATION_VALIDITY_DAYS", "120"))
if not 1 <= QUALIFICATION_VALIDITY_DAYS <= 3650:
    raise ValueError("QUALIFICATION_VALIDITY_DAYS must be from 1 to 3650")
if not 1 <= DEFAULT_PENDING_HOLD_MINUTES <= 20160:
    raise ValueError("DEFAULT_PENDING_HOLD_MINUTES must be from 1 to 20160")
# Sprint 1 fixed rules (demo values): latest bookable start date, and how many undecided requests a
# student whose induction is still under review may hold per qualification.
MIN_ADVANCE_DAYS = int(os.getenv("MIN_ADVANCE_DAYS", "7"))
MAX_ADVANCE_DAYS = int(os.getenv("MAX_ADVANCE_DAYS", "30"))
if not 0 <= MIN_ADVANCE_DAYS <= MAX_ADVANCE_DAYS <= 365 or MAX_ADVANCE_DAYS < 1:
    raise ValueError("Require 0 <= MIN_ADVANCE_DAYS <= MAX_ADVANCE_DAYS <= 365 and MAX_ADVANCE_DAYS >= 1")
UNVERIFIED_PENDING_LIMIT = int(os.getenv("UNVERIFIED_PENDING_LIMIT", "1"))
if not 1 <= UNVERIFIED_PENDING_LIMIT <= 100:
    raise ValueError("UNVERIFIED_PENDING_LIMIT must be from 1 to 100")
CORS_ALLOWED_ORIGINS = [x.strip() for x in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",") if x.strip()]
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
SECURE_CONTENT_TYPE_NOSNIFF = True

# Independent from AUTH_PROVIDER: students' demo/SSO tokens are never sent to Graph.
OUTLOOK_ENABLED = os.getenv("OUTLOOK_ENABLED", "false").lower() == "true"
OUTLOOK_SYNC_ON_WRITE = os.getenv("OUTLOOK_SYNC_ON_WRITE", "true").lower() == "true"
OUTLOOK_PROVIDER_FACTORY = os.getenv("OUTLOOK_PROVIDER_FACTORY", "booking.outlook.make_graph_calendar")
OUTLOOK_ACCESS_TOKEN = os.getenv("OUTLOOK_ACCESS_TOKEN", "").strip()
OUTLOOK_TOKEN_FILE = os.getenv("OUTLOOK_TOKEN_FILE", str(BASE_DIR / ".local" / "outlook-token") if DEBUG else "")
OUTLOOK_TENANT_ID = os.getenv("OUTLOOK_TENANT_ID", "").strip()
OUTLOOK_CLIENT_ID = os.getenv("OUTLOOK_CLIENT_ID", "").strip()
OUTLOOK_CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET", "")
OUTLOOK_MAILBOX = os.getenv("OUTLOOK_MAILBOX", "").strip()
OUTLOOK_CALENDAR_ID = os.getenv("OUTLOOK_CALENDAR_ID", "").strip()
OUTLOOK_HTTP_TIMEOUT_SECONDS = float(os.getenv("OUTLOOK_HTTP_TIMEOUT_SECONDS", "8"))
if not 0 < OUTLOOK_HTTP_TIMEOUT_SECONDS <= 30:
    raise ValueError("OUTLOOK_HTTP_TIMEOUT_SECONDS must be in (0, 30]")
