from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AIRecommendationViewSet,
    AIProviderConfigViewSet,
    ai_overview,
    bulk_generate,
    generate,
    match_service,
)

router = DefaultRouter()
router.register(r"ai/providers", AIProviderConfigViewSet, basename="ai-provider")
router.register(r"ai/recommendations", AIRecommendationViewSet, basename="ai-recommendation")

urlpatterns = [
    path("ai/", ai_overview, name="ai-overview"),
    path("ai/generate/", generate, name="ai-generate"),
    path("ai/bulk-generate/", bulk_generate, name="ai-bulk-generate"),
    path("ai/match-service/", match_service, name="ai-match-service"),
    *router.urls,
]
