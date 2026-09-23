"""Shared building blocks: timestamps, soft-delete, audit trail."""
from __future__ import annotations

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class TimeStampedModel(models.Model):
    """created_at / updated_at for every domain model."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """Opt-in soft delete. Nothing is physically destroyed by default."""

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self) -> None:
        from django.utils import timezone

        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


class AuditLog(models.Model):
    """Append-only record of every meaningful action in the platform."""

    class Action(models.TextChoices):
        # Auth
        LOGIN = "LOGIN", "Login"
        LOGOUT = "LOGOUT", "Logout"
        LOGIN_FAILED = "LOGIN_FAILED", "Login failed"
        # Imports
        IMPORT_STARTED = "IMPORT_STARTED", "Import started"
        IMPORT_UPLOADED = "IMPORT_UPLOADED", "Import file uploaded"
        IMPORT_MAPPING_SAVED = "IMPORT_MAPPING_SAVED", "Import mapping saved"
        IMPORT_PROGRESS = "IMPORT_PROGRESS", "Import progress"
        IMPORT_COMPLETED = "IMPORT_COMPLETED", "Import completed"
        IMPORT_FAILED = "IMPORT_FAILED", "Import failed"
        IMPORT_CANCELLED = "IMPORT_CANCELLED", "Import cancelled"
        # Leads
        LEAD_CREATED = "LEAD_CREATED", "Lead created"
        LEAD_UPDATED = "LEAD_UPDATED", "Lead updated"
        LEAD_MERGED = "LEAD_MERGED", "Lead merged"
        LEAD_SCORED = "LEAD_SCORED", "Lead rescored"
        LEAD_STATUS_CHANGED = "LEAD_STATUS_CHANGED", "Lead status changed"
        LEAD_SUPPRESSED = "LEAD_SUPPRESSED", "Lead suppressed"
        LEAD_ENRICHED = "LEAD_ENRICHED", "Lead enriched"
        # Campaigns
        CAMPAIGN_CREATED = "CAMPAIGN_CREATED", "Campaign created"
        CAMPAIGN_UPDATED = "CAMPAIGN_UPDATED", "Campaign updated"
        CAMPAIGN_STARTED = "CAMPAIGN_STARTED", "Campaign started"
        CAMPAIGN_PAUSED = "CAMPAIGN_PAUSED", "Campaign paused"
        CAMPAIGN_CANCELLED = "CAMPAIGN_CANCELLED", "Campaign cancelled"
        CAMPAIGN_COMPLETED = "CAMPAIGN_COMPLETED", "Campaign completed"
        # Email
        EMAIL_QUEUED = "EMAIL_QUEUED", "Email queued"
        EMAIL_SENT = "EMAIL_SENT", "Email sent"
        EMAIL_FAILED = "EMAIL_FAILED", "Email failed"
        EMAIL_BOUNCED = "EMAIL_BOUNCED", "Email bounced"
        EMAIL_OPENED = "EMAIL_OPENED", "Email opened"
        EMAIL_CLICKED = "EMAIL_CLICKED", "Email clicked"
        EMAIL_REPLIED = "EMAIL_REPLIED", "Email replied"
        UNSUBSCRIBED = "UNSUBSCRIBED", "Unsubscribed"
        QUOTA_REACHED = "QUOTA_REACHED", "Daily quota reached"
        # CRM / AI / settings
        CRM_STAGE_CHANGED = "CRM_STAGE_CHANGED", "CRM stage changed"
        AI_GENERATION = "AI_GENERATION", "AI generation"
        AI_FAILED = "AI_FAILED", "AI generation failed"
        SETTINGS_UPDATED = "SETTINGS_UPDATED", "Settings updated"
        SUPPRESSION_ADDED = "SUPPRESSION_ADDED", "Suppression added"
        SUPPRESSION_REMOVED = "SUPPRESSION_REMOVED", "Suppression removed"
        EXPORT = "EXPORT", "Data exported"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    actor_email = models.EmailField(blank=True, default="")
    action = models.CharField(max_length=40, choices=Action.choices, db_index=True)
    entity_type = models.CharField(max_length=80, blank=True, default="", db_index=True)
    entity_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    # Optional generic FK for objects that still exist.
    content_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL
    )
    object_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    content_object = GenericForeignKey("content_type", "object_id")
    description = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["action", "created_at"]),
        ]
        verbose_name = "Audit log"
        verbose_name_plural = "Audit logs"

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.action} · {self.entity_type or '-'} · {self.created_at:%Y-%m-%d %H:%M}"


def log_audit(
    *,
    action: str,
    actor=None,
    entity_type: str = "",
    entity_id=None,
    description: str = "",
    metadata: dict | None = None,
    obj=None,
    request=None,
) -> AuditLog:
    """Small helper used across the codebase (and from Celery tasks)."""
    ip = None
    user_agent = ""
    if request is not None:
        try:
            ip = request.META.get("REMOTE_ADDR") or None
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:400]
        except Exception:  # pragma: no cover - defensive
            pass

    return AuditLog.objects.create(
        actor=actor if (actor is None or getattr(actor, "pk", None)) else None,
        actor_email=getattr(actor, "email", "") or (metadata or {}).get("actor_email", ""),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else "",
        description=description,
        metadata=metadata or {},
        content_object=obj,
        ip_address=ip,
        user_agent=user_agent,
    )
