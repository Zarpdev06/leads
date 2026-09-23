"""Follow-up sequences and stop conditions."""
import pytest
from django.utils import timezone

from apps.campaigns.models import Campaign, CampaignLead
from apps.email_engine.models import EmailMessage, FollowUpSequence, FollowUpStep
from apps.email_engine.sender import compose_message, send_message
from apps.email_engine.services import process_follow_ups, schedule_next_follow_up
from apps.leads.models import CRMStage


@pytest.fixture
def sequence(db):
    seq = FollowUpSequence.objects.create(name="Standard")
    FollowUpStep.objects.create(sequence=seq, order=1, delay_days=3,
                                condition=FollowUpStep.Condition.NO_REPLY)
    FollowUpStep.objects.create(sequence=seq, order=2, delay_days=7,
                                condition=FollowUpStep.Condition.NO_REPLY)
    FollowUpStep.objects.create(sequence=seq, order=3, delay_days=14,
                                condition=FollowUpStep.Condition.NO_REPLY)
    return seq


def test_follow_up_is_scheduled_after_send(make_lead, template, sequence, monkeypatch):
    monkeypatch.setattr("apps.email_engine.sender.deliver", lambda message: None)
    lead = make_lead(email="owner@acme.com")
    campaign = Campaign.objects.create(name="C", template=template,
                                       follow_up_enabled=True,
                                       follow_up_sequence=sequence,
                                       status=Campaign.Status.RUNNING)
    campaign_lead = CampaignLead.objects.create(campaign=campaign, lead=lead)
    message = compose_message(lead=lead, template=template, campaign=campaign,
                              campaign_lead=campaign_lead, use_ai=False)
    message.save()
    send_message(message)

    follow_up = schedule_next_follow_up(campaign_lead)
    assert follow_up is not None
    assert follow_up.step_number == 1
    assert follow_up.scheduled_at > timezone.now()
    campaign_lead.refresh_from_db()
    assert campaign_lead.status == CampaignLead.Status.FOLLOW_UP
    assert campaign_lead.next_follow_up_at is not None
    assert campaign_lead.current_step == 1


def test_follow_up_creation_is_idempotent(make_lead, template, sequence, monkeypatch):
    monkeypatch.setattr("apps.email_engine.sender.deliver", lambda message: None)
    lead = make_lead(email="owner@acme.com")
    campaign = Campaign.objects.create(name="C", template=template,
                                       follow_up_sequence=sequence,
                                       status=Campaign.Status.RUNNING)
    campaign_lead = CampaignLead.objects.create(campaign=campaign, lead=lead)
    message = compose_message(lead=lead, template=template, campaign=campaign,
                              campaign_lead=campaign_lead, use_ai=False)
    message.save()
    send_message(message)

    assert schedule_next_follow_up(campaign_lead) is not None
    # Re-running the same step (e.g. a retried Celery task) must not duplicate.
    campaign_lead.current_step = 0
    campaign_lead.save(update_fields=["current_step"])
    assert schedule_next_follow_up(campaign_lead) is None
    assert EmailMessage.objects.filter(campaign_lead=campaign_lead,
                                       step_number=1).count() == 1


@pytest.mark.parametrize("stopper", ["reply", "unsubscribe", "bounce", "converted",
                                     "do_not_contact"])
def test_follow_up_stops_on_key_events(make_lead, template, sequence, stopper, monkeypatch):
    monkeypatch.setattr("apps.email_engine.sender.deliver", lambda message: None)
    lead = make_lead(email="owner@acme.com")
    campaign = Campaign.objects.create(name="C", template=template,
                                       follow_up_sequence=sequence,
                                       status=Campaign.Status.RUNNING)
    campaign_lead = CampaignLead.objects.create(campaign=campaign, lead=lead)
    message = compose_message(lead=lead, template=template, campaign=campaign,
                              campaign_lead=campaign_lead, use_ai=False)
    message.save()
    send_message(message)

    now = timezone.now()
    if stopper == "reply":
        lead.replied_at = now
        lead.save(update_fields=["replied_at"])
    elif stopper == "unsubscribe":
        lead.unsubscribed_at = now
        lead.save(update_fields=["unsubscribed_at"])
    elif stopper == "bounce":
        lead.bounced_at = now
        lead.save(update_fields=["bounced_at"])
    elif stopper == "converted":
        lead.set_stage(CRMStage.WON)
    elif stopper == "do_not_contact":
        lead.do_not_contact = True
        lead.save(update_fields=["do_not_contact"])

    assert schedule_next_follow_up(campaign_lead) is None
    campaign_lead.refresh_from_db()
    assert campaign_lead.status in {CampaignLead.Status.CANCELLED,
                                    CampaignLead.Status.COMPLETED,
                                    CampaignLead.Status.REPLIED}
    assert campaign_lead.next_follow_up_at is None


def test_sequence_completes_after_last_step(make_lead, template, sequence, monkeypatch):
    monkeypatch.setattr("apps.email_engine.sender.deliver", lambda message: None)
    lead = make_lead(email="owner@acme.com")
    campaign = Campaign.objects.create(name="C", template=template,
                                       follow_up_sequence=sequence,
                                       status=Campaign.Status.RUNNING)
    campaign_lead = CampaignLead.objects.create(campaign=campaign, lead=lead)
    message = compose_message(lead=lead, template=template, campaign=campaign,
                              campaign_lead=campaign_lead, use_ai=False)
    message.save()
    send_message(message)

    for step in range(1, 4):
        assert schedule_next_follow_up(campaign_lead) is not None
        campaign_lead.refresh_from_db()

    assert schedule_next_follow_up(campaign_lead) is None
    campaign_lead.refresh_from_db()
    assert campaign_lead.status == CampaignLead.Status.COMPLETED


def test_process_follow_ups_creates_due_messages(make_lead, template, sequence, monkeypatch):
    monkeypatch.setattr("apps.email_engine.sender.deliver", lambda message: None)
    lead = make_lead(email="owner@acme.com")
    campaign = Campaign.objects.create(name="C", template=template,
                                       follow_up_sequence=sequence,
                                       status=Campaign.Status.RUNNING)
    campaign_lead = CampaignLead.objects.create(
        campaign=campaign, lead=lead, status=CampaignLead.Status.SENT,
        sent_at=timezone.now() - timezone.timedelta(days=4),
        next_follow_up_at=timezone.now() - timezone.timedelta(days=1),
    )
    result = process_follow_ups(campaign)
    assert result["created"] == 1
    assert EmailMessage.objects.filter(campaign_lead=campaign_lead,
                                       step_number=1).exists()
