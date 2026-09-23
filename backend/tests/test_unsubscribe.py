"""Unsubscribe + suppression behaviour."""
import pytest

from apps.campaigns.models import Campaign, CampaignLead
from apps.email_engine.models import EmailMessage
from apps.email_engine.sender import compose_message, send_message
from apps.leads.eligibility import evaluate_lead_eligibility
from apps.leads.models import EmailStatus, Lead
from apps.suppression.models import Suppression
from apps.suppression.services import add_suppression, is_suppressed, remove_suppression


def test_unsubscribe_sets_everything(db, make_lead, template, anon_client, monkeypatch):
    monkeypatch.setattr("apps.email_engine.sender.deliver", lambda message: None)
    lead = make_lead(email="owner@acme.com")
    campaign = Campaign.objects.create(name="C", template=template)
    campaign_lead = CampaignLead.objects.create(campaign=campaign, lead=lead)
    message = compose_message(lead=lead, template=template, campaign=campaign,
                              campaign_lead=campaign_lead, use_ai=False)
    message.save()
    send_message(message)

    # A second, still queued message must be cancelled.
    queued = EmailMessage.objects.create(
        lead=lead, campaign=campaign, to_email=lead.email_normalized,
        subject="Follow-up", body_html="<p>x</p>", from_email="us@example.com",
        status=EmailMessage.Status.QUEUED, step_number=1,
    )

    response = anon_client.post(f"/api/unsubscribe/{message.unsubscribe_token}/")
    assert response.status_code == 200
    assert response.data["unsubscribed"] is True

    lead.refresh_from_db()
    queued.refresh_from_db()
    campaign_lead.refresh_from_db()
    assert lead.unsubscribed_at is not None
    assert lead.email_status == EmailStatus.UNSUBSCRIBED
    assert lead.is_blocked is True
    assert queued.status == EmailMessage.Status.CANCELLED
    assert campaign_lead.status == CampaignLead.Status.UNSUBSCRIBED
    assert is_suppressed("owner@acme.com")
    assert Suppression.objects.get(email_normalized="owner@acme.com").reason == "UNSUBSCRIBED"


def test_unsubscribe_is_idempotent(db, make_lead, template, anon_client):
    lead = make_lead(email="owner@acme.com")
    message = compose_message(lead=lead, template=template, use_ai=False)
    message.save()
    anon_client.post(f"/api/unsubscribe/{message.unsubscribe_token}/")
    response = anon_client.post(f"/api/unsubscribe/{message.unsubscribe_token}/")
    assert response.status_code == 200
    assert Suppression.objects.filter(email_normalized="owner@acme.com").count() == 1


def test_unsubscribed_lead_is_not_eligible(make_lead):
    lead = make_lead(email="owner@acme.com")
    lead.unsubscribed_at = __import__("django.utils.timezone", fromlist=["now"]).now()
    lead.save(update_fields=["unsubscribed_at"])
    result = evaluate_lead_eligibility(lead)
    assert not result.eligible
    assert result.code == "unsubscribed"


def test_invalid_token_returns_404(db, anon_client):
    assert anon_client.get("/api/unsubscribe/not-a-real-token/").status_code == 404


def test_suppression_service_add_remove(db):
    row, created = add_suppression("Blocked@Example.com", reason=Suppression.Reason.MANUAL_BLOCK)
    assert created is True
    assert row.email_normalized == "blocked@example.com"
    assert is_suppressed("blocked@example.com") is True
    assert is_suppressed("other@example.com") is False

    # Adding twice updates instead of duplicating.
    row2, created2 = add_suppression("blocked@example.com",
                                     reason=Suppression.Reason.COMPLAINT)
    assert created2 is False
    assert row2.reason == Suppression.Reason.COMPLAINT
    assert Suppression.objects.count() == 1

    assert remove_suppression("blocked@example.com") is True
    assert is_suppressed("blocked@example.com") is False
    # History is retained for audit.
    from apps.suppression.models import SuppressionLog

    assert SuppressionLog.objects.filter(email_normalized="blocked@example.com").count() >= 2


def test_suppression_requires_valid_email(db):
    with pytest.raises(ValueError):
        add_suppression("not-an-email")


def test_suppression_api_requires_auth(db, anon_client, api_client):
    assert anon_client.get("/api/suppression/").status_code in {401, 403}
    assert api_client.get("/api/suppression/").status_code == 200
