from django.contrib import admin

from .models import CRMActivity, LeadNote


@admin.register(CRMActivity)
class CRMActivityAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "lead", "type", "title", "actor")
    list_filter = ("type",)
    search_fields = ("title", "description")
    raw_id_fields = ("lead", "actor")
    date_hierarchy = "occurred_at"


@admin.register(LeadNote)
class LeadNoteAdmin(admin.ModelAdmin):
    list_display = ("lead", "author", "is_pinned", "created_at")
    search_fields = ("body",)
    raw_id_fields = ("lead", "author")
