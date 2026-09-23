from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.companies.models import Company
from apps.core.models import TimeStampedModel
from apps.core.normalizers import normalize_key


class Contact(TimeStampedModel):
    """A human being attached to a Company (may exist without an email)."""

    company = models.ForeignKey(
        Company, null=True, blank=True, on_delete=models.CASCADE, related_name="contacts"
    )
    first_name = models.CharField(max_length=120, blank=True, default="")
    last_name = models.CharField(max_length=120, blank=True, default="", db_index=True)
    full_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    job_title = models.CharField(max_length=200, blank=True, default="")
    seniority = models.CharField(max_length=60, blank=True, default="")
    department = models.CharField(max_length=80, blank=True, default="")

    email = models.CharField(max_length=320, blank=True, default="")
    email_normalized = models.CharField(max_length=320, default="", blank=True, db_index=True)
    phone = models.CharField(max_length=64, blank=True, default="")
    phone_normalized = models.CharField(max_length=64, default="", blank=True, db_index=True)
    phone_type = models.CharField(
        max_length=32, blank=True, default="",
        help_text="Mobile / Landline / VOIP / Unknown (as provided by the source file)",
    )
    mobile = models.CharField(max_length=64, blank=True, default="")

    linkedin_url = models.CharField(max_length=500, blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="")
    state = models.CharField(max_length=120, blank=True, default="")

    source = models.ForeignKey(
        "imports.LeadSource", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="contacts",
    )
    source_file = models.ForeignKey(
        "imports.ImportFile", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="contacts",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    is_primary = models.BooleanField(default=False)
    is_decision_maker = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("last_name", "first_name")
        verbose_name = "Contact"
        verbose_name_plural = "Contacts"
        indexes = [
            models.Index(fields=["company", "email_normalized"]),
            models.Index(fields=["email_normalized"]),
            models.Index(fields=["phone_normalized"]),
            models.Index(fields=["last_name", "first_name"]),
        ]

    def __str__(self) -> str:
        return self.display_name or self.email or f"Contact #{self.pk}"

    @property
    def display_name(self) -> str:
        name = " ".join(p for p in (self.first_name, self.last_name) if p).strip()
        return name or self.full_name

    def save(self, *args, **kwargs):
        if not self.full_name:
            self.full_name = self.display_name
        if self.email and not self.email_normalized:
            self.email_normalized = normalize_key(self.email).replace(" ", "")
        super().save(*args, **kwargs)
