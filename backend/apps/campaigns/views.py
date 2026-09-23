from __future__ import annotations

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.models import log_audit
from apps.core.permissions import CanModify, IsManagerOrAdmin
from apps.leads.eligibility import eligible_queryset
from apps.leads.models import Lead
from apps.settings.services import effective_daily_limit

from .models import Campaign, CampaignLead, Service, ServiceIndustryMapping
from .serializers import (
    CampaignDetailSerializer,
    CampaignLeadSerializer,
    CampaignListSerializer,
    CampaignWriteSerializer,
    ServiceIndustryMappingSerializer,
    ServiceSerializer,
)


class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    permission_classes = [IsAuthenticated, CanModify]
    search_fields = ["name", "category"]
    filterset_fields = ["category", "is_active"]
    ordering = ["sort_order", "name"]

    @action(detail=False, methods=["post"])
    def seed(self, request):
        from .models import seed_service_mappings, seed_services

        created = seed_services()
        mappings = seed_service_mappings()
        return Response({"services_created": created, "mappings_created": mappings})


class ServiceIndustryMappingViewSet(viewsets.ModelViewSet):
    queryset = ServiceIndustryMapping.objects.select_related("industry", "service").all()
    serializer_class = ServiceIndustryMappingSerializer
    permission_classes = [IsAuthenticated, CanModify]
    filterset_fields = ["industry", "service", "is_active"]
    ordering = ["priority"]


class CampaignViewSet(viewsets.ModelViewSet):
    queryset = Campaign.objects.select_related(
        "template", "recommended_service", "follow_up_sequence"
    ).prefetch_related("target_industries", "sources")
    permission_classes = [IsAuthenticated, CanModify]
    search_fields = ["name", "description"]
    filterset_fields = ["status"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return CampaignListSerializer
        if self.action in {"create", "update", "partial_update"}:
            return CampaignWriteSerializer
        return CampaignDetailSerializer

    def perform_create(self, serializer):
        campaign = serializer.save(created_by=self.request.user)
        log_audit(action="CAMPAIGN_CREATED", actor=self.request.user,
                  entity_type="campaign", entity_id=campaign.pk, obj=campaign,
                  description=f"Campaign '{campaign.name}' created",
                  request=self.request)

    # ------------------------------------------------------------------
    @action(detail=True, methods=["get"])
    def audience(self, request, pk=None):
        """Wizard: how many leads match, and a preview of them."""
        campaign = self.get_object()
        queryset = eligible_queryset(campaign)
        count = queryset.count()
        sample = list(
            queryset.order_by("-lead_score").values(
                "id", "company_name", "contact_name", "email_normalized", "city",
                "state", "lead_score", "industry__name", "sub_industry__name"
            )[:10]
        )
        return Response({
            "count": count,
            "eligible": count,
            "daily_limit": min(campaign.daily_limit, effective_daily_limit()),
            "estimated_days": _estimate_days(count, campaign.daily_limit),
            "sample": sample,
        })

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated,
                                                               IsManagerOrAdmin])
    def start(self, request, pk=None):
        campaign = self.get_object()
        if not campaign.can_start:
            return Response(
                {"detail": f"Cannot start a campaign in status {campaign.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if campaign.template is None:
            return Response({"detail": "Choose an email template first."},
                            status=status.HTTP_400_BAD_REQUEST)

        campaign.status = Campaign.Status.RUNNING
        campaign.started_at = campaign.started_at or timezone.now()
        campaign.save(update_fields=["status", "started_at", "updated_at"])

        dispatch = bool(request.data.get("dispatch_now", True))
        if dispatch:
            from apps.email_engine.tasks import dispatch_campaign_task

            dispatch_campaign_task.delay(campaign.pk, request.user.pk)
        log_audit(action="CAMPAIGN_STARTED", actor=request.user, entity_type="campaign",
                  entity_id=campaign.pk, obj=campaign,
                  description="Campaign started", request=request)
        return Response({"status": campaign.status, "dispatching": dispatch})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated,
                                                               IsManagerOrAdmin])
    def pause(self, request, pk=None):
        campaign = self.get_object()
        campaign.status = Campaign.Status.PAUSED
        campaign.save(update_fields=["status", "updated_at"])
        log_audit(action="CAMPAIGN_PAUSED", actor=request.user, entity_type="campaign",
                  entity_id=campaign.pk, obj=campaign, request=request)
        return Response({"status": campaign.status})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated,
                                                               IsManagerOrAdmin])
    def resume(self, request, pk=None):
        campaign = self.get_object()
        if campaign.status not in {Campaign.Status.PAUSED, Campaign.Status.READY}:
            return Response({"detail": "Only paused campaigns can be resumed."},
                            status=status.HTTP_400_BAD_REQUEST)
        campaign.status = Campaign.Status.RUNNING
        campaign.save(update_fields=["status", "updated_at"])
        from apps.email_engine.tasks import dispatch_campaign_task

        dispatch_campaign_task.delay(campaign.pk, request.user.pk)
        return Response({"status": campaign.status})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated,
                                                               IsManagerOrAdmin])
    def cancel(self, request, pk=None):
        campaign = self.get_object()
        from apps.email_engine.services import cancel_campaign_messages

        cancelled = cancel_campaign_messages(campaign, reason="Cancelled by user")
        campaign.status = Campaign.Status.CANCELLED
        campaign.completed_at = timezone.now()
        campaign.save(update_fields=["status", "completed_at", "updated_at"])
        log_audit(action="CAMPAIGN_CANCELLED", actor=request.user, entity_type="campaign",
                  entity_id=campaign.pk, obj=campaign,
                  description=f"{cancelled} queued messages cancelled", request=request)
        return Response({"status": campaign.status, "cancelled_messages": cancelled})

    @action(detail=True, methods=["post"], url_path="dispatch")
    def dispatch_now(self, request, pk=None):
        """Materialize + schedule messages now (idempotent).

        NOTE: the method is *not* called `dispatch` - that name belongs to
        Django/DRF's request dispatcher.
        """
        from apps.email_engine.tasks import dispatch_campaign_task

        campaign = self.get_object()
        result = dispatch_campaign_task(campaign.pk, request.user.pk)
        return Response(result)

    @action(detail=True, methods=["get"])
    def leads(self, request, pk=None):
        from apps.core.pagination import StandardResultsSetPagination

        campaign = self.get_object()
        queryset = campaign.campaign_leads.select_related("lead").order_by("-created_at")
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(CampaignLeadSerializer(page, many=True).data)

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        campaign = self.get_object()
        campaign.recalculate_stats()
        return Response({
            "id": campaign.pk,
            "name": campaign.name,
            "status": campaign.status,
            "selected": campaign.total_selected,
            "queued": campaign.total_queued,
            "sent": campaign.total_sent,
            "failed": campaign.total_failed,
            "opened": campaign.total_opened,
            "clicked": campaign.total_clicked,
            "replied": campaign.total_replied,
            "bounced": campaign.total_bounced,
            "unsubscribed": campaign.total_unsubscribed,
            "reply_rate": round(campaign.reply_rate, 2),
            "open_rate": round(campaign.open_rate, 2),
            "by_step": list(
                campaign.email_messages.values("step_number").annotate(
                    count=Count("id")
                ).order_by("step_number")
            ),
        })

    @action(detail=True, methods=["get"])
    def preview_email(self, request, pk=None):
        """Realistic preview of what recipients will receive."""
        from apps.email_engine.sender import compose_message

        campaign = self.get_object()
        lead_id = request.query_params.get("lead_id")
        lead = None
        if lead_id:
            lead = Lead.objects.filter(pk=lead_id).first()
        if lead is None:
            lead = eligible_queryset(campaign).order_by("-lead_score").first()
        if lead is None:
            return Response({"detail": "No eligible lead matches this campaign."},
                            status=status.HTTP_404_NOT_FOUND)

        message = compose_message(lead=lead, template=campaign.template, campaign=campaign)
        return Response({
            "lead_id": lead.pk,
            "to": message.to_email,
            "to_name": message.to_name,
            "from": f"{message.from_name} <{message.from_email}>".strip(),
            "reply_to": message.reply_to,
            "subject": message.subject,
            "body_html": message.body_html,
            "body_text": message.body_text,
            "is_ai_generated": message.is_ai_generated,
            "ai_provider": message.ai_provider,
            "recommended_service": message.recommended_service,
        })


