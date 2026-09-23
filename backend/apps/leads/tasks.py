"""Celery tasks for lead maintenance (queue: imports)."""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from celery import shared_task
from django.utils import timezone

from apps.core.models import log_audit

logger = logging.getLogger(__name__)


@shared_task(name="apps.leads.tasks.detect_duplicates_task")
def detect_duplicates_task(source_id: int | None = None, min_confidence: int = 55) -> dict:
    from apps.leads.dedupe import detect_duplicates
    from apps.leads.models import Lead

    queryset = Lead.objects.active()
    if source_id:
        queryset = queryset.filter(source_id=source_id)
    created = detect_duplicates(queryset, min_confidence=min_confidence)
    Lead.objects.filter(duplicate_candidates__isnull=False).filter(
        is_duplicate=False
    ).update(is_duplicate=True) if False else None
    return {"duplicate_candidates": created}


@shared_task(name="apps.leads.tasks.rescore_leads_task")
def rescore_leads_task(source_id: int | None = None, lead_ids: list[int] | None = None) -> dict:
    from apps.leads.models import Lead
    from apps.leads.scoring import rescore_queryset

    queryset = Lead.objects.active()
    if source_id:
        queryset = queryset.filter(source_id=source_id)
    if lead_ids:
        queryset = queryset.filter(id__in=lead_ids)
    updated = rescore_queryset(queryset)
    log_audit(action="LEAD_SCORED", entity_type="lead",
              entity_id=source_id or 0,
              description=f"Rescored {updated} leads")
    return {"rescored": updated}


@shared_task(name="apps.leads.tasks.mark_duplicates_flag")
def mark_duplicates_flag() -> dict:
    """Flag every lead that has an unresolved duplicate candidate."""
    from apps.leads.models import Lead, LeadDuplicate

    ids = set(
        LeadDuplicate.objects.filter(
            resolution=LeadDuplicate.Resolution.PENDING
        ).values_list("lead_id", flat=True)
    ) | set(
        LeadDuplicate.objects.filter(
            resolution=LeadDuplicate.Resolution.PENDING
        ).values_list("candidate_id", flat=True)
    )
    updated = Lead.objects.filter(id__in=list(ids)).update(is_duplicate=True)
    return {"flagged": updated}


# ---------------------------------------------------------------------------
# Missing-email enrichment (explicit, opt-in, never invents addresses)
# ---------------------------------------------------------------------------
MAILTO_RE = re.compile(r"mailto:([^\?\"'> ]+)", re.I)
CONTACT_PATHS = ("/contact", "/contact-us", "/contactus", "/about", "/about-us",
                 "/support", "/get-in-touch")
USER_AGENT = (
    "Mozilla/5.0 (compatible; LeadIntelBot/1.0; +https://example.com/bot) "
    "Python-httpx"
)


@shared_task(name="apps.leads.tasks.enrich_lead_task", bind=True,
             autoretry_for=(Exception,), retry_backoff=60, max_retries=1)
