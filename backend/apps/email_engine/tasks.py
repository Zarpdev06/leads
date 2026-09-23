"""
Celery tasks for the email pipeline.

Every task is idempotent and takes a primary key (never a queryset), so a
retry can never double-send. The (campaign_lead, step_number) unique constraint
backstops that at the database level.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.models import log_audit
from apps.settings.services import max_attempts, min_seconds_between_sends

from .models import EmailEvent, EmailMessage
from .quota import DailyEmailQuota

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="apps.email_engine.tasks.send_due_emails")
def send_due_emails(self, limit: int | None = None) -> dict:
    """Beat task: send everything that is due, within today's remaining quota."""
    from django.conf import settings

    from apps.settings.services import sending_weekdays

    limit = limit or int(settings.EMAIL_BATCH_SIZE_PER_RUN)
    today = timezone.localdate()

    if today.isoweekday() not in sending_weekdays():
        return {"sent": 0, "skipped": 0, "detail": "Outside configured sending days"}

    usage = DailyEmailQuota.usage_for(today)
    capacity = usage.remaining
    if capacity <= 0:
        return {"sent": 0, "skipped": 0, "detail": "Daily limit reached",
                "limit": usage.limit, "used": usage.sent_count}

    batch = min(limit, capacity)
    due = list(
        EmailMessage.objects.filter(
            status=EmailMessage.Status.QUEUED,
            scheduled_at__lte=timezone.now(),
        )
        .order_by("scheduled_at", "id")
        .values_list("id", flat=True)[:batch]
    )

    sent = failed = skipped = 0
    for message_id in due:
        result = send_email_message(message_id)
        if result.get("status") == "SENT":
            sent += 1
        elif result.get("status") == "SKIPPED":
            skipped += 1
        else:
            failed += 1
        wait = int(min_seconds_between_sends() or 0)
        if wait and (sent + failed + skipped) < len(due):
            # Pace ourselves: this is about respecting SMTP rate limits.
            time.sleep(min(wait, 5))

    return {"sent": sent, "failed": failed, "skipped": skipped,
            "remaining": DailyEmailQuota.usage_for(today).remaining}


@shared_task(bind=True, name="apps.email_engine.tasks.send_email_message",
             autoretry_for=(Exception,), retry_backoff=30, retry_backoff_max=900,
             max_retries=0, acks_late=True)
def send_email_message(self, message_id: int) -> dict:
    """Send one message. Idempotent: re-processing a sent message is a no-op."""
    message = EmailMessage.objects.filter(pk=message_id).select_related(
        "lead", "campaign", "campaign_lead"
    ).first()
    if message is None:
        return {"status": "MISSING"}

    if message.status in {
        EmailMessage.Status.SENT, EmailMessage.Status.CANCELLED,
        EmailMessage.Status.SKIPPED,
    }:
        return {"status": message.status, "detail": "already processed"}

    from .sender import send_message

    result = send_message(message)

    # Retry transient failures with exponential backoff (max_attempts total).
    if result.get("retryable") and message.attempt_count < max_attempts():
        backoff_minutes = 5 * (2 ** (message.attempt_count - 1))
        message.status = EmailMessage.Status.QUEUED
        message.scheduled_at = timezone.now() + timedelta(minutes=backoff_minutes)
        message.save(update_fields=["status", "scheduled_at", "updated_at"])
        result["retry_scheduled_at"] = message.scheduled_at.isoformat()
    elif result.get("status") == "FAILED":
        EmailEvent.objects.create(
            message=message, type=EmailEvent.Type.FAILED,
            metadata={"error": result.get("detail", "")[:400]},
        )
        log_audit(action="EMAIL_FAILED", entity_type="email_message",
                  entity_id=message.pk,
                  description=f"Failed to send to {message.to_email}",
                  metadata={"error": result.get("detail", "")[:400]})
    return result


@shared_task(name="apps.email_engine.tasks.dispatch_campaign")
def dispatch_campaign_task(campaign_id: int, user_id: int | None = None) -> dict:
    from apps.accounts.models import User
    from apps.campaigns.models import Campaign

    campaign = Campaign.objects.filter(pk=campaign_id).first()
    if campaign is None:
        return {"error": "campaign not found"}
    user = User.objects.filter(pk=user_id).first() if user_id else None

    from .services import dispatch_campaign, materialize_campaign_leads

    created_leads = materialize_campaign_leads(campaign, user=user)
    result = dispatch_campaign(campaign, user=user)
    result["campaign_leads_added"] = created_leads
    log_audit(action="CAMPAIGN_STARTED", actor=user, entity_type="campaign",
              entity_id=campaign.pk, obj=campaign,
              description=f"Campaign dispatched: {result}")
    return result


@shared_task(name="apps.email_engine.tasks.process_follow_ups")
def process_follow_ups(campaign_id: int | None = None) -> dict:
    from apps.campaigns.models import Campaign

    campaign = Campaign.objects.filter(pk=campaign_id).first() if campaign_id else None
    from .services import process_follow_ups as _process

    return _process(campaign)


@shared_task(name="apps.email_engine.tasks.release_stuck_messages")
def release_stuck_messages(minutes: int = 15) -> dict:
    """Return PROCESSING messages to the queue after a worker crash."""
    cutoff = timezone.now() - timedelta(minutes=minutes)
    stuck = EmailMessage.objects.filter(
        status=EmailMessage.Status.PROCESSING, processing_at__lte=cutoff
    )
    count = 0
    for message in stuck:
        if message.attempt_count < max_attempts():
            message.status = EmailMessage.Status.QUEUED
            message.scheduled_at = timezone.now() + timedelta(minutes=2 ** message.attempt_count)
        else:
            message.status = EmailMessage.Status.FAILED
            message.last_error = "Gave up after repeated failures"
            message.failed_at = timezone.now()
        message.save(update_fields=["status", "scheduled_at", "last_error",
                                    "failed_at", "updated_at"])
        count += 1
    return {"released": count}


