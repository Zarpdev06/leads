"""Read-side analytics. All aggregation happens in the database."""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.campaigns.models import Campaign
from apps.email_engine.models import DailyEmailUsage, EmailMessage
from apps.leads.models import CRMStage, EmailStatus, Lead, LeadQuality
from apps.suppression.models import Suppression


def _date_range(days: int):
    today = timezone.localdate()
    return today - timedelta(days=days - 1), today


def overview() -> dict:
    """KPI cards for the dashboard."""
    today = timezone.localdate()
    usage = DailyEmailUsage.objects.filter(date=today).first()

    leads = Lead.objects.active()
    emails_sent_today = (
        EmailMessage.objects.filter(sent_at__date=today).count()
    )
    limit = usage.limit if usage else 90
    sent_today_from_counter = usage.sent_count if usage else 0

    won = leads.filter(crm_stage=CRMStage.WON).count()
    contacted = leads.filter(times_contacted__gt=0).count()
    replied = leads.filter(replied_at__isnull=False).count()
    meetings = leads.filter(
        crm_stage__in=[CRMStage.MEETING_REQUESTED, CRMStage.MEETING_SCHEDULED]
    ).count()
    proposals = leads.filter(
        crm_stage__in=[CRMStage.PROPOSAL, CRMStage.NEGOTIATION]
    ).count()
    pipeline_value = leads.filter(
        crm_stage__in=[CRMStage.PROPOSAL, CRMStage.NEGOTIATION, CRMStage.WON]
    ).aggregate(total=Sum("deal_value"))["total"] or 0

    return {
        "total_leads": leads.count(),
        "valid_emails": leads.filter(email_status=EmailStatus.VALID).count(),
        "missing_emails": leads.filter(email_normalized="").count(),
        "invalid_emails": leads.filter(email_status=EmailStatus.INVALID).count(),
        "suppressed": Suppression.objects.filter(is_active=True).count(),
        "qualified_leads": leads.filter(
            lead_quality__in=[LeadQuality.HOT, LeadQuality.WARM]
        ).count(),
        "hot_leads": leads.filter(lead_quality=LeadQuality.HOT).count(),
        "emails_sent_today": max(emails_sent_today, sent_today_from_counter),
        "daily_limit": limit,
        "remaining_capacity": max(0, limit - max(emails_sent_today, sent_today_from_counter)),
        "emails_sent_total": EmailMessage.objects.filter(
            status=EmailMessage.Status.SENT
        ).count(),
        "replies": replied,
        "meetings": meetings,
        "proposals": proposals,
        "won": won,
        "lost": leads.filter(crm_stage=CRMStage.LOST).count(),
        "pipeline_value": float(pipeline_value),
        "conversion_rate": round((won / contacted * 100) if contacted else 0.0, 2),
        "reply_rate": round(
            (replied / emails_sent_today * 100) if emails_sent_today else 0.0, 2
        ),
        "active_campaigns": Campaign.objects.filter(status=Campaign.Status.RUNNING).count(),
    }


def capacity() -> dict:
    from apps.email_engine.quota import DailyEmailQuota

    status = DailyEmailQuota.status()
    return {
        **status,
        "bar": _capacity_bar(status["sent"], status["limit"]),
    }


def _capacity_bar(sent: int, limit: int, width: int = 20) -> str:
    filled = int(round(sent / limit * width)) if limit else 0
    filled = max(0, min(width, filled))
    return "█" * filled + "-" * (width - filled)


def daily_outreach(days: int = 30) -> list[dict]:
    start, end = _date_range(days)
    rows = (
        EmailMessage.objects.filter(sent_at__date__gte=start)
        .annotate(day=TruncDate("sent_at"))
        .values("day")
        .annotate(
            sent=Count("id", filter=Q(status=EmailMessage.Status.SENT)),
            failed=Count("id", filter=Q(status=EmailMessage.Status.FAILED)),
            bounced=Count("id", filter=Q(status=EmailMessage.Status.BOUNCED)),
            opened=Count("id", filter=Q(opened_at__isnull=False)),
            clicked=Count("id", filter=Q(clicked_at__isnull=False)),
            replied=Count("id", filter=Q(replied_at__isnull=False)),
        )
        .order_by("day")
    )
    by_day = {row["day"]: row for row in rows}
    out = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        row = by_day.get(day, {})
        out.append({
            "date": day.isoformat(),
            "sent": row.get("sent", 0),
            "failed": row.get("failed", 0),
            "bounced": row.get("bounced", 0),
            "opened": row.get("opened", 0),
            "clicked": row.get("clicked", 0),
            "replied": row.get("replied", 0),
        })
    return out


