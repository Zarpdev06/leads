from django.contrib import admin

from .models import Campaign, CampaignLead, Service, ServiceIndustryMapping


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_active", "sort_order")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ServiceIndustryMapping)
class ServiceIndustryMappingAdmin(admin.ModelAdmin):
    list_display = ("industry", "service", "priority", "is_active")
    list_filter = ("is_active",)
    raw_id_fields = ("industry", "service")


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "total_selected", "total_sent", "total_replied",
                    "daily_limit", "created_at")
    list_filter = ("status",)
    search_fields = ("name",)
    raw_id_fields = ("template", "recommended_service", "follow_up_sequence")


@admin.register(CampaignLead)
class CampaignLeadAdmin(admin.ModelAdmin):
    list_display = ("campaign", "lead", "status", "current_step", "scheduled_at")
    list_filter = ("status",)
    raw_id_fields = ("campaign", "lead")
