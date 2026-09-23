"""
The 90/day guarantee.

These tests encode the hard requirement: with SMTP limit 100 and marketing
limit 90, email #91 must never be sent, and N concurrent workers must never
overshoot the limit.
"""
import threading

import pytest
from django.db import connection, connections

from apps.email_engine.models import DailyEmailUsage
from apps.email_engine.quota import DailyEmailQuota
from apps.settings.services import effective_daily_limit, set_setting
from apps.suppression.models import Suppression


@pytest.fixture
def limits(db):
    """SMTP 100 / marketing 90 / hard cap 90 (the defaults)."""
    set_setting("sending.smtp_daily_limit", 100)
    set_setting("sending.daily_marketing_limit", 90)
    DailyEmailUsage.objects.all().delete()
    return 90


def test_effective_limit_is_the_minimum(db, settings):
    settings.EMAIL_HARD_DAILY_CAP = 100
    set_setting("sending.smtp_daily_limit", 100)
    set_setting("sending.daily_marketing_limit", 90)
    assert effective_daily_limit() == 90

    # A marketing limit above the SMTP quota is clamped down.
    set_setting("sending.daily_marketing_limit", 250)
    assert effective_daily_limit() == 100

    # A marketing limit below the SMTP quota is respected.
    set_setting("sending.daily_marketing_limit", 40)
    assert effective_daily_limit() == 40


def test_89_sent_next_email_sends(db, limits):
    for _ in range(89):
        assert DailyEmailQuota.reserve().granted is True
    assert DailyEmailQuota.remaining() == 1
    reservation = DailyEmailQuota.reserve()
    assert reservation.granted is True
    assert DailyEmailQuota.remaining() == 0


def test_90_sent_next_email_is_refused(db, limits):
    for _ in range(90):
        assert DailyEmailQuota.reserve().granted is True
    assert DailyEmailQuota.remaining() == 0
    refused = DailyEmailQuota.reserve()
    assert refused.granted is False
    assert refused.reason == "Daily marketing limit reached"
    assert DailyEmailUsage.objects.first().sent_count == 90


def test_limit_can_never_exceed_hard_cap(db, settings):
    settings.EMAIL_HARD_DAILY_CAP = 90
    set_setting("sending.smtp_daily_limit", 500)
    set_setting("sending.daily_marketing_limit", 500)
    assert effective_daily_limit() == 90
    for _ in range(90):
        assert DailyEmailQuota.reserve().granted is True
    assert DailyEmailQuota.reserve().granted is False


def test_counter_is_per_calendar_day(db, limits):
    from datetime import date, timedelta

    for _ in range(90):
        DailyEmailQuota.reserve()
    assert DailyEmailQuota.reserve().granted is False
    # Tomorrow is a fresh budget.
    tomorrow = date.today() + timedelta(days=1)
    assert DailyEmailQuota.reserve(day=tomorrow).granted is True
    assert DailyEmailUsage.objects.count() == 2


@pytest.mark.parametrize("workers,limit", [(12, 90), (8, 5), (20, 3)])
@pytest.mark.django_db(transaction=True)
def test_concurrent_workers_cannot_overshoot(monkeypatch, workers, limit):
    """Multiple workers racing must still respect the daily limit."""
    set_setting("sending.smtp_daily_limit", limit)
    set_setting("sending.daily_marketing_limit", limit)
    DailyEmailUsage.objects.all().delete()

    barrier = threading.Barrier(workers)
    results: list[bool] = []
    lock = threading.Lock()

    def worker():
        # Each thread gets its own DB connection (threads never share one).
        try:
            barrier.wait(timeout=30)
            granted = DailyEmailQuota.reserve().granted
            with lock:
                results.append(granted)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert len(results) == workers
    assert sum(results) == min(workers, limit), (
        f"{sum(results)} reservations granted with limit {limit} and {workers} workers"
    )
    assert DailyEmailUsage.objects.get().sent_count == min(workers, limit)


def test_send_message_respects_the_quota(db, limits, make_lead, template, monkeypatch):
    """The sender path is gated by the quota, not just the reservation helper."""
    from apps.campaigns.models import Campaign
    from apps.email_engine.models import EmailMessage
    from apps.email_engine.sender import send_message

    monkeypatch.setattr("apps.email_engine.sender.deliver", lambda message: None)
    campaign = Campaign.objects.create(name="Quota", template=template)
    leads = [make_lead(email=f"lead{index}@example.com") for index in range(3)]

    # Exhaust the budget first.
    for _ in range(90):
        DailyEmailQuota.reserve()

    for index, lead in enumerate(leads):
        message = EmailMessage.objects.create(
            campaign=campaign, lead=lead, to_email=lead.email_normalized,
            subject="Hi", body_html="<p>Hi</p>", from_email="us@example.com",
            step_number=index,
        )
        result = send_message(message)
        assert result["status"] == "SKIPPED"
        assert result["detail"] == "quota_exhausted"
        assert message.status == EmailMessage.Status.SKIPPED

    assert DailyEmailUsage.objects.get().sent_count == 90


def test_send_due_emails_stops_at_the_limit(db, limits, make_lead, template, monkeypatch):
    from apps.campaigns.models import Campaign, CampaignLead
    from apps.email_engine.models import EmailMessage
    from apps.email_engine.tasks import send_due_emails
    from apps.settings.services import set_setting
    from django.utils import timezone

    monkeypatch.setattr("apps.email_engine.sender.deliver", lambda message: None)
    set_setting("sending.weekdays", [1, 2, 3, 4, 5, 6, 7])  # ignore the weekday filter
    set_setting("sending.min_days_between_contacts", 0)
    set_setting("sending.min_seconds_between_sends", 0)

    campaign = Campaign.objects.create(name="Blast", template=template)
    now = timezone.now()
    for index in range(120):
        lead = make_lead(email=f"person{index}@example.com")
        campaign_lead = CampaignLead.objects.create(campaign=campaign, lead=lead)
        EmailMessage.objects.create(
            campaign=campaign, campaign_lead=campaign_lead, lead=lead,
            to_email=lead.email_normalized, subject="Hi", body_html="<p>x</p>",
            from_email="us@example.com", status=EmailMessage.Status.QUEUED,
            scheduled_at=now,
        )

    result = send_due_emails(limit=200)
    assert result["sent"] == 90
    assert result["remaining"] == 0
    assert DailyEmailUsage.objects.get().sent_count == 90
    assert EmailMessage.objects.filter(status=EmailMessage.Status.QUEUED).count() == 30


def test_suppressed_addresses_do_not_consume_the_quota(db, limits, make_lead, template,
                                                       monkeypatch):
    from apps.email_engine.models import EmailMessage
    from apps.email_engine.sender import send_message

    monkeypatch.setattr("apps.email_engine.sender.deliver", lambda message: None)
    lead = make_lead(email="blocked@example.com")
    Suppression.objects.create(email_normalized="blocked@example.com",
                               reason=Suppression.Reason.MANUAL_BLOCK)
    message = EmailMessage.objects.create(
        lead=lead, to_email=lead.email_normalized, subject="Hi",
        body_html="<p>x</p>", from_email="us@example.com",
    )
    result = send_message(message)
    assert result["status"] == "SKIPPED"
    assert DailyEmailUsage.objects.filter().first() is None or \
        DailyEmailUsage.objects.first().sent_count == 0
