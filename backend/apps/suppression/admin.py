from django.contrib import admin

from .models import Suppression, SuppressionLog


@admin.register(Suppression)
class SuppressionAdmin(admin.ModelAdmin):
    list_display = ("email_normalized", "reason", "source", "is_active", "created_at")
    list_filter = ("reason", "is_active", "source")
    search_fields = ("email_normalized", "email", "note")
    raw_id_fields = ("lead", "email_message")


@admin.register(SuppressionLog)
class SuppressionLogAdmin(admin.ModelAdmin):
    list_display = ("email_normalized", "action", "reason", "actor", "created_at")
    list_filter = ("action",)
    search_fields = ("email_normalized",)
