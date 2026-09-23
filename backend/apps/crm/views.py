from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.permissions import CanModify
from apps.leads.models import Lead

from .models import CRMActivity, LeadNote
from .serializers import (
    BulkStageSerializer,
    CRMActivitySerializer,
    LeadNoteSerializer,
    StageMoveSerializer,
)


class CRMActivityViewSet(viewsets.ModelViewSet):
    queryset = CRMActivity.objects.select_related("actor", "lead").all()
    serializer_class = CRMActivitySerializer
    permission_classes = [IsAuthenticated, CanModify]
    filterset_fields = ["lead", "type", "actor"]
    search_fields = ["title", "description"]
    ordering_fields = ["occurred_at", "created_at"]
    ordering = ["-occurred_at"]

    def perform_create(self, serializer):
        activity = serializer.save(actor=self.request.user)
        if activity.type == CRMActivity.Type.NOTE:
            LeadNote.objects.create(
                lead=activity.lead, body=activity.description or activity.title,
                author=self.request.user,
            )


class LeadNoteViewSet(viewsets.ModelViewSet):
    queryset = LeadNote.objects.select_related("author").all()
    serializer_class = LeadNoteSerializer
    permission_classes = [IsAuthenticated, CanModify]
    filterset_fields = ["lead", "is_pinned"]
    ordering = ["-is_pinned", "-created_at"]

    def perform_create(self, serializer):
        note = serializer.save(author=self.request.user)
        CRMActivity.objects.create(
            lead=note.lead, type=CRMActivity.Type.NOTE,
            title=f"Note added by {self.request.user.email}",
            description=note.body[:280], actor=self.request.user,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pipeline_board_view(request):
    """Stages with counts and pipeline value (optionally filtered by owner)."""
    from .models import pipeline_board

    owner_id = request.query_params.get("owner")
    queryset = Lead.objects.filter(merged_into__isnull=True)
    if owner_id:
        queryset = queryset.filter(owner_id=owner_id)
    if request.query_params.get("search"):
        q = request.query_params["search"]
        queryset = queryset.filter(
            Q(company_name__icontains=q) | Q(contact_name__icontains=q)
            | Q(email_normalized__icontains=q)
        )
    return Response({"stages": pipeline_board(queryset=queryset)})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def stage_leads(request, stage: str):
    """Leads in one pipeline stage (paginated through the standard pagination)."""
    from apps.core.pagination import StandardResultsSetPagination
    from apps.leads.serializers import LeadListSerializer

    queryset = Lead.objects.filter(crm_stage=stage, merged_into__isnull=True).select_related(
        "industry", "sub_industry", "owner"
    ).order_by("-updated_at")
    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(LeadListSerializer(page, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanModify])
def move_lead(request, lead_id: int):
    """Move one lead to a new pipeline stage (records history)."""
    lead = get_object_or_404(Lead, pk=lead_id)
    serializer = StageMoveSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    if data.get("deal_value") is not None:
        lead.deal_value = data["deal_value"]
    if data.get("expected_close_date"):
        lead.expected_close_date = data["expected_close_date"]
    if data["stage"] == "LOST" and data.get("lost_reason"):
        lead.lost_reason = data["lost_reason"]
    if data["stage"] == "WON":
        lead.set_stage("WON", actor=request.user, note=data.get("note", ""))
    else:
        lead.set_stage(data["stage"], actor=request.user, note=data.get("note", ""))
    lead.save()
    return Response({"id": lead.pk, "crm_stage": lead.crm_stage}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanModify])
def bulk_move(request):
    serializer = BulkStageSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    moved = 0
    for lead in Lead.objects.filter(id__in=data["ids"]):
        lead.set_stage(data["stage"], actor=request.user, note=data.get("note", ""))
        moved += 1
    return Response({"moved": moved})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def lead_timeline(request, lead_id: int):
    """Merged timeline: activities + emails + campaigns for one lead."""
    from apps.email_engine.models import EmailMessage

    lead = get_object_or_404(Lead, pk=lead_id)
    items: list[dict] = []

    for activity in lead.activities.select_related("actor")[:300]:
        items.append({
            "type": "activity",
            "kind": activity.type,
            "title": activity.title,
            "description": activity.description,
            "at": activity.occurred_at,
            "actor": getattr(activity.actor, "email", "") or "system",
        })
    for message in EmailMessage.objects.filter(lead=lead).order_by("-created_at")[:200]:
        items.append({
            "type": "email",
            "kind": message.status,
            "title": message.subject,
            "description": f"to {message.to_email}",
            "at": message.sent_at or message.created_at,
            "actor": "system",
            "message_id": message.pk,
        })
    items.sort(key=lambda item: item["at"], reverse=True)
    return Response({"lead_id": lead.pk, "timeline": items[:300]})
