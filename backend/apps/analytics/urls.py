from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CampaignDailyStatViewSet,
    DailyMetricViewSet,
    analytics_root,
    dashboard_summary,
)

router = DefaultRouter()
router.register(r"analytics/metrics", DailyMetricViewSet, basename="daily-metric")
router.register(r"analytics/campaign-stats", CampaignDailyStatViewSet,
                basename="campaign-daily-stat")

urlpatterns = [
    path("analytics/", analytics_root, name="analytics-root"),
    path("dashboard/summary/", dashboard_summary, name="dashboard-summary"),
    *router.urls,
]
