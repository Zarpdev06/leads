"""SMTP delivery, failures, retries, bounces, tracking and idempotency."""
import smtplib

import pytest
from django.core import mail
from django.utils import timezone

from apps.campaigns.models import Campaign, CampaignLead
from apps.email_engine.models import EmailEvent, EmailMessage
from apps.email_engine.sender import (
    PermanentSendError,
    TransientSendError,
    compose_message,
    send_message,
)
from apps.email_engine.tasks import send_due_emails, send_email_message
from apps.leads.models import EmailStatus, Lead, LeadStatus
from apps.settings.services import set_setting
from apps.suppression.models import Suppression


def test_compose_message_renders_variables(make_lead, template):
    lead = make_lead(email="owner@acmeauto.com", company_name="Acme Auto Detailing",
                     city="Dallas", state="TX")
    message = compose_message(lead=lead, template=template, use_ai=False)
    assert "Acme Auto Detailing" in message.subject or "Acme Auto Detailing" in message.body_html
    assert "{{" not in message.body_html          # no unresolved placeholders
    assert "unsubscribe" in message.body_html.lower()
    assert message.headers["List-Unsubscribe"]


def test_compose_adds_tracking_and_footer(make_lead, template):
    lead = make_lead(email="owner@acmeauto.com")
    message = compose_message(lead=lead, template=template, use_ai=False)
    message.save()
    assert f"/t/o/{message.uid}.png" in message.body_html
    assert message.unsubscribe_url in message.body_html
    assert message.body_text.strip()


def test_send_success(make_lead, template):
    lead = make_lead(email="owner@acmeauto.com")
    message = compose_message(lead=lead, template=template, use_ai=False)
    message.save()
    result = send_message(message)

    assert result["status"] == "SENT"
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["owner@acmeauto.com"]
    message.refresh_from_db()
    lead.refresh_from_db()
    assert message.status == EmailMessage.Status.SENT
    assert message.sent_at is not None
    assert lead.times_contacted == 1
    assert lead.lead_status == LeadStatus.CONTACTED
    assert EmailEvent.objects.filter(message=message, type=EmailEvent.Type.SENT).exists()


def test_send_is_idempotent(make_lead, template):
    lead = make_lead(email="owner@acmeauto.com")
    message = compose_message(lead=lead, template=template, use_ai=False)
    message.save()
    send_message(message)
    result = send_message(message)
    assert result["status"] == "SENT"
    assert result["detail"] == "Already processed"
    assert len(mail.outbox) == 1


def test_transient_failure_retries_later(make_lead, template, monkeypatch):
    def boom(message):
        raise TransientSendError("421 Service not available")

    monkeypatch.setattr("apps.email_engine.sender.deliver", boom)
    lead = make_lead(email="owner@acmeauto.com")
    message = compose_message(lead=lead, template=template, use_ai=False)
    message.save()

    result = send_message(message)
    assert result["status"] == "FAILED"
    assert result["retryable"] is True
    message.refresh_from_db()
    assert message.attempt_count == 1
    assert message.status == EmailMessage.Status.FAILED


def test_permanent_failure_creates_suppression(make_lead, template, monkeypatch):
    def bounce(message):
        raise PermanentSendError("550 5.1.1 recipient rejected")

    monkeypatch.setattr("apps.email_engine.sender.deliver", bounce)
    lead = make_lead(email="dead@acmeauto.com")
    message = compose_message(lead=lead, template=template, use_ai=False)
    message.save()

    result = send_message(message)
    assert result["status"] == "BOUNCED"
    message.refresh_from_db()
    lead.refresh_from_db()
    assert message.status == EmailMessage.Status.BOUNCED
    assert lead.email_status == EmailStatus.BOUNCED
    assert lead.is_blocked is True
    assert Suppression.objects.filter(email_normalized="dead@acmeauto.com",
                                      reason=Suppression.Reason.BOUNCED).exists()
    assert EmailEvent.objects.filter(message=message,
                                     type=EmailEvent.Type.BOUNCED).exists()


def test_retry_then_success(make_lead, template, monkeypatch):
    calls = {"n": 0}

    def flaky(message):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TransientSendError("450 greylisted")

    monkeypatch.setattr("apps.email_engine.sender.deliver", flaky)
    set_setting("sending.max_attempts", 3)
    lead = make_lead(email="owner@acmeauto.com")
    message = compose_message(lead=lead, template=template, use_ai=False)
    message.save()

    send_email_message(message.pk)          # fails, reschedules
    message.refresh_from_db()
    assert message.status == EmailMessage.Status.QUEUED
    assert message.scheduled_at > timezone.now()

    send_email_message(message.pk)          # succeeds
    message.refresh_from_db()
    assert message.status == EmailMessage.Status.SENT


def test_eligibility_gate_before_sending(make_lead, template, monkeypatch):
    monkeypatch.setattr("apps.email_engine.sender.deliver", lambda message: None)
    lead = make_lead(email="blocked@acme.com")
    lead.is_blocked = True
    lead.blocked_reason = "Manual review"
    lead.save(update_fields=["is_blocked", "blocked_reason"])

    message = compose_message(lead=lead, template=template, use_ai=False)
    message.save()
    result = send_message(message)
    assert result["status"] == "SKIPPED"
    assert len(mail.outbox) == 0


def test_send_due_emails_queues_and_sends(make_lead, template, monkeypatch):
    monkeypatch.setattr("apps.email_engine.sender.deliver", lambda message: None)
    set_setting("sending.weekdays", [1, 2, 3, 4, 5, 6, 7])
    campaign = Campaign.objects.create(name="Q", template=template)
    for index in range(3):
        lead = make_lead(email=f"lead{index}@acme.com")
        campaign_lead = CampaignLead.objects.create(campaign=campaign, lead=lead)
        EmailMessage.objects.create(
            campaign=campaign, campaign_lead=campaign_lead, lead=lead,
            to_email=lead.email_normalized, subject="Hi", body_html="<p>x</p>",
            from_email="us@example.com", scheduled_at=timezone.now(),
        )

    result = send_due_emails()
    assert result["sent"] == 3
    assert EmailMessage.objects.filter(status=EmailMessage.Status.SENT).count() == 3


def test_open_and_click_tracking(db, anon_client, make_lead, template, monkeypatch):
    monkeypatch.setattr("apps.email_engine.sender.deliver", lambda message: None)
    lead = make_lead(email="owner@acme.com")
    message = compose_message(lead=lead, template=template, use_ai=False)
    message.save()
    send_message(message)

    response = anon_client.get(f"/t/o/{message.uid}.png")
    assert response.status_code == 200
    message.refresh_from_db()
    assert message.opened_at is not None
    assert message.open_count == 1

    message_uid = message.uid
    response = anon_client.get(f"/t/c/{message_uid}?u=https%3A%2F%2Fexample.com%2Fbook")
    assert response.status_code == 302
    assert response["Location"] == "https://example.com/book"
    message.refresh_from_db()
    assert message.clicked_at is not None


def test_tracking_ignores_unknown_uid(anon_client, db):
    assert anon_client.get("/t/o/deadbeef.png").status_code == 200
