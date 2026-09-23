"""Import a CSV/XLSX file from the command line (headless, chunked).

    python manage.py import_csv data/leads.csv --source "Public Contacts" --city Chicago --state IL
"""
from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError

from apps.imports.mapping import auto_map
from apps.imports.models import ImportFile, ImportJob, LeadSource
from apps.imports.readers import estimate_row_count, inspect_file
from apps.imports.tasks import run_import_job


class Command(BaseCommand):
    help = "Import leads from a local CSV or XLSX file."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--source", default="")
        parser.add_argument("--category", default="")
        parser.add_argument("--city", default="")
        parser.add_argument("--state", default="")
        parser.add_argument("--chunk-size", type=int, default=1000)
        parser.add_argument("--valid-only", action="store_true")
        parser.add_argument("--no-rows-without-email", action="store_true")

    def handle(self, *args, **options):
        path = options["path"]
        if not os.path.exists(path):
            raise CommandError(f"No such file: {path}")

        name = options["source"] or os.path.basename(path)
        source, _ = LeadSource.objects.get_or_create(
            name=name[:255],
            defaults={
                "category": options["category"],
                "file_name": os.path.basename(path),
                "city": options["city"],
                "state": options["state"],
            },
        )

        file_type = "XLSX" if path.lower().endswith((".xlsx", ".xlsm")) else "CSV"
        import_file = ImportFile.objects.create(
            source=source, original_name=os.path.basename(path), file_type=file_type,
            size_bytes=os.path.getsize(path), status=ImportFile.Status.ANALYZING,
        )
        from django.core.files.base import ContentFile

        with open(path, "rb") as handle:
            import_file.file.save(os.path.basename(path), ContentFile(handle.read()), save=True)

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
        import_file.column_mapping = mapping["mapping"]
        import_file.mapping_suggestions = mapping["suggestions"]
        import_file.total_rows = estimate_row_count(
            import_file.path, file_type, sheet_name=import_file.sheet_name)
        import_file.status = ImportFile.Status.READY
        import_file.save()

        self.stdout.write(f"Detected {len(meta.headers)} columns; mapping: {mapping['mapping']}")
        if mapping["unmapped"]:
            self.stdout.write(self.style.WARNING(f"Unmapped: {mapping['unmapped']}"))

        job = ImportJob.objects.create(
            import_file=import_file,
            options={
                "chunk_size": options["chunk_size"],
                "import_valid_only": options["valid_only"],
                "import_rows_without_email": not options["no_rows_without_email"],
            },
            total_rows=import_file.total_rows,
        )
        result = run_import_job(job.pk)
        job.refresh_from_db()
        self.stdout.write(self.style.SUCCESS(
            f"Job {job.pk}: {job.status} · {job.created_rows} created · "
            f"{job.skipped_rows} skipped · {job.duplicate_rows} duplicates · "
            f"{job.invalid_rows} invalid"
        ))
        self.stdout.write(str(result))
