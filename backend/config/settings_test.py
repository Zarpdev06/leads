"""
Settings used by the automated test suite.

Everything external is replaced with in-process equivalents:
  * SQLite instead of PostgreSQL
  * Celery tasks run eagerly (no broker)
  * LocMem cache instead of Redis
  * in-memory email backend (no SMTP)
  * deterministic offline AI provider

The production code paths (quota, eligibility, dedupe, ...) are exercised for
real - only the infrastructure is swapped.
"""
from __future__ import annotations

import tempfile

from .settings import *  # noqa: F401,F403
from .settings import BASE_DIR, INSTALLED_APPS

DEBUG = False
SECRET_KEY = "test-only-secret-key-not-used-in-production"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(BASE_DIR / "db_test.sqlite3"),
        "TEST": {"NAME": "/tmp/leads_test.sqlite3"},
        "OPTIONS": {"timeout": 30},
    }
}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_TASK_STORE_EAGER_RESULT = True

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
EMAIL_HOST = "localhost"
EMAIL_HOST_USER = "test@example.com"
EMAIL_HOST_PASSWORD = "test"

AI_PROVIDER = "rules"
AI_ENABLED = True

MEDIA_ROOT = tempfile.mkdtemp(prefix="leads-test-media-")
STATIC_ROOT = str(BASE_DIR / "staticfiles_test")

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
