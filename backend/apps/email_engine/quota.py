"""
Daily email quota — the safety-critical part of the platform.

Guarantee: on any given calendar day the platform will never send more than
`min(marketing limit, SMTP limit, hard cap)` marketing emails, no matter how
many Celery workers run concurrently.

How it is enforced
------------------
`DailyEmailQuota.reserve()` performs a single conditional UPDATE:

    UPDATE email_engine_dailyemailusage
       SET sent_count = sent_count + 1
     WHERE date = <today> AND sent_count < <limit>

The database evaluates the WHERE clause atomically under a row lock, so exactly
`limit` concurrent callers can succeed. `SELECT ... FOR UPDATE` is used in
addition when the backend supports it, purely to make the intent explicit and
to keep the read-modify-write in one transaction with the send.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import date, timedelta

from django.db import OperationalError, connection, transaction
from django.db.models import F
from django.utils import timezone

from .models import DailyEmailUsage

logger = logging.getLogger(__name__)


@dataclass
class Reservation:
    granted: bool
    usage: DailyEmailUsage
    limit: int
    sent: int
    remaining: int
    reason: str = ""

    def __bool__(self) -> bool:
        return self.granted


class DailyEmailQuota:
    """Concurrency-safe daily marketing budget."""

    @staticmethod
    def effective_limit() -> int:
        from apps.settings.services import effective_daily_limit

        return effective_daily_limit()

    @staticmethod
    def smtp_limit() -> int:
        from apps.settings.services import smtp_daily_limit

        return smtp_daily_limit()

    @staticmethod
    def hard_cap() -> int:
        from django.conf import settings as django_settings

        return int(django_settings.EMAIL_HARD_DAILY_CAP)

    # ------------------------------------------------------------------
    @staticmethod
    def usage_for(day: date | None = None) -> DailyEmailUsage:
        """Get (or create) the counter row for a date, with today's limits."""
        from apps.settings.services import effective_daily_limit, smtp_daily_limit

        day = day or timezone.localdate()
        usage, created = _retry_on_lock(
            lambda: DailyEmailUsage.objects.get_or_create(
                date=day,
                defaults={
                    "limit": effective_daily_limit(),
                    "smtp_limit": smtp_daily_limit(),
                },
            )
        )[0], False
        usage, created = DailyEmailUsage.objects.get_or_create(
            date=day,
            defaults={
                "limit": effective_daily_limit(),
                "smtp_limit": smtp_daily_limit(),
            },
        )
        if not created:
            # Limits may have been changed in Settings; refresh the snapshot.
            limit, smtp = effective_daily_limit(), smtp_daily_limit()
            if usage.limit != limit or usage.smtp_limit != smtp:
                usage.limit, usage.smtp_limit = limit, smtp
                usage.save(update_fields=["limit", "smtp_limit", "updated_at"])
        return usage

    @staticmethod
    def status(day: date | None = None) -> dict:
        usage = DailyEmailQuota.usage_for(day)
        return {
            "date": usage.date.isoformat(),
            "sent": usage.sent_count,
            "failed": usage.failed_count,
            "bounced": usage.bounced_count,
            "skipped": usage.skipped_count,
            "transactional": usage.transactional_count,
            "limit": usage.limit,
            "smtp_limit": usage.smtp_limit,
            "remaining": usage.remaining,
            "percent_used": round(usage.percent_used, 1),
            "hard_cap": DailyEmailQuota.hard_cap(),
        }

    # ------------------------------------------------------------------
    @staticmethod
    def reserve(*, day: date | None = None, limit: int | None = None) -> Reservation:
        """Try to consume one slot. Returns a falsy Reservation when exhausted.

        The guarantee comes from a single conditional UPDATE:

            UPDATE email_engine_dailyemailusage
               SET sent_count = sent_count + 1
             WHERE id = <pk> AND sent_count < <limit>

        The database evaluates the WHERE clause atomically while holding the
        row lock, so exactly `limit` concurrent callers can succeed - even
        with dozens of Celery workers. `SELECT ... FOR UPDATE` is used in
        addition on backends that support it, purely to make the intent
        explicit; the UPDATE alone is what prevents overshoot.
        """
        day = day or timezone.localdate()
        usage = DailyEmailQuota.usage_for(day)
        effective = limit if limit is not None else usage.limit

        granted = _consume_slot(usage.pk, effective)
        if granted is None:
            return Reservation(False, usage, effective, usage.sent_count, 0,
                               "Daily marketing limit reached")

        sent = granted
        logger.info("Email quota reserved: %s/%s on %s", sent, effective, day)
        if sent >= effective:
            from apps.core.models import log_audit

            log_audit(
                action="QUOTA_REACHED",
                entity_type="daily_usage",
                entity_id=day.isoformat(),
                description=f"Daily marketing limit ({effective}) reached",
            )
        return Reservation(True, usage, effective, sent, max(0, effective - sent))

    @staticmethod
    def record_failure(*, day: date | None = None, bounced: bool = False) -> None:
        """Count a failure (the reserved slot is already consumed)."""
        day = day or timezone.localdate()
        usage = DailyEmailUsage.objects.filter(date=day).first()
        if usage is None:
            return
        if bounced:
            DailyEmailUsage.objects.filter(pk=usage.pk).update(
                bounced_count=F("bounced_count") + 1, failed_count=F("failed_count") + 1
            )
        else:
            DailyEmailUsage.objects.filter(pk=usage.pk).update(
                failed_count=F("failed_count") + 1
            )

    @staticmethod
    def record_skipped(*, day: date | None = None) -> None:
        day = day or timezone.localdate()
        DailyEmailUsage.objects.filter(date=day).update(skipped_count=F("skipped_count") + 1)

    @staticmethod
    def record_transactional(*, day: date | None = None) -> None:
        day = day or timezone.localdate()
        usage, _ = DailyEmailUsage.objects.get_or_create(
            date=day, defaults={"limit": DailyEmailQuota.effective_limit(),
                                "smtp_limit": DailyEmailQuota.smtp_limit()}
        )
        DailyEmailUsage.objects.filter(pk=usage.pk).update(
            transactional_count=F("transactional_count") + 1
        )

    @staticmethod
    def remaining(day: date | None = None) -> int:
        return DailyEmailQuota.usage_for(day).remaining

    # ------------------------------------------------------------------
    @staticmethod
    def schedule_capacity(days: int = 7, *, start: date | None = None) -> list[dict]:
        """Remaining capacity per day - used to spread campaigns over days."""
        start = start or timezone.localdate()
        out = []
        for offset in range(days):
            day = start + timedelta(days=offset)
            usage = DailyEmailUsage.objects.filter(date=day).first()
            limit = DailyEmailQuota.effective_limit()
            sent = usage.sent_count if usage else 0
            out.append({
                "date": day.isoformat(),
                "limit": limit,
                "sent": sent,
                "remaining": max(0, limit - sent),
            })
        return out


