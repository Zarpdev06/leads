"""Celery tasks for the import pipeline (queue: imports)."""
from __future__ import annotations

import logging
import os
import traceback

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.core.models import log_audit

from .models import ImportFile, ImportJob
from .readers import estimate_row_count, iter_rows

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="apps.imports.tasks.run_import_job",
             autoretry_for=(MemoryError,), retry_backoff=60, max_retries=1,
             soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
             time_limit=settings.CELERY_TASK_TIME_LIMIT)
def run_import_job(self, job_id: int) -> dict:
    """Stream the file in chunks and build leads. Progress is written per chunk."""
    job = ImportJob.objects.select_related("import_file", "import_file__source").filter(
        pk=job_id
    ).first()
    if job is None:
        return {"error": "job not found"}
    if job.status in {ImportJob.Status.COMPLETED, ImportJob.Status.PROCESSING}:
        return {"detail": f"job already {job.status}"}

    import_file: ImportFile = job.import_file
    options = job.options or {}
    job.mark_processing()
    import_file.status = ImportFile.Status.IMPORTING
    import_file.save(update_fields=["status", "updated_at"])

    log_audit(action="IMPORT_STARTED", entity_type="import_job", entity_id=job.pk,
              description=f"Import started: {import_file.original_name}",
              metadata={"file_id": import_file.pk, "options": options})

    from apps.imports.pipeline import LeadBuilder, RowStats, finalize_job_stats

    builder = LeadBuilder(
        source=import_file.source,
        import_file=import_file,
        job=job,
        options=options,
        user=job.created_by,
    )

    chunk_size = int(options.get("chunk_size") or settings.IMPORT_CHUNK_SIZE)
    totals = RowStats()
    row_offset = 1  # 1-based, header excluded
    processed = 0

    try:
        for chunk in iter_rows(import_file, chunk_size=chunk_size):
            stats = builder.process_chunk(chunk, import_file.effective_mapping,
                                          start_row=row_offset)
            totals.merge(stats)
            row_offset += len(chunk)
            processed += len(chunk)

            job.processed_rows = processed
            job.created_rows = totals.created
            job.updated_rows = totals.updated
            job.skipped_rows = totals.skipped
            job.duplicate_rows = totals.duplicates
            job.invalid_rows = totals.invalid
            job.rows_with_email = totals.with_email
            job.rows_without_email = totals.without_email
            job.invalid_email_rows = totals.invalid_emails
            job.missing_company_rows = totals.missing_company
            job.error_rows = totals.errors
            job.current_batch = job.current_batch + 1
            if job.total_rows:
                job.progress_percent = min(
                    99.0, round(processed / job.total_rows * 100, 2)
                )
            job.save(update_fields=[
                "processed_rows", "created_rows", "updated_rows", "skipped_rows",
                "duplicate_rows", "invalid_rows", "rows_with_email",
                "rows_without_email", "invalid_email_rows", "missing_company_rows",
                "error_rows", "current_batch", "progress_percent", "updated_at",
            ])

        builder.flush_errors(job)
        finalize_job_stats(job, totals)

        import_file.status = ImportFile.Status.COMPLETED
        import_file.total_rows = processed
        import_file.save(update_fields=["status", "total_rows", "updated_at"])
        if import_file.source_id:
            import_file.source.imported_at = timezone.now()
            import_file.source.save(update_fields=["imported_at", "updated_at"])
            import_file.source.recalculate_stats()

        job.mark_finished(ImportJob.Status.COMPLETED)
        log_audit(action="IMPORT_COMPLETED", entity_type="import_job", entity_id=job.pk,
                  description=f"Imported {processed} rows from {import_file.original_name}",
                  metadata={"stats": totals.as_dict()})

        # Post-import housekeeping
        if options.get("run_dedupe", True):
            from apps.leads.tasks import detect_duplicates_task

            detect_duplicates_task.delay(source_id=import_file.source_id)
        if options.get("rescore", True):
            from apps.leads.tasks import rescore_leads_task

            rescore_leads_task.delay(source_id=import_file.source_id)
        return {"processed": processed, **totals.as_dict()}

    except Exception as exc:  # pragma: no cover - operational safety net
        logger.exception("Import job %s failed", job_id)
        job.mark_finished(ImportJob.Status.FAILED, f"{exc}\n{traceback.format_exc()[-2000:]}")
        import_file.status = ImportFile.Status.FAILED
        import_file.error_message = str(exc)[:1000]
        import_file.save(update_fields=["status", "error_message", "updated_at"])
        log_audit(action="IMPORT_FAILED", entity_type="import_job", entity_id=job.pk,
                  description=str(exc)[:500])
        return {"error": str(exc)}


@shared_task(name="apps.imports.tasks.analyze_upload")
def analyze_upload(import_file_id: int) -> dict:
    """Detect headers, sample rows and auto-map columns (fast, streamed)."""
    from .mapping import auto_map
    from .readers import inspect_file, read_xlsx_sheets

    import_file = ImportFile.objects.filter(pk=import_file_id).first()
    if import_file is None:
        return {"error": "file not found"}

    try:
        if import_file.file_type == ImportFile.FileType.XLSX:
            import_file.available_sheets = read_xlsx_sheets(import_file.path)
            import_file.save(update_fields=["available_sheets", "updated_at"])

        meta = inspect_file(
            import_file.path, import_file.file_type, sheet_name=import_file.sheet_name
        )
        import_file.headers = meta.headers
        import_file.sample_rows = meta.sample_rows
        import_file.detected_delimiter = meta.delimiter
        import_file.detected_encoding = meta.encoding
        if meta.sheets:
            import_file.available_sheets = meta.sheets
        if not import_file.sheet_name and meta.sheets:
            import_file.sheet_name = meta.sheets[0]

        mapping = auto_map(meta.headers, meta.sample_rows)
        import_file.detected_mapping = mapping["mapping"]
        import_file.mapping_suggestions = mapping["suggestions"]
        import_file.column_mapping = mapping["mapping"]
        import_file.total_rows = estimate_row_count(
            import_file.path, import_file.file_type, sheet_name=import_file.sheet_name
        )
        import_file.status = ImportFile.Status.READY
        import_file.save(update_fields=[
            "headers", "sample_rows", "detected_delimiter", "detected_encoding",
            "available_sheets", "sheet_name", "detected_mapping",
            "mapping_suggestions", "column_mapping", "total_rows", "status", "updated_at",
        ])
        return {"headers": meta.headers, "rows": import_file.total_rows,
                "mapping": mapping["mapping"]}
    except Exception as exc:
        logger.exception("Analysis failed for %s", import_file_id)
        import_file.status = ImportFile.Status.FAILED
        import_file.error_message = str(exc)[:1000]
        import_file.save(update_fields=["status", "error_message", "updated_at"])
        return {"error": str(exc)}


@shared_task(name="apps.imports.tasks.purge_old_import_files")
def purge_old_import_files(days: int = 30) -> dict:
    """Delete uploaded files older than N days (keeps the DB rows + statistics)."""
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(days=days)
    removed = 0
    for import_file in ImportFile.objects.filter(
        created_at__lte=cutoff, deleted_at__isnull=True
    ).exclude(file="")[:500]:
        try:
            if import_file.file and os.path.exists(import_file.file.path):
                os.remove(import_file.file.path)
            import_file.deleted_at = timezone.now()
            import_file.save(update_fields=["deleted_at", "updated_at"])
            removed += 1
        except Exception:  # pragma: no cover
            continue
    return {"files_removed": removed}
