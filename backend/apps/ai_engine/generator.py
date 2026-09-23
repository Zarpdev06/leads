"""
AI personalization entrypoint.

`generate_email_for_lead` is the only function the email engine calls. It:
  1. builds a facts-only context from the lead,
  2. asks the configured provider for copy,
  3. validates the output with the safety validator,
  4. falls back to the rule-based provider when the output is unsafe/unavailable,
  5. caches the result as an `AIRecommendation` row (idempotent for retries).
"""
from __future__ import annotations

import logging

from django.conf import settings

from apps.campaigns.models import Service
from apps.settings.services import get_setting

from .models import AIRecommendation
from .providers.base import AIEmailContext, AIEmailResult
from .providers.registry import get_provider
from .providers.rules import RuleBasedProvider
from .safety import AISafetyValidator

logger = logging.getLogger(__name__)


def build_context(lead, *, campaign=None, template=None) -> AIEmailContext:
    industry = ""
    sub_industry = ""
    if lead.sub_industry_id:
        sub_industry = lead.sub_industry.name
        industry = lead.sub_industry.parent.name if lead.sub_industry.parent_id else sub_industry
    elif lead.industry_id:
        industry = lead.industry.name

    service_name = ""
    if campaign is not None and campaign.recommended_service_id:
        service_name = campaign.recommended_service.name
    elif lead.recommended_service_id:
        service_name = lead.recommended_service.name
    else:
        from .service_matching import recommend_service

        service_name = recommend_service(lead).service_name

    available_information = {
        key: value for key, value in {
            "phone": lead.phone,
            "street_address": lead.street_address,
            "zip_code": lead.zip_code,
            "country": lead.country,
            "employee_count": lead.employee_count,
            "job_title": lead.job_title,
        }.items() if value
    }

    return AIEmailContext(
        business_name=lead.company_name,
        industry=industry,
        sub_industry=sub_industry,
        city=lead.city,
        state=lead.state,
        country=lead.country,
        website=lead.website_domain,
        contact_name=lead.contact_name,
        first_name=lead.first_name,
        job_title=lead.job_title,
        employee_count=str(lead.employee_count or ""),
        available_information=available_information,
        selected_service=service_name,
        template={
            "subject": template.subject if template else "",
            "body_html": template.body_html if template else "",
        },
        extra_instructions=(campaign.ai_instructions if campaign else ""),
        brand_voice=get_setting("ai.brand_voice", "professional, concise, helpful"),
        sender_company=get_setting("compliance.legal_name", settings.COMPANY_LEGAL_NAME),
        sender_name=get_setting("email.from_name", ""),
    )


def generate_email_for_lead(lead, *, template=None, campaign=None, context: dict | None = None,
                            instructions: str = "", actor=None,
                            use_cache: bool = True) -> AIEmailResult:
    """Generate personalised copy for one lead (safe to call repeatedly)."""
    ai_context = build_context(lead, campaign=campaign, template=template)
    if instructions:
        ai_context.extra_instructions = instructions
    context_hash = AIRecommendation.hash_context(ai_context.as_dict())

    provider = get_provider()
    strict = bool(get_setting("ai.safety_strict", True))
    validator = AISafetyValidator(strict=strict)

    if use_cache:
        cached = AIRecommendation.objects.filter(
            lead=lead, provider=provider.key, context_hash=context_hash,
            status=AIRecommendation.Status.GENERATED,
        ).order_by("-created_at").first()
        if cached:
            return _result_from_row(cached)

    result: AIEmailResult
    safety_notes: list[str] = []
    try:
        result = provider.generate_email(ai_context)
        report = validator.validate(
            f"{result.subject} {result.body_html} {result.opening_sentence} "
            f"{result.personalization} {result.value_proposition} {result.cta}",
            ai_context.facts(),
        )
        safety_notes = report.issues
        if not report.passed:
            logger.warning(
                "AI output rejected for lead %s (%s): %s", lead.pk, provider.key, report.issues
            )
            fallback_context = ai_context
            fallback_context.extra_instructions = (
                f"{instructions}\nAvoid: {', '.join(report.issues[:5])}"
            )
            result = RuleBasedProvider(provider.config).generate_email(fallback_context)
            result.provider = f"{provider.key}+rules-fallback"
            result.raw = {"safety_issues": report.issues}
    except Exception as exc:
        logger.warning("Provider %s failed for lead %s: %s", provider.key, lead.pk, exc)
        result = RuleBasedProvider(provider.config).generate_email(ai_context)
        result.provider = "rules-fallback"
        safety_notes = [f"Provider error: {exc}"]

    service = Service.objects.filter(name__iexact=result.recommended_service).first()
    AIRecommendation.objects.create(
        lead=lead,
        campaign=campaign,
        service=service,
        provider=provider.key,
        model=result.model,
        subject=result.subject,
        opening_sentence=result.opening_sentence,
        personalization=result.personalization,
        value_proposition=result.value_proposition,
        cta=result.cta,
        body_html=result.body_html,
        body_text=result.body_text,
        recommended_service=result.recommended_service,
        confidence=0.7,
        prompt=result.prompt,
        raw_response=result.raw,
        context=ai_context.as_dict(),
        context_hash=context_hash,
        status=AIRecommendation.Status.GENERATED,
        safety_passed=not safety_notes,
        safety_notes=safety_notes,
        tokens_used=result.tokens_used,
        created_by=actor,
    )
    if service and not lead.recommended_service_id:
        lead.recommended_service = service
        lead.ai_recommendation = {
            "service": service.name,
            "rationale": result.value_proposition,
            "provider": result.provider,
        }
        lead.save(update_fields=["recommended_service", "ai_recommendation", "updated_at"])
    return result


def _result_from_row(row: AIRecommendation) -> AIEmailResult:
    return AIEmailResult(
        subject=row.subject,
        opening_sentence=row.opening_sentence,
        personalization=row.personalization,
        value_proposition=row.value_proposition,
        cta=row.cta,
        body_html=row.body_html,
        body_text=row.body_text,
        recommended_service=row.recommended_service,
        provider=row.provider,
        model=row.model,
        prompt=row.prompt,
        raw=row.raw_response,
        tokens_used=row.tokens_used,
    )