def enrich_lead_task(self, lead_id: int) -> dict:
    """Look for a *publicly listed* contact address on the business website.

    Rules:
      * never guess an address (no first.last@domain generation),
      * one polite request per page, short timeout, no parallel hammering,
      * only marks the lead FOUND when an address is literally published.
    """
    import httpx
    from bs4 import BeautifulSoup

    from apps.core.normalizers import normalize_email
    from apps.leads.models import EmailStatus, EnrichmentStatus, Lead, LeadStatus

    lead = Lead.objects.filter(pk=lead_id).first()
    if lead is None:
        return {"error": "lead not found"}
    if not lead.website_domain:
        lead.enrichment_status = EnrichmentStatus.SKIPPED
        lead.enrichment_note = "No website on record"
        lead.save(update_fields=["enrichment_status", "enrichment_note", "updated_at"])
        return {"status": "SKIPPED"}
    if lead.email_normalized:
        return {"status": "SKIPPED", "detail": "Lead already has an email"}

    lead.enrichment_status = EnrichmentStatus.PROCESSING
    lead.enrichment_checked_at = timezone.now()
    lead.save(update_fields=["enrichment_status", "enrichment_checked_at", "updated_at"])

    base_url = lead.website_normalized or f"https://{lead.website_domain}"
    candidates: list[str] = []
    pages_checked: list[str] = []

    try:
        with httpx.Client(timeout=12, follow_redirects=True,
                          headers={"User-Agent": USER_AGENT}) as client:
            urls = [base_url] + [urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
                                 for path in CONTACT_PATHS]
            for url in urls[:4]:
                try:
                    response = client.get(url)
                except Exception:
                    continue
                if response.status_code >= 400:
                    continue
                pages_checked.append(url)
                html = response.text[:600_000]
                candidates.extend(_extract_emails(html))
                soup = BeautifulSoup(html, "html.parser")
                for anchor in soup.select("a[href^='mailto:']")[:20]:
                    href = anchor.get("href", "")
                    match = MAILTO_RE.search(href)
                    if match:
                        candidates.append(match.group(1))
                if candidates:
                    break
    except Exception as exc:  # pragma: no cover
        lead.enrichment_status = EnrichmentStatus.FAILED
        lead.enrichment_note = str(exc)[:250]
        lead.enrichment_checked_at = timezone.now()
        lead.save(update_fields=["enrichment_status", "enrichment_note",
                                 "enrichment_checked_at", "updated_at"])
        return {"status": "FAILED", "detail": str(exc)}

    found: list[str] = []
    for candidate in candidates:
        result = normalize_email(candidate)
        if result.is_valid and not result.is_disposable:
            found.append(result.normalized)

    unique = sorted(set(found))
    lead.enrichment_data = {
        "pages_checked": pages_checked,
        "candidates": unique,
        "checked_at": timezone.now().isoformat(),
    }
    lead.enrichment_checked_at = timezone.now()

    if unique:
        best = unique[0]
        lead.enrichment_status = EnrichmentStatus.FOUND
        lead.enrichment_note = f"Publicly listed address found on {pages_checked[0] if pages_checked else lead.website_domain}"
        lead.email = best
        lead.email_normalized = best
        lead.email_status = EmailStatus.VALID
        lead.email_domain = best.split("@")[-1]
        if lead.lead_status == LeadStatus.MISSING_EMAIL:
            lead.lead_status = LeadStatus.VALID
        lead.log_activity(
            type="ENRICHMENT",
            title="Email found on business website",
            description=f"{best} (publicly listed)",
            metadata={"pages": pages_checked},
        )
    else:
        lead.enrichment_status = EnrichmentStatus.NOT_FOUND
        lead.enrichment_note = "No publicly listed email address found"
        lead.log_activity(
            type="ENRICHMENT", title="Enrichment: no public email found",
            description=f"Checked {len(pages_checked)} page(s)",
        )

    lead.save(update_fields=[
        "enrichment_status", "enrichment_note", "enrichment_data",
        "enrichment_checked_at", "email", "email_normalized", "email_status",
        "email_domain", "lead_status", "updated_at",
    ])
    log_audit(action="LEAD_ENRICHED", entity_type="lead", entity_id=lead.pk,
              description=f"Enrichment {lead.enrichment_status}",
              metadata={"found": unique[:3]})
    return {"status": lead.enrichment_status, "found": unique, "pages": pages_checked}


def _extract_emails(html: str) -> list[str]:
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = text.replace(" [at] ", "@").replace(" (at) ", "@").replace(" [dot] ", ".")
    return re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", text)[:20]


@shared_task(name="apps.leads.tasks.bulk_enrich_task")
def bulk_enrich_task(lead_ids: list[int] | None = None, *, source_id: int | None = None,
                     limit: int = 200) -> dict:
    """Queue enrichment for leads without an email (explicitly triggered)."""
    from apps.leads.models import EnrichmentStatus, Lead

    queryset = Lead.objects.filter(
        email_normalized="",
        enrichment_status__in=[EnrichmentStatus.NOT_PROCESSED, EnrichmentStatus.FAILED],
    ).exclude(website_domain="")
    if lead_ids:
        queryset = queryset.filter(id__in=lead_ids)
    if source_id:
        queryset = queryset.filter(source_id=source_id)

    queued = 0
    for lead_id in queryset.values_list("id", flat=True)[:limit]:
        enrich_lead_task.delay(lead_id)
        queued += 1
    return {"queued": queued}
