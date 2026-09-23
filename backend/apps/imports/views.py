"""
Import API.

    POST   /api/imports/upload/            upload + analyse (drag & drop)
    GET    /api/imports/                   list import files
    GET    /api/imports/{id}/              file + mapping + preview
    PATCH  /api/imports/{id}/              change mapping / sheet
    POST   /api/imports/{id}/process/      start the async job
    GET    /api/imports/{id}/preview/      first 50 normalized rows + stats
    GET    /api/imports/jobs/              import history
"""
from __future__ import annotations

from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.models import log_audit
from apps.core.permissions import CanModify

from .mapping import suggest_mapping
from .models import ImportFile, ImportJob, LeadSource
from .pipeline import preview_stats
from .readers import ImportFileError, inspect_file, validate_upload
from .serializers import (
    ImportFileSerializer,
    ImportFileUploadSerializer,
    ImportJobSerializer,
    ImportProcessSerializer,
    ImportRowErrorSerializer,
    LeadSourceSerializer,
    MappingConfirmSerializer,
)


class LeadSourceViewSet(viewsets.ModelViewSet):
    queryset = LeadSource.objects.all()
    serializer_class = LeadSourceSerializer
    permission_classes = [IsAuthenticated, CanModify]
    search_fields = ["name", "category", "file_name", "city", "state"]
    filterset_fields = ["category", "city", "state", "is_active"]
    ordering = ["-created_at"]

    @action(detail=True, methods=["post"])
    def recalculate(self, request, pk=None):
        source = self.get_object()
        source.recalculate_stats()
        return Response(LeadSourceSerializer(source).data)


