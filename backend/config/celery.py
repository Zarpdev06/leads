"""Celery application wiring."""
from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("leads")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Beat is configured here (single source of truth) so the schedule is versioned
# with the code instead of living in a database that can drift.
app.conf.beat_schedule = {
    # ---- Outreach -------------------------------------------------------
    "send-due-emails-every-minute": {
        "task": "apps.email_engine.tasks.send_due_emails",
        "schedule": 60.0,
        "options": {"queue": "email", "expires": 55},
    },
    "process-follow-ups": {
        "task": "apps.email_engine.tasks.process_follow_ups",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "email", "expires": 800},
    },
    "release-stuck-messages": {
        "task": "apps.email_engine.tasks.release_stuck_messages",
        "schedule": crontab(minute="*/10"),
        "options": {"queue": "email", "expires": 500},
    },
    "rollover-daily-usage": {
        "task": "apps.email_engine.tasks.rollover_daily_usage",
        "schedule": crontab(hour=0, minute=5),
        "options": {"queue": "email"},
    },
    # ---- Analytics ------------------------------------------------------
    "build-daily-metrics": {
        "task": "apps.analytics.tasks.build_daily_metrics",
        "schedule": crontab(hour=0, minute=20),
        "options": {"queue": "analytics"},
    },
    # ---- Mailbox (replies/bounces), only active when IMAP is configured --
    "poll-mailbox": {
        "task": "apps.email_engine.tasks.poll_mailbox",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "analytics", "expires": 800},
    },
    # ---- Maintenance ----------------------------------------------------
    "purge-old-import-files": {
        "task": "apps.imports.tasks.purge_old_import_files",
        "schedule": crontab(hour=3, minute=10),
        "options": {"queue": "default"},
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):  # pragma: no cover - operational helper
    """Echo task metadata; useful to verify the worker is alive."""
    print(f"Request: {self.request!r}")
