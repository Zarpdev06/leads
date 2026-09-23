"""Duplicate detection, confidence scoring and merging."""
import pytest

from apps.leads.dedupe import compare, detect_duplicates, find_duplicates_for_lead
from apps.leads.merge import merge_leads, resolve_duplicate
from apps.leads.models import Lead, LeadDuplicate


def test_same_email_is_100_percent(make_lead):
    lead = make_lead(email="a@acme.com", company_name="Acme One", city="Dallas")
    other = make_lead(email="a@acme.com", company_name="Acme Two", city="Austin")
    match = compare(lead, other)
    assert match is not None
    assert match.confidence == 100
    assert match.method == "Same email"


def test_company_and_website_is_95(make_lead):
    lead = make_lead(email="a@acme.com", company_name="Acme Auto", website="acmeauto.com")
    other = make_lead(email="b@acme.com", company_name="Acme Auto", website="acmeauto.com")
    match = compare(lead, other)
    assert match.confidence == 95


def test_company_and_phone_is_90(make_lead):
    lead = make_lead(email="a@acme.com", company_name="Acme Auto", phone="2145550100")
    other = make_lead(email="b@acme.com", company_name="Acme Auto", phone="214-555-0100")
    match = compare(lead, other)
    assert match.confidence == 90


def test_company_and_address_is_80(make_lead):
    lead = make_lead(email="a@acme.com", company_name="Acme Auto",
                     street_address="1200 Main St", phone="")
    other = make_lead(email="b@acme.com", company_name="Acme Auto",
                      street_address="1200 Main St", phone="")
    match = compare(lead, other)
    assert match.confidence == 80


def test_company_city_state_is_70(make_lead):
    lead = make_lead(email="a@acme.com", company_name="Acme Auto", city="Dallas",
                     state="TX", street_address="", phone="", website="")
    other = make_lead(email="b@acme.com", company_name="Acme Auto", city="Dallas",
                      state="TX", street_address="", phone="", website="")
    match = compare(lead, other)
    assert match.confidence == 70


def test_unrelated_records_do_not_match(make_lead):
    lead = make_lead(email="a@acme.com", company_name="Acme Auto", city="Dallas",
                     state="TX", street_address="", phone="", website="")
    other = make_lead(email="b@bravo.com", company_name="Bravo Dental", city="Boise",
                      state="ID", street_address="", phone="", website="")
    assert compare(lead, other) is None


def test_batch_detection_creates_review_rows(make_lead):
    make_lead(email="a@acme.com", company_name="Acme Auto", website="acmeauto.com")
    make_lead(email="b@acme.com", company_name="Acme Auto", website="acmeauto.com")
    make_lead(email="c@bravo.com", company_name="Bravo Dental", website="bravo.com")

    created = detect_duplicates()
    assert created >= 1
    duplicate = LeadDuplicate.objects.first()
    assert duplicate.resolution == LeadDuplicate.Resolution.PENDING
    assert duplicate.confidence >= 55


def test_detection_is_idempotent(make_lead):
    make_lead(email="a@acme.com", company_name="Acme Auto", website="acmeauto.com")
    make_lead(email="b@acme.com", company_name="Acme Auto", website="acmeauto.com")
    first = detect_duplicates()
    second = detect_duplicates()
    assert second == 0
    assert LeadDuplicate.objects.count() == first


def test_find_duplicates_for_lead(make_lead):
    lead = make_lead(email="a@acme.com", company_name="Acme Auto", website="acmeauto.com")
    make_lead(email="b@acme.com", company_name="Acme Auto", website="acmeauto.com")
    matches = find_duplicates_for_lead(lead)
    assert len(matches) == 1
    assert matches[0].candidate.email_normalized == "b@acme.com"


def test_merge_keeps_richest_record_and_history(make_lead):
    survivor = make_lead(email="", company_name="Acme Auto", phone="2145550100",
                         city="Dallas", state="TX")
    absorbed = make_lead(email="owner@acmeauto.com", company_name="Acme Auto",
                         website="acmeauto.com", city="Dallas", state="TX")
    survivor.source_name = "File A"
    survivor.save(update_fields=["source_name"])
    absorbed.source_name = "File B"
    absorbed.save(update_fields=["source_name"])

    summary = merge_leads(survivor, absorbed)

    survivor.refresh_from_db()
    absorbed.refresh_from_db()
    assert survivor.email_normalized == "owner@acmeauto.com"
    assert survivor.website_domain == "acmeauto.com"
    assert survivor.phone_normalized == "+12145550100"
    assert absorbed.merged_into_id == survivor.pk
    assert absorbed.is_duplicate is True
    # Source history is preserved on both records.
    sources = {entry["source"] for entry in survivor.raw_data["sources"]}
    assert {"File A", "File B"} <= sources
    assert summary["survivor_id"] == survivor.pk


def test_merge_moves_related_records(make_lead, template):
    from apps.campaigns.models import Campaign, CampaignLead
    from apps.email_engine.models import EmailMessage

    survivor = make_lead(email="owner@acmeauto.com", company_name="Acme Auto")
    absorbed = make_lead(email="billing@acmeauto.com", company_name="Acme Auto")
    campaign = Campaign.objects.create(name="C1", template=template)
    CampaignLead.objects.create(campaign=campaign, lead=absorbed)
    message = EmailMessage.objects.create(
        lead=absorbed, to_email="billing@acmeauto.com", subject="Hi",
        body_html="<p>Hi</p>", from_email="us@example.com",
    )

    merge_leads(survivor, absorbed)

    assert CampaignLead.objects.filter(lead=survivor, campaign=campaign).exists()
    assert EmailMessage.objects.get(pk=message.pk).lead_id == survivor.pk


def test_keep_both_resolution(make_lead):
    lead = make_lead(email="a@acme.com", company_name="Acme Auto", website="a.com")
    other = make_lead(email="b@acme.com", company_name="Acme Auto", website="a.com")
    detect_duplicates()
    duplicate = LeadDuplicate.objects.first()
    resolve_duplicate(duplicate, LeadDuplicate.Resolution.KEPT_BOTH)
    duplicate.refresh_from_db()
    other.refresh_from_db()
    assert duplicate.resolution == LeadDuplicate.Resolution.KEPT_BOTH
    assert other.merged_into_id is None
    assert other.duplicate_of_id in {lead.pk, other.pk}


def test_ignore_resolution_clears_flag(make_lead):
    lead = make_lead(email="a@acme.com", company_name="Acme Auto", website="a.com")
    make_lead(email="b@acme.com", company_name="Acme Auto", website="a.com")
    detect_duplicates()
    duplicate = LeadDuplicate.objects.first()
    lead.is_duplicate = True
    lead.save(update_fields=["is_duplicate"])
    resolve_duplicate(duplicate, LeadDuplicate.Resolution.IGNORED)
    lead.refresh_from_db()
    assert lead.is_duplicate is False
