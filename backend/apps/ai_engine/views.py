from __future__ import annotations

from django.conf import settings
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.core.permissions import CanModify, IsManagerOrAdmin
from apps.leads.models import Lead
from apps.settings.services import get_setting

from .models import AIProviderConfig, AIRecommendation
from .providers.registry import available_providers, get_provider
from .serializers import (
    AIProviderConfigSerializer,
    AIProviderConfigWriteSerializer,
    AIRecommendationSerializer,
    GenerateSerializer,
)


class AIProviderConfigViewSet(viewsets.ModelViewSet):
    queryset = AIProviderConfig.objects.all()
    permission_classes = [IsAuthenticated, IsManagerOrAdmin]
    filterset_fields = ["provider", "is_active"]

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return AIProviderConfigWriteSerializer
        return AIProviderConfigSerializer

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        from django.utils import timezone

        config = self.get_object()
        provider = get_provider(config.provider)
        try:
            ok, message = provider.test_connection()
        except Exception as exc:  # pragma: no cover
            ok, message = False, str(exc)
        config.last_tested_at = timezone.now()
        config.last_test_ok = ok
        config.last_error = "" if ok else message[:500]
        config.save(update_fields=["last_tested_at", "last_test_ok", "last_error",
                                   "updated_at"])
        return Response({"ok": ok, "message": message})

    @action(detail=False, methods=["get"])
    def catalog(self, request):
        return Response(available_providers())


class AIRecommendationViewSet(viewsets.ModelViewSet):
    queryset = AIRecommendation.objects.select_related("lead", "service").all()
    serializer_class = AIRecommendationSerializer
    permission_classes = [IsAuthenticated, CanModify]
    filterset_fields = ["lead", "campaign", "provider", "status", "service"]
    ordering = ["-created_at"]

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        recommendation = self.get_object()
        recommendation.status = AIRecommendation.Status.APPROVED
        recommendation.approved_by = request.user
        recommendation.save(update_fields=["status", "approved_by", "updated_at"])
        return Response(AIRecommendationSerializer(recommendation).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ai_overview(request):
    """Status card for the AI page (no secrets)."""
    provider = get_provider()
    configured = AIProviderConfig.objects.filter(is_active=True)
    return Response({
        "enabled": bool(get_setting("ai.enabled", settings.AI_ENABLED)),
        "active_provider": provider.key,
        "active_label": provider.label,
        "model": provider.model or "(default)",
        "requires_api_key": provider.requires_api_key,
        "has_api_key": bool(provider.api_key),
        "providers": available_providers(),
        "configured_providers": AIProviderConfigSerializer(
            configured, many=True
        ).data,
        "brand_voice": get_setting("ai.brand_voice", ""),
        "safety_strict": bool(get_setting("ai.safety_strict", True)),
        "stats": {
            "generated": AIRecommendation.objects.count(),
            "generated_today": AIRecommendation.objects.filter(
                created_at__date=timezone.localdate()
            ).count(),
            "rejected": AIRecommendation.objects.filter(safety_passed=False).count(),
        },
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate(request):
    """Generate AI copy for one lead (preview or cached)."""
    throttle = ScopedRateThrottle()
    throttle.scope = "ai"

    serializer = GenerateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    lead = get_object_or_404(Lead, pk=serializer.validated_data["lead_id"])

    campaign = None
    if serializer.validated_data.get("campaign_id"):
        from apps.campaigns.models import Campaign

        campaign = Campaign.objects.filter(
            pk=serializer.validated_data["campaign_id"]
        ).first()
    template = None
    if serializer.validated_data.get("template_id"):
        from apps.email_engine.models import EmailTemplate

        template = EmailTemplate.objects.filter(
            pk=serializer.validated_data["template_id"]
        ).first()
    template = template or (campaign.template if campaign else None)

    from .generator import generate_email_for_lead

    result = generate_email_for_lead(
        lead,
        template=template,
        campaign=campaign,
        instructions=serializer.validated_data.get("instructions", ""),
        actor=request.user,
        use_cache=not serializer.validated_data.get("regenerate", False),
    )
    return Response(result.as_dict())


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def match_service(request):
    from .serializers import ServiceMatchSerializer
    from .service_matching import recommend_service

    serializer = ServiceMatchSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    lead = get_object_or_404(Lead, pk=serializer.validated_data["lead_id"])
    recommendation = recommend_service(
        lead, use_ai=serializer.validated_data.get("use_ai", True)
    )
    return Response(recommendation.as_dict())


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanModify])
def bulk_generate(request):
    """Queue AI generation for many leads."""
    from .tasks import generate_lead_recommendation

    ids = request.data.get("ids") or []
    campaign_id = request.data.get("campaign_id")
    queued = 0
    for lead_id in ids[:500]:
        generate_lead_recommendation.delay(lead_id, campaign_id, request.user.pk)
        queued += 1
    return Response({"queued": queued})
