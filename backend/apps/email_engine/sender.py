"""
Message composition and SMTP delivery.

Composition pipeline
--------------------
    lead context  ->  service match  ->  (AI personalization | template only)
                  ->  variable rendering  ->  link wrapping + open pixel
                  ->  compliance footer  ->  EmailMessage row

Delivery
--------
    reserve quota (atomic)  ->  SMTP send  ->  update status / counters / CRM
"""
from __future__ import annotations

import logging
import smtplib
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db.models import F
from django.utils import timezone

from apps.core.models import log_audit
from apps.leads.models import CRMStage, EmailStatus, LeadStatus
from apps.settings.services import get_setting

from .models import EmailEvent, EmailMessage
from .quota import DailyEmailQuota
from .render import (
    add_tracking_pixel,
    build_footer,
    html_to_text,
    preview_context,
    render_variables,
    wrap_click_links,
)

logger = logging.getLogger(__name__)

# SMTP reply codes that mean "this address will never work".
HARD_BOUNCE_CODES = {500, 501, 502, 503, 504, 521, 550, 551, 552, 553, 554}
SOFT_BOUNCE_CODES = {421, 450, 451, 452, 455}


class PermanentSendError(Exception):
    """The message can never be delivered (bad address / policy rejection)."""


class TransientSendError(Exception):
    """Temporary problem (rate limit, greylisting, connection dropped)."""


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------
def default_sender_identity() -> tuple[str, str, str]:
    """(from_name, from_email, reply_to) from settings + SystemSetting."""
    from_email = get_setting("email.from_address", "") or settings.DEFAULT_FROM_EMAIL
    from_name = get_setting("email.from_name", "") or settings.COMPANY_LEGAL_NAME
    reply_to = get_setting("email.reply_to", "") or settings.DEFAULT_REPLY_TO
    return from_name, from_email, reply_to


def build_context(lead, *, campaign=None) -> dict:
    context = preview_context(lead)

    service_name = ""
    if campaign is not None and campaign.recommended_service_id:
        service_name = campaign.recommended_service.name
    elif lead.recommended_service_id:
        service_name = lead.recommended_service.name
    if not service_name:
        from apps.ai_engine.service_matching import recommend_service

        recommendation = recommend_service(lead)
        service_name = recommendation.service.name if recommendation.service else ""
    context["recommended_service"] = service_name or "automation"
    context.setdefault("personalization", "")
    context.setdefault("opening_sentence", "")
    context.setdefault("value_proposition", "")
    context.setdefault("cta", "")
    return context


def compose_message(*, lead, template, campaign=None, campaign_lead=None,
                    step_number: int = 0, subject: str = "", body_html: str = "",
                    use_ai: bool | None = None, ai_instructions: str = "",
                    from_name: str = "", from_email: str = "", reply_to: str = "",
                    actor=None) -> EmailMessage:
    """Create (but do not send) an EmailMessage for a lead."""
    if use_ai is None:
        use_ai = bool(campaign.use_ai_personalization) if campaign else False

    context = build_context(lead, campaign=campaign)
    ai_result: dict[str, Any] = {}

    if use_ai:
        try:
            from apps.ai_engine.generator import generate_email_for_lead

            generated = generate_email_for_lead(
                lead,
                template=template,
                campaign=campaign,
                context=context,
                instructions=ai_instructions or (campaign.ai_instructions if campaign else ""),
            )
            ai_result = generated.as_dict()
            context.update({
                "personalization": generated.personalization,
                "opening_sentence": generated.opening_sentence,
                "value_proposition": generated.value_proposition,
                "cta": generated.cta,
                "recommended_service": generated.recommended_service or context["recommended_service"],
            })
            subject = subject or generated.subject
            body_html = body_html or generated.body_html
        except Exception as exc:  # never block a campaign because the AI is down
            logger.warning("AI generation failed for lead %s: %s", lead.pk, exc)
            log_audit(action="AI_FAILED", actor=actor, entity_type="lead", entity_id=lead.pk,
                      description=str(exc)[:500])
            ai_result = {"error": str(exc)}

    template_subject = template.subject if template else (subject or "")
    template_body = template.body_html if template else (body_html or "")
    final_subject = render_variables(subject or template_subject, context)
    body = body_html or template_body
    final_body = render_variables(body, context)

    # Fallback personalization when AI is unavailable: still business-specific,
    # but strictly limited to facts we actually have.
    if "{{personalization}}" in final_body or not context.get("personalization"):
        fallback = _fallback_personalization(lead, context)
        final_body = final_body.replace("{{personalization}}", fallback)

    dn, de, rt = default_sender_identity()
    from_name = from_name or (campaign.from_name if campaign else "") or dn
    from_email = from_email or (campaign.from_email if campaign else "") or de
    reply_to = reply_to or (campaign.reply_to if campaign else "") or rt

    # Tracking + compliance -------------------------------------------------
    message = EmailMessage(
        campaign=campaign,
        campaign_lead=campaign_lead,
        lead=lead,
        template=template,
        step_number=step_number,
        to_email=lead.email_normalized or lead.email,
        to_name=lead.contact_name,
        from_email=from_email,
        from_name=from_name,
        reply_to=reply_to,
        subject=final_subject.strip()[:400],
        body_html=final_body,
        body_text=html_to_text(final_body),
        is_ai_generated=bool(ai_result and not ai_result.get("error")),
        ai_provider=ai_result.get("provider", ""),
        ai_model=ai_result.get("model", ""),
        ai_prompt=ai_result.get("prompt", "") or "",
        ai_response=ai_result,
        recommended_service=context.get("recommended_service", ""),
        status=EmailMessage.Status.QUEUED,
    )
    # uid/token defaults are generated at save() time; we need them for links.
    message.uid = message.uid or EmailMessage._meta.get_field("uid").get_default()
    message.unsubscribe_token = (
        message.unsubscribe_token
        or EmailMessage._meta.get_field("unsubscribe_token").get_default()
    )

    base = settings.PUBLIC_BASE_URL
    unsubscribe_url = f"{base}{message.unsubscribe_url}"
    if get_setting("email.track_clicks", True):
        final_body = wrap_click_links(final_body, base, message.uid)
    if get_setting("email.track_opens", True):
        final_body = add_tracking_pixel(final_body, f"{base}{message.tracking_pixel_url}")
    final_body += build_footer(
        unsubscribe_url=unsubscribe_url,
        postal_address=get_setting("compliance.postal_address",
                                   settings.COMPANY_POSTAL_ADDRESS),
        legal_name=get_setting("compliance.legal_name", settings.COMPANY_LEGAL_NAME),
    )
    message.body_html = final_body
    message.body_text = html_to_text(final_body)
    message.headers = {
        "List-Unsubscribe": f"<{unsubscribe_url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        "X-Campaign-Id": str(campaign.pk if campaign else ""),
        "X-Message-Uid": message.uid,
        "Precedence": "bulk",
        "Auto-Submitted": "auto-generated",
    }
    return message


