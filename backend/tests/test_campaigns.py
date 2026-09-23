"""Campaign audience filtering, dispatch scheduling and lifecycle."""
import pytest
from django.utils import timezone

from apps.campaigns.models import Campaign, CampaignLead
from apps.email_engine.models import EmailMessage
from apps.email_engine.services import (
    build_schedule,
    dispatch_campaign,
    materialize_campaign_leads,
    process_follow_ups,
)
from apps.leads.eligibility import eligible_queryset, evaluate_lead_eligibility
from apps.leads.models import Lead
from apps.settings.services import set_setting
from apps.suppression.models import Suppression


@pytest.fixture
def campaign(db, template, industry):
    return Campaign.objects.create(
        name="Auto Detailing TX", template=template, status=Campaign.Status.DRAFT,
        min_lead_score=0, daily_limit=90,
    )


def test_audience_filters_by_industry(campaign, make_lead):
    matching = make_lead(email="a@detail.com", company_name="Shine Detail")
    other = make_lead(email="b@dental.com", company_name="Smile Dental")
    other.sub_industry = None
    other.industry = None
    other.save()

    campaign.target_industries.set([matching.sub_industry])
    selected = eligible_queryset(campaign)
    assert list(selected.values_list("id", flat=True)) == [matching.pk]


def test_audience_filters_by_state_and_score(campaign, make_lead):
    good = make_lead(email="a@x.com", state="TX")
    make_lead(email="b@x.com", state="CA")
    campaign.target_states = ["TX"]
    campaign.save(update_fields=["target_states"])
    assert eligible_queryset(campaign).count() == 1

    good.lead_score = 10
    good.save(update_fields=["lead_score"])
    campaign.min_lead_score = 50
    campaign.save(update_fields=["min_lead_score"])
    assert eligible_queryset(campaign).count() == 0


def test_audience_excludes_missing_and_invalid_email(campaign, make_lead):
    make_lead(email="valid@x.com")
    make_lead(email="")
    make_lead(email="broken-email")
    assert eligible_queryset(campaign).count() == 1


def test_audience_excludes_suppressed(campaign, make_lead):
    lead = make_lead(email="blocked@x.com")
    Suppression.objects.create(email_normalized="blocked@x.com",
                               reason=Suppression.Reason.MANUAL_BLOCK)
    assert eligible_queryset(campaign).count() == 0


def test_audience_excludes_unsubscribed_and_dnc(campaign, make_lead):
    lead = make_lead(email="a@x.com")
    lead.unsubscribed_at = timezone.now()
    lead.save(update_fields=["unsubscribed_at"])
    assert eligible_queryset(campaign).count() == 0

    lead.unsubscribed_at = None
    lead.do_not_contact = True
    lead.save(update_fields=["unsubscribed_at", "do_not_contact"])
    assert eligible_queryset(campaign).count() == 0


def test_eligibility_reports_reasons(campaign, make_lead):
    make_lead(email="blocked@x.com")
    lead = Lead.objects.get(email_normalized="blocked@x.com")
    Suppression.objects.create(email_normalized="blocked@x.com",
                               reason=Suppression.Reason.BOUNCED)
    result = evaluate_lead_eligibility(lead)
    assert result.eligible is False
    assert result.code == "suppressed"


def test_materialize_is_idempotent(campaign, make_lead):
    for index in range(3):
        make_lead(email=f"lead{index}@x.com")
    first = materialize_campaign_leads(campaign)
    second = materialize_campaign_leads(campaign)
    assert first == 3
    assert second == 0
    assert CampaignLead.objects.filter(campaign=campaign).count() == 3


def test_dispatch_schedules_messages(campaign, make_lead, monkeypatch):
    monkeypatch.setattr("apps.email_engine.sender.compose_message",
                        _fake_compose)
    for index in range(5):
        make_lead(email=f"lead{index}@x.com")
    materialize_campaign_leads(campaign)
    result = dispatch_campaign(campaign)
    assert result["created"] == 5
    assert EmailMessage.objects.filter(campaign=campaign, step_number=0).count() == 5
    assert all(m.scheduled_at for m in EmailMessage.objects.filter(campaign=campaign))


def test_dispatch_is_retry_safe(campaign, make_lead, monkeypatch):
    monkeypatch.setattr("apps.email_engine.sender.compose_message", _fake_compose)
    make_lead(email="lead0@x.com")
    materialize_campaign_leads(campaign)
    dispatch_campaign(campaign)
    result = dispatch_campaign(campaign)
    assert result["created"] == 0
    assert EmailMessage.objects.filter(campaign=campaign).count() == 1


def test_schedule_spreads_over_days_and_window(campaign):
    set_setting("sending.window_start", "09:30")
    set_setting("sending.window_end", "17:30")
    schedule = build_schedule(campaign, count=200)
    assert len(schedule) == 200
    per_day = {}
    for moment in schedule:
        local = timezone.localtime(moment)
        per_day.setdefault(local.date(), 0)
        per_day[local.date()] += 1
        assert 9 <= local.hour <= 17
    # Never more than the daily limit on any single day.
    assert max(per_day.values()) <= campaign.daily_limit
    assert len(per_day) >= 3  # 200 emails at 90/day spans several days


def test_campaign_lifecycle(campaign, make_lead, admin_client):
    make_lead(email="a@x.com")
    response = admin_client.post(f"/api/campaigns/{campaign.pk}/start/", {}, format="json")
    assert response.status_code == 200
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.RUNNING

    response = admin_client.post(f"/api/campaigns/{campaign.pk}/pause/", {}, format="json")
    assert response.status_code == 200
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.PAUSED

    response = admin_client.post(f"/api/campaigns/{campaign.pk}/cancel/", {}, format="json")
    assert response.status_code == 200
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.CANCELLED


def test_audience_endpoint_counts(campaign, make_lead, api_client):
    for index in range(4):
        make_lead(email=f"lead{index}@x.com")
    make_lead(email="")
    response = api_client.get(f"/api/campaigns/{campaign.pk}/audience/")
    assert response.status_code == 200
    assert response.data["count"] == 4


def _fake_compose(*, lead, campaign, campaign_lead, step_number=0, **kwargs):
    from apps.email_engine.models import EmailMessage

    return EmailMessage(
        campaign=campaign, campaign_lead=campaign_lead, lead=lead,
        step_number=step_number, to_email=lead.email_normalized,
        subject=f"Hello {lead.company_name}", body_html="<p>Hi</p>",
        from_email="us@example.com",
    )
