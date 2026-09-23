"""Analytics aggregation (queue: analytics)."""
from __future__ import annotations

from celery import shared_task
from django.db.models import Count, Q
from django.utils import timezone

from .models import CampaignDailyStat, DailyMetric, ImportDailyStat
from .services import overview


@shared_task(name="apps.analytics.tasks.build_daily_metrics")
def build_daily_metrics(day: str | None = None) -> dict:
    """Recompute the aggregate tables for one day (idempotent)."""
    from datetime import datetime

    from apps.email_engine.models import EmailMessage

    date = datetime.fromisoformat(day).date() if day else timezone.localdate()

    messages = EmailMessage.objects.filter(sent_at__date=date)
    aggregates = messages.aggregate(
        sent=Count("id", filter=Q(status=EmailMessage.Status.SENT)),
        failed=Count("id", filter=Q(status=EmailMessage.Status.FAILED)),
        bounced=Count("id", filter=Q(bounced_at__isnull=False)),
        opened=Count("id", filter=Q(opened_at__isnull=False)),
        clicked=Count("id", filter=Q(clicked_at__isnull=False)),
        replied=Count("id", filter=Q(replied_at__isnull=False)),
        unsubscribed=Count("id", filter=Q(unsubscribed_at__isnull=False)),
    )
    written = 0
    for key, value in aggregates.items():
        DailyMetric.objects.update_or_create(
            date=date, scope="global", key=f"email.{key}", dimension="",
            defaults={"value": float(value or 0)},
        )
        written += 1

    # Per-campaign rows
    rows = (
        messages.values("campaign_id")
        .annotate(
            sent=Count("id", filter=Q(status=EmailMessage.Status.SENT)),
            opened=Count("id", filter=Q(opened_at__isnull=False)),
            clicked=Count("id", filter=Q(clicked_at__isnull=False)),
            replied=Count("id", filter=Q(replied_at__isnull=False)),
            bounced=Count("id", filter=Q(bounced_at__isnull=False)),
            unsubscribed=Count("id", filter=Q(unsubscribed_at__isnull=False)),
            failed=Count("id", filter=Q(status=EmailMessage.Status.FAILED)),
        )
    )
    for row in rows:
        if not row["campaign_id"]:
            continue
        CampaignDailyStat.objects.update_or_create(
            campaign_id=row["campaign_id"], date=date,
            defaults={key: row[key] or 0 for key in
                      ("sent", "opened", "clicked", "replied", "bounced",
                       "unsubscribed", "failed")},
        )
        written += 1

    # Per-source import stats
    from apps.imports.models import LeadSource
    from apps.leads.models import EmailStatus, Lead

    for source in LeadSource.objects.all():
        leads = Lead.objects.filter(source=source)
        stats = leads.aggregate(
            rows=Count("id"),
            with_email=Count("id", filter=~Q(email_normalized="")),
            invalid=Count("id", filter=Q(email_status=EmailStatus.INVALID)),
            duplicates=Count("id", filter=Q(is_duplicate=True)),
        )
        ImportDailyStat.objects.update_or_create(
            source=source, date=date,
            defaults={
                "rows": stats["rows"] or 0,
                "with_email": stats["with_email"] or 0,
                "without_email": (stats["rows"] or 0) - (stats["with_email"] or 0),
                "invalid_email": stats["invalid"] or 0,
                "duplicates": stats["duplicates"] or 0,
            },
        )
        written += 1

    return {"date": date.isoformat(), "rows_written": written}


@shared_task(name="apps.analytics.tasks.snapshot_overview")
def snapshot_overview() -> dict:
    data = overview()
    today = timezone.localdate()
    for key in ("total_leads", "valid_emails", "missing_emails", "won", "replies"):
        DailyMetric.objects.update_or_create(
            date=today, scope="global", key=f"snapshot.{key}", dimension="",
            defaults={"value": float(data.get(key, 0) or 0)},
        )
    return data
