"""
Email eligibility.

A lead may enter an outreach campaign only if ALL of the following hold:

    1. email exists and is syntactically valid
    2. not on the global suppression list
    3. has not unsubscribed
    4. has not permanently bounced
    5. lead is not blocked / marked do-not-contact
    6. contact-frequency rules are respected
    7. campaign criteria match (industry, location, score, sources, ...)
    8. daily sending capacity exists   <- checked at send time by the quota

Rules 1-6 are enforced here; rule 7 is applied both here and as a database
filter (`eligible_queryset`) so large audiences stay server-side; rule 8 is
enforced by `email_engine.quota.DailyEmailQuota`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.suppression.services import is_suppressed

from .models import EmailStatus, Lead, LeadStatus

if TYPE_CHECKING:  # pragma: no cover
    from apps.campaigns.models import Campaign


@dataclass
class EligibilityResult:
    eligible: bool
    reasons: list[str] = field(default_factory=list)
    code: str | None = None

    def __bool__(self) -> bool:
        return self.eligible


def evaluate_lead_eligibility(lead: Lead, campaign: "Campaign | None" = None,
                              *, now=None) -> EligibilityResult:
    """Full rule evaluation for one lead. Used by campaigns and manual sends."""
    from apps.settings.services import max_contacts_per_lead, min_days_between_contacts

    now = now or timezone.now()
    reasons: list[str] = []

    def fail(reason: str, code: str) -> EligibilityResult:
        reasons.append(reason)
        return EligibilityResult(False, reasons, code)

    # -- 0. Structural -----------------------------------------------------
    if lead.merged_into_id:
        return fail("Record was merged into another lead", "merged")
    if lead.lead_status == LeadStatus.ARCHIVED:
        return fail("Record archived", "archived")

    # -- 1. Email ----------------------------------------------------------
    if not lead.email_normalized:
        return fail("No email address", "no_email")
    if lead.email_status != EmailStatus.VALID:
        return fail(f"Email status: {lead.get_email_status_display()}", "email_invalid")

    # -- 2. Suppression ----------------------------------------------------
    if is_suppressed(lead.email_normalized):
        return fail("Address is on the suppression list", "suppressed")

    # -- 3. Unsubscribed ---------------------------------------------------
    if lead.unsubscribed_at or lead.lead_status == LeadStatus.UNSUBSCRIBED:
        return fail("Contact unsubscribed", "unsubscribed")

    # -- 4. Bounce ---------------------------------------------------------
    if lead.bounced_at or lead.email_status == EmailStatus.BOUNCED:
        return fail("Previous message bounced", "bounced")

    # -- 5. Blocking flags --------------------------------------------------
    if lead.do_not_contact or lead.lead_status == LeadStatus.DO_NOT_CONTACT:
        return fail("Marked do-not-contact", "do_not_contact")
    if lead.is_blocked:
        return fail(f"Blocked ({lead.blocked_reason or 'no reason'})", "blocked")

    # -- 6. Contact frequency ----------------------------------------------
    if lead.last_contacted_at:
        min_days = min_days_between_contacts()
        elapsed = (now - lead.last_contacted_at).days
        if elapsed < min_days:
            return fail(
                f"Contacted {elapsed} day(s) ago (minimum {min_days})", "contacted_recently"
            )
    if max_contacts_per_lead() and lead.times_contacted >= max_contacts_per_lead():
        return fail(
            f"Already contacted {lead.times_contacted} times (max {max_contacts_per_lead()})",
            "max_contacts",
        )

    # -- 7. Campaign criteria ----------------------------------------------
    if campaign is not None:
        reasons.extend(_campaign_mismatches(lead, campaign))
        if reasons:
            return EligibilityResult(False, reasons, "campaign_criteria")
        if campaign.min_lead_score and lead.lead_score < campaign.min_lead_score:
            return fail(f"Score {lead.lead_score} < {campaign.min_lead_score}", "score")

    return EligibilityResult(True, reasons)


def _campaign_mismatches(lead: Lead, campaign) -> list[str]:
    problems: list[str] = []
    if campaign.target_industries.exists() and (
        not lead.industry_id or not campaign.target_industries.filter(id=lead.industry_id).exists()
    ):
        if not (lead.sub_industry_id and campaign.target_industries.filter(
                id=lead.sub_industry_id).exists()):
            problems.append("Industry not targeted")
    if campaign.target_sub_industries.exists() and (
        not lead.sub_industry_id
        or not campaign.target_sub_industries.filter(id=lead.sub_industry_id).exists()
    ):
        problems.append("Sub-industry not targeted")
    states = campaign.target_states or []
    if states and not state_matches(lead.state, states):
        problems.append("State not targeted")
    cities = campaign.target_cities or []
    if cities and lead.city not in cities:
        problems.append("City not targeted")
    if campaign.sources.exists() and (
        not lead.source_id or not campaign.sources.filter(id=lead.source_id).exists()
    ):
        problems.append("Source not selected")
    if campaign.require_website and not lead.website_domain:
        problems.append("No website")
    if campaign.require_phone and not lead.phone_normalized:
        problems.append("No phone")
    if campaign.require_contact_person and not (lead.contact_name or lead.first_name):
        problems.append("No contact person")
    if campaign.min_lead_score and lead.lead_score < campaign.min_lead_score:
        problems.append(f"Score below {campaign.min_lead_score}")
    if campaign.max_lead_score and lead.lead_score > campaign.max_lead_score:
        problems.append(f"Score above {campaign.max_lead_score}")
    if campaign.exclude_replied and lead.replied_at:
        problems.append("Already replied")
    if campaign.exclude_ever_contacted and lead.times_contacted:
        problems.append("Already contacted")
    return problems


def eligible_queryset(campaign=None, base: QuerySet[Lead] | None = None) -> QuerySet[Lead]:
    """Database-level version of rules 0-7 (everything except the daily quota).

    Suppression is applied as a subquery so it costs one SQL statement even for
    millions of rows.
    """
    from apps.suppression.models import Suppression
    from apps.settings.services import max_contacts_per_lead, min_days_between_contacts

    qs = (base if base is not None else Lead.objects.all()).filter(
        merged_into__isnull=True,
        do_not_contact=False,
        is_blocked=False,
        email_status=EmailStatus.VALID,
        unsubscribed_at__isnull=True,
        bounced_at__isnull=True,
    ).exclude(email_normalized="").exclude(lead_status=LeadStatus.ARCHIVED)

    now = timezone.now()
    min_days = min_days_between_contacts()
    if min_days:
        cutoff = now - timezone.timedelta(days=min_days)
        qs = qs.filter(Q(last_contacted_at__isnull=True) | Q(last_contacted_at__lte=cutoff))
    max_contacts = max_contacts_per_lead()
    if max_contacts:
        qs = qs.filter(times_contacted__lt=max_contacts)

    # Suppression: exclude active (non-expired) entries.
    suppressed = Suppression.objects.filter(is_active=True).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    ).values("email_normalized")
    qs = qs.exclude(email_normalized__in=suppressed)

    if campaign is not None:
        qs = apply_campaign_filters(qs, campaign)
    return qs


def apply_campaign_filters(qs: QuerySet[Lead], campaign) -> QuerySet[Lead]:
    if campaign.target_industries.exists():
        industry_ids = list(campaign.target_industries.values_list("id", flat=True))
        qs = qs.filter(Q(industry_id__in=industry_ids) | Q(sub_industry_id__in=industry_ids))
    if campaign.target_sub_industries.exists():
        qs = qs.filter(
            sub_industry_id__in=list(campaign.target_sub_industries.values_list("id", flat=True))
        )
    if campaign.target_states:
        qs = qs.filter(state__in=sorted(state_target_values(campaign.target_states)))
    if campaign.target_cities:
        qs = qs.filter(city__in=list(campaign.target_cities))
    if campaign.sources.exists():
        qs = qs.filter(source_id__in=list(campaign.sources.values_list("id", flat=True)))
    if campaign.require_website:
        qs = qs.exclude(website_domain="")
    if campaign.require_phone:
        qs = qs.exclude(phone_normalized="")
    if campaign.require_contact_person:
        qs = qs.exclude(contact_name="", first_name="")
    if campaign.min_lead_score:
        qs = qs.filter(lead_score__gte=campaign.min_lead_score)
    if campaign.max_lead_score:
        qs = qs.filter(lead_score__lte=campaign.max_lead_score)
    if campaign.exclude_replied:
        qs = qs.filter(replied_at__isnull=True)
    if campaign.exclude_ever_contacted:
        qs = qs.filter(times_contacted=0)
    return qs


def state_target_values(targets: Iterable[str]) -> set[str]:
    """Every literal a lead's ``state`` may hold to satisfy ``targets``.

    Leads store normalised USPS codes ("TX") while a user targets campaigns by
    whatever they type ("Texas", "texas", "TX"). This is the single source of
    truth used by BOTH the SQL filter (`apply_campaign_filters`) and the
    per-lead check (`_campaign_mismatches`).

    Keeping it in one place matters: when the two implementations disagreed,
    a campaign targeting "Texas" selected a full audience at dispatch time and
    then rejected every single lead at send time with "State not targeted" —
    the campaign reported RUNNING but silently delivered nothing.
    """
    from apps.core.utils import US_STATE_NAMES, normalize_state

    code_to_names: dict[str, list[str]] = {}
    for name, code in US_STATE_NAMES.items():
        code_to_names.setdefault(code, []).append(name.title())

    values: set[str] = set()
    for raw in targets or []:
        text = str(raw or "").strip()
        if not text:
            continue
        values.add(text)
        code = normalize_state(text)
        if code:
            values.add(code)
            values.update(code_to_names.get(code, ()))
    return values


def state_matches(lead_state: str | None, targets: Iterable[str]) -> bool:
    """Case-insensitive counterpart of `state_target_values` for single leads."""
    if not targets:
        return True
    wanted = {value.lower() for value in state_target_values(targets)}
    return str(lead_state or "").strip().lower() in wanted


def summarize(leads: Iterable[Lead], campaign=None) -> dict:
    """Counts used by the campaign wizard ("Total eligible: 1,284")."""
    total = eligible = 0
    reasons: dict[str, int] = {}
    for lead in leads:
        total += 1
        result = evaluate_lead_eligibility(lead, campaign)
        if result.eligible:
            eligible += 1
        for reason in result.reasons:
            reasons[reason] = reasons.get(reason, 0) + 1
    return {"total": total, "eligible": eligible, "reasons": reasons}
