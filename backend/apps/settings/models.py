"""Typed key/value configuration with an audit trail.

Secrets (AI keys, etc.) are stored encrypted and never leave the API.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.fields import EncryptedTextField
from apps.core.models import TimeStampedModel

CATEGORY_CHOICES = [
    ("email", "Email & SMTP"),
    ("sending", "Sending limits & schedule"),
    ("ai", "AI"),
    ("scoring", "Lead scoring"),
    ("dedupe", "Deduplication"),
    ("imports", "Imports"),
    ("crm", "CRM"),
    ("compliance", "Compliance & branding"),
    ("general", "General"),
]


class SystemSetting(TimeStampedModel):
    key = models.CharField(max_length=120, unique=True, db_index=True)
    value = models.JSONField(default=None, null=True, blank=True)
    secret_value = EncryptedTextField(blank=True, default="")
    category = models.CharField(max_length=40, choices=CATEGORY_CHOICES, default="general",
                                db_index=True)
    label = models.CharField(max_length=200, blank=True, default="")
    description = models.TextField(blank=True, default="")
    is_secret = models.BooleanField(default=False)
    is_public = models.BooleanField(
        default=False, help_text="Safe to expose to the frontend (e.g. brand name)."
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ("category", "key")
        verbose_name = "System setting"
        verbose_name_plural = "System settings"

    def __str__(self) -> str:
        return self.key

    @property
    def resolved_value(self):
        return self.secret_value if self.is_secret else self.value


class SettingChangeLog(TimeStampedModel):
    """Who changed which setting, from what, to what."""

    setting = models.ForeignKey(
        SystemSetting, null=True, blank=True, on_delete=models.SET_NULL, related_name="changes"
    )
    key = models.CharField(max_length=120, db_index=True)
    old_value = models.JSONField(default=None, null=True, blank=True)
    new_value = models.JSONField(default=None, null=True, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Setting change log"
        verbose_name_plural = "Setting change logs"
