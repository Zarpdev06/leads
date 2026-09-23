from __future__ import annotations

from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services
from .models import CampaignDailyStat, DailyMetric
from .serializers import CampaignDailyStatSerializer, DailyMetricSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analytics_root(request):
    """Everything the Analytics page needs (single round trip)."""
    days = int(request.query_params.get("days", 30) or 30)
    return Response({
        "overview": services.overview(),
        "capacity": services.capacity(),
        "daily_outreach": services.daily_outreach(days),
        "campaigns": services.campaign_performance(days),
        "industries": services.industry_performance(days),
        "locations": services.location_performance(days),
        "funnel": services.funnel(),
        "services": services.service_interest(days),
        "ai_vs_template": services.ai_vs_template(days),
        "rates": services.rates(days),
        "lead_quality": services.lead_quality_breakdown(),
        "email_status": services.email_status_breakdown(),
        "sources": services.source_quality(),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    """KPI cards + capacity meter for the home dashboard."""
    from apps.email_engine.models import EmailMessage

    recent = EmailMessage.objects.select_related("lead", "campaign").order_by(
        "-sent_at", "-created_at"
    )[:8]
    return Response({
        "overview": services.overview(),
        "capacity": services.capacity(),
        "daily_outreach": services.daily_outreach(14),
        "funnel": services.funnel(),
        "lead_quality": services.lead_quality_breakdown(),
        "email_status": services.email_status_breakdown(),
        "recent_activity": [
            {
                "id": message.pk,
                "to": message.to_email,
                "subject": message.subject,
                "status": message.status,
                "sent_at": message.sent_at,
                "campaign": message.campaign.name if message.campaign_id else "",
                "company": message.lead.company_name if message.lead_id else "",
            }
            for message in recent
        ],
    })


class DailyMetricViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DailyMetric.objects.all()
    serializer_class = DailyMetricSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["key", "scope", "dimension"]
    ordering = ["-date"]


class CampaignDailyStatViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CampaignDailyStat.objects.select_related("campaign").all()
    serializer_class = CampaignDailyStatSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["campaign"]
    ordering = ["-date"]