def campaign_performance(days: int = 30) -> list[dict]:
    start, _ = _date_range(days)
    return list(
        Campaign.objects.annotate(
            sent=Count("email_messages", filter=Q(
                email_messages__status=EmailMessage.Status.SENT)),
            opened=Count("email_messages", filter=Q(
                email_messages__opened_at__isnull=False)),
            replied=Count("email_messages", filter=Q(
                email_messages__replied_at__isnull=False)),
            bounced=Count("email_messages", filter=Q(
                email_messages__bounced_at__isnull=False)),
            unsubscribed=Count("email_messages", filter=Q(
                email_messages__unsubscribed_at__isnull=False)),
        ).values("id", "name", "status", "sent", "opened", "replied", "bounced",
                 "unsubscribed")
    )


def industry_performance(days: int = 90, limit: int = 12) -> list[dict]:
    start, _ = _date_range(days)
    rows = (
        EmailMessage.objects.filter(sent_at__date__gte=start)
        .values("lead__industry__name")
        .annotate(
            sent=Count("id"),
            replied=Count("id", filter=Q(replied_at__isnull=False)),
            opened=Count("id", filter=Q(opened_at__isnull=False)),
        )
        .order_by("-sent")[:limit]
    )
    return [
        {
            "industry": row["lead__industry__name"] or "Uncategorized",
            "sent": row["sent"],
            "replied": row["replied"],
            "opened": row["opened"],
            "reply_rate": round(row["replied"] / row["sent"] * 100, 2) if row["sent"] else 0.0,
        }
        for row in rows
    ]


def location_performance(days: int = 90, limit: int = 12) -> list[dict]:
    start, _ = _date_range(days)
    rows = (
        EmailMessage.objects.filter(sent_at__date__gte=start)
        .values("lead__state", "lead__city")
        .annotate(
            sent=Count("id"),
            replied=Count("id", filter=Q(replied_at__isnull=False)),
        )
        .order_by("-sent")[:limit]
    )
    return [
        {
            "location": ", ".join(p for p in (row["lead__city"], row["lead__state"]) if p)
                        or "Unknown",
            "state": row["lead__state"] or "",
            "city": row["lead__city"] or "",
            "sent": row["sent"],
            "replied": row["replied"],
            "reply_rate": round(row["replied"] / row["sent"] * 100, 2) if row["sent"] else 0.0,
        }
        for row in rows
    ]


def funnel() -> list[dict]:
    leads = Lead.objects.active()
    stages = [
        ("Imported", leads.count()),
        ("Valid email", leads.filter(email_status=EmailStatus.VALID).count()),
        ("Contacted", leads.filter(times_contacted__gt=0).count()),
        ("Replied", leads.filter(replied_at__isnull=False).count()),
        ("Meeting", leads.filter(crm_stage__in=[
            CRMStage.MEETING_REQUESTED, CRMStage.MEETING_SCHEDULED]).count()),
        ("Proposal", leads.filter(crm_stage__in=[
            CRMStage.PROPOSAL, CRMStage.NEGOTIATION]).count()),
        ("Won", leads.filter(crm_stage=CRMStage.WON).count()),
    ]
    total = stages[0][1] or 1
    return [
        {"stage": name, "count": value, "percent": round(value / total * 100, 2)}
        for name, value in stages
    ]


