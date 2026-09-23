from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import SuppressionLogViewSet, SuppressionViewSet, suppress_leads

router = DefaultRouter()
router.register(r"suppression", SuppressionViewSet, basename="suppression")
router.register(r"suppression-logs", SuppressionLogViewSet, basename="suppression-log")

urlpatterns = [
    path("leads/suppress/", suppress_leads, name="leads-suppress"),
    *router.urls,
]