def _consume_slot(usage_pk: int, limit: int, *, attempts: int = 10) -> int | None:
    """Atomically increment the counter if below the limit.

    Returns the new sent_count, or None when the budget is exhausted.
    The UPDATE is deliberately the *first* statement of the transaction: on
    SQLite a transaction that reads before writing cannot upgrade its lock and
    gets SQLITE_BUSY immediately (the busy handler is not invoked), so
    write-first keeps the wait (and the retry loop) effective.
    """
    for attempt in range(attempts):
        try:
            with transaction.atomic():
                if connection.features.has_select_for_update:
                    usage = DailyEmailUsage.objects.select_for_update().get(pk=usage_pk)
                    if usage.sent_count >= limit:
                        return None
                updated = DailyEmailUsage.objects.filter(
                    pk=usage_pk, sent_count__lt=limit
                ).update(sent_count=F("sent_count") + 1)
                if not updated:
                    return None
                return DailyEmailUsage.objects.get(pk=usage_pk).sent_count
        except OperationalError:
            if attempt == attempts - 1:
                raise
            transaction.set_rollback(True, using=None) if False else None
            time.sleep(min(0.25, (2 ** attempt) / 1000) * (0.5 + random.random()))
    return None


def _retry_on_lock(func, *, attempts: int = 10):
    """Run `func`, retrying on transient 'database is locked' errors."""
    for attempt in range(attempts):
        try:
            return func()
        except OperationalError:
            if attempt == attempts - 1:
                raise
            time.sleep(min(0.25, (2 ** attempt) / 1000) * (0.5 + random.random()))
    return None