def service_interest(days: int = 90) -> list[dict]:
    start, _ = _date_range(days)
    rows = (
        EmailMessage.objects.filter(sent_at__date__gte=start)
        .exclude(recommended_service="")
        .values("recommended_service")
        .annotate(
            sent=Count("id"),
            replied=Count("id", filter=Q(replied_at__isnull=False)),
        )
        .order_by("-sent")[:12]
    )
    return [
        {
            "service": row["recommended_service"],
            "sent": row["sent"],
            "replied": row["replied"],
            "reply_rate": round(row["replied"] / row["sent"] * 100, 2) if row["sent"] else 0.0,
        }
        for row in rows
    ]


def ai_vs_template(days: int = 90) -> dict:
    start, _ = _date_range(days)
    rows = (
        EmailMessage.objects.filter(sent_at__date__gte=start)
        .values("is_ai_generated")
        .annotate(
            sent=Count("id"),
            opened=Count("id", filter=Q(opened_at__isnull=False)),
            replied=Count("id", filter=Q(replied_at__isnull=False)),
        )
    )
    result = {"ai": {"sent": 0, "opened": 0, "replied": 0},
              "template": {"sent": 0, "opened": 0, "replied": 0}}
    for row in rows:
        bucket = "ai" if row["is_ai_generated"] else "template"
        result[bucket] = {
            "sent": row["sent"], "opened": row["opened"], "replied": row["replied"],
            "open_rate": round(row["opened"] / row["sent"] * 100, 2) if row["sent"] else 0.0,
            "reply_rate": round(row["replied"] / row["sent"] * 100, 2) if row["sent"] else 0.0,
        }
    return result


def source_quality() -> list[dict]:
    """Data-quality dashboard: per-source record health."""
    from apps.imports.models import LeadSource

    out = []
    for source in LeadSource.objects.all():
        out.append({
            "source_id": source.pk,
            "source": source.name,
            "category": source.category,
            "total": source.total_rows,
            "with_email": source.rows_with_email,
            "without_email": source.rows_without_email,
            "invalid_email": source.invalid_emails,
            "duplicates": source.duplicate_rows,
            "missing_company": source.missing_company_names,
            "imported_at": source.imported_at.isoformat() if source.imported_at else None,
        })
    return out


def lead_quality_breakdown() -> list[dict]:
    rows = (
        Lead.objects.active().values("lead_quality").annotate(count=Count("id"))
    )
    labels = dict(LeadQuality.choices)
    return [
        {"quality": labels.get(row["lead_quality"], row["lead_quality"]),
         "key": row["lead_quality"], "count": row["count"]}
        for row in rows
    ]


def email_status_breakdown() -> list[dict]:
    rows = Lead.objects.active().values("email_status").annotate(count=Count("id"))
    labels = dict(EmailStatus.choices)
    return [
        {"status": labels.get(row["email_status"], row["email_status"]),
         "key": row["email_status"], "count": row["count"]}
        for row in rows
    ]


def rates(days: int = 30) -> dict:
    start, _ = _date_range(days)
    sent = EmailMessage.objects.filter(
        status=EmailMessage.Status.SENT, sent_at__date__gte=start
    )
    total = sent.count()
    if not total:
        return {"sent": 0, "bounce_rate": 0, "unsubscribe_rate": 0, "reply_rate": 0,
                "open_rate": 0, "click_rate": 0, "meeting_rate": 0, "conversion_rate": 0}
    bounced = sent.filter(bounced_at__isnull=False).count()
    unsubscribed = sent.filter(unsubscribed_at__isnull=False).count()
    opened = sent.filter(opened_at__isnull=False).count()
    clicked = sent.filter(clicked_at__isnull=False).count()
    replied = sent.filter(replied_at__isnull=False).count()
    meetings = Lead.objects.filter(
        crm_stage__in=[CRMStage.MEETING_REQUESTED, CRMStage.MEETING_SCHEDULED]
    ).count()
    won = Lead.objects.filter(crm_stage=CRMStage.WON).count()
    return {
        "sent": total,
        "bounce_rate": round(bounced / total * 100, 2),
        "unsubscribe_rate": round(unsubscribed / total * 100, 2),
        "open_rate": round(opened / total * 100, 2),
        "click_rate": round(clicked / total * 100, 2),
        "reply_rate": round(replied / total * 100, 2),
        "meeting_rate": round(meetings / total * 100, 2),
        "conversion_rate": round(won / total * 100, 2),
    }