def _fallback_personalization(lead, context: dict) -> str:
    """Facts-only personalization used when AI generation is unavailable."""
    industry = context.get("sub_industry") or context.get("industry") or ""
    location = context.get("location") or context.get("state") or ""
    if industry and location:
        return (
            f"you operate in {industry} in {location}, where enquiries and follow-ups "
            f"tend to arrive faster than a small team can answer them"
        )
    if industry:
        return f"you operate in {industry}, where speed of response decides who wins the job"
    if location:
        return f"you serve customers in {location}, where word of mouth drives most new business"
    return "your team handles every new enquiry by hand"


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------
def _smtp_connection():
    return get_connection(
        backend=settings.EMAIL_BACKEND,
        fail_silently=False,
        timeout=settings.EMAIL_TIMEOUT,
    )


def deliver(message: EmailMessage) -> None:
    """Perform the SMTP send for one message. Raises on failure."""
    connection = _smtp_connection()
    email = EmailMultiAlternatives(
        subject=message.subject,
        body=message.body_text or html_to_text(message.body_html),
        from_email=f"{message.from_name} <{message.from_email}>" if message.from_name
        else message.from_email,
        to=[message.to_email],
        connection=connection,
        headers=message.headers or {},
        reply_to=[message.reply_to] if message.reply_to else None,
    )
    email.mixed_subtype = "related"
    email.attach_alternative(message.body_html, "text/html")
    try:
        sent = email.send(fail_silently=False)
    except smtplib.SMTPRecipientsRefused as exc:
        raise PermanentSendError(f"Recipient refused: {exc}") from exc
    except smtplib.SMTPResponseException as exc:
        code = exc.smtp_code
        if code in HARD_BOUNCE_CODES:
            raise PermanentSendError(f"SMTP {code}: {exc.smtp_error}") from exc
        raise TransientSendError(f"SMTP {code}: {exc.smtp_error}") from exc
    except (smtplib.SMTPException, OSError, TimeoutError) as exc:
        raise TransientSendError(str(exc)) from exc
    finally:
        try:
            connection.close()
        except Exception:  # pragma: no cover
            pass
    if not sent:  # pragma: no cover - defensive
        raise TransientSendError("SMTP backend reported 0 messages sent")


