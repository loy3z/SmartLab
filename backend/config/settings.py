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
CORS_ALLOWED_ORIGINS = [x.strip() for x in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",") if x.strip()]
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
SECURE_CONTENT_TYPE_NOSNIFF = True
