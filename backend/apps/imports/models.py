"""
Source management & import bookkeeping.

LeadSource  -> "82 Million USA - Public Contacts File 01.xlsx" (category: Public Contacts)
ImportFile  -> the uploaded file (metadata, detected headers, saved mapping)
ImportJob   -> one execution of an import (async, chunked, resumable progress)
ImportRowError -> row-level validation problems (sampled, never unbounded)
"""
from __future__ import annotations

import hashlib
import os

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


def source_file_upload_to(instance, filename: str) -> str:
    return f"imports/{timezone.now():%Y/%m/%d}/{filename}"


class LeadSource(TimeStampedModel):
    """Where a dataset came from (public file, purchased list, scrape, ...)."""

    name = models.CharField(max_length=255, db_index=True)
    category = models.CharField(
        max_length=120, blank=True, default="", db_index=True,
        help_text="e.g. Public Contacts, Scraped, Purchased, Manual",
    )
    description = models.TextField(blank=True, default="")
    file_name = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="", db_index=True)
    state = models.CharField(max_length=120, blank=True, default="")
    country = models.CharField(max_length=120, blank=True, default="")
    industry_hint = models.CharField(max_length=180, blank=True, default="")
    provider = models.CharField(max_length=180, blank=True, default="")
    acquired_at = models.DateField(null=True, blank=True)

    # Rolling statistics (recomputed after every job)
    total_rows = models.PositiveBigIntegerField(default=0)
    valid_rows = models.PositiveBigIntegerField(default=0)
    invalid_rows = models.PositiveBigIntegerField(default=0)
    rows_with_email = models.PositiveBigIntegerField(default=0)
    rows_without_email = models.PositiveBigIntegerField(default=0)
    duplicate_rows = models.PositiveBigIntegerField(default=0)
    invalid_emails = models.PositiveBigIntegerField(default=0)
    missing_company_names = models.PositiveBigIntegerField(default=0)

    imported_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Lead source"
        verbose_name_plural = "Lead sources"
        indexes = [models.Index(fields=["category", "created_at"])]

    def __str__(self) -> str:
        return self.name

    def recalculate_stats(self) -> None:
        """Recompute counters from the leads that reference this source."""
        from django.db.models import Count, Q

        from apps.leads.models import EmailStatus, Lead

        rows = Lead.objects.filter(source=self).aggregate(
            total=Count("id"),
            with_email=Count("id", filter=~Q(email_normalized="")),
            invalid_email=Count("id", filter=Q(email_status=EmailStatus.INVALID)),
            no_company=Count("id", filter=Q(company_name="")),
            duplicates=Count("id", filter=Q(is_duplicate=True)),
        )
        self.total_rows = rows["total"] or 0
        self.rows_with_email = rows["with_email"] or 0
        self.rows_without_email = self.total_rows - self.rows_with_email
        self.invalid_emails = rows["invalid_email"] or 0
        self.missing_company_names = rows["no_company"] or 0
        self.duplicate_rows = rows["duplicates"] or 0
        self.valid_rows = self.total_rows - self.invalid_emails
        self.save(update_fields=[
            "total_rows", "valid_rows", "invalid_rows", "rows_with_email",
            "rows_without_email", "duplicate_rows", "invalid_emails",
            "missing_company_names", "updated_at",
        ])


