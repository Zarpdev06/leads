"""
Campaign dispatch, scheduling and follow-up orchestration.

Dispatch converts a campaign audience into scheduled EmailMessage rows:

    * one message per lead for step 0,
    * spread across the send window (09:30-17:30 by default),
    * spread across DAYS so that no single day exceeds the daily limit,
    * never more than `min(campaign.daily_limit, global remaining capacity)`
      messages on any given day.
"""
from __future__ import annotations

import logging
import random
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.campaigns.models import Campaign, CampaignLead
from apps.leads.eligibility import apply_campaign_filters, eligible_queryset
from apps.leads.models import CRMStage, EmailStatus, Lead, LeadStatus
from apps.settings.services import (
    effective_daily_limit,
    sending_weekdays,
    sending_timezone,
)

from .models import EmailMessage
from .quota import DailyEmailQuota

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audience selection
# ---------------------------------------------------------------------------
def select_audience(campaign: Campaign, *, base=None) -> "QuerySet[Lead]":
    """Leads matching the campaign criteria and eligible for outreach."""
    if campaign.lead_ids:
        base = Lead.objects.filter(id__in=campaign.lead_ids)
    qs = eligible_queryset(campaign, base=base)
    if campaign.exclude_missing_email:
        qs = qs.exclude(email_normalized="")
    return qs


def materialize_campaign_leads(campaign: Campaign, *, user=None, limit: int | None = None
                               ) -> int:
    """Create CampaignLead rows for the audience (idempotent)."""
    leads = select_audience(campaign)
    if limit:
        leads = leads[:limit]
    lead_ids = list(leads.values_list("id", flat=True))
    existing = set(
        CampaignLead.objects.filter(campaign=campaign, lead_id__in=lead_ids)
        .values_list("lead_id", flat=True)
    )
    to_create = [
        CampaignLead(campaign=campaign, lead_id=lead_id, status=CampaignLead.Status.PENDING,
                     added_by=user)
        for lead_id in lead_ids if lead_id not in existing
    ]
    if to_create:
        CampaignLead.objects.bulk_create(to_create, batch_size=500,
                                         ignore_conflicts=True)
    campaign.total_selected = CampaignLead.objects.filter(campaign=campaign).count()
    campaign.save(update_fields=["total_selected", "updated_at"])
    return len(to_create)


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------
def _parse_hhmm(value: str, default: str) -> time:
    try:
        hour, minute = str(value or default).split(":")
        return time(hour=int(hour), minute=int(minute))
    except Exception:
        hour, minute = default.split(":")
        return time(hour=int(hour), minute=int(minute))


def _now_in_tz() -> datetime:
    try:
        import zoneinfo

        tz = zoneinfo.ZoneInfo(sending_timezone())
    except Exception:  # pragma: no cover - unknown timezone
        tz = timezone.get_current_timezone()
    return timezone.localtime(timezone.now(), tz)


def next_sending_day(start: date, weekdays: list[int]) -> date:
    day = start
    for _ in range(14):
        if day.isoweekday() in weekdays:
            return day
        day += timedelta(days=1)
    return start


