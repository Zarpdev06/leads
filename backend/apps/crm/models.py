"""
CRM pipeline: the activity timeline and notes.

The pipeline stage itself lives on `Lead.crm_stage` (indexed, filterable);
every change writes a `CRMActivity` so the timeline is complete and auditable.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.leads.models import CRMStage, Lead


class CRMActivity(TimeStampedModel):
    class Type(models.TextChoices):
        NOTE = "NOTE", "Note"
        IMPORT = "IMPORT", "Imported"
        EMAIL_QUEUED = "EMAIL_QUEUED", "Email queued"
        EMAIL_SENT = "EMAIL_SENT", "Email sent"
        EMAIL_OPENED = "EMAIL_OPENED", "Email opened"
        EMAIL_CLICKED = "EMAIL_CLICKED", "Email clicked"
        EMAIL_FAILED = "EMAIL_FAILED", "Email failed"
        EMAIL_BOUNCED = "EMAIL_BOUNCED", "Email bounced"
        REPLY = "REPLY", "Reply received"
        UNSUBSCRIBED = "UNSUBSCRIBED", "Unsubscribed"
        STAGE_CHANGE = "STAGE_CHANGE", "Pipeline stage changed"
        STATUS_CHANGE = "STATUS_CHANGE", "Status changed"
        MERGE = "MERGE", "Merged"
        CAMPAIGN_ADDED = "CAMPAIGN_ADDED", "Added to campaign"
        CAMPAIGN_REMOVED = "CAMPAIGN_REMOVED", "Removed from campaign"
        AI_GENERATED = "AI_GENERATED", "AI personalization"
        CALL = "CALL", "Call"
        MEETING = "MEETING", "Meeting"
        TASK = "TASK", "Task"
        ENRICHMENT = "ENRICHMENT", "Enrichment"
        SUPPRESSION = "SUPPRESSION", "Suppression"

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="activities")
    type = models.CharField(max_length=24, choices=Type.choices, default=Type.NOTE,
                            db_index=True)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="crm_activities",
    )
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    is_pinned = models.BooleanField(default=False)

    class Meta:
        ordering = ("-occurred_at",)
        verbose_name = "CRM activity"
        verbose_name_plural = "CRM activities"
        indexes = [
            models.Index(fields=["lead", "occurred_at"]),
            models.Index(fields=["type", "occurred_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.lead_id} · {self.type} · {self.title[:40]}"


class LeadNote(TimeStampedModel):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="notes")
    body = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="lead_notes",
    )
    is_pinned = models.BooleanField(default=False)

    class Meta:
        ordering = ("-is_pinned", "-created_at")
        verbose_name = "Lead note"
        verbose_name_plural = "Lead notes"

    def __str__(self) -> str:  # pragma: no cover
        return f"Note on {self.lead_id} by {self.author_id}"

    def save(self, *args, **kwargs):
        created = self.pk is None
        super().save(*args, **kwargs)
        if created:
            Lead.objects.filter(pk=self.lead_id).update(notes_count=models.F("notes_count") + 1)

    def delete(self, *args, **kwargs):
        Lead.objects.filter(pk=self.lead_id).update(
            notes_count=models.functions.Greatest(models.F("notes_count") - 1, 0)
        )
        super().delete(*args, **kwargs)


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------
PIPELINE_STAGES = [
    {"key": CRMStage.NEW, "label": "New", "color": "#64748b"},
    {"key": CRMStage.QUALIFIED, "label": "Qualified", "color": "#0ea5e9"},
    {"key": CRMStage.CONTACTED, "label": "Contacted", "color": "#6366f1"},
    {"key": CRMStage.REPLIED, "label": "Replied", "color": "#22c55e"},
    {"key": CRMStage.MEETING_REQUESTED, "label": "Meeting requested", "color": "#14b8a6"},
    {"key": CRMStage.MEETING_SCHEDULED, "label": "Meeting scheduled", "color": "#06b6d4"},
    {"key": CRMStage.PROPOSAL, "label": "Proposal", "color": "#f59e0b"},
    {"key": CRMStage.NEGOTIATION, "label": "Negotiation", "color": "#f97316"},
    {"key": CRMStage.WON, "label": "Won", "color": "#16a34a"},
    {"key": CRMStage.LOST, "label": "Lost", "color": "#ef4444"},
    {"key": CRMStage.DO_NOT_CONTACT, "label": "Do not contact", "color": "#991b1b"},
]


def pipeline_board(*, owner=None, queryset=None) -> list[dict]:
    """Leads grouped by stage, with totals and value. Server-side, paginated by caller."""
    from django.db.models import Count, Sum

    qs = queryset if queryset is not None else Lead.objects.filter(merged_into__isnull=True)
    if owner is not None:
        qs = qs.filter(owner=owner)

    grouped = (
        qs.values("crm_stage")
        .annotate(count=Count("id"), value=Sum("deal_value"))
        .order_by("crm_stage")
    )
    by_stage = {row["crm_stage"]: row for row in grouped}
    board = []
    for stage in PIPELINE_STAGES:
        row = by_stage.get(stage["key"], {"count": 0, "value": None})
        board.append({
            "stage": stage["key"],
            "label": stage["label"],
            "color": stage["color"],
            "count": row["count"],
            "value": float(row["value"] or 0),
        })
    return board
