from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CampaignLeadViewSet,
    CampaignViewSet,
    ServiceIndustryMappingViewSet,
    ServiceViewSet,
    campaign_dashboard,
)

router = DefaultRouter()
router.register(r"campaigns", CampaignViewSet, basename="campaign")
router.register(r"campaign-leads", CampaignLeadViewSet, basename="campaign-lead")
router.register(r"services", ServiceViewSet, basename="service")
router.register(r"service-mappings", ServiceIndustryMappingViewSet, basename="service-mapping")

urlpatterns = [
    path("campaigns/dashboard/", campaign_dashboard, name="campaign-dashboard"),
    *router.urls,
]
