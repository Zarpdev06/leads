"""Lead scoring engine and quality bands."""

from apps.leads.scoring import (
    DEFAULT_RULES,
    apply_score,
    get_rules,
    quality_for,
    rescore_queryset,
    score_lead,
)
from apps.leads.models import EmailStatus, Lead, LeadQuality
from apps.settings.services import set_setting


def test_score_components(make_lead):
    lead = make_lead(email="owner@acmeauto.com", website="acmeauto.com",
                     phone="2145550100", street_address="1 Main St")
    result = score_lead(lead)
    # valid email 20 + website 15 + contact 10 + company 10 + phone 10
    # + category 10 + location 10 + job title 0 + address 5 = 90 (website not verified)
    assert result.breakdown["valid_email"] == DEFAULT_RULES["valid_email"]
    assert result.breakdown["website_exists"] == 15
    assert result.breakdown["contact_person"] == 10
    assert result.score >= 80
    assert result.quality == LeadQuality.HOT


def test_missing_email_scores_low(make_lead):
    lead = make_lead(email="", with_industry=True)
    result = score_lead(lead)
    assert result.breakdown["no_email"] == -20
    assert result.quality == LeadQuality.UNQUALIFIED


def test_invalid_email_penalty(make_lead):
    lead = make_lead(email="not-an-email")
    assert lead.email_status == EmailStatus.INVALID
    result = score_lead(lead)
    assert result.breakdown["invalid_email"] == -30


def test_unsubscribed_and_bounced_penalties(make_lead):
    lead = make_lead(email="owner@acme.com")
    lead.unsubscribed_at = __import__("django.utils.timezone", fromlist=["now"]).now()
    assert score_lead(lead).breakdown["unsubscribed"] == -50

    other = make_lead(email="other@acme.com")
    other.email_status = EmailStatus.BOUNCED
    assert score_lead(other).breakdown["bounced"] == -100


def test_contacted_recently_penalty(make_lead):
    from datetime import timedelta

    from django.utils import timezone

    lead = make_lead(email="owner@acme.com")
    lead.times_contacted = 1
    lead.last_contacted_at = timezone.now() - timedelta(days=3)
    assert score_lead(lead).breakdown["contacted_too_recently"] == -100


def test_score_is_clamped_to_0_100(make_lead):
    lead = make_lead(email="bad-email")
    lead.email_status = EmailStatus.BOUNCED
    lead.unsubscribed_at = __import__("django.utils.timezone", fromlist=["now"]).now()
    assert score_lead(lead).score == 0
    assert score_lead(lead).quality == LeadQuality.UNQUALIFIED


def test_quality_thresholds(db):
    assert quality_for(80) == LeadQuality.HOT
    assert quality_for(75) == LeadQuality.HOT
    assert quality_for(60) == LeadQuality.WARM
    assert quality_for(30) == LeadQuality.COLD
    assert quality_for(10) == LeadQuality.UNQUALIFIED


def test_thresholds_are_configurable(make_lead):
    set_setting("scoring.thresholds", {"hot": 95, "warm": 80, "cold": 10})
    lead = make_lead(email="owner@acmeauto.com", website="acmeauto.com")
    assert score_lead(lead).quality in {LeadQuality.WARM, LeadQuality.COLD}
    set_setting("scoring.thresholds", {"hot": 75, "warm": 50, "cold": 25})


def test_rules_are_configurable(make_lead):
    set_setting("scoring.rules", {"valid_email": 50})
    assert get_rules()["valid_email"] == 50
    lead = make_lead(email="owner@acmeauto.com")
    assert score_lead(lead).breakdown["valid_email"] == 50
    set_setting("scoring.rules", {})


def test_apply_score_persists(make_lead):
    lead = make_lead(email="owner@acmeauto.com")
    lead.lead_score = 0
    lead.lead_quality = LeadQuality.UNQUALIFIED
    lead.save(update_fields=["lead_score", "lead_quality"])
    apply_score(lead)
    lead.refresh_from_db()
    assert lead.lead_score > 0
    assert lead.lead_quality != LeadQuality.UNQUALIFIED


def test_bulk_rescore(make_lead):
    for index in range(5):
        lead = make_lead(email=f"lead{index}@acme.com")
        lead.lead_score = 0
        lead.save(update_fields=["lead_score"])
    updated = rescore_queryset(Lead.objects.all())
    assert updated == 5
    assert Lead.objects.filter(lead_score__gt=0).count() == 5
