"""
Template rendering + tracking + compliance footer.

Variables come from the canonical lead schema, e.g.
{{first_name}} {{contact_name}} {{company_name}} {{industry}} {{city}}
{{state}} {{website}} {{recommended_service}} {{personalization}}
"""
from __future__ import annotations

import html
import re

from django.conf import settings

VARIABLE_RE = re.compile(r"\{\{\s*([a-z0-9_\.]+)\s*\}\}", re.I)
LINK_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
TRACKING_PIXEL_HTML = (
    '<img src="{url}" width="1" height="1" alt="" style="display:block;width:1px;'
    'height:1px;border:0;" />'
)


def available_variables() -> list[dict]:
    """Documented in the template editor."""
    return [
        {"name": "first_name", "description": "Contact first name"},
        {"name": "last_name", "description": "Contact last name"},
        {"name": "contact_name", "description": "Full contact name"},
        {"name": "company_name", "description": "Business name"},
        {"name": "job_title", "description": "Job title"},
        {"name": "industry", "description": "Industry"},
        {"name": "sub_industry", "description": "Sub-industry / niche"},
        {"name": "city", "description": "City"},
        {"name": "state", "description": "State"},
        {"name": "location", "description": "City, State"},
        {"name": "website", "description": "Business website (host only)"},
        {"name": "phone", "description": "Phone number"},
        {"name": "recommended_service", "description": "Matched service"},
        {"name": "personalization", "description": "AI-generated personalization sentence"},
        {"name": "value_proposition", "description": "AI value proposition"},
        {"name": "opening_sentence", "description": "AI opening sentence"},
        {"name": "cta", "description": "AI call to action"},
        {"name": "sender_name", "description": "Sender display name"},
        {"name": "company_legal_name", "description": "Your legal entity name"},
        {"name": "unsubscribe_url", "description": "One-click unsubscribe link"},
    ]


def extract_variables(text: str) -> list[str]:
    return sorted({match.group(1).lower() for match in VARIABLE_RE.finditer(text or "")})


def render_variables(text: str, context: dict, *, keep_missing: bool = False) -> str:
    """Replace {{var}} with context values. Unknown variables are removed."""
    def replace(match: re.Match) -> str:
        key = match.group(1).lower()
        value = context.get(key, "")
        if value in (None, ""):
            return match.group(0) if keep_missing else _fallback(key, context)
        return str(value)

    return VARIABLE_RE.sub(replace, text or "")


def _fallback(key: str, context: dict) -> str:
    """Sensible fallbacks so an email never reads '{{first_name}}'."""
    fallbacks = {
        "first_name": context.get("contact_name") or "there",
        "contact_name": context.get("first_name") or "there",
        "company_name": "your business",
        "city": context.get("state") or "your area",
        "location": context.get("state") or "your area",
        "industry": context.get("sub_industry") or "your industry",
        "recommended_service": "automation",
        "sender_name": context.get("sender_name") or "",
    }
    return fallbacks.get(key, "")


def wrap_click_links(html_body: str, tracking_base: str, uid: str) -> str:
    """Rewrite every link through the click-tracking redirect."""
    if not html_body:
        return html_body

    def replace(match: re.Match) -> str:
        url = match.group(1)
        if url.startswith(("mailto:", "tel:", "#", "{{")):
            return match.group(0)
        return f'href="{tracking_base}/t/c/{uid}?u={html.escape(url)}"'

    return LINK_RE.sub(replace, html_body)


def add_tracking_pixel(html_body: str, pixel_url: str) -> str:
    if not pixel_url:
        return html_body
    pixel = TRACKING_PIXEL_HTML.format(url=html.escape(pixel_url))
    if "</body>" in html_body:
        return html_body.replace("</body>", f"{pixel}</body>")
    return html_body + pixel


def build_footer(*, unsubscribe_url: str, postal_address: str = "",
                 legal_name: str = "") -> str:
    """Compliance footer: unsubscribe link + physical address (CAN-SPAM).

    Every marketing email must carry a working unsubscribe mechanism; the
    postal address line is required by CAN-SPAM for commercial messages.
    """
    from apps.settings.services import get_setting

    link_text = str(
        get_setting(
            "compliance.unsubscribe_text",
            "Don't want to receive emails from us? Unsubscribe",
        )
    )
    safe_url = html.escape(unsubscribe_url, quote=True)
    link_html = (
        '<a href="{url}" style="color:#6b7280;text-decoration:underline;">{label}</a>'
    ).format(url=safe_url, label=html.escape("Unsubscribe"))
    if "Unsubscribe" in link_text:
        footer_text = html.escape(link_text).replace("Unsubscribe", link_html)
    else:
        footer_text = f"{html.escape(link_text)} {link_html}"

    identity = " · ".join(part for part in (legal_name, postal_address) if part)
    identity_html = f"<br />{html.escape(identity)}" if identity else ""

    return (
        '<p style="font-size:12px;color:#6b7280;line-height:1.5;margin-top:24px;">'
        f"{footer_text}{identity_html}</p>"
    )


def html_to_text(html_body: str) -> str:
    """Very small HTML → text conversion for the plaintext alternative."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html_body or "", flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(p|div|tr|h[1-6])>", "\n\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def preview_context(lead) -> dict:
    """Build the template context for a lead (used by preview + real sends)."""
    industry = lead.sub_industry.name if lead.sub_industry_id else (
        lead.industry.name if lead.industry_id else ""
    )
    parent_industry = ""
    if lead.sub_industry_id and lead.sub_industry.parent_id:
        parent_industry = lead.sub_industry.parent.name
    elif lead.industry_id:
        parent_industry = lead.industry.name

    from apps.settings.services import get_setting

    return {
        "first_name": lead.first_name or (lead.contact_name or "").split(" ")[0],
        "last_name": lead.last_name,
        "contact_name": lead.contact_name or f"{lead.first_name} {lead.last_name}".strip(),
        "company_name": lead.company_name,
        "job_title": lead.job_title,
        "industry": industry or parent_industry,
        "sub_industry": industry,
        "city": lead.city,
        "state": lead.state,
        "location": lead.location,
        "website": lead.website_domain,
        "phone": lead.phone,
        "employee_count": lead.employee_count or "",
        "recommended_service": (
            lead.recommended_service.name if lead.recommended_service_id else ""
        ),
        "sender_name": get_setting("email.from_name", ""),
        "company_legal_name": get_setting("compliance.legal_name",
                                          settings.COMPANY_LEGAL_NAME),
    }
