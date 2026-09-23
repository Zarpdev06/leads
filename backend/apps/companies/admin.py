from django.contrib import admin

from .models import Company, CompanyMergeLog, Industry


@admin.register(Industry)
class IndustryAdmin(admin.ModelAdmin):
    list_display = ("full_path", "parent", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name", "keywords")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "domain", "city", "state", "industry", "lead_count")
    search_fields = ("name", "domain", "city", "state")
    list_filter = ("industry", "state")
    raw_id_fields = ("source", "source_file")


@admin.register(CompanyMergeLog)
class CompanyMergeLogAdmin(admin.ModelAdmin):
    list_display = ("survivor", "absorbed", "merged_by", "created_at")
    raw_id_fields = ("survivor", "absorbed")
