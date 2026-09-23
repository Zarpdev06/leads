"""
Rule-based provider (default).

Deterministic, offline, zero-cost and fully testable. It produces genuinely
business-specific copy from the *verified* fields only - it cannot invent a
fact because there is no model doing the guessing.

It is the fallback whenever no API key is configured or a remote provider
fails, so campaigns keep running instead of stalling.
"""
from __future__ import annotations

import html

from .base import AIEmailContext, AIEmailResult, AIProvider, AIServiceResult

OPENERS = [
    "I came across {business} while looking at {niche} businesses in {place}.",
    "I was looking at {niche} businesses in {place} and {business} stood out.",
    "{business} came up while I was researching {niche} in {place}.",
]

BODIES = [
    (
        "<p>Hi {first_name},</p>"
        "<p>{opener}</p>"
        "<p>Most {niche} businesses we work with lose enquiries simply because follow-up "
        "depends on someone remembering to do it. We build {service} that replies to every "
        "new enquiry within seconds, keeps the conversation in one place and hands the hot "
        "ones to your team.</p>"
        "<p>{cta}</p>"
        "<p>{signature}</p>"
    ),
    (
        "<p>Hi {first_name},</p>"
        "<p>{opener}</p>"
        "<p>The pattern we see in {niche}: the work is won by whoever responds first, but "
        "the day gets in the way. We build {service} so every enquiry gets an instant, "
        "personal reply, bookings land straight in your calendar and nothing is chased "
        "manually.</p>"
        "<p>{cta}</p>"
        "<p>{signature}</p>"
    ),
    (
        "<p>Hi {first_name},</p>"
        "<p>{opener}</p>"
        "<p>One idea for {business}: {service}, built around how your team already works. "
        "Enquiries, bookings and follow-ups run themselves, and you keep full visibility "
        "in one dashboard.</p>"
        "<p>{cta}</p>"
        "<p>{signature}</p>"
    ),
]

CTAS = [
    "Would you be open to a 10-minute call this week to see if it fits how you work?",
    "Open to a quick 10-minute conversation about whether this would help {business}?",
    "Worth a 10-minute call to see whether this is relevant for {business}?",
]

SERVICE_INTRO = {
    "CRM Development": "a CRM shaped around your sales process",
    "AI Lead Follow-up Automation": "AI follow-up that answers every new enquiry instantly",
    "Appointment Automation": "self-service booking and automatic reminders",
    "AI Receptionist": "an AI receptionist that answers and books 24/7",
    "Website Development": "a fast, mobile-first website built to generate enquiries",
    "Business Dashboards": "live dashboards showing what is happening across the business",
    "Document Automation": "automatic document generation",
    "API Integrations": "integrations that sync your tools automatically",
    "Workflow Automation": "workflow automation for approvals and handoffs",
    "AI Chatbot": "an AI chatbot that answers customer questions instantly",
    "Client Portal": "a client portal for documents, progress and invoices",
}


class RuleBasedProvider(AIProvider):
    key = "rules"
    label = "Rule-based (offline)"
    requires_api_key = False

    def generate_email(self, context: AIEmailContext) -> AIEmailResult:
        business = context.business_name or "your business"
        niche = context.sub_industry or context.industry or "your industry"
        place = ", ".join(p for p in (context.city, context.state) if p) or "your area"
        first_name = context.first_name or (context.contact_name or "").split(" ")[0] or "there"
        service = context.selected_service or "automation"
        service_phrase = SERVICE_INTRO.get(service, service.lower())

        # Deterministic but varied: hash the business name so the same lead
        # always gets the same email (idempotent across retries/re-renders).
        seed = sum(ord(c) for c in f"{business}{service}")
        opener = (OPENERS[seed % len(OPENERS)]).format(
            business=html.escape(business), niche=niche.lower(), place=place
        )
        body_template = BODIES[seed % len(BODIES)]
        cta = (CTAS[seed % len(CTAS)]).format(business=html.escape(business))

        subject = f"A quick {service_phrase if len(service_phrase) < 28 else service.lower()} idea for {business}"
        subject = subject[:60] if len(subject) <= 60 else f"Quick idea for {business}"[:60]

        body = body_template.format(
            first_name=html.escape(first_name),
            opener=html.escape(opener),
            niche=niche.lower(),
            business=html.escape(business),
            service=service_phrase,
            cta=html.escape(cta),
            signature=html.escape(context.sender_name or context.sender_company or ""),
        )

        return AIEmailResult(
            subject=subject,
            opening_sentence=opener,
            personalization=f"you operate in {niche} in {place}",
            value_proposition=(
                f"{service} removes the manual follow-up that costs {niche} "
                f"businesses enquiries."
            ),
            cta=cta,
            body_html=body,
            body_text=_strip_html(body),
            recommended_service=service,
            provider=self.key,
            model="rules-v1",
            prompt="(deterministic rule-based generation - no model call)",
        )

    def recommend_service(self, context: AIEmailContext,
                          candidates: list[str]) -> AIServiceResult:
        return AIServiceResult(
            service=candidates[0] if candidates else "",
            confidence=0.6 if candidates else 0.0,
            rationale="Rule-based ranking from the industry → service mappings.",
            alternatives=candidates[1:4],
        )

    def test_connection(self) -> tuple[bool, str]:
        return True, "Rule-based provider is always available."


def _strip_html(value: str) -> str:
    import re

    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()
