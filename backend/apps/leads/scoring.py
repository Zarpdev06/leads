"""
Configurable lead scoring engine.

Signals and thresholds live in `SystemSetting` (Settings → Lead scoring) and
fall back to the defaults below. Scoring is deterministic and offline: it never
calls an AI provider and never invents data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone

from .models import EmailStatus, Lead, LeadQuality, LeadStatus

DEFAULT_RULES: dict[str, int] = {
    # Positive signals
    "valid_email": 20,
    "website_exists": 15,
    "contact_person": 10,
    "company_name": 10,
    "phone": 10,
    "category_known": 10,
    "location_known": 10,
    "website_accessible": 15,
    "job_title": 5,
    "employee_count_known": 5,
    "street_address": 5,
    # Negative signals
    "invalid_email": -30,
    "unsubscribed": -50,
    "bounced": -100,
    "contacted_too_recently": -100,
    "role_email": -5,
    "free_email_provider": -5,
    "disposable_email": -25,
    "suppressed": -100,
    "no_email": -20,
    "no_website": -5,
}

DEFAULT_THRESHOLDS: dict[str, int] = {"hot": 75, "warm": 50, "cold": 25}

SETTING_KEY_RULES = "scoring.rules"
SETTING_KEY_THRESHOLDS = "scoring.thresholds"
SETTING_KEY_RECENT_DAYS = "scoring.contacted_recently_days"


def get_rules() -> dict[str, int]:
    from apps.settings.services import get_setting

    return {**DEFAULT_RULES, **(get_setting(SETTING_KEY_RULES, {}) or {})}


def get_thresholds() -> dict[str, int]:
    from apps.settings.services import get_setting

    return {**DEFAULT_THRESHOLDS, **(get_setting(SETTING_KEY_THRESHOLDS, {}) or {})}


def get_recent_contact_days() -> int:
    from apps.settings.services import get_setting

    return int(get_setting(SETTING_KEY_RECENT_DAYS, 30) or 30)


@dataclass
class ScoreResult:
    score: int
    quality: str
    breakdown: dict[str, int] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "quality": self.quality,
            "breakdown": self.breakdown,
            "reasons": self.reasons,
        }


def quality_for(score: int, thresholds: dict[str, int] | None = None) -> str:
    t = thresholds or get_thresholds()
    if score >= int(t.get("hot", 75)):
        return LeadQuality.HOT
    if score >= int(t.get("warm", 50)):
        return LeadQuality.WARM
    if score >= int(t.get("cold", 25)):
        return LeadQuality.COLD
    return LeadQuality.UNQUALIFIED


def score_lead(lead: Lead, *, rules: dict[str, int] | None = None,
               thresholds: dict[str, int] | None = None) -> ScoreResult:
    """Compute the score for a lead without mutating it."""
    rules = rules or get_rules()
    breakdown: dict[str, int] = {}
    reasons: list[str] = []

    def add(signal: str, condition: bool, detail: str = "") -> None:
        value = int(rules.get(signal, 0))
        if value and condition:
            breakdown[signal] = value
            if detail:
                reasons.append(detail)

    # ---- Email ------------------------------------------------------------
    if lead.email_status == EmailStatus.VALID and lead.email_normalized:
        add("valid_email", True, "Valid business email")
    elif lead.email_status in {EmailStatus.INVALID, EmailStatus.RISKY}:
        add("invalid_email", True, "Invalid email syntax")
    elif not lead.email_normalized:
        add("no_email", True, "No email address")
    if lead.email_is_role:
        add("role_email", True, "Role/shared mailbox")
    if lead.email_is_free_provider:
        add("free_email_provider", True, "Free email provider")
    if lead.email_status in {EmailStatus.BOUNCED, EmailStatus.SUPPRESSED,
                             EmailStatus.UNSUBSCRIBED}:
        add("bounced" if lead.email_status == EmailStatus.BOUNCED else "unsubscribed",
            True, f"Email status: {lead.get_email_status_display()}")

    # ---- Company / contact -------------------------------------------------
    add("company_name", bool(lead.company_name_key), "Company name present")
    add("contact_person", bool(lead.contact_name or lead.first_name or lead.last_name),
        "Contact person present")
    add("job_title", bool(lead.job_title), "Job title known")
    add("phone", bool(lead.phone_normalized), "Phone number present")
    add("category_known", bool(lead.industry_id or lead.sub_industry_id), "Industry known")
    add("location_known", bool(lead.city or lead.state), "Location known")
    add("street_address", bool(lead.street_address), "Street address present")
    add("employee_count_known", bool(lead.employee_count), "Employee count known")

    # ---- Website -----------------------------------------------------------
    add("website_exists", bool(lead.website_domain), "Website present")
    add("website_accessible", lead.website_accessible is True, "Website reachable")
    add("no_website", not lead.website_domain, "No website")

    # ---- Suppression / throttling -----------------------------------------
    if lead.unsubscribed_at:
        add("unsubscribed", True, "Contact unsubscribed")
    if lead.do_not_contact or lead.lead_status == LeadStatus.DO_NOT_CONTACT:
        add("suppressed", True, "Do not contact")
    if lead.times_contacted and lead.last_contacted_at:
        recent_days = get_recent_contact_days()
        elapsed = (timezone.now() - lead.last_contacted_at).days
        if elapsed < recent_days:
            add("contacted_too_recently", True, f"Contacted {elapsed}d ago (< {recent_days}d)")

    raw = sum(breakdown.values())
    score = max(0, min(100, raw))
    return ScoreResult(score=score, quality=quality_for(score, thresholds),
                       breakdown=breakdown, reasons=reasons)


LeadStatus_DNC = LeadStatus.DO_NOT_CONTACT


def apply_score(lead: Lead, *, save: bool = True, rules=None, thresholds=None) -> ScoreResult:
    result = score_lead(lead, rules=rules, thresholds=thresholds)
    lead.lead_score = result.score
    lead.lead_quality = result.quality
    if save:
        lead.save(update_fields=["lead_score", "lead_quality", "updated_at"])
    return result


def rescore_queryset(queryset: QuerySet[Lead], *, batch_size: int = 1000) -> int:
    """Recompute scores in bulk (used by the Celery task and after rule edits)."""
    rules, thresholds = get_rules(), get_thresholds()
    updated: list[Lead] = []
    count = 0
    for lead in queryset.iterator(chunk_size=batch_size):
        result = score_lead(lead, rules=rules, thresholds=thresholds)
        if lead.lead_score != result.score or lead.lead_quality != result.quality:
            lead.lead_score = result.score
            lead.lead_quality = result.quality
            updated.append(lead)
        if len(updated) >= batch_size:
            Lead.objects.bulk_update(updated, ["lead_score", "lead_quality", "updated_at"])
            count += len(updated)
            updated = []
    if updated:
        Lead.objects.bulk_update(updated, ["lead_score", "lead_quality", "updated_at"])
        count += len(updated)
    return count
