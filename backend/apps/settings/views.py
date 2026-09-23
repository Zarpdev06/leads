from __future__ import annotations

from django.conf import settings as django_settings
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.permissions import IsManagerOrAdmin

from .defaults import settings_schema
from .models import SettingChangeLog, SystemSetting
from .serializers import SettingChangeLogSerializer, SystemSettingSerializer
from .services import (
    clear_cache,
    effective_daily_limit,
    hard_cap,
    public_settings_payload,
    set_setting,
    smtp_status,
    validate_daily_marketing_limit,
)


class SystemSettingViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SystemSetting.objects.all()
    serializer_class = SystemSettingSerializer
    permission_classes = [IsAuthenticated, IsManagerOrAdmin]
    filterset_fields = ["category", "is_secret"]
    search_fields = ["key", "label"]


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsManagerOrAdmin])
def settings_overview(request):
    """Everything the Settings page needs (secrets masked)."""
    return Response({
        "schema": settings_schema(),
        "values": public_settings_payload(),
        "smtp": smtp_status(),
        "limits": {
            "marketing": public_settings_payload().get("sending.daily_marketing_limit"),
            "smtp": smtp_status() and public_settings_payload().get("sending.smtp_daily_limit"),
            "effective": effective_daily_limit(),
            "hard_cap": hard_cap(),
        },
    })


@api_view(["PATCH", "PUT"])
@permission_classes([IsAuthenticated, IsManagerOrAdmin])
def update_settings(request):
    """Partial update of one or many settings.

    Body: {"sending.daily_marketing_limit": 85, "ai.provider": "openai", ...}
    """
    from apps.core.models import log_audit

    updated: dict = {}
    notes: dict = {}
    for key, value in (request.data or {}).items():
        if key == "ai.api_key" and value in ("", "***", None):
            continue  # masked value returned by the UI - keep the stored key

        if key == "sending.daily_marketing_limit":
            value, note = validate_daily_marketing_limit(value)
            if note:
                notes[key] = note
        set_setting(key, value, user=request.user)
        updated[key] = value

    for key, value in updated.items():
        log_audit(
            action="SETTINGS_UPDATED", actor=request.user, entity_type="system_setting",
            entity_id=key, description=f"{key} updated",
            metadata={"value": "***" if "key" in key or "password" in key else value},
            request=request,
        )

    payload = public_settings_payload()
    return Response({"updated": updated, "notes": notes, "values": payload})


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsManagerOrAdmin])
def smtp_status_view(request):
    return Response(smtp_status())


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsManagerOrAdmin])
def reset_settings(request):
    """Restore defaults for one category (or everything)."""
    from .defaults import SETTING_DEFAULTS

    category = request.data.get("category")
    reset = 0
    for key, default, cat, *_ in SETTING_DEFAULTS:
        if category and cat != category:
            continue
        SystemSetting.objects.filter(key=key).delete()
        reset += 1
    clear_cache()
    return Response({"reset": reset})


class SettingChangeLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SettingChangeLog.objects.select_related("changed_by").all()
    serializer_class = SettingChangeLogSerializer
    permission_classes = [IsAuthenticated, IsManagerOrAdmin]
    filterset_fields = ["key"]
    ordering = ["-created_at"]


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsManagerOrAdmin])
def seed_all(request):
    """Seed industries, services, mappings, templates and the default sequence."""
    from apps.campaigns.models import seed_service_mappings, seed_services
    from apps.email_engine.seeds import seed_default_templates
    from apps.leads.classifier import seed_industries

    result = {
        "industries": seed_industries(),
        "services": seed_services(),
        "service_mappings": seed_service_mappings(),
        "templates": seed_default_templates(),
    }
    from apps.email_engine.models import FollowUpSequence

    sequence, _ = FollowUpSequence.objects.get_or_create(
        name="Standard (day 0 / +3 / +7 / +14)",
        defaults={"description": "Initial email plus three follow-ups."},
    )
    result["follow_up_sequence"] = sequence.pk
    return Response(result)
