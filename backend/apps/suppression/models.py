"""
Global suppression list.

A suppressed address must never receive another marketing email. The list is
checked *before* the daily quota is consumed (see
`email_engine.quota.DailyEmailQuota`).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Suppression(TimeStampedModel):
    class Reason(models.TextChoices):
        UNSUBSCRIBED = "UNSUBSCRIBED", "Unsubscribed"
        BOUNCED = "BOUNCED", "Bounced"
        COMPLAINT = "COMPLAINT", "Spam complaint"
        MANUAL_BLOCK = "MANUAL_BLOCK", "Manual block"
        DO_NOT_CONTACT = "DO_NOT_CONTACT", "Do not contact"
        INVALID = "INVALID", "Invalid address"
        IMPORT = "IMPORT", "Imported suppression list"

    email_normalized = models.EmailField(max_length=320, unique=True, db_index=True)
    email = models.CharField(max_length=320, blank=True, default="")
    reason = models.CharField(
        max_length=24, choices=Reason.choices, default=Reason.MANUAL_BLOCK, db_index=True
    )
    source = models.CharField(
        max_length=40, blank=True, default="MANUAL",
        help_text="UNSUBSCRIBE_LINK | BOUNCE_HANDLER | MANUAL | IMPORT | API",
    )
    note = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    lead = models.ForeignKey(
        "leads.Lead", null=True, blank=True, on_delete=models.SET_NULL, related_name="suppressions"
    )
    email_message = models.ForeignKey(
        "email_engine.EmailMessage", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="suppressions",
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Suppressed email"
        verbose_name_plural = "Suppressed emails"
        indexes = [
            models.Index(fields=["reason", "is_active"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.email_normalized} ({self.reason})"


class SuppressionLog(TimeStampedModel):
    """History of additions/removals for a suppressed address."""

    class Action(models.TextChoices):
        ADDED = "ADDED", "Added"
        REMOVED = "REMOVED", "Removed"
        REACTIVATED = "REACTIVATED", "Reactivated"
        UPDATED = "UPDATED", "Updated"

    suppression = models.ForeignKey(
        Suppression, null=True, blank=True, on_delete=models.SET_NULL, related_name="history"
    )
    email_normalized = models.EmailField(max_length=320, db_index=True)
    action = models.CharField(max_length=16, choices=Action.choices, default=Action.ADDED)
    reason = models.CharField(max_length=24, blank=True, default="")
    note = models.TextField(blank=True, default="")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Suppression log"
        verbose_name_plural = "Suppression logs"

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.action} · {self.email_normalized}"
