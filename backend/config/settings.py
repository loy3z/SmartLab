"""API configuration. The database is optional: see USE_POSTGRES below and database/README.md."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
ENABLE_DEMO_AUTH = os.getenv("ENABLE_DEMO_AUTH", "false").lower() == "true"
ENABLE_TEST_CONSOLE = os.getenv("ENABLE_TEST_CONSOLE", "false").lower() == "true"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY; use DEBUG=true only for local development.")
    SECRET_KEY = secrets.token_urlsafe(48)
ALLOWED_HOSTS = [x.strip() for x in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if x.strip()]
INSTALLED_APPS = ["rest_framework", "booking"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "booking.middleware.CorsMiddleware", "django.middleware.common.CommonMiddleware",
              "booking.middleware.NotificationDeliveryMiddleware"]
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
        # 2026-10-29 (load test S3): keep a worker's connection for this many seconds instead of opening one per
        # request (about 12 ms each); 0 turns reuse off. Health checks drop a connection the server has closed.
        # Safe with the write lock: pg_advisory_xact_lock ends with its transaction.
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": True,
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
# Booking start dates use the resource's local calendar. The client maximum is four weeks;
# the existing seven-day minimum remains configurable pending client confirmation.
MIN_ADVANCE_DAYS = int(os.getenv("MIN_ADVANCE_DAYS", "7"))
MAX_ADVANCE_DAYS = int(os.getenv("MAX_ADVANCE_DAYS", "28"))
if not 0 <= MIN_ADVANCE_DAYS <= MAX_ADVANCE_DAYS <= 365 or MAX_ADVANCE_DAYS < 1:
    raise ValueError("Require 0 <= MIN_ADVANCE_DAYS <= MAX_ADVANCE_DAYS <= 365 and MAX_ADVANCE_DAYS >= 1")
# Fair-use rules confirmed by the client, validated by booking.rules.BookingRules. One quota slot is
# 30 minutes; a normal request may use 6 slots, a person may hold 24 slots per local week,
# and at most 8 active future bookings.
# Check-in, missed-booking freezes and the longest weekly series remain configurable below.
BOOKING_SLOT_MINUTES = int(os.getenv("BOOKING_SLOT_MINUTES", "30"))
MAX_SLOTS_PER_BOOKING = int(os.getenv("MAX_SLOTS_PER_BOOKING", "6"))
MAX_SLOTS_PER_WEEK = int(os.getenv("MAX_SLOTS_PER_WEEK", "24"))
MAX_ACTIVE_FUTURE_BOOKINGS = int(os.getenv("MAX_ACTIVE_FUTURE_BOOKINGS", "8"))
CHECK_IN_OPENS_MINUTES = int(os.getenv("CHECK_IN_OPENS_MINUTES", "15"))
CHECK_IN_CLOSES_MINUTES = int(os.getenv("CHECK_IN_CLOSES_MINUTES", "30"))
FREEZE_AFTER_NO_SHOWS = int(os.getenv("FREEZE_AFTER_NO_SHOWS", "4"))
FREEZE_DAYS = int(os.getenv("FREEZE_DAYS", "30"))
MAX_SERIES_WEEKS = int(os.getenv("MAX_SERIES_WEEKS", "14"))
# Sprint 3 reminders in the notification bell.
REMINDER_HOURS_BEFORE = int(os.getenv("REMINDER_HOURS_BEFORE", "24"))
INDUCTION_REMINDER_DAYS = int(os.getenv("INDUCTION_REMINDER_DAYS", "14"))
# Sprint 3: extra delivery channels for notifications (website notifications are always stored). Comma-separated dotted
# paths of classes implementing booking.notification_channels.NotificationChannel (e.g. a future Outlook mail channel).
NOTIFICATION_CHANNELS = [x.strip() for x in os.getenv("NOTIFICATION_CHANNELS", "").split(",") if x.strip()]

# Sprint 3: email notifications from a system mailbox (Gmail SMTP with an app password; see docs/email-setup.md).
# Set the password only as an environment variable; never put it in a file in the repository.
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "").strip()
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "").replace(" ", "")  # Gmail shows app passwords in groups of 4
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
EMAIL_MAX_ATTEMPTS = int(os.getenv("EMAIL_MAX_ATTEMPTS", "6"))
EMAIL_LEASE_SECONDS = int(os.getenv("EMAIL_LEASE_SECONDS", "300"))
EMAIL_BATCH_SIZE = int(os.getenv("EMAIL_BATCH_SIZE", "50"))
if not 1 <= EMAIL_MAX_ATTEMPTS <= 20:
    raise ValueError("Require 1 <= EMAIL_MAX_ATTEMPTS <= 20")
if not 30 <= EMAIL_LEASE_SECONDS <= 3600:
    raise ValueError("Require 30 <= EMAIL_LEASE_SECONDS <= 3600")
if not 1 <= EMAIL_BATCH_SIZE <= 500:
    raise ValueError("Require 1 <= EMAIL_BATCH_SIZE <= 500")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", f"SmartLab <{EMAIL_HOST_USER}>" if EMAIL_HOST_USER else "SmartLab <webmaster@localhost>")
# Who receives emails: none, allowlist (default: only EMAIL_ALLOWED_RECIPIENTS), redirect (all to EMAIL_REDIRECT_TO), all.
EMAIL_MODE = os.getenv("EMAIL_MODE", "allowlist").strip().lower()
EMAIL_ALLOWED_RECIPIENTS = [x.strip() for x in os.getenv("EMAIL_ALLOWED_RECIPIENTS", "").split(",") if x.strip()]
EMAIL_REDIRECT_TO = os.getenv("EMAIL_REDIRECT_TO", "").strip()
EMAIL_NOTIFICATION_KINDS = [x.strip() for x in os.getenv("EMAIL_NOTIFICATION_KINDS", ",".join([
    "BOOKING_SUBMITTED", "BOOKING_CREATED_FOR_YOU", "SERIES_CREATED", "SERIES_CREATED_FOR_YOU",
    "BOOKING_APPROVED", "BOOKING_REJECTED", "BOOKING_EXPIRED", "BOOKING_PROMOTED", "BOOKING_RESCHEDULED",
    "BOOKING_CANCELLED", "BOOKING_REMINDER", "INDUCTION_EXPIRING",
    # Sprint 3 (1.16.0): change requests and resources going out of / back into service.
    "CHANGE_REQUESTED", "CHANGE_APPROVED", "CHANGE_REJECTED", "RESOURCE_OUT_OF_SERVICE", "RESOURCE_REOPENED"])).split(",") if x.strip()]
# Address of the web app, used for links in emails.
SITE_URL = os.getenv("SITE_URL", "http://localhost:5173").strip()
if EMAIL_ENABLED and "booking.email_channel.EmailChannel" not in NOTIFICATION_CHANNELS:
    NOTIFICATION_CHANNELS.append("booking.email_channel.EmailChannel")
# 2026-10-27: print the booking app's INFO lines (email sent / skipped, with times) in the server log
# (docker compose logs api). Without this, Python showed only warnings and errors.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {"booking": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO").upper()}},
}
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
# Device-code sign-in (renews itself): the Application (client) ID of a public-client app registration.
# Not a secret, but keep it in the environment like the rest. The refresh token file is ignored by Git.
OUTLOOK_PUBLIC_CLIENT_ID = os.getenv("OUTLOOK_PUBLIC_CLIENT_ID", "").strip()
OUTLOOK_AUTHORITY = os.getenv("OUTLOOK_AUTHORITY", "common").strip() or "common"
OUTLOOK_REFRESH_TOKEN_FILE = os.getenv("OUTLOOK_REFRESH_TOKEN_FILE",
                                       str(BASE_DIR / ".local" / "outlook-refresh-token") if DEBUG else "")
# Who receives a meeting invitation: none, allowlist (only OUTLOOK_ALLOWED_ATTENDEES) or all.
# The default sends no invitation unless the address is listed, so testing only ever reaches your own mailbox.
OUTLOOK_INVITE_MODE = os.getenv("OUTLOOK_INVITE_MODE", "allowlist").strip().lower()
if OUTLOOK_INVITE_MODE not in ("none", "allowlist", "all"):
    raise ValueError("OUTLOOK_INVITE_MODE must be none, allowlist or all")
OUTLOOK_ALLOWED_ATTENDEES = tuple(item.strip() for item in os.getenv("OUTLOOK_ALLOWED_ATTENDEES", "").split(",") if item.strip())
