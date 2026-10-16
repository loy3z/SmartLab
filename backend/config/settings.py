"""API configuration. The database is optional: see USE_POSTGRES below and database/README.md."""
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
# Persistence is chosen by REPOSITORY_FACTORY (below). Only the PostgreSQL adapter needs a Django
# database connection; the in-memory demo runs without PostgreSQL or psycopg installed.
USE_POSTGRES = os.getenv("REPOSITORY_FACTORY", "").endswith("postgres.PostgresRepository")
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "SmartLab_9900_F15E_BREAD"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
} if USE_POSTGRES else {"default": {"ENGINE": "django.db.backends.dummy"}}
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
# Review window for the demo resources: a pending request holds its slot this long while an Admin decides;
# if nobody does, the system approves it when it still follows the rules and rejects it otherwise.
# Default 24 hours (client meeting); a Manager may change it per resource (1 to 20160 minutes).
DEFAULT_PENDING_HOLD_MINUTES = int(os.getenv("DEFAULT_PENDING_HOLD_MINUTES", "1440"))
# Sprint 1 fixed policy: verified induction lasts one term, counted in days from approval.
# A demo value, not a client-confirmed rule; see README "资格来源与有效期".
QUALIFICATION_VALIDITY_DAYS = int(os.getenv("QUALIFICATION_VALIDITY_DAYS", "120"))
if not 1 <= QUALIFICATION_VALIDITY_DAYS <= 3650:
    raise ValueError("QUALIFICATION_VALIDITY_DAYS must be from 1 to 3650")
if not 1 <= DEFAULT_PENDING_HOLD_MINUTES <= 20160:
    raise ValueError("DEFAULT_PENDING_HOLD_MINUTES must be from 1 to 20160")
# Where booking rules are read from (booking/rules.py). Swap for a provider that reads Manager-edited
# values from the database without changing booking code.
RULES_PROVIDER = os.getenv("RULES_PROVIDER", "booking.rules.SettingsRulesProvider")
# Team proposal (not client-confirmed): earliest and latest bookable start date, in days from today.
MIN_ADVANCE_DAYS = int(os.getenv("MIN_ADVANCE_DAYS", "7"))
MAX_ADVANCE_DAYS = int(os.getenv("MAX_ADVANCE_DAYS", "30"))
if not 0 <= MIN_ADVANCE_DAYS <= MAX_ADVANCE_DAYS <= 365 or MAX_ADVANCE_DAYS < 1:
    raise ValueError("Require 0 <= MIN_ADVANCE_DAYS <= MAX_ADVANCE_DAYS <= 365 and MAX_ADVANCE_DAYS >= 1")
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
