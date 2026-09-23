"""
Service recommendation: rules first, AI as a re-ranker.

The rules are the source of truth (and are configurable in the admin); the AI
only re-ranks the shortlist and explains the choice. If the AI is unavailable
or fails the safety check, the rule-based answer stands.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings

from apps.campaigns.models import Service, ServiceIndustryMapping


@dataclass
class ServiceRecommendation:
    service: Service | None = None
    score: float = 0.0
    rationale: str = ""
    method: str = "rules"
    alternatives: list[Service] = field(default_factory=list)

    @property
    def service_name(self) -> str:
        return self.service.name if self.service else ""

    def as_dict(self) -> dict:
        return {
            "service_id": self.service.pk if self.service else None,
            "service": self.service_name,
            "score": round(self.score, 2),
            "rationale": self.rationale,
            "method": self.method,
            "alternatives": [s.name for s in self.alternatives],
        }


#: Fallback mapping when no admin rule exists (industry keyword -> services).
GENERIC_FALLBACK = {
    "Automotive": ["AI Lead Follow-up Automation", "CRM Development",
                   "Appointment Automation", "Website Development"],
    "Health & Wellness": ["Appointment Automation", "AI Receptionist",
                          "CRM Development", "Website Development"],
    "Professional Services": ["CRM Development", "Document Automation",
                              "Client Portal", "Workflow Automation"],
    "Home Services": ["AI Lead Follow-up Automation", "Appointment Automation",
                      "CRM Development", "Business Dashboards"],
    "Food & Hospitality": ["Website Development", "AI Chatbot", "Business Dashboards"],
    "Real Estate": ["CRM Development", "AI Lead Follow-up Automation",
                    "Website Development", "AI Chatbot"],
    "Retail": ["Website Development", "Business Dashboards", "API Integrations"],
    "Technology": ["Custom Software Development", "API Integrations",
                   "Custom SaaS Development"],
    "Finance": ["Document Automation", "Client Portal", "Workflow Automation"],
}


def _rule_candidates(lead) -> list[tuple[Service, float, str]]:
    """Industry mappings (sub-industry beats industry) + keyword matches."""
    scored: dict[int, tuple[Service, float, str]] = {}

    def add(service: Service, score: float, reason: str) -> None:
        current = scored.get(service.pk)
        if current is None or score > current[1]:
            scored[service.pk] = (service, score, reason)

    industry_ids = [i for i in (lead.sub_industry_id, lead.industry_id) if i]
    if industry_ids:
        mappings = (
            ServiceIndustryMapping.objects.filter(industry_id__in=industry_ids, is_active=True)
            .select_related("service")
            .order_by("priority")
        )
        for mapping in mappings:
            weight = 100 - min(mapping.priority, 50)
            bonus = 10 if mapping.industry_id == lead.sub_industry_id else 0
            add(mapping.service, weight + bonus,
                mapping.reason or f"Configured for {mapping.industry.name}")

    # Keyword match against service keywords / names using the company data.
    blob = " ".join(filter(None, [
        lead.company_name or "", lead.website_domain or "", lead.job_title or "",
    ])).lower()
    if blob:
        for service in Service.objects.filter(is_active=True):
            for keyword in service.keywords or []:
                if keyword and keyword.lower() in blob:
                    add(service, 55.0, f"Keyword match: {keyword}")

    # Generic fallback by industry name
    if not scored:
        industry_name = ""
        if lead.sub_industry_id:
            industry_name = lead.sub_industry.parent.name if lead.sub_industry.parent_id else lead.sub_industry.name
        elif lead.industry_id:
            industry_name = lead.industry.name
        for name in GENERIC_FALLBACK.get(industry_name, []):
            service = Service.objects.filter(name__iexact=name, is_active=True).first()
            if service:
                add(service, 40.0, f"Common service for {industry_name or 'this industry'}")
    return sorted(scored.values(), key=lambda item: -item[1])


def recommend_service(lead, *, use_ai: bool | None = None) -> ServiceRecommendation:
    """Return the best service for a lead (rules + optional AI re-rank)."""
    from apps.settings.services import get_setting

    if use_ai is None:
        use_ai = bool(get_setting("ai.enabled", settings.AI_ENABLED)) and \
            get_setting("ai.provider", settings.AI_PROVIDER) != "rules"

    candidates = _rule_candidates(lead)
    if not candidates:
        return ServiceRecommendation(method="none", rationale="No matching service rules.")

    top_service, top_score, top_reason = candidates[0]
    recommendation = ServiceRecommendation(
        service=top_service,
        score=top_score,
        rationale=top_reason,
        method="rules",
        alternatives=[service for service, _, _ in candidates[1:4]],
    )
    if not use_ai:
        return recommendation

    try:
        from .providers.base import AIEmailContext
        from .providers.registry import get_provider

        context = AIEmailContext(
            business_name=lead.company_name,
            industry=lead.industry.name if lead.industry_id else "",
            sub_industry=lead.sub_industry.name if lead.sub_industry_id else "",
            city=lead.city, state=lead.state, website=lead.website_domain,
            contact_name=lead.contact_name, job_title=lead.job_title,
            selected_service=top_service.name,
        )
        names = [service.name for service, _, _ in candidates[:8]]
        result = get_provider().recommend_service(context, names)
        if result.service:
            service = Service.objects.filter(name__iexact=result.service).first() or top_service
            if service != top_service:
                recommendation.alternatives = [top_service, *recommendation.alternatives][:3]
            recommendation.service = service
            recommendation.score = max(top_score, (result.confidence or 0) * 100)
            recommendation.rationale = result.rationale or top_reason
            recommendation.method = "rules+ai"
    except Exception:  # pragma: no cover - AI is best-effort here
        pass
    return recommendation
