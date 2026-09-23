from django.contrib import admin

from .models import DailyEmailUsage, EmailEvent, EmailMessage, EmailTemplate
from .models import FollowUpSequence, FollowUpStep


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_active", "is_default", "usage_count")
    search_fields = ("name", "subject")
    list_filter = ("category", "is_active")


@admin.register(FollowUpSequence)
class FollowUpSequenceAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "max_steps")
    inlines = []


@admin.register(FollowUpStep)
class FollowUpStepAdmin(admin.ModelAdmin):
    list_display = ("sequence", "order", "delay_days", "condition", "is_active")
    raw_id_fields = ("template",)


@admin.register(EmailMessage)
class EmailMessageAdmin(admin.ModelAdmin):
    list_display = ("to_email", "subject", "status", "scheduled_at", "sent_at",
                    "attempt_count")
    list_filter = ("status", "step_number")
    search_fields = ("to_email", "subject")
    raw_id_fields = ("lead", "campaign", "campaign_lead")
    date_hierarchy = "created_at"


@admin.register(EmailEvent)
class EmailEventAdmin(admin.ModelAdmin):
    list_display = ("message", "type", "occurred_at")
    list_filter = ("type",)
    raw_id_fields = ("message",)


@admin.register(DailyEmailUsage)
class DailyEmailUsageAdmin(admin.ModelAdmin):
    list_display = ("date", "sent_count", "failed_count", "bounced_count", "limit",
                    "smtp_limit")
    date_hierarchy = "date"
