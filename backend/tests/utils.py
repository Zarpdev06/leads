"""Helpers shared by the integration tests."""
from __future__ import annotations

from django.core.files.base import ContentFile

from apps.imports.mapping import auto_map
from apps.imports.models import ImportFile, ImportJob, LeadSource
from apps.imports.readers import inspect_file


def build_import_file(path: str, *, source: LeadSource | None = None,
                      file_type: str | None = None, name: str | None = None) -> ImportFile:
    """Persist a file on disk, detect headers and auto-map its columns."""
    import os

    original_name = name or os.path.basename(path)
    with open(path, "rb") as handle:
        content = handle.read()

    file_type = file_type or ("XLSX" if original_name.lower().endswith(".xlsx") else "CSV")
    source = source or LeadSource.objects.create(name=original_name, category="Public Contacts",
                                                 file_name=original_name)
    import_file = ImportFile(source=source, original_name=original_name,
                             file_type=file_type, size_bytes=len(content))
    import_file.file.save(original_name, ContentFile(content), save=False)
    import_file.save()

    meta = inspect_file(import_file.path, file_type)
    import_file.headers = meta.headers
    import_file.sample_rows = meta.sample_rows
    import_file.detected_delimiter = meta.delimiter
    import_file.detected_encoding = meta.encoding
    if meta.sheets:
        import_file.available_sheets = meta.sheets
        import_file.sheet_name = meta.sheets[0]
    mapping = auto_map(meta.headers, meta.sample_rows)
    import_file.detected_mapping = mapping["mapping"]
    import_file.mapping_suggestions = mapping["suggestions"]
    import_file.column_mapping = mapping["mapping"]
    import_file.status = ImportFile.Status.READY
    import_file.save()
    return import_file


def run_import(import_file: ImportFile, **options) -> ImportJob:
    """Create and execute an import job synchronously."""
    from apps.imports.tasks import run_import_job

    job = ImportJob.objects.create(import_file=import_file, options=options or {},
                                   total_rows=import_file.total_rows)
    run_import_job(job.pk)
    job.refresh_from_db()
    return job