def send_message(message: EmailMessage, *, actor=None, force: bool = False) -> dict:
    """Send a single message, honouring suppression, eligibility and the quota.

    Returns a dict describing what happened. Never raises for expected
    conditions (suppressed / quota exhausted) — those are recorded instead.
    """
    from apps.leads.eligibility import evaluate_lead_eligibility
    from apps.suppression.services import is_suppressed

    if message.status in {
        EmailMessage.Status.SENT, EmailMessage.Status.CANCELLED,
        EmailMessage.Status.SKIPPED,
    }:
        return {"status": message.status, "detail": "Already processed"}

    lead = message.lead

    # -- Pre-flight checks (do not consume quota) --------------------------
    if is_suppressed(message.to_email):
        message.mark_skipped("Recipient is on the suppression list")
        return {"status": "SKIPPED", "detail": "suppressed"}

    if lead is not None:
        eligibility = evaluate_lead_eligibility(lead, message.campaign)
        if not eligibility.eligible and not force:
            message.mark_skipped("; ".join(eligibility.reasons) or "Not eligible")
            if message.campaign_lead_id:
                from apps.campaigns.models import CampaignLead

                CampaignLead.objects.filter(pk=message.campaign_lead_id).update(
                    status=CampaignLead.Status.SKIPPED,
                    stopped_reason="; ".join(eligibility.reasons)[:200],
                )
            return {"status": "SKIPPED", "detail": eligibility.reasons}

    # -- Quota --------------------------------------------------------------
    if not message.is_transactional:
        reservation = DailyEmailQuota.reserve()
        if not reservation:
            message.mark_skipped("Daily marketing limit reached")
            DailyEmailQuota.record_skipped()
            return {
                "status": "SKIPPED",
                "detail": "quota_exhausted",
                "limit": reservation.limit,
                "sent": reservation.sent,
            }
    else:
        DailyEmailQuota.record_transactional()

    # -- Send -----------------------------------------------------------------
    message.mark_processing()
    try:
        deliver(message)
    except PermanentSendError as exc:
        message.mark_failed(str(exc), bounced=True)
        DailyEmailQuota.record_failure(bounced=True)
        _handle_bounce(message, reason=str(exc))
        return {"status": "BOUNCED", "detail": str(exc)}
    except TransientSendError as exc:
        message.mark_failed(str(exc))
        DailyEmailQuota.record_failure()
        return {"status": "FAILED", "detail": str(exc), "retryable": True}
    except Exception as exc:  # pragma: no cover - unexpected
        logger.exception("Unexpected error sending message %s", message.pk)
        message.mark_failed(str(exc))
        DailyEmailQuota.record_failure()
        return {"status": "FAILED", "detail": str(exc), "retryable": True}

    # -- Success -------------------------------------------------------------
    message.mark_sent()
    EmailEvent.objects.create(
        message=message, type=EmailEvent.Type.SENT,
        metadata={"provider_message_id": message.provider_message_id},
    )
    if lead is not None:
        lead.mark_contacted()
        lead.set_status(
            LeadStatus.CONTACTED,
            actor=actor,
            note=f"Email sent: {message.subject[:80]}",
        )
        if lead.crm_stage in {CRMStage.NEW, CRMStage.QUALIFIED}:
            lead.set_stage(CRMStage.CONTACTED, actor=actor,
                           note="First outreach email sent")
        lead.log_activity(
            type="EMAIL_SENT",
            title="Email sent",
            description=message.subject,
            actor=actor,
            metadata={"message_id": message.pk, "step": message.step_number,
                      "campaign_id": message.campaign_id},
        )
    if message.campaign_lead_id:
        from apps.campaigns.models import CampaignLead

        CampaignLead.objects.filter(pk=message.campaign_lead_id).update(
            status=CampaignLead.Status.SENT, sent_at=timezone.now(),
            current_step=message.step_number,
        )
    if message.campaign_id:
        from apps.campaigns.models import Campaign

        Campaign.objects.filter(pk=message.campaign_id).update(
            total_sent=F("total_sent") + 1
        )
    log_audit(
        action="EMAIL_SENT", actor=actor, entity_type="email_message",
        entity_id=message.pk, description=f"Sent to {message.to_email}",
        metadata={"campaign_id": message.campaign_id, "lead_id": message.lead_id},
    )
    return {"status": "SENT", "detail": "ok"}


def _handle_bounce(message: EmailMessage, *, reason: str) -> None:
    """Hard bounce: suppress the address, stop follow-ups, update the lead."""
    from apps.leads.models import EmailStatus, Lead
    from apps.suppression.services import add_suppression

    add_suppression(
        message.to_email,
        reason="BOUNCED",
        source="BOUNCE_HANDLER",
        note=f"Hard bounce: {reason[:200]}",
        lead=message.lead,
        email_message=message,
    )
    if message.lead_id:
        Lead.objects.filter(pk=message.lead_id).update(
            email_status=EmailStatus.BOUNCED,
            bounced_at=timezone.now(),
            is_blocked=True,
            blocked_reason="Hard bounce",
        )
        lead = Lead.objects.filter(pk=message.lead_id).first()
        if lead:
            lead.log_activity(
                type="EMAIL_BOUNCED", title="Email bounced",
                description=reason[:200], metadata={"message_id": message.pk},
            )
    if message.campaign_lead_id:
        from apps.campaigns.models import CampaignLead

        CampaignLead.objects.filter(pk=message.campaign_lead_id).update(
            status=CampaignLead.Status.BOUNCED, stopped_reason="Bounced"
        )
    EmailEvent.objects.create(
        message=message, type=EmailEvent.Type.BOUNCED, metadata={"reason": reason[:400]}
    )
