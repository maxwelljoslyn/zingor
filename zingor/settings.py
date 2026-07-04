"""Django settings for zingor project."""

import os
from pathlib import Path

import sentry_sdk
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN", ""),
    # Add data like request headers and IP for users.
    # See https://docs.sentry.io/platforms/python/data-management/data-collected/
    send_default_pii=True,
    enable_logs=True,
    traces_sample_rate=1.0,  # 1.0 captures 100% of transactions for tracing
    profile_session_sample_rate=1.0,  # 1.0 captures 100% of profile sessions
    profile_lifecycle="trace",  # "trace" automatically runs the profiler during an active transaction
)

SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

ALLOWED_HOSTS = (
    os.environ.get("ALLOWED_HOSTS", "").split(",")
    if os.environ.get("ALLOWED_HOSTS")
    else []
)

INSTALLED_APPS = [
    # characters must precede django.contrib.admin: both ship
    # registration/password_reset_*.html templates, and the app-directories
    # loader resolves in INSTALLED_APPS order, so admin-first would shadow ours.
    "characters",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "zingor.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "characters.context_processors.registration_enabled",
                "characters.context_processors.git_commit",
            ],
        },
    },
]

WSGI_APPLICATION = "zingor.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

# Allow JS to read CSRF cookie for HTMX requests
CSRF_COOKIE_HTTPONLY = False

CSRF_TRUSTED_ORIGINS = (
    os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if os.environ.get("CSRF_TRUSTED_ORIGINS")
    else []
)

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "false").lower() == "true"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "no-reply@zingor.local")

EMAIL_CONFIRMATION_REQUIRED = (
    os.environ.get("EMAIL_CONFIRMATION_REQUIRED", "false" if DEBUG else "true").lower()
    == "true"
)

REGISTRATION_ENABLED = os.environ.get("REGISTRATION_ENABLED", "true").lower() == "true"

GITHUB_FEEDBACK_REPO = os.environ.get("GITHUB_FEEDBACK_REPO", "")
GITHUB_FEEDBACK_TOKEN = os.environ.get("GITHUB_FEEDBACK_TOKEN", "")
