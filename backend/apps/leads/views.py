from __future__ import annotations

import csv
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.campaigns.models import Campaign, CampaignLead
from apps.core.models import log_audit
from apps.core.permissions import CanModify

from .filters import LeadFilter
from .merge import merge_leads, resolve_duplicate
from .models import EmailStatus, Lead, LeadDuplicate, LeadStatus
from .scoring import apply_score
from .serializers import (
    LeadBulkCampaignSerializer,
    LeadBulkOwnerSerializer,
    LeadBulkStatusSerializer,
    LeadDetailSerializer,
    LeadDuplicateSerializer,
    LeadListSerializer,
    LeadWriteSerializer,
)


class LeadViewSet(viewsets.ModelViewSet):
    """Lead Explorer: server-side filtering, pagination and bulk actions."""

    queryset = (
        Lead.objects.select_related(
            "industry", "sub_industry", "source", "owner", "recommended_service", "company"
        )
        .prefetch_related("campaign_leads__campaign")
        .all()
    )
    permission_classes = [IsAuthenticated, CanModify]
    filterset_class = LeadFilter
    search_fields = ["company_name", "contact_name", "email_normalized",
                     "phone_normalized", "website_domain", "city", "state"]
    ordering_fields = ["lead_score", "company_name", "created_at", "last_contacted_at",
                       "city", "state", "email_status", "crm_stage", "updated_at"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action in {"list"}:
            return LeadListSerializer
        if self.action in {"create", "update", "partial_update"}:
            return LeadWriteSerializer
        return LeadDetailSerializer

    def get_queryset(self):
        queryset = self.queryset
        if self.action == "list":
            if self.request.query_params.get("exclude_merged", "true").lower() != "false":
                queryset = queryset.filter(merged_into__isnull=True)
        return queryset

    def perform_create(self, serializer):
        lead = serializer.save()
        apply_score(lead)
        lead.log_activity(type="IMPORT", title="Lead created manually",
                          description=f"Created by {self.request.user.email}",
                          actor=self.request.user)
        log_audit(action="LEAD_CREATED", actor=self.request.user, entity_type="lead",
                  entity_id=lead.pk, obj=lead, request=self.request)

    def perform_update(self, serializer):
        lead = serializer.save()
        # Keep the email status and score in sync with manual edits.
        if "email" in serializer.validated_data:
            from apps.core.normalizers import normalize_email

            result = normalize_email(lead.email)
            lead.email_normalized = result.normalized
            lead.email_domain = result.domain
            lead.email_status = (
                EmailStatus.VALID if result.is_valid
                else EmailStatus.INVALID if lead.email else EmailStatus.MISSING
            )
            lead.save(update_fields=[
                "email_normalized", "email_domain", "email_status", "updated_at"
            ])
        apply_score(lead)

    # ------------------------------------------------------------------
    # Bulk actions
    # ------------------------------------------------------------------
    @action(detail=False, methods=["post"], url_path="bulk-add-campaign")
    def bulk_add_campaign(self, request):
        serializer = LeadBulkCampaignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = get_object_or_404(Campaign, pk=serializer.validated_data["campaign_id"])
        ids = serializer.validated_data["ids"]
        created = 0
        with transaction.atomic():
            for lead_id in ids:
                _, new = CampaignLead.objects.get_or_create(
                    campaign=campaign, lead_id=lead_id,
                    defaults={"status": CampaignLead.Status.PENDING,
                              "added_by": request.user},
                )
                created += int(new)
        campaign.total_selected = CampaignLead.objects.filter(campaign=campaign).count()
        campaign.save(update_fields=["total_selected", "updated_at"])
        log_audit(action="CAMPAIGN_UPDATED", actor=request.user, entity_type="campaign",
                  entity_id=campaign.pk, description=f"{created} leads added to campaign",
                  request=request)
        return Response({"added": created, "campaign": campaign.pk})

    @action(detail=False, methods=["post"], url_path="bulk-remove-campaign")
    def bulk_remove_campaign(self, request):
        serializer = LeadBulkCampaignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = get_object_or_404(Campaign, pk=serializer.validated_data["campaign_id"])
        from apps.email_engine.models import EmailMessage

        removed = CampaignLead.objects.filter(
            campaign=campaign, lead_id__in=serializer.validated_data["ids"]
        )
        lead_ids = list(removed.values_list("lead_id", flat=True))
        EmailMessage.objects.filter(
            campaign=campaign, lead_id__in=lead_ids,
            status__in=[EmailMessage.Status.QUEUED, EmailMessage.Status.PROCESSING],
        ).update(status=EmailMessage.Status.CANCELLED, cancelled_at=timezone.now())
        count = removed.count()
        removed.delete()
        return Response({"removed": count})

    @action(detail=False, methods=["post"], url_path="bulk-status")
    def bulk_status(self, request):
        serializer = LeadBulkStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        count = 0
        for lead in Lead.objects.filter(id__in=serializer.validated_data["ids"]):
            lead.set_status(serializer.validated_data["status"], actor=request.user,
                            note=serializer.validated_data.get("note", ""))
            count += 1
        return Response({"updated": count})

    @action(detail=False, methods=["post"], url_path="bulk-owner")
    def bulk_owner(self, request):
        serializer = LeadBulkOwnerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = Lead.objects.filter(id__in=serializer.validated_data["ids"]).update(
            owner_id=serializer.validated_data["owner_id"]
        )
        return Response({"updated": updated})

    @action(detail=False, methods=["post"], url_path="bulk-rescore")
    def bulk_rescore(self, request):
        ids = request.data.get("ids") or []
        from .scoring import rescore_queryset

        queryset = Lead.objects.active()
        if ids:
            queryset = queryset.filter(id__in=ids)
        updated = rescore_queryset(queryset)
        return Response({"rescored": updated})

    @action(detail=False, methods=["post"], url_path="bulk-archive")
    def bulk_archive(self, request):
        ids = request.data.get("ids") or []
        updated = Lead.objects.filter(id__in=ids).update(
            lead_status=LeadStatus.ARCHIVED, is_blocked=True,
            blocked_reason="Archived by user",
        )
        return Response({"archived": updated})

    @action(detail=False, methods=["post"], url_path="bulk-enrich")
    def bulk_enrich(self, request):
        """Opt-in enrichment for leads with a website but no email."""
        from .tasks import bulk_enrich_task

        ids = request.data.get("ids") or []
        result = bulk_enrich_task(lead_ids=ids or None,
                                  limit=int(request.data.get("limit", 100)))
        return Response(result)

    @action(detail=False, methods=["get"])
    def export(self, request):
        """Stream a CSV export of the current filter (no memory blow-up)."""
        queryset = self.filter_queryset(self.get_queryset())
        ids = request.query_params.get("ids")
        if ids:
            queryset = queryset.filter(id__in=[int(i) for i in ids.split(",") if i.isdigit()])

        columns = [
            "company_name", "contact_name", "first_name", "last_name", "job_title",
            "email", "phone", "website", "street_address", "city", "state", "zip_code",
            "country", "employee_count", "industry", "sub_industry", "lead_score",
            "lead_quality", "lead_status", "email_status", "crm_stage", "source",
            "source_category", "created_at",
        ]

        def row_generator():
            buffer = _Echo()
            writer = csv.writer(buffer)
            yield writer.writerow(columns)
            for lead in queryset.iterator(chunk_size=1000):
                yield writer.writerow([
                    lead.company_name, lead.contact_name, lead.first_name,
                    lead.last_name, lead.job_title, lead.email, lead.phone,
                    lead.website, lead.street_address, lead.city, lead.state,
                    lead.zip_code, lead.country, lead.employee_count,
                    lead.industry.name if lead.industry_id else "",
                    lead.sub_industry.name if lead.sub_industry_id else "",
                    lead.lead_score, lead.lead_quality, lead.lead_status,
                    lead.email_status, lead.crm_stage,
                    lead.source.name if lead.source_id else "",
                    lead.source_category, lead.created_at.isoformat(),
                ])

        response = StreamingHttpResponse(row_generator(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="leads_export.csv"'
        log_audit(action="EXPORT", actor=request.user, entity_type="lead",
                  entity_id="csv", description="Lead export", request=request)
        return response

    # ------------------------------------------------------------------
    # Per-lead actions
    # ------------------------------------------------------------------
    @action(detail=True, methods=["post"])
    def rescore(self, request, pk=None):
        lead = self.get_object()
        result = apply_score(lead)
        return Response(result.as_dict())

    @action(detail=True, methods=["post"])
    def enrich(self, request, pk=None):
        from .tasks import enrich_lead_task

        lead = self.get_object()
        result = enrich_lead_task(lead.pk)
        return Response(result)

    @action(detail=True, methods=["post"])
    def generate_ai(self, request, pk=None):
        from apps.ai_engine.generator import generate_email_for_lead

        lead = self.get_object()
        campaign_id = request.data.get("campaign_id")
        campaign = Campaign.objects.filter(pk=campaign_id).first() if campaign_id else None
        result = generate_email_for_lead(lead, campaign=campaign, actor=request.user,
                                         use_cache=False)
        return Response(result.as_dict())

    @action(detail=True, methods=["get"])
    def duplicates(self, request, pk=None):
        from .dedupe import find_duplicates_for_lead

        lead = self.get_object()
        matches = find_duplicates_for_lead(lead)
        return Response([
            {"lead_id": match.lead_id, "candidate_id": match.candidate_id,
             "confidence": match.confidence, "method": match.method,
             "details": match.details,
             "company": match.candidate.company_name,
             "email": match.candidate.email_normalized}
            for match in matches
        ])

    @action(detail=True, methods=["post"])
    def merge(self, request, pk=None):
        """Merge another lead into this one: {other_id, keep_both}"""
        lead = self.get_object()
        other = get_object_or_404(Lead, pk=request.data.get("other_id"))
        summary = merge_leads(
            lead, other, actor=request.user,
            keep_both=bool(request.data.get("keep_both")),
        )
        return Response(summary)

    @action(detail=True, methods=["post"])
    def block(self, request, pk=None):
        lead = self.get_object()
        reason = request.data.get("reason", "Blocked manually")
        lead.stop_outreach(reason)
        lead.log_activity(type="STATUS_CHANGE", title="Outreach blocked",
                          description=reason, actor=request.user)
        return Response({"blocked": True, "reason": reason})

    @action(detail=True, methods=["post"])
    def unblock(self, request, pk=None):
        lead = self.get_object()
        lead.is_blocked = False
        lead.blocked_reason = ""
        lead.save(update_fields=["is_blocked", "blocked_reason", "updated_at"])
        return Response({"blocked": False})


class LeadDuplicateViewSet(viewsets.ModelViewSet):
    """Duplicate Review: merge / keep both / ignore."""

    queryset = LeadDuplicate.objects.select_related("lead", "candidate").all()
    serializer_class = LeadDuplicateSerializer
    permission_classes = [IsAuthenticated, CanModify]
    filterset_fields = ["resolution", "method", "confidence"]
    ordering_fields = ["confidence", "created_at"]
    ordering = ["-confidence"]

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        duplicate = self.get_object()
        resolution = request.data.get("resolution")
        if resolution not in dict(LeadDuplicate.Resolution.choices):
            return Response({"detail": "Unknown resolution."},
                            status=status.HTTP_400_BAD_REQUEST)
        result = resolve_duplicate(duplicate, resolution, actor=request.user)
        return Response(result)

    @action(detail=False, methods=["post"])
    def bulk_resolve(self, request):
        ids = request.data.get("ids") or []
        resolution = request.data.get("resolution")
        if resolution not in dict(LeadDuplicate.Resolution.choices):
            return Response({"detail": "Unknown resolution."},
                            status=status.HTTP_400_BAD_REQUEST)
        resolved = 0
        for duplicate in LeadDuplicate.objects.filter(id__in=ids):
            resolve_duplicate(duplicate, resolution, actor=request.user)
            resolved += 1
        return Response({"resolved": resolved})

    @action(detail=False, methods=["post"])
    def run_detection(self, request):
        from .dedupe import detect_duplicates

        min_confidence = int(request.data.get("min_confidence", 55))
        source_id = request.data.get("source_id")
        queryset = Lead.objects.active()
        if source_id:
            queryset = queryset.filter(source_id=source_id)
        created = detect_duplicates(queryset, min_confidence=min_confidence)
        return Response({"candidates_created": created})


class _Echo:
    """File-like object that returns the value written (for streaming CSV)."""

    def write(self, value):
        return value


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def lead_stats(request):
    """Counts for the Lead Explorer header (respects the current filters)."""
    queryset = LeadFilter(request.GET, queryset=Lead.objects.active()).qs
    return Response({
        "total": queryset.count(),
        "with_email": queryset.exclude(email_normalized="").count(),
        "without_email": queryset.filter(email_normalized="").count(),
        "valid_email": queryset.filter(email_status=EmailStatus.VALID).count(),
        "invalid_email": queryset.filter(email_status=EmailStatus.INVALID).count(),
        "with_website": queryset.exclude(website_domain="").count(),
        "suppressed": queryset.filter(lead_status=LeadStatus.SUPPRESSED).count(),
        "by_quality": list(queryset.values("lead_quality").annotate(count=Count("id"))),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def missing_email_leads(request):
    """The 'Missing email leads' workspace."""
    from apps.core.pagination import StandardResultsSetPagination

    queryset = Lead.objects.active().filter(email_normalized="").exclude(
        lead_status=LeadStatus.ARCHIVED
    ).select_related("industry", "sub_industry", "source").order_by("-created_at")

    if request.GET.get("has_website") == "true":
        queryset = queryset.exclude(website_domain="")
    if request.GET.get("state"):
        queryset = queryset.filter(state__iexact=request.GET["state"])
    if request.GET.get("search"):
        value = request.GET["search"]
        queryset = queryset.filter(
            Q(company_name__icontains=value) | Q(contact_name__icontains=value)
            | Q(city__icontains=value)
        )

    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(queryset, request)
    data = [
        {
            "id": lead.pk,
            "company_name": lead.company_name,
            "contact_name": lead.contact_name,
            "phone": lead.phone,
            "website": lead.website_domain,
            "city": lead.city,
            "state": lead.state,
            "industry": lead.sub_industry.name if lead.sub_industry_id else (
                lead.industry.name if lead.industry_id else ""),
            "enrichment_status": lead.enrichment_status,
            "enrichment_note": lead.enrichment_note,
            "source": lead.source.name if lead.source_id else "",
        }
        for lead in page
    ]
    return paginator.get_paginated_response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def upcoming_followups(request):
    """Follow-ups due in the next N days."""
    days = int(request.GET.get("days", 7) or 7)
    until = timezone.now() + timedelta(days=days)
    rows = (
        CampaignLead.objects.filter(
            next_follow_up_at__isnull=False,
            next_follow_up_at__lte=until,
            status__in=[CampaignLead.Status.SENT, CampaignLead.Status.FOLLOW_UP],
        )
        .select_related("lead", "campaign")
        .order_by("next_follow_up_at")[:200]
    )
    return Response([
        {
            "id": row.pk,
            "lead_id": row.lead_id,
            "company": row.lead.company_name,
            "email": row.lead.email_normalized,
            "campaign": row.campaign.name,
            "campaign_id": row.campaign_id,
            "step": row.current_step,
            "next_follow_up_at": row.next_follow_up_at,
            "status": row.status,
        }
        for row in rows
    ])
