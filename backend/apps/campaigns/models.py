"""
Campaigns, the service catalogue and the service-matching rules.

A campaign is an *audience + message + schedule*. It never sends anything
directly: it materialises `CampaignLead` rows, and the email engine turns those
into scheduled `EmailMessage` rows that compete for the daily quota.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.companies.models import Industry
from apps.core.models import TimeStampedModel


class Service(TimeStampedModel):
    """One of the services you sell."""

    name = models.CharField(max_length=180, unique=True)
    slug = models.SlugField(max_length=200, unique=True)
    short_name = models.CharField(max_length=80, blank=True, default="")
    category = models.CharField(max_length=80, blank=True, default="", db_index=True)
    description = models.TextField(blank=True, default="")
    value_proposition = models.TextField(
        blank=True, default="",
        help_text="One or two sentences used by the AI personalizer.",
    )
    pain_points = models.JSONField(
        default=list, blank=True,
        help_text="Bullet list of pain points this service solves (feeds the AI).",
    )
    outcomes = models.JSONField(default=list, blank=True)
    keywords = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "name")
        verbose_name = "Service"
        verbose_name_plural = "Services"

    def __str__(self) -> str:
        return self.name


DEFAULT_SERVICES: list[dict] = [
    {"name": "AI Development", "category": "AI", "value_proposition":
     "Custom AI models and features built into the tools your team already uses.",
     "pain_points": ["manual data entry", "slow reporting", "repetitive decisions"]},
    {"name": "AI Automation", "category": "AI", "value_proposition":
     "AI-driven automation that removes repetitive work from your daily operations.",
     "pain_points": ["manual follow-up", "missed enquiries", "after-hours requests"]},
    {"name": "Business Process Automation", "category": "Automation",
     "value_proposition": "End-to-end automation of the processes that slow your team down.",
     "pain_points": ["spreadsheet workflows", "double entry", "error-prone handoffs"]},
    {"name": "Custom Software Development", "category": "Engineering",
     "value_proposition": "Bespoke software built around how your business actually works.",
     "pain_points": ["off-the-shelf tools that don't fit", "manual workarounds"]},
    {"name": "ERP Development", "category": "Engineering",
     "value_proposition": "A single operational system for inventory, finance and operations.",
     "pain_points": ["disconnected systems", "no real-time stock visibility"]},
    {"name": "CRM Development", "category": "Engineering",
     "value_proposition": "A CRM that matches your sales process instead of forcing a template.",
     "pain_points": ["leads slipping through", "no pipeline visibility", "manual reminders"]},
    {"name": "Website Development", "category": "Web",
     "value_proposition": "Fast, mobile-first websites that turn visitors into enquiries.",
     "pain_points": ["outdated site", "slow load times", "no online enquiries"]},
    {"name": "Web Application Development", "category": "Web",
     "value_proposition": "Secure web applications your customers and staff can rely on.",
     "pain_points": ["manual processes", "spreadsheet-based operations"]},
    {"name": "API Integrations", "category": "Engineering",
     "value_proposition": "Connect your tools so data flows automatically between them.",
     "pain_points": ["copy-paste between systems", "data silos", "reconciliation"]},
    {"name": "Business Dashboards", "category": "Data",
     "value_proposition": "Live dashboards that show what is actually happening in the business.",
     "pain_points": ["no real-time reporting", "manual monthly reports"]},
    {"name": "Workflow Automation", "category": "Automation",
     "value_proposition": "Approvals, handoffs and reminders that run themselves.",
     "pain_points": ["chasing approvals", "missed follow-ups", "inconsistent process"]},
    {"name": "Custom SaaS Development", "category": "Engineering",
     "value_proposition": "Turn your internal process into a product your customers can buy.",
     "pain_points": ["manual delivery", "no recurring revenue"]},
    {"name": "AI Lead Follow-up Automation", "category": "AI",
     "value_proposition":
     "Every new enquiry gets an instant, personalised response - day or night.",
     "pain_points": ["missed calls", "slow response times", "lost enquiries"]},
    {"name": "Appointment Automation", "category": "Automation",
     "value_proposition": "Let customers book, reschedule and confirm appointments themselves.",
     "pain_points": ["phone tag", "no-shows", "double bookings"]},
    {"name": "AI Receptionist", "category": "AI",
     "value_proposition": "An AI receptionist that answers, qualifies and books 24/7.",
     "pain_points": ["missed calls after hours", "reception overload"]},
    {"name": "AI Chatbot", "category": "AI",
     "value_proposition": "Answer customer questions instantly on your website.",
     "pain_points": ["repeated questions", "slow email responses"]},
    {"name": "Document Automation", "category": "Automation",
     "value_proposition": "Generate contracts, invoices and reports automatically.",
     "pain_points": ["manual document prep", "version errors"]},
    {"name": "Client Portal", "category": "Engineering",
     "value_proposition": "A secure portal where clients can see progress, documents and invoices.",
     "pain_points": ["status update requests", "email attachments"]},
]


class ServiceIndustryMapping(TimeStampedModel):
    """Admin-configurable "industry -> recommended services" rules."""

    industry = models.ForeignKey(
        Industry, on_delete=models.CASCADE, related_name="service_mappings"
    )
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="industry_mappings"
    )
    priority = models.PositiveIntegerField(
        default=10, help_text="Lower number = recommended first."
    )
    reason = models.CharField(
        max_length=300, blank=True, default="",
        help_text="Why this service fits (shown to the AI and in the UI).",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("priority", "id")
        verbose_name = "Service / industry mapping"
        verbose_name_plural = "Service / industry mappings"
        constraints = [
            models.UniqueConstraint(
                fields=["industry", "service"], name="uniq_industry_service"
            )
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.industry} → {self.service}"


class Campaign(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        READY = "READY", "Ready"
        RUNNING = "RUNNING", "Running"
        PAUSED = "PAUSED", "Paused"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    name = models.CharField(max_length=200, db_index=True)
    slug = models.SlugField(max_length=220, blank=True, default="")
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True
    )

    # ---- Audience --------------------------------------------------------
    target_industries = models.ManyToManyField(
        Industry, blank=True, related_name="campaigns"
    )
    target_sub_industries = models.ManyToManyField(
        Industry, blank=True, related_name="sub_industry_campaigns"
    )
    target_states = models.JSONField(default=list, blank=True)
    target_cities = models.JSONField(default=list, blank=True)
    sources = models.ManyToManyField("imports.LeadSource", blank=True, related_name="campaigns")
    lead_ids = models.JSONField(
        default=list, blank=True,
        help_text="Explicitly selected leads (from the Lead Explorer).",
    )
    min_lead_score = models.PositiveIntegerField(default=0)
    max_lead_score = models.PositiveIntegerField(default=0)
    require_website = models.BooleanField(default=False)
    require_phone = models.BooleanField(default=False)
    require_contact_person = models.BooleanField(default=False)
    exclude_replied = models.BooleanField(default=True)
    exclude_ever_contacted = models.BooleanField(default=False)
    exclude_missing_email = models.BooleanField(default=True)

    # ---- Message ---------------------------------------------------------
    template = models.ForeignKey(
        "email_engine.EmailTemplate", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="campaigns",
    )
    use_ai_personalization = models.BooleanField(default=True)
    ai_instructions = models.TextField(blank=True, default="")
    recommended_service = models.ForeignKey(
        Service, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="campaigns",
        help_text="Fixed service for this campaign (otherwise matched per lead).",
    )
    subject = models.CharField(max_length=300, blank=True, default="")
    preview_text = models.CharField(max_length=300, blank=True, default="")

    # ---- Schedule ---------------------------------------------------------
    daily_limit = models.PositiveIntegerField(default=90)
    send_window_start = models.CharField(max_length=8, blank=True, default="09:30")
    send_window_end = models.CharField(max_length=8, blank=True, default="17:30")
    timezone_name = models.CharField(max_length=64, default="UTC")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    # ---- Follow-ups --------------------------------------------------------
    follow_up_enabled = models.BooleanField(default=True)
    follow_up_sequence = models.ForeignKey(
        "email_engine.FollowUpSequence", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="campaigns",
    )

    # ---- Sender identity ----------------------------------------------------
    from_name = models.CharField(max_length=180, blank=True, default="")
    from_email = models.EmailField(blank=True, default="")
    reply_to = models.EmailField(blank=True, default="")

    # ---- Bookkeeping ---------------------------------------------------------
    total_selected = models.PositiveIntegerField(default=0)
    total_queued = models.PositiveIntegerField(default=0)
    total_sent = models.PositiveIntegerField(default=0)
    total_failed = models.PositiveIntegerField(default=0)
    total_replied = models.PositiveIntegerField(default=0)
    total_bounced = models.PositiveIntegerField(default=0)
    total_unsubscribed = models.PositiveIntegerField(default=0)
    total_opened = models.PositiveIntegerField(default=0)
    total_clicked = models.PositiveIntegerField(default=0)

    last_dispatched_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="campaigns",
    )

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Campaign"
        verbose_name_plural = "Campaigns"
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["start_date", "end_date"]),
        ]

    def __str__(self) -> str:
        return self.name

    # ------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self.status == self.Status.RUNNING

    @property
    def can_start(self) -> bool:
        return self.status in {self.Status.DRAFT, self.Status.READY, self.Status.PAUSED}

    @property
    def reply_rate(self) -> float:
        return (self.total_replied / self.total_sent * 100) if self.total_sent else 0.0

    @property
    def open_rate(self) -> float:
        return (self.total_opened / self.total_sent * 100) if self.total_sent else 0.0

    def recalculate_stats(self) -> None:
        from apps.email_engine.models import EmailMessage

        messages = EmailMessage.objects.filter(campaign=self)
        self.total_queued = messages.filter(status=EmailMessage.Status.QUEUED).count()
        self.total_sent = messages.filter(status=EmailMessage.Status.SENT).count()
        self.total_failed = messages.filter(
            status__in=[EmailMessage.Status.FAILED, EmailMessage.Status.BOUNCED]
        ).count()
        self.total_opened = messages.filter(opened_at__isnull=False).count()
        self.total_clicked = messages.filter(clicked_at__isnull=False).count()
        self.total_replied = messages.filter(replied_at__isnull=False).count()
        self.total_bounced = messages.filter(bounced_at__isnull=False).count()
        self.total_unsubscribed = messages.filter(unsubscribed_at__isnull=False).count()
        self.save(update_fields=[
            "total_queued", "total_sent", "total_failed", "total_opened",
            "total_clicked", "total_replied", "total_bounced", "total_unsubscribed",
            "updated_at",
        ])


class CampaignLead(TimeStampedModel):
    """Membership of a lead in a campaign (one row per lead per campaign)."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SCHEDULED = "SCHEDULED", "Scheduled"
        SENT = "SENT", "Sent"
        FOLLOW_UP = "FOLLOW_UP", "In follow-up"
        REPLIED = "REPLIED", "Replied"
        BOUNCED = "BOUNCED", "Bounced"
        UNSUBSCRIBED = "UNSUBSCRIBED", "Unsubscribed"
        FAILED = "FAILED", "Failed"
        SKIPPED = "SKIPPED", "Skipped"
        CANCELLED = "CANCELLED", "Cancelled"
        COMPLETED = "COMPLETED", "Sequence completed"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="campaign_leads")
    lead = models.ForeignKey("leads.Lead", on_delete=models.CASCADE, related_name="campaign_leads")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    current_step = models.PositiveIntegerField(default=0)
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    next_follow_up_at = models.DateTimeField(null=True, blank=True, db_index=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    stopped_reason = models.CharField(max_length=200, blank=True, default="")
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    ai_generated = models.BooleanField(default=False)
    recommended_service = models.ForeignKey(
        Service, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Campaign lead"
        verbose_name_plural = "Campaign leads"
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "lead"], name="uniq_campaign_lead"
            )
        ]
        indexes = [
            models.Index(fields=["campaign", "status"]),
            models.Index(fields=["status", "scheduled_at"]),
            models.Index(fields=["next_follow_up_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.campaign} · {self.lead}"

    def stop(self, reason: str) -> None:
        self.stopped_reason = reason[:200]
        self.next_follow_up_at = None
        if self.status not in {
            self.Status.REPLIED, self.Status.UNSUBSCRIBED, self.Status.BOUNCED,
            self.Status.COMPLETED,
        }:
            self.status = self.Status.CANCELLED
        self.save(update_fields=["stopped_reason", "next_follow_up_at", "status", "updated_at"])


def seed_services(*, reset: bool = False) -> int:
    """Create the 12 core services (+ common AI/automation packages)."""
    from django.utils.text import slugify

    created = 0
    for index, payload in enumerate(DEFAULT_SERVICES):
        service, new = Service.objects.get_or_create(
            name=payload["name"],
            defaults={
                "slug": slugify(payload["name"]),
                "category": payload["category"],
                "value_proposition": payload["value_proposition"],
                "pain_points": payload["pain_points"],
                "sort_order": index,
            },
        )
        created += int(new)
    return created


def seed_service_mappings() -> int:
    """Starter rules: industry -> recommended services (editable in admin)."""
    created = 0
    mapping = {
        "Auto Detailing": ["AI Lead Follow-up Automation", "CRM Development",
                           "Appointment Automation", "Website Development"],
        "Auto Repair": ["CRM Development", "Appointment Automation", "AI Receptionist",
                        "Website Development", "Business Dashboards"],
        "Chiropractors": ["Appointment Automation", "CRM Development", "AI Receptionist",
                          "Website Development"],
        "Accountants": ["CRM Development", "Document Automation", "AI Lead Follow-up Automation",
                        "Client Portal", "Workflow Automation"],
        "Real Estate Agents": ["CRM Development", "AI Lead Follow-up Automation",
                               "Website Development", "AI Chatbot", "Document Automation"],
        "Restaurants": ["Website Development", "AI Chatbot", "Business Dashboards"],
        "Cafes": ["Website Development", "AI Chatbot", "Business Dashboards"],
        "Coffee Shops": ["Website Development", "AI Chatbot", "Business Dashboards"],
        "Business Consultants": ["CRM Development", "Workflow Automation",
                                 "Business Dashboards", "Custom SaaS Development"],
        "Architects": ["CRM Development", "Client Portal", "Document Automation",
                       "Website Development"],
    }
    for industry_name, services in mapping.items():
        industry = Industry.objects.filter(name__iexact=industry_name).first()
        if industry is None:
            continue
        for priority, service_name in enumerate(services, start=1):
            service = Service.objects.filter(name__iexact=service_name).first()
            if service is None:
                continue
            _, new = ServiceIndustryMapping.objects.get_or_create(
                industry=industry, service=service,
                defaults={"priority": priority,
                          "reason": f"Common need for {industry_name}."},
            )
            created += int(new)
    return created
