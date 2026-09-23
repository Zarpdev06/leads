"""
Email templates, messages, events, follow-up sequences and the daily quota.

`EmailMessage` is the unit of work for the sending pipeline. The unique
constraint on (campaign_lead, step_number) is what makes Celery retries safe:
a retried task can never create a second copy of the same email.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


def new_uid() -> str:
    return uuid.uuid4().hex


def new_unsubscribe_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex[:8]


class EmailTemplate(TimeStampedModel):
    """Reusable template with {{variable}} placeholders."""

    class Category(models.TextChoices):
        COLD_OUTREACH = "COLD_OUTREACH", "Cold outreach"
        FOLLOW_UP = "FOLLOW_UP", "Follow-up"
        MEETING = "MEETING", "Meeting request"
        PROPOSAL = "PROPOSAL", "Proposal"
        RE_ENGAGE = "RE_ENGAGE", "Re-engagement"
        CUSTOM = "CUSTOM", "Custom"

    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.COLD_OUTREACH
    )
    subject = models.CharField(max_length=300)
    preheader = models.CharField(max_length=300, blank=True, default="")
    body_html = models.TextField()
    body_text = models.TextField(blank=True, default="")
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    is_default = models.BooleanField(default=False)
    variables = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    usage_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("name",)
        verbose_name = "Email template"
        verbose_name_plural = "Email templates"

    def __str__(self) -> str:
        return self.name


class FollowUpSequence(TimeStampedModel):
    """Configurable follow-up sequence (campaign-level)."""

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    stop_on_reply = models.BooleanField(default=True)
    stop_on_bounce = models.BooleanField(default=True)
    stop_on_unsubscribe = models.BooleanField(default=True)
    stop_on_click = models.BooleanField(default=False)
    stop_on_converted = models.BooleanField(default=True)
    max_steps = models.PositiveIntegerField(default=4)

    class Meta:
        ordering = ("name",)
        verbose_name = "Follow-up sequence"
        verbose_name_plural = "Follow-up sequences"

    def __str__(self) -> str:
        return self.name


class FollowUpStep(TimeStampedModel):
    class Condition(models.TextChoices):
        ALWAYS = "ALWAYS", "Always"
        NO_REPLY = "NO_REPLY", "No reply yet"
        NO_OPEN = "NO_OPEN", "Not opened yet"
        NO_CLICK = "NO_CLICK", "Not clicked yet"

    sequence = models.ForeignKey(
        FollowUpSequence, on_delete=models.CASCADE, related_name="steps"
    )
    order = models.PositiveIntegerField(default=0, db_index=True)
    delay_days = models.PositiveIntegerField(default=3)
    delay_hours = models.PositiveIntegerField(default=0)
    condition = models.CharField(
        max_length=16, choices=Condition.choices, default=Condition.NO_REPLY
    )
    template = models.ForeignKey(
        EmailTemplate, null=True, blank=True, on_delete=models.SET_NULL, related_name="followup_steps"
    )
    subject = models.CharField(max_length=300, blank=True, default="")
    body_html = models.TextField(blank=True, default="")
    use_ai = models.BooleanField(default=True)
    ai_instructions = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("order",)
        verbose_name = "Follow-up step"
        verbose_name_plural = "Follow-up steps"
        constraints = [
            models.UniqueConstraint(fields=["sequence", "order"], name="uniq_sequence_step")
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.sequence} · step {self.order} (+{self.delay_days}d)"


class EmailMessage(TimeStampedModel):
    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        PROCESSING = "PROCESSING", "Processing"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"
        BOUNCED = "BOUNCED", "Bounced"
        CANCELLED = "CANCELLED", "Cancelled"
        SKIPPED = "SKIPPED", "Skipped (quota/suppression)"

    campaign = models.ForeignKey(
        "campaigns.Campaign", null=True, blank=True, on_delete=models.CASCADE,
        related_name="email_messages",
    )
    campaign_lead = models.ForeignKey(
        "campaigns.CampaignLead", null=True, blank=True, on_delete=models.CASCADE,
        related_name="email_messages",
    )
    lead = models.ForeignKey(
        "leads.Lead", null=True, blank=True, on_delete=models.CASCADE,
        related_name="email_messages",
    )
    template = models.ForeignKey(
        EmailTemplate, null=True, blank=True, on_delete=models.SET_NULL, related_name="messages"
    )
    step_number = models.PositiveIntegerField(default=0, db_index=True)

    uid = models.CharField(max_length=64, unique=True, default=new_uid, db_index=True)
    unsubscribe_token = models.CharField(
        max_length=64, unique=True, default=new_unsubscribe_token, db_index=True
    )

    to_email = models.EmailField(db_index=True)
    to_name = models.CharField(max_length=255, blank=True, default="")
    from_email = models.EmailField()
    from_name = models.CharField(max_length=180, blank=True, default="")
    reply_to = models.EmailField(blank=True, default="")

    subject = models.CharField(max_length=400)
    body_html = models.TextField()
    body_text = models.TextField(blank=True, default="")
    headers = models.JSONField(default=dict, blank=True)

    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.QUEUED, db_index=True
    )
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    processing_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    replied_at = models.DateTimeField(null=True, blank=True, db_index=True)
    bounced_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    open_count = models.PositiveIntegerField(default=0)
    click_count = models.PositiveIntegerField(default=0)
    attempt_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    provider_message_id = models.CharField(max_length=255, blank=True, default="")

    is_ai_generated = models.BooleanField(default=False, db_index=True)
    ai_provider = models.CharField(max_length=40, blank=True, default="")
    ai_model = models.CharField(max_length=80, blank=True, default="")
    ai_prompt = models.TextField(blank=True, default="")
    ai_response = models.JSONField(default=dict, blank=True)
    recommended_service = models.CharField(max_length=180, blank=True, default="")

    is_transactional = models.BooleanField(
        default=False, help_text="Transactional mail does not consume the marketing quota."
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Email message"
        verbose_name_plural = "Email messages"
        indexes = [
            models.Index(fields=["status", "scheduled_at"]),
            models.Index(fields=["campaign", "status"]),
            models.Index(fields=["lead", "created_at"]),
            models.Index(fields=["to_email", "created_at"]),
            models.Index(fields=["sent_at"]),
            models.Index(fields=["step_number"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign_lead", "step_number"],
                name="uniq_campaign_lead_step",
                condition=models.Q(campaign_lead__isnull=False),
            )
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.to_email} · {self.subject[:40]}"

    # ------------------------------------------------------------------
    def mark_processing(self) -> None:
        self.status = self.Status.PROCESSING
        self.processing_at = timezone.now()
        self.attempt_count += 1
        self.save(update_fields=["status", "processing_at", "attempt_count", "updated_at"])

    def mark_sent(self, *, message_id: str = "") -> None:
        now = timezone.now()
        self.status = self.Status.SENT
        self.sent_at = now
        self.provider_message_id = message_id or ""
        self.last_error = ""
        self.save(update_fields=[
            "status", "sent_at", "provider_message_id", "last_error", "updated_at"
        ])

    def mark_failed(self, error: str, *, bounced: bool = False) -> None:
        now = timezone.now()
        self.last_error = str(error)[:2000]
        if bounced:
            self.status = self.Status.BOUNCED
            self.bounced_at = now
        else:
            self.status = self.Status.FAILED
            self.failed_at = now
        self.save(update_fields=[
            "status", "last_error", "bounced_at", "failed_at", "updated_at"
        ])

    def mark_cancelled(self, reason: str = "") -> None:
        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()
        if reason:
            self.metadata = {**self.metadata, "cancel_reason": reason}
        self.save(update_fields=["status", "cancelled_at", "metadata", "updated_at"])

    def mark_skipped(self, reason: str) -> None:
        self.status = self.Status.SKIPPED
        self.last_error = reason[:500]
        self.save(update_fields=["status", "last_error", "updated_at"])

    @property
    def tracking_pixel_url(self) -> str:
        return f"/t/o/{self.uid}.png"

    @property
    def unsubscribe_url(self) -> str:
        return f"/unsubscribe/{self.unsubscribe_token}"


class EmailEvent(TimeStampedModel):
    class Type(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        SENT = "SENT", "Sent"
        DELIVERED = "DELIVERED", "Delivered"
        OPENED = "OPENED", "Opened"
        CLICKED = "CLICKED", "Clicked"
        REPLIED = "REPLIED", "Replied"
        BOUNCED = "BOUNCED", "Bounced"
        FAILED = "FAILED", "Failed"
        UNSUBSCRIBED = "UNSUBSCRIBED", "Unsubscribed"
        COMPLAINT = "COMPLAINT", "Spam complaint"
        CANCELLED = "CANCELLED", "Cancelled"
        SKIPPED = "SKIPPED", "Skipped"

    message = models.ForeignKey(
        EmailMessage, on_delete=models.CASCADE, related_name="events"
    )
    type = models.CharField(max_length=16, choices=Type.choices, db_index=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    url = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True, default="")

    class Meta:
        ordering = ("-occurred_at",)
        verbose_name = "Email event"
        verbose_name_plural = "Email events"
        indexes = [models.Index(fields=["message", "type"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.type} · {self.message_id}"


class DailyEmailUsage(models.Model):
    """One row per calendar day: the single source of truth for the quota."""

    date = models.DateField(unique=True, db_index=True)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    bounced_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    transactional_count = models.PositiveIntegerField(default=0)
    limit = models.PositiveIntegerField(default=90)
    smtp_limit = models.PositiveIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-date",)
        verbose_name = "Daily email usage"
        verbose_name_plural = "Daily email usage"

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.date}: {self.sent_count}/{self.limit}"

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.sent_count)

    @property
    def percent_used(self) -> float:
        return min(100.0, (self.sent_count / self.limit * 100) if self.limit else 0.0)
