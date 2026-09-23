"""
Duplicate detection.

Confidence model (as specified):
    same email                       -> 100
    same website + same company      ->  95
    same phone   + same company      ->  90
    same company + same address      ->  80
    same company + city + state      ->  70 (review only)
    same company name only           ->  55 (fuzzy, review only)

Matches are written as `LeadDuplicate` rows for human review; nothing is ever
merged automatically by the importer.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from django.db import transaction
from django.db.models import Q, QuerySet

from apps.core.utils import jaccard, normalize_key

from .models import EmailStatus, Lead, LeadDuplicate

CONFIDENCE = {
    "email": 100,
    "website": 95,
    "phone": 90,
    "address": 80,
    "city_state": 70,
    "name": 55,
}


@dataclass
class Candidate:
    lead: Lead
    candidate: Lead
    confidence: int
    method: str
    details: dict

    @property
    def lead_id(self):
        return self.lead.pk

    @property
    def candidate_id(self):
        return self.candidate.pk

    @property
    def method_code(self) -> str:
        return {
            "Same email": LeadDuplicate.Method.EMAIL,
            "Company + website": LeadDuplicate.Method.COMPANY_WEBSITE,
            "Company + phone": LeadDuplicate.Method.COMPANY_PHONE,
            "Company + address": LeadDuplicate.Method.COMPANY_ADDRESS,
            "Company + city + state": LeadDuplicate.Method.COMPANY_CITY_STATE,
            "Company name only": LeadDuplicate.Method.COMPANY_NAME,
        }.get(self.method, LeadDuplicate.Method.COMPANY_NAME)


def _company_similarity(a: Lead, b: Lead) -> float:
    """Token Jaccard similarity of the two company names (0..1)."""
    return jaccard(normalize_key(a.company_name).split(), normalize_key(b.company_name).split())


def compare(lead: Lead, candidate: Lead) -> Candidate | None:
    """Pairwise comparison. Returns None when the pair is not a duplicate."""
    if lead.pk == candidate.pk:
        return None

    # 1. Same normalized email -------------------------------------------
    if lead.email_normalized and lead.email_normalized == candidate.email_normalized:
        return Candidate(lead, candidate, CONFIDENCE["email"], "Same email",
                         {"email": lead.email_normalized})

    company_similarity = _company_similarity(lead, candidate)
    company_match = (
        lead.company_name_key
        and lead.company_name_key == candidate.company_name_key
    ) or company_similarity >= 0.85
    if not company_match:
        return None

    # 2. Same company + website -------------------------------------------
    if lead.website_domain and lead.website_domain == candidate.website_domain:
        return Candidate(lead, candidate, CONFIDENCE["website"], "Company + website",
                         {"domain": lead.website_domain,
                          "similarity": round(company_similarity, 2)})

    # 3. Same company + phone ----------------------------------------------
    if lead.phone_normalized and lead.phone_normalized == candidate.phone_normalized:
        return Candidate(lead, candidate, CONFIDENCE["phone"], "Company + phone",
                         {"phone": lead.phone_normalized,
                          "similarity": round(company_similarity, 2)})

    # 4. Same company + street address -------------------------------------
    if lead.street_address and candidate.street_address:
        a = normalize_key(lead.street_address)
        b = normalize_key(candidate.street_address)
        if a and a == b:
            return Candidate(lead, candidate, CONFIDENCE["address"], "Company + address",
                             {"address": lead.street_address,
                              "similarity": round(company_similarity, 2)})

    # 5. Same company + city + state ---------------------------------------
    if (
        lead.city
        and lead.state
        and normalize_key(lead.city) == normalize_key(candidate.city)
        and normalize_key(lead.state) == normalize_key(candidate.state)
    ):
        return Candidate(lead, candidate, CONFIDENCE["city_state"], "Company + city + state",
                         {"city": lead.city, "state": lead.state,
                          "similarity": round(company_similarity, 2)})

    # 6. Company name only (fuzzy) ------------------------------------------
    if company_similarity >= 0.92:
        return Candidate(lead, candidate, CONFIDENCE["name"], "Company name only",
                         {"similarity": round(company_similarity, 2)})
    return None


def _blocking_key(lead: Lead) -> str:
    """Cheap blocking key so we never compare every row with every row."""
    if lead.email_normalized:
        return f"e:{lead.email_normalized}"
    if lead.website_domain:
        return f"w:{lead.website_domain}"
    if lead.phone_normalized:
        return f"p:{lead.phone_normalized}"
    return f"c:{lead.company_name_key}|{normalize_key(lead.city)}|{normalize_key(lead.state)}"


def find_duplicates_for_lead(lead: Lead, *, limit: int = 25) -> list[Candidate]:
    """Candidates for a single lead (used by the UI + by the importer)."""
    conditions = Q()
    if lead.email_normalized:
        conditions |= Q(email_normalized=lead.email_normalized)
    if lead.website_domain:
        conditions |= Q(website_domain=lead.website_domain)
    if lead.phone_normalized:
        conditions |= Q(phone_normalized=lead.phone_normalized)
    if lead.company_name_key:
        conditions |= Q(company_name_key=lead.company_name_key)
    if not conditions:
        return []

    pool = (
        Lead.objects.filter(conditions)
        .exclude(pk=lead.pk)
        .exclude(merged_into__isnull=False)
        .distinct()[:500]
    )

    matches = [
        match for match in (compare(lead, other) for other in pool) if match is not None
    ]
    matches.sort(key=lambda m: (-m.confidence, -m.candidate.pk))
    return matches[:limit]


def detect_duplicates(queryset: QuerySet[Lead] | None = None, *, chunk_size: int = 2000,
                      min_confidence: int = 55) -> int:
    """Batch duplicate detection; writes LeadDuplicate rows (idempotent)."""
    qs = queryset if queryset is not None else Lead.objects.active().filter(is_duplicate=False)
    qs = qs.order_by("id")

    buckets: dict[str, list[Lead]] = defaultdict(list)
    processed = 0
    created = 0

    for lead in qs.iterator(chunk_size=chunk_size):
        key = _blocking_key(lead)
        # Compare inside the bucket, then keep a bounded bucket size.
        for other in buckets[key]:
            match = compare(lead, other)
            if match and match.confidence >= min_confidence:
                created += _record(match)
        buckets[key].append(lead)
        if len(buckets[key]) > 200:  # pathological buckets (e.g. all blank rows)
            buckets[key] = buckets[key][-100:]
        processed += 1

    # Cross-bucket pass on company+city+state for records blocked elsewhere.
    by_place: dict[tuple[str, str], list[Lead]] = defaultdict(list)
    for bucket in buckets.values():
        for lead in bucket:
            by_place[(lead.company_name_key, normalize_key(lead.city))].append(lead)
    for group in by_place.values():
        if 1 < len(group) <= 50:
            for a, b in combinations(group, 2):
                match = compare(a, b)
                if match and match.confidence >= min_confidence:
                    created += _record(match)

    return created


def _record(match: Candidate) -> int:
    """Insert the pair once, in a stable (min,max) order."""
    low, high = sorted([match.lead_id, match.candidate_id])
    with transaction.atomic():
        obj, created = LeadDuplicate.objects.get_or_create(
            lead_id=low,
            candidate_id=high,
            defaults={
                "confidence": match.confidence,
                "method": match.method_code,
                "details": match.details,
            },
        )
        if not created and obj.resolution == LeadDuplicate.Resolution.PENDING:
            obj.confidence = max(obj.confidence, match.confidence)
            obj.details = match.details
            obj.save(update_fields=["confidence", "details", "updated_at"])
    return int(created)


