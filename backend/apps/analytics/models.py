"""
Pre-aggregated metrics.

Everything here can be recomputed from the source tables
(`analytics.tasks.build_daily_metrics`); the tables exist so that dashboards
over tens of millions of rows stay instant.
"""
from __future__ import annotations

from django.db import models


class DailyMetric(models.Model):
    date = models.DateField(db_index=True)
    scope = models.CharField(max_length=40, default="global", db_index=True)
    key = models.CharField(max_length=60, db_index=True)
    dimension = models.CharField(max_length=180, blank=True, default="", db_index=True)
    value = models.FloatField(default=0)

    class Meta:
        ordering = ("-date", "scope", "key")
        verbose_name = "Daily metric"
        verbose_name_plural = "Daily metrics"
        constraints = [
            models.UniqueConstraint(
                fields=["date", "scope", "key", "dimension"],
                name="uniq_daily_metric",
            )
        ]
        indexes = [models.Index(fields=["key", "date"])]


class CampaignDailyStat(models.Model):
    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.CASCADE, related_name="daily_stats"
    )
    date = models.DateField(db_index=True)
    sent = models.PositiveIntegerField(default=0)
    delivered = models.PositiveIntegerField(default=0)
    opened = models.PositiveIntegerField(default=0)
    clicked = models.PositiveIntegerField(default=0)
    replied = models.PositiveIntegerField(default=0)
    bounced = models.PositiveIntegerField(default=0)
    unsubscribed = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-date",)
        verbose_name = "Campaign daily stat"
        verbose_name_plural = "Campaign daily stats"
        constraints = [
            models.UniqueConstraint(fields=["campaign", "date"], name="uniq_campaign_daily")
        ]


class ImportDailyStat(models.Model):
    source = models.ForeignKey(
        "imports.LeadSource", on_delete=models.CASCADE, related_name="daily_stats"
    )
    date = models.DateField(db_index=True)
    rows = models.PositiveBigIntegerField(default=0)
    with_email = models.PositiveBigIntegerField(default=0)
    without_email = models.PositiveBigIntegerField(default=0)
    invalid_email = models.PositiveBigIntegerField(default=0)
    duplicates = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ("-date",)
        verbose_name = "Import daily stat"
        verbose_name_plural = "Import daily stats"
        constraints = [
            models.UniqueConstraint(fields=["source", "date"], name="uniq_source_daily")
        ]
