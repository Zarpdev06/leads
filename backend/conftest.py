"""
Root pytest configuration.

The test settings module (config.settings_test) replaces all external
infrastructure; this file only makes sure the environment variables a
developer may have in `.env` cannot re-enable Redis/Postgres during tests.
"""
from __future__ import annotations

import os

os.environ["DB_ENGINE"] = "sqlite"
os.environ["USE_REDIS_CACHE"] = "False"
os.environ["CELERY_BROKER_URL"] = "memory://"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "True"
os.environ["CELERY_TASK_EAGER_PROPAGATES"] = "False"
os.environ["EMAIL_BACKEND"] = "django.core.mail.backends.locmem.EmailBackend"
os.environ["AI_PROVIDER"] = "rules"
