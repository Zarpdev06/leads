"""AI tasks (queue: ai)."""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="apps.ai_engine.tasks.generate_lead_recommendation",
             bind=True, autoretry_for=(Exception,), retry_backoff=30, max_retries=1)
def generate_lead_recommendation(self, lead_id: int, campaign_id: int | None = None,
                                 user_id: int | None = None) -> dict:
    from apps.accounts.models import User
    from apps.campaigns.models import Campaign
    from apps.leads.models import Lead

    lead = Lead.objects.filter(pk=lead_id).first()
    if lead is None:
        return {"error": "lead not found"}
    campaign = Campaign.objects.filter(pk=campaign_id).first() if campaign_id else None
    user = User.objects.filter(pk=user_id).first() if user_id else None

    from .generator import generate_email_for_lead

    result = generate_email_for_lead(lead, campaign=campaign, actor=user, use_cache=False)
    lead.log_activity(
        type="AI_GENERATED",
        title="AI personalization generated",
        description=f"{result.provider} · {result.subject[:80]}",
        actor=user,
        metadata={"provider": result.provider, "model": result.model},
    )
    return {
        "lead_id": lead.pk,
        "subject": result.subject,
        "provider": result.provider,
        "service": result.recommended_service,
    }


@shared_task(name="apps.ai_engine.tasks.generate_campaign_copy")
def generate_campaign_copy(campaign_id: int, *, limit: int = 200, user_id: int | None = None
                           ) -> dict:
    """Pre-generate AI copy for a campaign's queued leads."""
    from apps.campaigns.models import CampaignLead

    queued = 0
    for campaign_lead_id in CampaignLead.objects.filter(
        campaign_id=campaign_id,
        status__in=[CampaignLead.Status.PENDING, CampaignLead.Status.SCHEDULED],
    ).values_list("id", flat=True)[:limit]:
        campaign_lead = CampaignLead.objects.filter(pk=campaign_lead_id).first()
        if campaign_lead is None:
            continue
        generate_lead_recommendation.delay(campaign_lead.lead_id, campaign_id, user_id)
        queued += 1
    return {"queued": queued}


@shared_task(name="apps.ai_engine.tasks.test_provider")
def test_provider(provider_key: str) -> dict:
    from .providers.registry import get_provider

    provider = get_provider(provider_key)
    ok, message = provider.test_connection()
    return {"provider": provider_key, "ok": ok, "message": message}
