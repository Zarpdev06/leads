"""
Django settings for the Lead Intelligence / Outreach / CRM platform.

Every operational value is environment driven (see ../.env.example). Secrets -
SMTP password, AI keys, encryption key - are *never* hardcoded and never
returned by the API.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import environ

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent          # /app/backend
ROOT_DIR = BASE_DIR.parent                                  # /app

# Make the backend package importable as `apps.*` / `config.*`
sys.path.insert(0, str(BASE_DIR))

env = environ.Env()

# Read .env if present (docker-compose passes env vars directly too).
for _env_file in (ROOT_DIR / ".env", BASE_DIR / ".env"):
    if _env_file.exists():
        env.read_env(str(_env_file))
        break

# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
DEBUG = env.bool("DJANGO_DEBUG", default=False)
SECRET_KEY = env.str(
    "DJANGO_SECRET_KEY",
    default="django-insecure-DEV-ONLY-change-me-in-production-0123456789",
)

ALLOWED_HOSTS = [
    h.strip()
    for h in env.str(
        "DJANGO_ALLOWED_HOSTS",
        default="localhost,127.0.0.1,0.0.0.0,[::1],*.e2b.app,testserver",
    ).split(",")
    if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in env.str(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        default="http://localhost,http://localhost:5173,http://localhost:80,https://*.e2b.app",
    ).split(",")
    if o.strip()
]

TIME_ZONE = env.str("DJANGO_TIME_ZONE", default="UTC")
USE_TZ = True
LANGUAGE_CODE = env.str("DJANGO_LANGUAGE_CODE", default="en-us")

# Encryption at rest for AI provider keys etc. (Fernet; key from env, else
# deterministically derived from SECRET_KEY so a fresh deploy still boots).
ENCRYPTION_KEY = env.str("ENCRYPTION_KEY", default="")

INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "corsheaders",
    "django_filters",
    # Project apps
    "apps.core",
    "apps.accounts",
    "apps.companies",
    "apps.contacts",
    "apps.leads",
    "apps.imports",
    "apps.campaigns",
    "apps.email_engine",
    "apps.ai_engine",
    "apps.crm",
    "apps.analytics",
    "apps.suppression",
    "apps.settings",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
DB_ENGINE = env.str("DB_ENGINE", default="postgres").lower()

if DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": env.str("SQLITE_PATH", default=str(BASE_DIR / "db.sqlite3")),
            "TEST": {"NAME": os.path.join(tempfile.gettempdir(), "leads_test.sqlite3")},
            "OPTIONS": {"timeout": 30},
        }
    }
else:
    db_url = env.str("DATABASE_URL", default="")
    if db_url:
        DATABASES = {"default": env.db_url("DATABASE_URL", default=db_url)}
    else:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": env.str("POSTGRES_DB", default="leads"),
                "USER": env.str("POSTGRES_USER", default="leads"),
                "PASSWORD": env.str("POSTGRES_PASSWORD", default="leads"),
                "HOST": env.str("POSTGRES_HOST", default="db"),
                "PORT": env.str("POSTGRES_PORT", default="5432"),
                "CONN_MAX_AGE": env.int("DATABASE_CONN_MAX_AGE", default=60),
            }
        }
    DATABASES["default"]["ATOMIC_REQUESTS"] = False
    DATABASES["default"]["TEST"] = {
        "NAME": env.str("POSTGRES_TEST_DB", default="test_leads")
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Password validation
# --------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------
# Cache / Celery / Redis
# --------------------------------------------------------------------------
REDIS_URL = env.str("REDIS_URL", default="redis://redis:6379/0")
CELERY_BROKER_URL = env.str("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env.str("CELERY_RESULT_BACKEND", default="redis://redis:6379/1")

if env.bool("USE_REDIS_CACHE", default=True):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"client_class": "django_redis.client.DefaultClient"}
            if False
            else {},
        }
    }
else:  # pragma: no cover - dev fallback
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = env.bool("CELERY_TASK_EAGER_PROPAGATES", default=False)
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 60 * 60  # 1h hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 55 * 60
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "apps.imports.tasks.*": {"queue": "imports"},
    "apps.leads.tasks.*": {"queue": "imports"},
    "apps.ai_engine.tasks.*": {"queue": "ai"},
    "apps.email_engine.tasks.send_due_emails": {"queue": "email"},
    "apps.email_engine.tasks.send_email_message": {"queue": "email"},
    "apps.email_engine.tasks.dispatch_campaign": {"queue": "email"},
    "apps.email_engine.tasks.process_follow_ups": {"queue": "email"},
    "apps.email_engine.tasks.release_stuck_messages": {"queue": "email"},
    "apps.email_engine.tasks.rollover_daily_usage": {"queue": "email"},
    "apps.email_engine.tasks.poll_mailbox": {"queue": "analytics"},
    "apps.analytics.tasks.*": {"queue": "analytics"},
}

# --------------------------------------------------------------------------
# Email (SMTP only - credentials from environment)
# --------------------------------------------------------------------------
EMAIL_BACKEND = env.str(
    "EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = env.str("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env.str("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env.str("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=30)
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="Leads Platform <noreply@example.com>")
DEFAULT_REPLY_TO = env.str("DEFAULT_REPLY_TO", default="")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# --------------------------------------------------------------------------
# Sending limits / scheduling
# --------------------------------------------------------------------------
SMTP_DAILY_LIMIT = env.int("SMTP_DAILY_LIMIT", default=100)
DEFAULT_DAILY_MARKETING_LIMIT = env.int("DEFAULT_DAILY_MARKETING_LIMIT", default=90)
EMAIL_HARD_DAILY_CAP = env.int("EMAIL_HARD_DAILY_CAP", default=90)
SEND_WINDOW_START = env.str("SEND_WINDOW_START", default="09:30")
SEND_WINDOW_END = env.str("SEND_WINDOW_END", default="17:30")
SEND_WEEKDAYS = [
    int(d) for d in env.str("SEND_WEEKDAYS", default="1,2,3,4,5").split(",") if d.strip()
]
EMAIL_MIN_SECONDS_BETWEEN_SENDS = env.int("EMAIL_MIN_SECONDS_BETWEEN_SENDS", default=20)
EMAIL_MAX_ATTEMPTS = env.int("EMAIL_MAX_ATTEMPTS", default=3)
EMAIL_BATCH_SIZE_PER_RUN = env.int("EMAIL_BATCH_SIZE_PER_RUN", default=25)
TRACK_OPENS = env.bool("TRACK_OPENS", default=True)
TRACK_CLICKS = env.bool("TRACK_CLICKS", default=True)

IMAP_ENABLED = env.bool("IMAP_ENABLED", default=False)
IMAP_HOST = env.str("IMAP_HOST", default="")
IMAP_PORT = env.int("IMAP_PORT", default=993)
IMAP_USERNAME = env.str("IMAP_USERNAME", default="")
IMAP_PASSWORD = env.str("IMAP_PASSWORD", default="")
IMAP_USE_SSL = env.bool("IMAP_USE_SSL", default=True)
IMAP_MAILBOX = env.str("IMAP_MAILBOX", default="INBOX")

# --------------------------------------------------------------------------
# Compliance / branding
# --------------------------------------------------------------------------
COMPANY_LEGAL_NAME = env.str("COMPANY_LEGAL_NAME", default="Your Company")
COMPANY_POSTAL_ADDRESS = env.str("COMPANY_POSTAL_ADDRESS", default="")
PUBLIC_BASE_URL = env.str("PUBLIC_BASE_URL", default="http://localhost").rstrip("/")
UNSUBSCRIBE_SECRET = env.str("UNSUBSCRIBE_SECRET", default=SECRET_KEY)

# --------------------------------------------------------------------------
# AI
# --------------------------------------------------------------------------
AI_PROVIDER = env.str("AI_PROVIDER", default="rules")
AI_MODEL = env.str("AI_MODEL", default="")
AI_API_KEY = env.str("AI_API_KEY", default="")
AI_BASE_URL = env.str("AI_BASE_URL", default="")
AI_TEMPERATURE = env.float("AI_TEMPERATURE", default=0.4)
AI_MAX_TOKENS = env.int("AI_MAX_TOKENS", default=700)
AI_ENABLED = env.bool("AI_ENABLED", default=True)

# --------------------------------------------------------------------------
# Imports
# --------------------------------------------------------------------------
IMPORT_CHUNK_SIZE = env.int("IMPORT_CHUNK_SIZE", default=1000)
IMPORT_MAX_FILE_MB = env.int("IMPORT_MAX_FILE_MB", default=500)
IMPORT_MAX_ROWS_PER_JOB = env.int("IMPORT_MAX_ROWS_PER_JOB", default=50_000_000)
IMPORT_ERROR_SAMPLE_LIMIT = env.int("IMPORT_ERROR_SAMPLE_LIMIT", default=500)
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024 * 25  # 25 MB before spooling to disk
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024 * 600

MEDIA_URL = "/media/"
MEDIA_ROOT = env.str("MEDIA_ROOT", default=str(BASE_DIR / "media"))
STATIC_URL = "/static/"
STATIC_ROOT = env.str("STATIC_ROOT", default=str(BASE_DIR / "staticfiles"))
# Only include the project-level "static/" directory when it actually exists,
# otherwise `collectstatic` (and every `manage.py` call) emits W004 on a fresh
# checkout where the directory is empty and therefore not tracked by git.
STATICFILES_DIRS = [path for path in (BASE_DIR / "static",) if path.is_dir()]
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": MEDIA_ROOT},
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# --------------------------------------------------------------------------
# REST framework
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/hour",
        "user": "6000/hour",
        "ai": "120/hour",
        "imports": "120/hour",
        "tracking": "600/min",
    },
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "COERCE_DECIMAL_TO_STRING": False,
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
}

# --------------------------------------------------------------------------
# CORS / CSRF (dev friendly, locked down in production via env)
# --------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in env.str(
        "CORS_ALLOWED_ORIGINS",
        default="http://localhost:5173,http://localhost:80,http://localhost",
    ).split(",")
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = DEBUG and env.bool("CORS_ALLOW_ALL_ORIGINS", default=False)
CSRF_COOKIE_HTTPONLY = False  # the SPA reads the csrf token for session-auth calls
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"

# --------------------------------------------------------------------------
# Security (hardened when DEBUG=0)
# --------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
    SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
    CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = bool(SECURE_HSTS_SECONDS)
    SECURE_HSTS_PRELOAD = bool(SECURE_HSTS_SECONDS)

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
        "simple": {"format": "{levelname} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOGS_DIR / "app.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": env.str("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "apps": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "celery": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
    },
}
