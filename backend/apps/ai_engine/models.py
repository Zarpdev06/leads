from __future__ import annotations

import hashlib

from django.conf import settings
from django.db import models

from apps.core.fields import EncryptedCharField, EncryptedTextField
from apps.core.models import TimeStampedModel


class AIProviderConfig(TimeStampedModel):
    """Connection details for an AI provider (keys stored encrypted)."""

    PROVIDER_CHOICES = [
        ("rules", "Rule-based (offline, no API key)"),
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("ollama", "Ollama (local)"),
    ]

    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES, unique=True)
    label = models.CharField(max_length=120, blank=True, default="")
    model = models.CharField(max_length=120, blank=True, default="")
    base_url = models.CharField(max_length=500, blank=True, default="")
    api_key = EncryptedCharField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    temperature = models.FloatField(default=0.4)
    max_tokens = models.PositiveIntegerField(default=700)
    extra = models.JSONField(default=dict, blank=True)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_test_ok = models.BooleanField(null=True)
    last_error = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ("provider",)
        verbose_name = "AI provider"
        verbose_name_plural = "AI providers"

    def __str__(self) -> str:
        return self.label or self.provider

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)


class AIRecommendation(TimeStampedModel):
    """Cached AI output for a lead (also the audit trail for AI usage)."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        GENERATED = "GENERATED", "Generated"
        FAILED = "FAILED", "Failed"
        REJECTED = "REJECTED", "Rejected by safety check"
        APPROVED = "APPROVED", "Approved"

    lead = models.ForeignKey(
        "leads.Lead", null=True, blank=True, on_delete=models.CASCADE,
        related_name="ai_recommendations",
    )
    campaign = models.ForeignKey(
        "campaigns.Campaign", null=True, blank=True, on_delete=models.CASCADE,
        related_name="ai_recommendations",
    )
    service = models.ForeignKey(
        "campaigns.Service", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="recommendations",
    )
    provider = models.CharField(max_length=32, default="rules")
    model = models.CharField(max_length=120, blank=True, default="")

    subject = models.CharField(max_length=400, blank=True, default="")
    opening_sentence = models.TextField(blank=True, default="")
    personalization = models.TextField(blank=True, default="")
    value_proposition = models.TextField(blank=True, default="")
    cta = models.TextField(blank=True, default="")
    body_html = models.TextField(blank=True, default="")
    body_text = models.TextField(blank=True, default="")
    recommended_service = models.CharField(max_length=180, blank=True, default="")
    rationale = models.TextField(blank=True, default="")
    confidence = models.FloatField(default=0.0)

    prompt = models.TextField(blank=True, default="")
    raw_response = models.JSONField(default=dict, blank=True)
    context = models.JSONField(default=dict, blank=True)
    context_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING,
                              db_index=True)
    safety_passed = models.BooleanField(default=True)
    safety_notes = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True, default="")
    tokens_used = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="approved_recommendations",
    )
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "AI recommendation"
        verbose_name_plural = "AI recommendations"
        indexes = [
            models.Index(fields=["lead", "provider", "context_hash"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.provider} · {self.recommended_service or self.subject[:40]}"

    @staticmethod
    def hash_context(context: dict) -> str:
        import json

        payload = json.dumps(context, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()
