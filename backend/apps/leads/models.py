"""
Canonical lead schema.

Every import - whatever its column names - is projected onto this model. The
first block of fields is the canonical schema requested in the specification;
the second block is the operational state needed by campaigns, follow-ups,
CRM and analytics.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Count, Q
from django.utils import timezone

from apps.companies.models import Company, Industry
from apps.contacts.models import Contact
from apps.core.models import TimeStampedModel
from apps.core.normalizers import normalize_key


class LeadStatus(models.TextChoices):
    NEW = "NEW", "New"
    IMPORTED = "IMPORTED", "Imported"
    VALID = "VALID", "Valid"
    INVALID = "INVALID", "Invalid"
    MISSING_EMAIL = "MISSING_EMAIL", "Missing email"
    DUPLICATE = "DUPLICATE", "Duplicate"
    SUPPRESSED = "SUPPRESSED", "Suppressed"
    QUEUED = "QUEUED", "Queued"
    CONTACTED = "CONTACTED", "Contacted"
    REPLIED = "REPLIED", "Replied"
    BOUNCED = "BOUNCED", "Bounced"
    UNSUBSCRIBED = "UNSUBSCRIBED", "Unsubscribed"
    CONVERTED = "CONVERTED", "Converted"
    DO_NOT_CONTACT = "DO_NOT_CONTACT", "Do not contact"
    ARCHIVED = "ARCHIVED", "Archived"


class EmailStatus(models.TextChoices):
    VALID = "VALID", "Valid"
    INVALID = "INVALID", "Invalid"
    MISSING = "MISSING", "Missing"
    UNVERIFIED = "UNVERIFIED", "Unverified"
    RISKY = "RISKY", "Risky"
    BOUNCED = "BOUNCED", "Bounced"
    SUPPRESSED = "SUPPRESSED", "Suppressed"
    UNSUBSCRIBED = "UNSUBSCRIBED", "Unsubscribed"


class LeadQuality(models.TextChoices):
    HOT = "HOT", "Hot"
    WARM = "WARM", "Warm"
    COLD = "COLD", "Cold"
    UNQUALIFIED = "UNQUALIFIED", "Unqualified"


class CRMStage(models.TextChoices):
    NEW = "NEW", "New"
    QUALIFIED = "QUALIFIED", "Qualified"
    CONTACTED = "CONTACTED", "Contacted"
    REPLIED = "REPLIED", "Replied"
    MEETING_REQUESTED = "MEETING_REQUESTED", "Meeting requested"
    MEETING_SCHEDULED = "MEETING_SCHEDULED", "Meeting scheduled"
    PROPOSAL = "PROPOSAL", "Proposal"
    NEGOTIATION = "NEGOTIATION", "Negotiation"
    WON = "WON", "Won"
    LOST = "LOST", "Lost"
    DO_NOT_CONTACT = "DO_NOT_CONTACT", "Do not contact"


class EnrichmentStatus(models.TextChoices):
    NOT_PROCESSED = "NOT_PROCESSED", "Not processed"
    PROCESSING = "PROCESSING", "Processing"
    FOUND = "FOUND", "Found"
    NOT_FOUND = "NOT_FOUND", "Not found"
    FAILED = "FAILED", "Failed"
    SKIPPED = "SKIPPED", "Skipped (no website)"


class LeadQuerySet(models.QuerySet):
    def mailable(self):
        return (
            self.filter(email_status=EmailStatus.VALID)
            .exclude(email_normalized="")
            .filter(do_not_contact=False, is_blocked=False)
        )

    def with_totals(self):
        return self.annotate(_emails_sent=Count("email_messages"))

    def missing_email(self):
        return self.filter(Q(email_normalized="") | Q(email_status=EmailStatus.MISSING))

    def valid_email(self):
        return self.filter(email_status=EmailStatus.VALID).exclude(email_normalized="")

    def active(self):
        """Not merged away, not archived."""
        return self.filter(merged_into__isnull=True).exclude(lead_status=LeadStatus.ARCHIVED)




class Lead(TimeStampedModel):
    # ------------------------------------------------------------------
    # Canonical schema
    # ------------------------------------------------------------------
    company = models.ForeignKey(
        Company, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads"
    )
    contact = models.ForeignKey(
        Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads"
    )
    source = models.ForeignKey(
        "imports.LeadSource", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="leads",
    )
    source_file = models.ForeignKey(
        "imports.ImportFile", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="leads",
    )
    source_row_number = models.PositiveIntegerField(null=True, blank=True)

    company_name = models.CharField(max_length=300, db_index=True)
    company_name_key = models.CharField(max_length=300, default="", blank=True, db_index=True)
    industry = models.ForeignKey(
        Industry, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads"
    )
    sub_industry = models.ForeignKey(
        Industry, null=True, blank=True, on_delete=models.SET_NULL, related_name="sub_industry_leads"
    )

    contact_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    first_name = models.CharField(max_length=120, blank=True, default="")
    last_name = models.CharField(max_length=120, blank=True, default="", db_index=True)
    job_title = models.CharField(max_length=200, blank=True, default="")

    email = models.CharField(max_length=320, blank=True, default="")
    email_normalized = models.CharField(max_length=320, default="", blank=True, db_index=True)
    email_status = models.CharField(
        max_length=20, choices=EmailStatus.choices, default=EmailStatus.MISSING, db_index=True
    )
    email_domain = models.CharField(max_length=255, blank=True, default="", db_index=True)
    email_is_role = models.BooleanField(default=False)
    email_is_free_provider = models.BooleanField(default=False)

    phone = models.CharField(max_length=64, blank=True, default="")
    phone_normalized = models.CharField(max_length=64, default="", blank=True, db_index=True)
    phone_type = models.CharField(max_length=32, blank=True, default="")

    website = models.CharField(max_length=500, blank=True, default="")
    website_normalized = models.CharField(max_length=500, default="", blank=True, db_index=True)
    website_domain = models.CharField(max_length=255, default="", blank=True, db_index=True)
    website_accessible = models.BooleanField(null=True, blank=True)

    street_address = models.CharField(max_length=300, blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="", db_index=True)
    state = models.CharField(max_length=120, blank=True, default="", db_index=True)
    zip_code = models.CharField(max_length=32, blank=True, default="")
    country = models.CharField(max_length=120, blank=True, default="", db_index=True)

    employee_count = models.PositiveIntegerField(null=True, blank=True)
    employee_range = models.CharField(max_length=60, blank=True, default="")

    lead_status = models.CharField(
        max_length=24, choices=LeadStatus.choices, default=LeadStatus.NEW, db_index=True
    )
    lead_score = models.IntegerField(default=0, db_index=True)
    lead_quality = models.CharField(
        max_length=16, choices=LeadQuality.choices, default=LeadQuality.COLD, db_index=True
    )

    source_name = models.CharField(max_length=255, blank=True, default="")
    source_category = models.CharField(max_length=120, blank=True, default="", db_index=True)
    source_city = models.CharField(max_length=120, blank=True, default="", db_index=True)

    # ------------------------------------------------------------------
    # Operational state
    # ------------------------------------------------------------------
    crm_stage = models.CharField(
        max_length=24, choices=CRMStage.choices, default=CRMStage.NEW, db_index=True
    )
    stage_changed_at = models.DateTimeField(null=True, blank=True)
    deal_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=8, default="USD")
    expected_close_date = models.DateField(null=True, blank=True)
    won_at = models.DateTimeField(null=True, blank=True)
    lost_at = models.DateTimeField(null=True, blank=True)
    lost_reason = models.CharField(max_length=255, blank=True, default="")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="owned_leads",
    )

    # Deduplication
    is_duplicate = models.BooleanField(default=False, db_index=True)
    duplicate_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="duplicates"
    )
    merged_into = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="merged_records"
    )
    dedupe_key = models.CharField(max_length=400, blank=True, default="", db_index=True)

    # Outreach bookkeeping
    is_blocked = models.BooleanField(default=False, db_index=True)
    blocked_reason = models.CharField(max_length=255, blank=True, default="")
    times_contacted = models.PositiveIntegerField(default=0)
    last_contacted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    next_follow_up_at = models.DateTimeField(null=True, blank=True, db_index=True)
    replied_at = models.DateTimeField(null=True, blank=True, db_index=True)
    bounced_at = models.DateTimeField(null=True, blank=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    do_not_contact = models.BooleanField(default=False, db_index=True)

    # Enrichment (missing-email workflow)
    enrichment_status = models.CharField(
        max_length=20, choices=EnrichmentStatus.choices,
        default=EnrichmentStatus.NOT_PROCESSED, db_index=True,
    )
    enrichment_checked_at = models.DateTimeField(null=True, blank=True)
    enrichment_data = models.JSONField(default=dict, blank=True)
    enrichment_note = models.CharField(max_length=300, blank=True, default="")

    # AI cache + raw data
    ai_recommendation = models.JSONField(default=dict, blank=True)
    recommended_service = models.ForeignKey(
        "campaigns.Service", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="leads",
    )
    raw_data = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=list, blank=True)
    notes_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Lead"
        verbose_name_plural = "Leads"
        indexes = [
            models.Index(fields=["company_name_key"]),
            models.Index(fields=["email_normalized"]),
            models.Index(fields=["website_domain"]),
            models.Index(fields=["phone_normalized"]),
            models.Index(fields=["industry", "lead_score"]),
            models.Index(fields=["sub_industry", "lead_score"]),
            models.Index(fields=["state", "city"]),
            models.Index(fields=["lead_status", "email_status"]),
            models.Index(fields=["crm_stage"]),
            models.Index(fields=["source", "created_at"]),
            models.Index(fields=["next_follow_up_at"]),
            models.Index(fields=["is_duplicate", "merged_into"]),
        ]

    objects = LeadQuerySet.as_manager()

    def __str__(self) -> str:
        return self.company_name or self.email or f"Lead #{self.pk}"

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------
    @property
    def location(self) -> str:
        parts = [p for p in (self.city, self.state) if p]
        return ", ".join(parts)

    @property
    def has_email(self) -> bool:
        return bool(self.email_normalized)

    @property
    def has_website(self) -> bool:
        return bool(self.website_domain)

    @property
    def has_phone(self) -> bool:
        return bool(self.phone_normalized)

    @property
    def is_mailable(self) -> bool:
        """Cheap structural check only; full rules live in `eligibility.py`."""
        return (
            self.has_email
            and self.email_status == EmailStatus.VALID
            and not self.do_not_contact
            and not self.is_blocked
            and self.merged_into_id is None
        )

    def save(self, *args, **kwargs):
        if self.company_name and not self.company_name_key:
            self.company_name_key = normalize_key(self.company_name)
        if self.email and not self.email_normalized:
            from apps.core.normalizers import normalize_email

            self.email_normalized = normalize_email(self.email).normalized
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Mutators (all of them write CRM + audit history)
    # ------------------------------------------------------------------
    def set_status(self, status: str, *, actor=None, note: str = "") -> None:
        if self.lead_status == status:
            return
        previous = self.lead_status
        self.lead_status = status
        self.save(update_fields=["lead_status", "updated_at"])
        self.log_activity(
            type="STATUS_CHANGE",
            title=f"Status: {previous} → {status}",
            description=note,
            actor=actor,
            metadata={"from": previous, "to": status},
        )

    def set_stage(self, stage: str, *, actor=None, note: str = "") -> None:
        """Move the lead through the CRM pipeline, recording history."""
        if self.crm_stage == stage:
            return
        previous = self.crm_stage
        self.crm_stage = stage
        self.stage_changed_at = timezone.now()
        update_fields = ["crm_stage", "stage_changed_at", "updated_at"]
        if stage == CRMStage.WON and not self.won_at:
            self.won_at = timezone.now()
            update_fields.append("won_at")
        if stage == CRMStage.LOST and not self.lost_at:
            self.lost_at = timezone.now()
            update_fields.append("lost_at")
        self.save(update_fields=update_fields)
        self.log_activity(
            type="STAGE_CHANGE",
            title=f"Pipeline: {previous} → {stage}",
            description=note or self.lost_reason,
            actor=actor,
            metadata={"from": previous, "to": stage},
        )

    def log_activity(self, *, type: str, title: str, description: str = "",
                     actor=None, metadata: dict | None = None, occurred_at=None):
        from apps.crm.models import CRMActivity

        return CRMActivity.objects.create(
            lead=self,
            type=type,
            title=title,
            description=description,
            actor=actor,
            metadata=metadata or {},
            occurred_at=occurred_at or timezone.now(),
        )

    def mark_contacted(self, *, when=None) -> None:
        self.times_contacted = (self.times_contacted or 0) + 1
        self.last_contacted_at = when or timezone.now()
        if self.lead_status in {LeadStatus.NEW, LeadStatus.IMPORTED, LeadStatus.VALID}:
            self.lead_status = LeadStatus.CONTACTED
        if self.crm_stage == CRMStage.NEW:
            self.crm_stage = CRMStage.CONTACTED
            self.stage_changed_at = self.last_contacted_at
        self.save(update_fields=[
            "times_contacted", "last_contacted_at", "lead_status", "crm_stage",
            "stage_changed_at", "updated_at",
        ])

    def stop_outreach(self, reason: str) -> None:
        """Cancel queued messages and block any future outreach."""
        from apps.email_engine.models import EmailMessage

        EmailMessage.objects.filter(
            lead=self, status__in=[EmailMessage.Status.QUEUED, EmailMessage.Status.PROCESSING]
        ).update(status=EmailMessage.Status.CANCELLED, cancelled_at=timezone.now())
        self.is_blocked = True
        self.blocked_reason = reason[:255]
        self.next_follow_up_at = None
        self.save(update_fields=[
            "is_blocked", "blocked_reason", "next_follow_up_at", "updated_at"
        ])


class LeadDuplicate(TimeStampedModel):
    """Candidate duplicate pairs produced by the dedupe engine."""

    class Method(models.TextChoices):
        EMAIL = "EMAIL", "Same email"
        COMPANY_WEBSITE = "COMPANY_WEBSITE", "Company + website"
        COMPANY_PHONE = "COMPANY_PHONE", "Company + phone"
        COMPANY_ADDRESS = "COMPANY_ADDRESS", "Company + address"
        COMPANY_CITY_STATE = "COMPANY_CITY_STATE", "Company + city + state"
        COMPANY_NAME = "COMPANY_NAME", "Company name only"

    class Resolution(models.TextChoices):
        PENDING = "PENDING", "Pending review"
        MERGED = "MERGED", "Merged"
        KEPT_BOTH = "KEPT_BOTH", "Kept both"
        IGNORED = "IGNORED", "Ignored"

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="duplicate_candidates")
    candidate = models.ForeignKey(
        Lead, on_delete=models.CASCADE, related_name="duplicate_matches"
    )
    confidence = models.PositiveIntegerField(default=0, db_index=True)
    method = models.CharField(max_length=24, choices=Method.choices)
    resolution = models.CharField(
        max_length=16, choices=Resolution.choices, default=Resolution.PENDING, db_index=True
    )
    details = models.JSONField(default=dict, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-confidence", "-created_at")
        verbose_name = "Lead duplicate"
        verbose_name_plural = "Lead duplicates"
        constraints = [
            models.UniqueConstraint(
                fields=["lead", "candidate"], name="uniq_duplicate_pair"
            )
        ]
        indexes = [models.Index(fields=["resolution", "confidence"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.lead_id} ≈ {self.candidate_id} ({self.confidence}%)"