class ImportFileViewSet(viewsets.ModelViewSet):
    queryset = ImportFile.objects.select_related("source").all()
    serializer_class = ImportFileSerializer
    permission_classes = [IsAuthenticated, CanModify]
    filterset_fields = ["status", "source", "file_type"]
    search_fields = ["original_name"]
    ordering = ["-created_at"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def patch(self, request, *args, **kwargs):
        """Update the column mapping (STEP 6: manual override)."""
        import_file = self.get_object()
        serializer = MappingConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        import_file.column_mapping = data["column_mapping"]
        if data.get("sheet_name"):
            import_file.sheet_name = data["sheet_name"]
        import_file.has_header_row = data.get("has_header_row", True)
        import_file.mapping_confirmed = True
        import_file.status = ImportFile.Status.MAPPED
        import_file.save(update_fields=[
            "column_mapping", "sheet_name", "has_header_row", "mapping_confirmed",
            "status", "updated_at",
        ])
        log_audit(action="IMPORT_MAPPING_SAVED", actor=request.user,
                  entity_type="import_file", entity_id=import_file.pk,
                  description="Column mapping confirmed", request=request)
        return Response(ImportFileSerializer(import_file).data)

    @action(detail=False, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def upload(self, request):
        """STEP 1-6: validate, store, detect headers, auto-map."""
        serializer = ImportFileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded = serializer.validated_data["file"]

        try:
            file_type = validate_upload(uploaded)
        except ImportFileError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        source = None
        source_id = serializer.validated_data.get("source_id")
        if source_id:
            source = LeadSource.objects.filter(pk=source_id).first()
        if source is None:
            name = (serializer.validated_data.get("source_name")
                    or uploaded.name or "Imported file")
            source, _ = LeadSource.objects.get_or_create(
                name=name[:255],
                defaults={
                    "category": serializer.validated_data.get("category", ""),
                    "file_name": uploaded.name[:255],
                    "city": serializer.validated_data.get("city", ""),
                    "state": serializer.validated_data.get("state", ""),
                    "industry_hint": serializer.validated_data.get("industry_hint", ""),
                    "created_by": request.user,
                },
            )

        import_file = ImportFile.objects.create(
            source=source,
            file=uploaded,
            original_name=uploaded.name[:255],
            file_type=file_type,
            size_bytes=getattr(uploaded, "size", 0) or 0,
            uploaded_by=request.user,
            status=ImportFile.Status.ANALYZING,
        )

        try:
            from .tasks import analyze_upload

            # Small files are analysed synchronously so the UI shows the
            # mapping immediately; anything big goes to the worker.
            if import_file.size_bytes <= 5 * 1024 * 1024:
                analyze_upload(import_file.pk)
            else:
                analyze_upload.delay(import_file.pk)
                import_file.status = ImportFile.Status.ANALYZING
                import_file.save(update_fields=["status", "updated_at"])
        except Exception as exc:  # pragma: no cover
            import_file.status = ImportFile.Status.FAILED
            import_file.error_message = str(exc)[:1000]
            import_file.save(update_fields=["status", "error_message", "updated_at"])
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        import_file.refresh_from_db()  # analysis (sync or async) mutates the row

        log_audit(action="IMPORT_UPLOADED", actor=request.user, entity_type="import_file",
                  entity_id=import_file.pk,
                  description=f"Uploaded {import_file.original_name}", request=request)
        return Response(ImportFileSerializer(import_file).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        """STEP 7-8: first 50 normalized rows + quality stats."""
        import_file = self.get_object()
        if not import_file.sample_rows:
            meta = inspect_file(import_file.path, import_file.file_type,
                                sheet_name=import_file.sheet_name)
            import_file.headers = meta.headers
            import_file.sample_rows = meta.sample_rows
            import_file.save(update_fields=["headers", "sample_rows", "updated_at"])

        mapping = import_file.effective_mapping
        result = preview_stats(
            import_file.sample_rows,
            mapping,
            source_category=import_file.source.category if import_file.source_id else "",
            source_name=import_file.source.name if import_file.source_id else
            import_file.original_name,
            source_city=import_file.source.city if import_file.source_id else "",
        )
        return Response({
            "stats": result["stats"],
            "preview": result["preview"],
            "mapping": mapping,
            "headers": import_file.headers,
            "total_rows": import_file.total_rows,
            "suggestions": import_file.mapping_suggestions,
        })

    @action(detail=True, methods=["post"])
    def reanalyze(self, request, pk=None):
        """Re-detect headers/mapping (e.g. after changing the worksheet)."""
        from .tasks import analyze_upload

        import_file = self.get_object()
        analyze_upload(import_file.pk)
        return Response(ImportFileSerializer(import_file).data)

    @action(detail=True, methods=["post"])
    def process(self, request, pk=None):
        """STEP 9-10: start the asynchronous import."""
        import_file = self.get_object()
        if not import_file.effective_mapping:
            return Response(
                {"detail": "No column mapping. Confirm the mapping first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = ImportProcessSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        options = serializer.validated_data

        job = ImportJob.objects.create(
            import_file=import_file,
            options=options,
            created_by=request.user,
            total_rows=import_file.total_rows,
        )
        from .tasks import run_import_job

        task = run_import_job.delay(job.pk)
        job.celery_task_id = task.id
        job.save(update_fields=["celery_task_id", "updated_at"])
        return Response(ImportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class ImportJobViewSet(viewsets.ReadOnlyModelViewSet):
    """Import history + progress polling."""

    queryset = ImportJob.objects.select_related("import_file", "import_file__source").all()
    serializer_class = ImportJobSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "import_file", "import_file__source"]
    ordering = ["-created_at"]

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        job = self.get_object()
        if job.status in {ImportJob.Status.COMPLETED, ImportJob.Status.CANCELLED}:
            return Response({"detail": f"Job is already {job.status}."},
                            status=status.HTTP_400_BAD_REQUEST)
        if job.celery_task_id:
            from config.celery import app as celery_app

            celery_app.control.revoke(job.celery_task_id, terminate=True)
        job.mark_finished(ImportJob.Status.CANCELLED, "Cancelled by user")
        log_audit(action="IMPORT_CANCELLED", actor=request.user, entity_type="import_job",
                  entity_id=job.pk, request=request)
        return Response(ImportJobSerializer(job).data)

    @action(detail=True, methods=["get"])
    def errors(self, request, pk=None):
        job = self.get_object()
        rows = job.row_errors.all()[:500]
        return Response(ImportRowErrorSerializer(rows, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def import_overview(request):
    """Summary for the Imports page."""
    return Response({
        "files": ImportFile.objects.count(),
        "jobs_running": ImportJob.objects.filter(
            status__in=[ImportJob.Status.PENDING, ImportJob.Status.PROCESSING]
        ).count(),
        "sources": LeadSource.objects.count(),
        "rows_imported": sum(
            job.created_rows for job in ImportJob.objects.all()[:1000]
        ),
        "max_file_mb": settings.IMPORT_MAX_FILE_MB,
        "chunk_size": settings.IMPORT_CHUNK_SIZE,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def dry_run_mapping(request):
    """Map arbitrary headers without uploading a file (used by the UI helper)."""
    headers = request.data.get("headers") or []
    suggestions = suggest_mapping(headers)
    return Response({
        "suggestions": [s.as_dict() for s in suggestions],
        "mapping": {s.source_column: s.target_field for s in suggestions if s.target_field},
    })
