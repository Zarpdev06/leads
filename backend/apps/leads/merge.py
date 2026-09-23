"""
Lead merging.

Merging *never* loses data: the absorbed record is kept (flagged
`merged_into`) with its own source provenance, and the survivor receives the
most complete value for every field. Every related object (emails, campaigns,
CRM activity, notes) is re-pointed to the survivor.
"""
from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.models import log_audit

from .models import EmailStatus, Lead, LeadDuplicate, LeadStatus


#: How each field is merged when both records disagree.
FIELD_POLICY: dict[str, str] = {
    "longest": {"company_name", "contact_name", "first_name", "last_name",
                "job_title", "street_address", "website", "phone"},
    "prefer_valid_email": {"email", "email_normalized", "email_status", "email_domain"},
    "first_truthy": {"city", "state", "zip_code", "country", "website_normalized",
                     "website_domain", "phone_normalized", "phone_type",
                     "industry", "sub_industry", "employee_count", "employee_range",
                     "company", "contact", "source_city", "source_category"},
}

BOOL_FIELDS = {"email_is_role", "email_is_free_provider", "website_accessible"}


def _merge_value(field: str, survivor_value: Any, absorbed_value: Any) -> Any:
    if field in FIELD_POLICY["longest"]:
        if survivor_value and absorbed_value:
            return survivor_value if len(str(survivor_value)) >= len(str(absorbed_value)) else absorbed_value
        return survivor_value or absorbed_value
    if field in FIELD_POLICY["prefer_valid_email"]:
        if survivor_value == "VALID" or absorbed_value == "VALID":
            pass
        # handled by caller (email is merged as a block)
        return survivor_value or absorbed_value
    return survivor_value if survivor_value not in (None, "", 0) else absorbed_value


@transaction.atomic
def merge_leads(survivor: Lead, absorbed: Lead, *, actor=None,
                keep_both: bool = False) -> dict:
    """Merge `absorbed` into `survivor`. Returns a summary dict."""
    if survivor.pk == absorbed.pk:
        raise ValueError("Cannot merge a lead into itself.")

    absorbed.refresh_from_db()
    survivor.refresh_from_db()

    summary: dict[str, Any] = {
        "survivor_id": survivor.pk,
        "absorbed_id": absorbed.pk,
        "fields_updated": [],
        "related_moved": {},
    }

    # 1. Email block: prefer a valid, non-role address ----------------------
    if _email_rank(absorbed) > _email_rank(survivor):
        for field in ("email", "email_normalized", "email_status", "email_domain",
                      "email_is_role", "email_is_free_provider"):
            setattr(survivor, field, getattr(absorbed, field))
        summary["fields_updated"].append("email")

    # 2. Everything else ----------------------------------------------------
    for field in FIELD_POLICY["first_truthy"] | FIELD_POLICY["longest"]:
        if field in {"email", "email_normalized", "email_status", "email_domain"}:
            continue
        current = getattr(survivor, field, None)
        incoming = getattr(absorbed, field, None)
        if field in BOOL_FIELDS:
            if current in (None, False) and incoming:
                setattr(survivor, field, incoming)
                summary["fields_updated"].append(field)
            continue
        merged = _merge_value(field, current, incoming)
        if merged != current and merged not in (None, ""):
            setattr(survivor, field, merged)
            summary["fields_updated"].append(field)

    for field in BOOL_FIELDS:
        if getattr(absorbed, field) and not getattr(survivor, field):
            setattr(survivor, field, True)

    # 3. Provenance: remember every source this lead came from --------------
    provenance = list(survivor.raw_data.get("sources", []) or [])
    for record in (survivor, absorbed):
        entry = {
            "source": record.source_name or (record.source.name if record.source_id else ""),
            "source_id": record.source_id,
            "file": record.source_file.original_name if record.source_file_id else "",
            "file_id": record.source_file_id,
            "row": record.source_row_number,
            "imported_at": record.created_at.isoformat() if record.created_at else None,
        }
        if entry not in provenance:
            provenance.append(entry)
    survivor.raw_data = {**survivor.raw_data, **absorbed.raw_data, "sources": provenance}
    absorbed.raw_data = {**absorbed.raw_data, "sources": provenance}

    # 4. Tags union ----------------------------------------------------------
    survivor.tags = sorted(set(list(survivor.tags or []) + list(absorbed.tags or [])))

    survivor.is_duplicate = False
    survivor.save()

    # 5. Re-point related objects -------------------------------------------
    from apps.campaigns.models import CampaignLead
    from apps.crm.models import CRMActivity, LeadNote
    from apps.email_engine.models import EmailMessage

    for model, fk_field in (
        (EmailMessage, "lead"),
        (CampaignLead, "lead"),
        (CRMActivity, "lead"),
        (LeadNote, "lead"),
    ):
        moved = model.objects.filter(**{fk_field: absorbed}).exclude(
            pk__in=[]  # no-op, keeps the queryset chain readable
        )
        if model is CampaignLead:
            # A lead can only be in a campaign once; skip collisions.
            existing = set(
                CampaignLead.objects.filter(lead=survivor).values_list("campaign_id", flat=True)
            )
            moved = moved.exclude(campaign_id__in=existing)
        count = moved.update(**{fk_field: survivor})
        summary["related_moved"][model.__name__] = count

    # 6. Flag the absorbed record -------------------------------------------
    if keep_both:
        absorbed.is_duplicate = True
        absorbed.duplicate_of = survivor
        absorbed.save(update_fields=["is_duplicate", "duplicate_of", "updated_at"])
        resolution = LeadDuplicate.Resolution.KEPT_BOTH
    else:
        absorbed.merged_into = survivor
        absorbed.is_duplicate = True
        absorbed.duplicate_of = survivor
        absorbed.lead_status = LeadStatus.ARCHIVED
        absorbed.next_follow_up_at = None
        absorbed.save(update_fields=[
            "merged_into", "is_duplicate", "duplicate_of", "lead_status",
            "next_follow_up_at", "updated_at",
        ])
        resolution = LeadDuplicate.Resolution.MERGED

    LeadDuplicate.objects.filter(
        lead__in=[survivor, absorbed]
    ).exclude(resolution=LeadDuplicate.Resolution.IGNORED).update(
        resolution=resolution, reviewed_by=actor, reviewed_at=timezone.now()
    )
    LeadDuplicate.objects.filter(candidate__in=[survivor, absorbed]).exclude(
        resolution=LeadDuplicate.Resolution.IGNORED
    ).update(resolution=resolution, reviewed_by=actor, reviewed_at=timezone.now())

    survivor.log_activity(
        type="MERGE",
        title=f"Merged duplicate: {absorbed.company_name or absorbed.email}",
        description=f"Absorbed lead #{absorbed.pk} ({resolution})",
        actor=actor,
        metadata={"absorbed_id": absorbed.pk, "resolution": resolution,
                  "fields": summary["fields_updated"], "related": summary["related_moved"]},
    )
    log_audit(
        action="LEAD_MERGED",
        actor=actor,
        entity_type="lead",
        entity_id=survivor.pk,
        obj=survivor,
        description=f"Lead #{absorbed.pk} merged into #{survivor.pk}",
        metadata=summary,
    )
    from .scoring import apply_score

    apply_score(survivor)
    return summary