def _estimate_days(count: int, daily_limit: int) -> int:
    limit = max(1, min(daily_limit or 90, effective_daily_limit()))
    return -(-count // limit) if count else 0


class CampaignLeadViewSet(viewsets.ModelViewSet):
    queryset = CampaignLead.objects.select_related("lead", "campaign").all()
    serializer_class = CampaignLeadSerializer
    permission_classes = [IsAuthenticated, CanModify]
    filterset_fields = ["campaign", "status", "lead"]
    ordering = ["-created_at"]

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        campaign_lead = self.get_object()
        reason = request.data.get("reason", "Stopped manually")
        campaign_lead.stop(reason)
        from apps.email_engine.models import EmailMessage

        EmailMessage.objects.filter(
            campaign_lead=campaign_lead,
            status__in=[EmailMessage.Status.QUEUED, EmailMessage.Status.PROCESSING],
        ).update(status=EmailMessage.Status.CANCELLED, cancelled_at=timezone.now())
        return Response({"stopped": True, "reason": reason})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def campaign_dashboard(request):
    """Cards for the Campaigns list page."""
    return Response({
        "total": Campaign.objects.count(),
        "running": Campaign.objects.filter(status=Campaign.Status.RUNNING).count(),
        "draft": Campaign.objects.filter(status=Campaign.Status.DRAFT).count(),
        "completed": Campaign.objects.filter(status=Campaign.Status.COMPLETED).count(),
        "sent_total": Campaign.objects.aggregate(total=Sum("total_sent"))["total"] or 0,
        "daily_limit": effective_daily_limit(),
    })
