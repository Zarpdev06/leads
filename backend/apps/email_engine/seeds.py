"""Starter email templates (idempotent)."""
from __future__ import annotations

from django.utils.text import slugify

from .models import EmailTemplate, FollowUpSequence, FollowUpStep

TEMPLATES: list[dict] = [
    {
        "name": "Cold outreach — automation idea",
        "category": EmailTemplate.Category.COLD_OUTREACH,
        "subject": "Quick idea for {{company_name}}",
        "body_html": (
            "<p>Hi {{first_name}},</p>"
            "<p>I came across {{company_name}} and noticed you operate in "
            "{{sub_industry}} in {{city}}.</p>"
            "<p>{{personalization}}.</p>"
            "<p>We help businesses like yours automate repetitive processes such as "
            "lead follow-up, customer communication, CRM workflows and internal "
            "operations. For {{company_name}}, the most obvious win would be "
            "{{recommended_service}}.</p>"
            "<p>Would you be open to a quick 10-minute conversation?</p>"
            "<p>Regards,<br />{{sender_name}}</p>"
        ),
        "is_default": True,
    },
    {
        "name": "Cold outreach — website / enquiries",
        "category": EmailTemplate.Category.COLD_OUTREACH,
        "subject": "{{company_name}} — more enquiries from your website?",
        "body_html": (
            "<p>Hi {{first_name}},</p>"
            "<p>{{opening_sentence}}</p>"
            "<p>{{value_proposition}}</p>"
            "<p>{{cta}}</p>"
            "<p>Regards,<br />{{sender_name}}</p>"
        ),
    },
    {
        "name": "Follow-up 1 (day 3)",
        "category": EmailTemplate.Category.FOLLOW_UP,
        "subject": "Re: Quick idea for {{company_name}}",
        "body_html": (
            "<p>Hi {{first_name}},</p>"
            "<p>Following up on my note about {{recommended_service}} for "
            "{{company_name}}.</p>"
            "<p>{{personalization}} — that is usually where the hours go.</p>"
            "<p>Worth a 10-minute call this week?</p>"
            "<p>Regards,<br />{{sender_name}}</p>"
        ),
    },
    {
        "name": "Follow-up 2 (day 7)",
        "category": EmailTemplate.Category.FOLLOW_UP,
        "subject": "One more thought for {{company_name}}",
        "body_html": (
            "<p>Hi {{first_name}},</p>"
            "<p>I will keep this short. If {{recommended_service}} is not a priority "
            "right now, no problem at all — I would rather know than keep emailing.</p>"
            "<p>If it is, I can show you in 10 minutes what it would look like for "
            "{{company_name}}.</p>"
            "<p>Regards,<br />{{sender_name}}</p>"
        ),
    },
    {
        "name": "Follow-up 3 — last check-in (day 14)",
        "category": EmailTemplate.Category.FOLLOW_UP,
        "subject": "Should I close the file on {{company_name}}?",
        "body_html": (
            "<p>Hi {{first_name}},</p>"
            "<p>Last note from me. If automating {{recommended_service}} at "
            "{{company_name}} is not on the roadmap this quarter, just reply "
            "\"not now\" and I will stop emailing.</p>"
            "<p>If timing improves later, my details are below.</p>"
            "<p>Regards,<br />{{sender_name}}</p>"
        ),
    },
    {
        "name": "Meeting request",
        "category": EmailTemplate.Category.MEETING,
        "subject": "10 minutes for {{company_name}}?",
        "body_html": (
            "<p>Hi {{first_name}},</p>"
            "<p>Thanks for the reply. Would {{recommended_service}} be worth 10 "
            "minutes this week? I can walk through what it would look like for "
            "{{company_name}} and what it typically costs.</p>"
            "<p>Regards,<br />{{sender_name}}</p>"
        ),
    },
]


def seed_default_templates() -> int:
    from .render import html_to_text

    created = 0
    for payload in TEMPLATES:
        template, new = EmailTemplate.objects.get_or_create(
            name=payload["name"],
            defaults={
                "slug": slugify(payload["name"]),
                "category": payload["category"],
                "subject": payload["subject"],
                "body_html": payload["body_html"],
                "body_text": html_to_text(payload["body_html"]),
                "is_default": payload.get("is_default", False),
            },
        )
        created += int(new)

    # Wire the default sequence to the follow-up templates.
    sequence, _ = FollowUpSequence.objects.get_or_create(
        name="Standard (day 0 / +3 / +7 / +14)",
        defaults={"description": "Initial email plus three follow-ups."},
    )
    mapping = [
        (1, 3, "Follow-up 1 (day 3)"),
        (2, 7, "Follow-up 2 (day 7)"),
        (3, 14, "Follow-up 3 — last check-in (day 14)"),
    ]
    for order, days, template_name in mapping:
        template = EmailTemplate.objects.filter(name=template_name).first()
        FollowUpStep.objects.get_or_create(
            sequence=sequence, order=order,
            defaults={
                "delay_days": days,
                "template": template,
                "condition": FollowUpStep.Condition.NO_REPLY,
                "use_ai": True,
            },
        )
    return created
