from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Count

from apps.core.models import TimeStampedModel
from apps.core.normalizers import normalize_key


class Industry(TimeStampedModel):
    """Industry / niche taxonomy.

    Two levels are used by the product:
      * top level   -> industry        (e.g. "Automotive", "Healthcare")
      * child level -> sub_industry   (e.g. "Auto Detailing", "Chiropractors")

    `keywords` powers the rule-based classifier: any keyword hit raises the
    score of that industry for a given company name / website text.
    """

    name = models.CharField(max_length=180, db_index=True)
    slug = models.SlugField(max_length=200, unique=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    code = models.CharField(max_length=32, blank=True, default="", db_index=True)
    keywords = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=0)
    full_path = models.CharField(max_length=400, blank=True, default="", db_index=True)

    class Meta:
        ordering = ("sort_order", "name")
        verbose_name = "Industry"
        verbose_name_plural = "Industries"
        indexes = [models.Index(fields=["parent", "name"])]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "name"], name="uniq_industry_parent_name"
            )
        ]

    def __str__(self) -> str:
        return self.full_path or self.name

    @property
    def is_sub_industry(self) -> bool:
        return self.parent_id is not None

    def save(self, *args, **kwargs):
        self.full_path = f"{self.parent.full_path} > {self.name}" if self.parent_id else self.name
        super().save(*args, **kwargs)

    @property
    def lead_count(self) -> int:
        return self.leads.count()


class Company(TimeStampedModel):
    """One canonical business record (deduplicated across sources)."""

    name = models.CharField(max_length=300, db_index=True)
    name_normalized = models.CharField(max_length=300, default="", blank=True, db_index=True)
    legal_name = models.CharField(max_length=300, blank=True, default="")
    dba_name = models.CharField(max_length=300, blank=True, default="")

    website = models.CharField(max_length=500, blank=True, default="")
    website_normalized = models.CharField(max_length=500, default="", blank=True, db_index=True)
    domain = models.CharField(max_length=255, default="", blank=True, db_index=True)

    email = models.CharField(max_length=320, blank=True, default="")
    phone = models.CharField(max_length=64, blank=True, default="")
    phone_normalized = models.CharField(max_length=64, default="", blank=True, db_index=True)

    street_address = models.CharField(max_length=300, blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="", db_index=True)
    state = models.CharField(max_length=120, blank=True, default="", db_index=True)
    zip_code = models.CharField(max_length=32, blank=True, default="")
    country = models.CharField(max_length=120, blank=True, default="", db_index=True)

    employee_count = models.PositiveIntegerField(null=True, blank=True)
    employee_range = models.CharField(max_length=60, blank=True, default="")
    annual_revenue = models.CharField(max_length=60, blank=True, default="")

    industry = models.ForeignKey(
        Industry, null=True, blank=True, on_delete=models.SET_NULL, related_name="companies"
    )
    sub_industry = models.ForeignKey(
        Industry, null=True, blank=True, on_delete=models.SET_NULL, related_name="sub_companies"
    )

    linkedin_url = models.CharField(max_length=500, blank=True, default="")
    description = models.TextField(blank=True, default="")
    tags = models.JSONField(default=list, blank=True)
    extra = models.JSONField(default=dict, blank=True)

    source = models.ForeignKey(
        "imports.LeadSource", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="companies",
    )
    source_file = models.ForeignKey(
        "imports.ImportFile", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="companies",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    # Operational counters (kept in sync by the import / dedupe pipelines)
    lead_count = models.PositiveIntegerField(default=0)
    website_status = models.CharField(max_length=32, blank=True, default="")
    last_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        indexes = [
            models.Index(fields=["name_normalized", "domain"]),
            models.Index(fields=["industry", "state"]),
            models.Index(fields=["city", "state"]),
            models.Index(fields=["domain"]),
            models.Index(fields=["created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["name_normalized", "domain", "city", "state"],
                name="uniq_company_name_domain_place",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.name_normalized and self.name:
            self.name_normalized = normalize_key(self.name)
        super().save(*args, **kwargs)

    @property
    def location(self) -> str:
        parts = [p for p in (self.city, self.state) if p]
        return ", ".join(parts)

    @property
    def industry_path(self) -> str:
        if self.sub_industry_id:
            return self.sub_industry.full_path
        return self.industry.full_path if self.industry_id else ""


class CompanyMergeLog(TimeStampedModel):
    """Audit trail for company merges (survivor + absorbed duplicates)."""

    survivor = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="merged_from")
    absorbed = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="merged_into_log")
    merged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    snapshot = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Company merge log"

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.absorbed} -> {self.survivor}"


def industry_choices_queryset():  # pragma: no cover - helper for admin/API
    return Industry.objects.filter(parent__isnull=True).annotate(
        num_children=Count("children")
    )
