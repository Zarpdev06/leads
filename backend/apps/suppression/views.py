from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.permissions import CanModify, IsManagerOrAdmin

from .models import Suppression, SuppressionLog
from .serializers import (
    SuppressionCreateSerializer,
    SuppressionLogSerializer,
    SuppressionSerializer,
)
from .services import add_suppression, is_suppressed, remove_suppression


class SuppressionViewSet(viewsets.ModelViewSet):
    queryset = Suppression.objects.select_related("lead", "created_by").all()
    serializer_class = SuppressionSerializer
    permission_classes = [IsAuthenticated, CanModify]
    filterset_fields = ["reason", "is_active", "source"]
    search_fields = ["email_normalized", "email", "note"]
    ordering_fields = ["created_at", "email_normalized"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        return SuppressionCreateSerializer if self.action == "create" else SuppressionSerializer

    def perform_destroy(self, instance):
        remove_suppression(
            instance.email_normalized,
            actor=self.request.user,
            note="Deleted from suppression UI",
        )

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated, CanModify])
    def bulk_add(self, request):
        """Body: {emails: [...], reason, note}"""
        emails = request.data.get("emails") or []
        if isinstance(emails, str):
            emails = [line for line in emails.replace(",", "\n").splitlines() if line.strip()]
        reason = request.data.get("reason", Suppression.Reason.MANUAL_BLOCK)
        note = request.data.get("note", "")
        added = skipped = 0
        for email in emails:
            try:
                add_suppression(
                    str(email).strip(), reason=reason, note=note, source="MANUAL",
                    actor=request.user,
                )
                added += 1
            except ValueError:
                skipped += 1
        return Response({"added": added, "skipped": skipped})

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated, CanModify])
    def check(self, request):
        emails = request.data.get("emails") or []
        return Response({email: is_suppressed(email) for email in emails})

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        logs = SuppressionLog.objects.filter(suppression_id=pk).order_by("-created_at")
        return Response(SuppressionLogSerializer(logs, many=True).data)


class SuppressionLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SuppressionLog.objects.select_related("actor").all()
    serializer_class = SuppressionLogSerializer
    permission_classes = [IsAuthenticated, IsManagerOrAdmin]
    search_fields = ["email_normalized", "note"]
    ordering = ["-created_at"]


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def suppress_leads(request):
    """Add every lead in `ids` to the suppression list and stop their outreach."""
    from apps.leads.models import Lead, LeadStatus

    ids = request.data.get("ids") or []
    reason = request.data.get("reason", Suppression.Reason.MANUAL_BLOCK)
    note = request.data.get("note", "")
    count = 0
    for lead in Lead.objects.filter(id__in=ids).exclude(email_normalized=""):
        add_suppression(
            lead.email_normalized, reason=reason, note=note, source="MANUAL",
            actor=request.user, lead=lead,
        )
        lead.do_not_contact = True
        lead.is_blocked = True
        lead.blocked_reason = note or "Suppressed"
        lead.lead_status = LeadStatus.SUPPRESSED
        lead.save(update_fields=[
            "do_not_contact", "is_blocked", "blocked_reason", "lead_status", "updated_at"
        ])
        lead.stop_outreach("Suppressed")
        lead.log_activity(
            type="STATUS_CHANGE", title="Added to suppression list",
            description=note, actor=request.user, metadata={"reason": reason},
        )
        count += 1
    return Response({"suppressed": count}, status=status.HTTP_200_OK)
