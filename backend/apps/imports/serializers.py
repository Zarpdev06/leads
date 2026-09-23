from __future__ import annotations

from rest_framework import serializers

from .models import ImportFile, ImportJob, ImportRowError, LeadSource


class LeadSourceSerializer(serializers.ModelSerializer):
    files_count = serializers.SerializerMethodField()

    class Meta:
        model = LeadSource
        fields = [
            "id", "name", "category", "description", "file_name", "city", "state",
            "country", "industry_hint", "provider", "acquired_at", "total_rows",
            "valid_rows", "invalid_rows", "rows_with_email", "rows_without_email",
            "duplicate_rows", "invalid_emails", "missing_company_names",
            "imported_at", "is_active", "created_at", "files_count",
        ]
        read_only_fields = [
            "total_rows", "valid_rows", "invalid_rows", "rows_with_email",
            "rows_without_email", "duplicate_rows", "invalid_emails",
            "missing_company_names", "imported_at", "created_at",
        ]

    def get_files_count(self, obj) -> int:
        return obj.files.count()


class ImportFileSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source="source.name", read_only=True)
    mapping = serializers.SerializerMethodField()

    class Meta:
        model = ImportFile
        fields = [
            "id", "source", "source_name", "original_name", "file_type", "size_bytes",
            "checksum", "sheet_name", "available_sheets", "has_header_row",
            "detected_delimiter", "detected_encoding", "headers", "sample_rows",
            "detected_mapping", "column_mapping", "mapping_suggestions",
            "mapping_confirmed", "total_rows", "status", "error_message", "mapping",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "original_name", "file_type", "size_bytes", "checksum", "available_sheets",
            "headers", "sample_rows", "detected_mapping", "mapping_suggestions",
            "total_rows", "status", "error_message", "created_at", "updated_at",
        ]

    def get_mapping(self, obj) -> dict:
        return obj.effective_mapping


class ImportFileUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    source_id = serializers.IntegerField(required=False, allow_null=True)
    source_name = serializers.CharField(required=False, allow_blank=True, default="")
    category = serializers.CharField(required=False, allow_blank=True, default="")
    city = serializers.CharField(required=False, allow_blank=True, default="")
    state = serializers.CharField(required=False, allow_blank=True, default="")
    industry_hint = serializers.CharField(required=False, allow_blank=True, default="")


class MappingConfirmSerializer(serializers.Serializer):
    column_mapping = serializers.JSONField()
    sheet_name = serializers.CharField(required=False, allow_blank=True, default="")
    has_header_row = serializers.BooleanField(required=False, default=True)


class ImportProcessSerializer(serializers.Serializer):
    import_valid_only = serializers.BooleanField(default=False)
    skip_invalid_emails = serializers.BooleanField(default=False)
    import_rows_without_email = serializers.BooleanField(default=True)
    update_existing = serializers.BooleanField(default=False)
    run_dedupe = serializers.BooleanField(default=True)
    rescore = serializers.BooleanField(default=True)
    enrich_on_import = serializers.BooleanField(default=False)
    chunk_size = serializers.IntegerField(default=1000, min_value=100, max_value=20000)


class ImportJobSerializer(serializers.ModelSerializer):
    file_name = serializers.CharField(source="import_file.original_name", read_only=True)
    source_name = serializers.CharField(source="import_file.source.name", read_only=True)

    class Meta:
        model = ImportJob
        fields = [
            "id", "import_file", "file_name", "source_name", "celery_task_id", "status",
            "options", "total_rows", "processed_rows", "created_rows", "updated_rows",
            "skipped_rows", "duplicate_rows", "invalid_rows", "rows_with_email",
            "rows_without_email", "invalid_email_rows", "missing_company_rows",
            "error_rows", "progress_percent", "current_batch", "error_message",
            "started_at", "finished_at", "created_at",
        ]
        read_only_fields = ["celery_task_id", "status", "total_rows", "processed_rows",
                            "created_rows", "updated_rows", "skipped_rows",
                            "duplicate_rows", "invalid_rows", "rows_with_email",
                            "rows_without_email", "invalid_email_rows",
                            "missing_company_rows", "error_rows", "progress_percent",
                            "started_at", "finished_at", "created_at"]


class ImportRowErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportRowError
        fields = ["id", "job", "row_number", "severity", "field", "message", "raw_data",
                  "created_at"]


class PreviewSerializer(serializers.Serializer):
    """Preview of the first 50 rows after normalization (STEP 7 + 8)."""

    stats = serializers.DictField(read_only=True)
    preview = serializers.ListField(read_only=True)