def _email_rank(lead: Lead) -> int:
    """Rank an email so the merge always keeps the most valuable address."""
    if not lead.email_normalized:
        return 0
    rank = 1
    if lead.email_status == EmailStatus.VALID:
        rank += 4
    if not lead.email_is_role:
        rank += 2
    if not lead.email_is_free_provider:
        rank += 1
    return rank


def resolve_duplicate(duplicate: LeadDuplicate, resolution: str, *, actor=None) -> dict:
    """Apply a review decision from the Duplicate Review screen."""
    duplicate.refresh_from_db()
    if resolution == LeadDuplicate.Resolution.MERGED:
        # Keep the richer record as the survivor.
        survivor, absorbed = _pick_survivor(duplicate.lead, duplicate.candidate)
        return merge_leads(survivor, absorbed, actor=actor)
    if resolution == LeadDuplicate.Resolution.KEPT_BOTH:
        survivor, absorbed = _pick_survivor(duplicate.lead, duplicate.candidate)
        return merge_leads(survivor, absorbed, actor=actor, keep_both=True)

    duplicate.resolution = resolution
    duplicate.reviewed_by = actor
    duplicate.reviewed_at = timezone.now()
    duplicate.save(update_fields=["resolution", "reviewed_by", "reviewed_at", "updated_at"])
    if resolution == LeadDuplicate.Resolution.IGNORED:
        duplicate.lead.is_duplicate = False
        duplicate.lead.save(update_fields=["is_duplicate", "updated_at"])
    return {"resolution": resolution, "duplicate_id": duplicate.pk}


def _pick_survivor(a: Lead, b: Lead) -> tuple[Lead, Lead]:
    def richness(lead: Lead) -> int:
        score = 0
        score += 5 if lead.email_normalized else 0
        score += 4 if lead.email_status == EmailStatus.VALID else 0
        score += 3 if lead.phone_normalized else 0
        score += 3 if lead.website_domain else 0
        score += 2 if lead.contact_name else 0
        score += 2 if lead.industry_id else 0
        score += 1 if lead.city else 0
        score += 1 if lead.street_address else 0
        score += min(lead.lead_score, 100) / 100
        return score

    return (a, b) if richness(a) >= richness(b) else (b, a)