@shared_task(name="apps.email_engine.tasks.rollover_daily_usage")
def rollover_daily_usage() -> dict:
    """Make sure today's counter row exists with current limits."""
    usage = DailyEmailQuota.usage_for(timezone.localdate())
    return {"date": usage.date.isoformat(), "limit": usage.limit,
            "sent": usage.sent_count}


@shared_task(name="apps.email_engine.tasks.poll_mailbox")
def poll_mailbox() -> dict:
    """Optional IMAP poll for replies / bounces (stdlib imaplib, no deps)."""
    from django.conf import settings

    if not settings.IMAP_ENABLED or not settings.IMAP_HOST:
        return {"enabled": False}

    import email as email_lib
    import imaplib
    import re

    from apps.leads.models import CRMStage, Lead, LeadStatus
    from apps.suppression.services import add_suppression

    processed = {"replies": 0, "bounces": 0}
    try:
        client = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT) \
            if settings.IMAP_USE_SSL else imaplib.IMAP4(settings.IMAP_HOST, settings.IMAP_PORT)
        client.login(settings.IMAP_USERNAME, settings.IMAP_PASSWORD)
        client.select(settings.IMAP_MAILBOX)
        typ, data = client.search(None, "UNSEEN")
        if typ != "OK":
            return {"enabled": True, **processed}
        for num in (data[0].split() if data and data[0] else [])[:200]:
            typ, msg_data = client.fetch(num, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            parsed = email_lib.message_from_bytes(msg_data[0][1])
            body = _extract_text(parsed)
            uid_match = re.search(r"X-Message-Uid:\s*([a-f0-9]{32})",
                                  parsed.as_string(), re.I)
            message = None
            if uid_match:
                message = EmailMessage.objects.filter(uid=uid_match.group(1)).first()
            if message is None:
                continue

            if _looks_like_bounce(parsed, body):
                message.mark_failed("Bounce detected by mailbox poll", bounced=True)
                DailyEmailQuota.record_failure(bounced=True)
                add_suppression(message.to_email, reason="BOUNCED",
                                source="BOUNCE_HANDLER", email_message=message,
                                note="Detected by IMAP poll")
                processed["bounces"] += 1
            else:
                message.replied_at = timezone.now()
                message.save(update_fields=["replied_at", "updated_at"])
                EmailEvent.objects.create(message=message, type=EmailEvent.Type.REPLIED,
                                          metadata={"snippet": body[:200]})
                if message.lead_id:
                    Lead.objects.filter(pk=message.lead_id).update(
                        replied_at=timezone.now(),
                        lead_status=LeadStatus.REPLIED,
                        crm_stage=CRMStage.REPLIED if
                        Lead.objects.filter(pk=message.lead_id).first().crm_stage
                        in {CRMStage.NEW, CRMStage.QUALIFIED,
                            CRMStage.CONTACTED} else F("crm_stage"),
                    )
                if message.campaign_lead_id:
                    from apps.campaigns.models import CampaignLead

                    CampaignLead.objects.filter(pk=message.campaign_lead_id).update(
                        status=CampaignLead.Status.REPLIED, replied_at=timezone.now()
                    )
                processed["replies"] += 1
            client.store(num, "+FLAGS", "\\Seen")
        client.close()
        client.logout()
    except Exception as exc:
        logger.warning("IMAP poll failed: %s", exc)
        return {"enabled": True, "error": str(exc), **processed}
    return {"enabled": True, **processed}


def _extract_text(parsed) -> str:
    if parsed.is_multipart():
        for part in parsed.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                return payload.decode(errors="replace") if payload else ""
    payload = parsed.get_payload(decode=True)
    return payload.decode(errors="replace") if payload else ""


def _looks_like_bounce(parsed, body: str) -> bool:
    subject = (parsed.get("Subject") or "").lower()
    if any(token in subject for token in ("undeliverable", "delivery status notification",
                                          "failure notice", "returned mail", "bounce")):
        return True
    lowered = (body or "").lower()
    return any(token in lowered for token in (
        "550 5.1.1", "permanent failure", "address not found", "user unknown",
        "no such user", "recipient address rejected",
    ))


@shared_task(name="apps.email_engine.tasks.send_test_email")
def send_test_email(to_email: str, subject: str = "SMTP test", body: str = "") -> dict:
    """Send a transactional test message (does not consume the marketing quota)."""
    from django.core.mail import send_mail

    from apps.settings.services import smtp_status

    status = smtp_status()
    if not status["configured"]:
        return {"ok": False, "detail": "SMTP is not configured in the environment."}
    try:
        with transaction.atomic():
            EmailMessage.objects.create(
                to_email=to_email, from_email=status["from_email"], subject=subject,
                body_html=body or "This is a test message from your outreach platform.",
                body_text=body or "This is a test message from your outreach platform.",
                status=EmailMessage.Status.QUEUED, is_transactional=True,
            )
            sent = send_mail(
                subject,
                body or "This is a test message from your outreach platform.",
                status["from_email"],
                [to_email],
                fail_silently=False,
            )
        DailyEmailQuota.record_transactional()
        return {"ok": bool(sent), "detail": "Sent" if sent else "Not sent"}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}
