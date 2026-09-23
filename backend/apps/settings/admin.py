from django.contrib import admin

from .models import SettingChangeLog, SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "category", "is_secret", "is_public", "updated_at")
    list_filter = ("category", "is_secret")
    search_fields = ("key", "label")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SettingChangeLog)
class SettingChangeLogAdmin(admin.ModelAdmin):
    list_display = ("key", "changed_by", "created_at")
    list_filter = ("key",)
    readonly_fields = [f.name for f in SettingChangeLog._meta.fields]
