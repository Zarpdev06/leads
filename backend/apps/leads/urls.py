from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    LeadDuplicateViewSet,
    LeadViewSet,
    lead_stats,
    missing_email_leads,
    upcoming_followups,
)

router = DefaultRouter()
router.register(r"leads", LeadViewSet, basename="lead")
router.register(r"duplicates", LeadDuplicateViewSet, basename="lead-duplicate")

urlpatterns = [
    path("leads/stats/", lead_stats, name="lead-stats"),
    path("leads/missing-email/", missing_email_leads, name="lead-missing-email"),
    path("follow-ups/upcoming/", upcoming_followups, name="followups-upcoming"),
    *router.urls,
]