class ImportFile(TimeStampedModel):
    class FileType(models.TextChoices):
        CSV = "CSV", "CSV"
        XLSX = "XLSX", "Excel (.xlsx)"
        XLS = "XLS", "Excel (.xls)"

    class Status(models.TextChoices):
        UPLOADED = "UPLOADED", "Uploaded"
        ANALYZING = "ANALYZING", "Analyzing"
        READY = "READY", "Ready for mapping"
        MAPPED = "MAPPED", "Mapping confirmed"
        IMPORTING = "IMPORTING", "Importing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    source = models.ForeignKey(
        LeadSource, null=True, blank=True, on_delete=models.SET_NULL, related_name="files"
    )
    file = models.FileField(upload_to=source_file_upload_to, max_length=500)
    original_name = models.CharField(max_length=255, blank=True, default="")
    file_type = models.CharField(max_length=8, choices=FileType.choices, default=FileType.CSV)
    size_bytes = models.PositiveBigIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True, default="", db_index=True)

    sheet_name = models.CharField(max_length=255, blank=True, default="")
    available_sheets = models.JSONField(default=list, blank=True)
    has_header_row = models.BooleanField(default=True)
    header_row_index = models.PositiveIntegerField(default=0)
    detected_delimiter = models.CharField(max_length=8, blank=True, default=",")
    detected_encoding = models.CharField(max_length=32, blank=True, default="utf-8")

    headers = models.JSONField(default=list, blank=True)
    sample_rows = models.JSONField(default=list, blank=True)
    detected_mapping = models.JSONField(default=dict, blank=True)
    column_mapping = models.JSONField(default=dict, blank=True)
    mapping_suggestions = models.JSONField(default=list, blank=True)
    mapping_confirmed = models.BooleanField(default=False)

    total_rows = models.PositiveBigIntegerField(default=0)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.UPLOADED, db_index=True
    )
    error_message = models.TextField(blank=True, default="")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Import file"
        verbose_name_plural = "Import files"
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self) -> str:
        return self.original_name or os.path.basename(self.file.name or "import")

    @property
    def effective_mapping(self) -> dict:
        return self.column_mapping or self.detected_mapping or {}

    @property
    def path(self) -> str:
        return self.file.path if self.file else ""

    def compute_checksum(self) -> str:
        digest = hashlib.sha256()
        with default_storage.open(self.file.name, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()


class ImportJob(TimeStampedModel):
    """One asynchronous execution. Progress is written from the Celery task."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"
        PARTIAL = "PARTIAL", "Completed with errors"

    import_file = models.ForeignKey(
        ImportFile, on_delete=models.CASCADE, related_name="jobs"
    )
    celery_task_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    options = models.JSONField(default=dict, blank=True)

    total_rows = models.PositiveBigIntegerField(default=0)
    processed_rows = models.PositiveBigIntegerField(default=0)
    created_rows = models.PositiveBigIntegerField(default=0)
    updated_rows = models.PositiveBigIntegerField(default=0)
    skipped_rows = models.PositiveBigIntegerField(default=0)
    duplicate_rows = models.PositiveBigIntegerField(default=0)
    invalid_rows = models.PositiveBigIntegerField(default=0)
    rows_with_email = models.PositiveBigIntegerField(default=0)
    rows_without_email = models.PositiveBigIntegerField(default=0)
    invalid_email_rows = models.PositiveBigIntegerField(default=0)
    missing_company_rows = models.PositiveBigIntegerField(default=0)
    error_rows = models.PositiveBigIntegerField(default=0)

    progress_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    current_batch = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")
    error_log = models.JSONField(default=list, blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Import job"
        verbose_name_plural = "Import jobs"
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"Job #{self.pk} · {self.import_file} · {self.status}"

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def mark_processing(self) -> None:
        self.status = self.Status.PROCESSING
        self.started_at = self.started_at or timezone.now()
        self.save(update_fields=["status", "started_at", "updated_at"])

    def mark_finished(self, status: str, message: str = "") -> None:
        self.status = status
        self.finished_at = timezone.now()
        self.progress_percent = 100 if status != self.Status.FAILED else self.progress_percent
        if message:
            self.error_message = message[:5000]
        self.save(update_fields=["status", "finished_at", "progress_percent",
                                 "error_message", "updated_at"])


class ImportRowError(TimeStampedModel):
    job = models.ForeignKey(ImportJob, on_delete=models.CASCADE, related_name="row_errors")
    row_number = models.PositiveBigIntegerField(db_index=True)
    severity = models.CharField(
        max_length=12,
        choices=[("ERROR", "Error"), ("WARNING", "Warning")],
        default="ERROR",
    )
    field = models.CharField(max_length=80, blank=True, default="")
    message = models.CharField(max_length=500)
    raw_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("row_number",)
        verbose_name = "Import row error"
        verbose_name_plural = "Import row errors"
        indexes = [models.Index(fields=["job", "row_number"])]
