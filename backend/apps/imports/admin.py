from django.contrib import admin

from .models import ImportFile, ImportJob, ImportRowError, LeadSource


@admin.register(LeadSource)
class LeadSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "total_rows", "rows_with_email",
                    "rows_without_email", "duplicate_rows", "imported_at")
    search_fields = ("name", "category", "file_name")
    list_filter = ("category", "is_active")


@admin.register(ImportFile)
class ImportFileAdmin(admin.ModelAdmin):
    list_display = ("original_name", "source", "file_type", "status", "total_rows",
                    "created_at")
    list_filter = ("status", "file_type")
    search_fields = ("original_name",)
    raw_id_fields = ("source",)


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = ("id", "import_file", "status", "progress_percent", "processed_rows",
                    "created_rows", "started_at", "finished_at")
    list_filter = ("status",)
    raw_id_fields = ("import_file",)


@admin.register(ImportRowError)
class ImportRowErrorAdmin(admin.ModelAdmin):
    list_display = ("job", "row_number", "field", "message")
    search_fields = ("message",)
    raw_id_fields = ("job",)
