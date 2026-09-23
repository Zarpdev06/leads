"""Operational endpoints: health, current user, global search, audit log."""
from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.permissions import IsAdminRole
from apps.leads.models import Lead

from .models import AuditLog
from .serializers import AuditLogSerializer


@api_view(["GET"])
@permission_classes([])
def health(_request):
    """Liveness/readiness probe (used by docker healthchecks)."""
    from django.db import connection

    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # pragma: no cover
        db_ok = False
    return Response(
        {
            "status": "ok" if db_ok else "degraded",
            "database": "ok" if db_ok else "down",
            "time": timezone.now().isoformat(),
        },
        status=status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
    )


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related("actor").all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsAdminRole]
    filterset_fields = ["action", "entity_type", "entity_id", "actor"]
    search_fields = ["description", "actor_email", "entity_id"]
    ordering_fields = ["created_at", "action"]
    ordering = ["-created_at"]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def global_search(request):
    """Search businesses, contacts, emails, phones, websites, city, state, industry."""
    q = (request.query_params.get("q") or "").strip()
    limit = min(int(request.query_params.get("limit", 20) or 20), 50)
    if len(q) < 2:
        return Response({"query": q, "count": 0, "results": []})

    qs = (
        Lead.objects.filter(
            Q(company_name__icontains=q)
            | Q(contact_name__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email_normalized__icontains=q.lower())
            | Q(phone_normalized__icontains=q)
            | Q(website_normalized__icontains=q.lower())
            | Q(city__icontains=q)
            | Q(state__icontains=q)
            | Q(industry__name__icontains=q)
            | Q(sub_industry__name__icontains=q)
        )
        .select_related("industry", "sub_industry")
        .order_by("-lead_score", "company_name")[:limit]
    )
    results = [
        {
            "id": lead.id,
            "type": "lead",
            "title": lead.company_name,
            "subtitle": lead.contact_name or lead.email or lead.city or "",
            "email": lead.email,
            "city": lead.city,
            "state": lead.state,
            "industry": lead.industry.name if lead.industry_id else "",
            "score": lead.lead_score,
            "url": f"/leads/{lead.id}",
        }
        for lead in qs
    ]
    return Response({"query": q, "count": len(results), "results": results})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def content_types(_request):  # pragma: no cover - helper for the admin UI
    return Response(
        [
            {"id": ct.id, "app_label": ct.app_label, "model": ct.model}
            for ct in ContentType.objects.all()
        ]
    )