def build_schedule(campaign: Campaign, *, count: int, start: date | None = None,
                   per_day: int | None = None) -> list[datetime]:
    """Distribute `count` sends over days and over the daily send window.

    Guarantees: at most `per_day` messages on any calendar day, and all of them
    inside the configured window (with jitter so we do not look like a blast).
    """
    if count <= 0:
        return []

    window_start = _parse_hhmm(campaign.send_window_start, settings.SEND_WINDOW_START)
    window_end = _parse_hhmm(campaign.send_window_end, settings.SEND_WINDOW_END)
    weekdays = sending_weekdays() or [1, 2, 3, 4, 5]

    global_limit = effective_daily_limit()
    per_day = max(1, min(per_day or campaign.daily_limit or global_limit, global_limit))

    start_date = start or _now_in_tz().date()
    if campaign.start_date and campaign.start_date > start_date:
        start_date = campaign.start_date

    window_minutes = max(
        1,
        (window_end.hour * 60 + window_end.minute)
        - (window_start.hour * 60 + window_start.minute),
    )

    schedule: list[datetime] = []
    day = next_sending_day(start_date, weekdays)
    remaining = count
    guard = 0
    while remaining > 0 and guard < 3650:
        guard += 1
        # How much capacity is left on this day (globally, not just for us)?
        capacity_left = DailyEmailQuota.schedule_capacity(1, start=day)[0]["remaining"]
        day_allocation = min(per_day, remaining, max(capacity_left, 0))
        if day_allocation <= 0:
            day = next_sending_day(day + timedelta(days=1), weekdays)
            continue

        for index in range(day_allocation):
            offset = (window_minutes * (index + 1)) // (day_allocation + 1)
            jitter = random.randint(0, max(1, min(9, window_minutes // max(1, day_allocation))))
            minute_of_day = (window_start.hour * 60 + window_start.minute) + offset + jitter
            naive = datetime.combine(day, time(0, 0)) + timedelta(minutes=minute_of_day)
            schedule.append(timezone.make_aware(naive, timezone.get_current_timezone()))

        remaining -= day_allocation
        day = next_sending_day(day + timedelta(days=1), weekdays)

    return schedule


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
def dispatch_campaign(campaign: Campaign, *, user=None, batch_size: int = 500) -> dict:
    """Create scheduled EmailMessage rows for PENDING campaign leads.

    Idempotent: leads that already have a step-0 message are skipped.
    """
    from apps.email_engine.sender import compose_message

    created = 0
    skipped = 0
    errors: list[str] = []

    pending = (
        CampaignLead.objects.filter(campaign=campaign, status=CampaignLead.Status.PENDING)
        .select_related("lead", "lead__industry", "lead__sub_industry")
        .order_by("-lead__lead_score", "id")
    )
    # Leads that already have a message for step 0 (retry-safe).
    already = set(
        EmailMessage.objects.filter(campaign=campaign, step_number=0)
        .values_list("campaign_lead_id", flat=True)
    )
    pending_ids = [cl.pk for cl in pending if cl.pk not in already]
    if not pending_ids:
        return {"created": 0, "skipped": 0, "errors": []}

    schedule = build_schedule(campaign, count=len(pending_ids))
    if not schedule:
        return {"created": 0, "skipped": len(pending_ids),
                "errors": ["No sending capacity in the configured schedule."]}

    messages: list[EmailMessage] = []
    for index, campaign_lead in enumerate(
        CampaignLead.objects.filter(pk__in=pending_ids).select_related(
            "lead", "lead__industry", "lead__sub_industry"
        )
    ):
        lead = campaign_lead.lead
        try:
            message = compose_message(
                lead=lead,
                template=campaign.template,
                campaign=campaign,
                campaign_lead=campaign_lead,
                step_number=0,
                subject=campaign.subject,
            )
        except Exception as exc:
            logger.exception("Failed to compose message for lead %s", lead.pk)
            errors.append(f"Lead {lead.pk}: {exc}")
            skipped += 1
            continue
        message.scheduled_at = schedule[index] if index < len(schedule) else schedule[-1]
        messages.append(message)
        campaign_lead.scheduled_at = message.scheduled_at
        campaign_lead.status = CampaignLead.Status.SCHEDULED

        if len(messages) >= batch_size:
            _bulk_save(messages)
            created += len(messages)
            messages = []

    if messages:
        _bulk_save(messages)
        created += len(messages)

    CampaignLead.objects.filter(pk__in=pending_ids).update(
        status=CampaignLead.Status.SCHEDULED
    )
    # scheduled_at is per-row; write it in one pass.
    scheduled_map = {m.campaign_lead_id: m.scheduled_at for m in
                     EmailMessage.objects.filter(campaign=campaign, step_number=0,
                                                 campaign_lead_id__in=pending_ids)}
    for campaign_lead_id, scheduled_at in scheduled_map.items():
        CampaignLead.objects.filter(pk=campaign_lead_id).update(scheduled_at=scheduled_at)

    campaign.total_queued = EmailMessage.objects.filter(
        campaign=campaign, status=EmailMessage.Status.QUEUED
    ).count()
    campaign.last_dispatched_at = timezone.now()
    campaign.save(update_fields=["total_queued", "last_dispatched_at", "updated_at"])
    return {"created": created, "skipped": skipped, "errors": errors[:20]}


def _bulk_save(messages: list[EmailMessage]) -> None:
    EmailMessage.objects.bulk_create(messages, batch_size=200, ignore_conflicts=True)


# ---------------------------------------------------------------------------
# Follow-ups
# ---------------------------------------------------------------------------
def stop_condition_met(campaign_lead: CampaignLead) -> str | None:
    """Return a reason string when the sequence must stop, else None."""
    lead = campaign_lead.lead
    sequence = campaign_lead.campaign.follow_up_sequence
    stop_on_reply = sequence.stop_on_reply if sequence else True
    stop_on_bounce = sequence.stop_on_bounce if sequence else True
    stop_on_unsub = sequence.stop_on_unsubscribe if sequence else True
    stop_on_click = sequence.stop_on_click if sequence else False
    stop_on_converted = sequence.stop_on_converted if sequence else True

    if stop_on_unsub and (lead.unsubscribed_at or
                          lead.lead_status == LeadStatus.UNSUBSCRIBED):
        return "Unsubscribed"
    if stop_on_bounce and (lead.bounced_at or
                           lead.email_status == EmailStatus.BOUNCED):
        return "Bounced"
    if stop_on_reply and lead.replied_at:
        return "Replied"
    if stop_on_converted and lead.crm_stage in {
        CRMStage.WON, CRMStage.LOST, CRMStage.DO_NOT_CONTACT,
    }:
        return f"Lead {lead.get_crm_stage_display()}"
    if lead.do_not_contact or lead.is_blocked:
        return "Blocked / do not contact"
    if stop_on_click:
        last = (
            EmailMessage.objects.filter(campaign_lead=campaign_lead)
            .order_by("-created_at").first()
        )
        if last and last.clicked_at:
            return "Clicked"
    if campaign_lead.campaign.status not in {
        Campaign.Status.RUNNING, Campaign.Status.READY, Campaign.Status.PAUSED,
    }:
        return "Campaign not running"
    return None


def schedule_next_follow_up(campaign_lead: CampaignLead) -> EmailMessage | None:
    """Create the next follow-up message if the sequence says so."""
    from apps.email_engine.sender import compose_message

    campaign = campaign_lead.campaign
    if not campaign.follow_up_enabled:
        campaign_lead.status = CampaignLead.Status.COMPLETED
        campaign_lead.save(update_fields=["status", "updated_at"])
        return None

    sequence = campaign.follow_up_sequence
    if sequence is None:
        campaign_lead.status = CampaignLead.Status.COMPLETED
        campaign_lead.save(update_fields=["status", "updated_at"])
        return None

    reason = stop_condition_met(campaign_lead)
    if reason:
        campaign_lead.stop(reason)
        return None

    next_order = campaign_lead.current_step + 1
    step = sequence.steps.filter(order=next_order, is_active=True).first()
    if step is None:
        campaign_lead.status = CampaignLead.Status.COMPLETED
        campaign_lead.next_follow_up_at = None
        campaign_lead.save(update_fields=["status", "next_follow_up_at", "updated_at"])
        return None

    if step.condition == step.Condition.NO_REPLY and campaign_lead.lead.replied_at:
        campaign_lead.stop("Replied")
        return None

    # Unique constraint on (campaign_lead, step_number) makes this idempotent.
    if EmailMessage.objects.filter(campaign_lead=campaign_lead,
                                   step_number=next_order).exists():
        return None

    base_time = campaign_lead.sent_at or timezone.now()
    scheduled_at = base_time + timedelta(days=step.delay_days, hours=step.delay_hours)
    scheduled_at = _snap_to_window(scheduled_at, campaign)

    message = compose_message(
        lead=campaign_lead.lead,
        template=step.template or campaign.template,
        campaign=campaign,
        campaign_lead=campaign_lead,
        step_number=next_order,
        subject=step.subject or campaign.subject,
        body_html=step.body_html,
        use_ai=step.use_ai if step.template or step.body_html else campaign.use_ai_personalization,
        ai_instructions=step.ai_instructions or campaign.ai_instructions,
    )
    message.scheduled_at = scheduled_at
    message.save()

    campaign_lead.current_step = next_order
    campaign_lead.next_follow_up_at = scheduled_at
    campaign_lead.status = CampaignLead.Status.FOLLOW_UP
    campaign_lead.save(update_fields=[
        "current_step", "next_follow_up_at", "status", "updated_at",
    ])
    campaign_lead.lead.next_follow_up_at = scheduled_at
    campaign_lead.lead.save(update_fields=["next_follow_up_at", "updated_at"])
    return message


def _snap_to_window(moment: datetime, campaign: Campaign) -> datetime:
    """Keep follow-ups inside the send window and on sending days."""
    weekdays = sending_weekdays() or [1, 2, 3, 4, 5]
    window_start = _parse_hhmm(campaign.send_window_start, settings.SEND_WINDOW_START)
    window_end = _parse_hhmm(campaign.send_window_end, settings.SEND_WINDOW_END)

    local = timezone.localtime(moment)
    for _ in range(14):
        if local.isoweekday() in weekdays:
            break
        local = local + timedelta(days=1)
    start_minutes = window_start.hour * 60 + window_start.minute
    end_minutes = window_end.hour * 60 + window_end.minute
    current = local.hour * 60 + local.minute
    if current < start_minutes:
        local = local + timedelta(minutes=start_minutes - current)
    elif current > end_minutes:
        local = local + timedelta(days=1)
        local = local.replace(hour=window_start.hour, minute=window_start.minute,
                              second=0, microsecond=0)
        for _ in range(14):
            if local.isoweekday() in weekdays:
                break
            local = local + timedelta(days=1)
    return local


def process_follow_ups(campaign: Campaign | None = None, *, limit: int = 500) -> dict:
    """Create follow-up messages that are due. Safe to run repeatedly."""
    from .models import EmailMessage

    queryset = CampaignLead.objects.filter(
        status__in=[
            CampaignLead.Status.SENT, CampaignLead.Status.FOLLOW_UP,
        ],
        next_follow_up_at__isnull=False,
        next_follow_up_at__lte=timezone.now(),
    ).select_related("campaign", "lead", "campaign__follow_up_sequence")
    if campaign is not None:
        queryset = queryset.filter(campaign=campaign)

    created = stopped = 0
    for campaign_lead in queryset[:limit]:
        reason = stop_condition_met(campaign_lead)
        if reason:
            campaign_lead.stop(reason)
            stopped += 1
            continue
        message = schedule_next_follow_up(campaign_lead)
        if message is not None:
            created += 1
    return {"created": created, "stopped": stopped}


def cancel_campaign_messages(campaign: Campaign, *, reason: str = "Campaign cancelled"
                             ) -> int:
    updated = EmailMessage.objects.filter(
        campaign=campaign,
        status__in=[EmailMessage.Status.QUEUED, EmailMessage.Status.PROCESSING],
    ).update(status=EmailMessage.Status.CANCELLED, cancelled_at=timezone.now())
    CampaignLead.objects.filter(
        campaign=campaign,
        status__in=[CampaignLead.Status.PENDING, CampaignLead.Status.SCHEDULED,
                    CampaignLead.Status.FOLLOW_UP],
    ).update(status=CampaignLead.Status.CANCELLED, stopped_reason=reason[:200],
             next_follow_up_at=None)
    return updated
