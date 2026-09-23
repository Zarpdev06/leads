from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CRMActivityViewSet,
    LeadNoteViewSet,
    bulk_move,
    lead_timeline,
    move_lead,
    pipeline_board_view,
    stage_leads,
)

router = DefaultRouter()
router.register(r"crm/activities", CRMActivityViewSet, basename="crm-activity")
router.register(r"crm/notes", LeadNoteViewSet, basename="crm-note")

urlpatterns = [
    path("crm/pipeline/", pipeline_board_view, name="crm-pipeline"),
    path("crm/pipeline/<str:stage>/leads/", stage_leads, name="crm-stage-leads"),
    path("crm/leads/<int:lead_id>/move/", move_lead, name="crm-move-lead"),
    path("crm/leads/<int:lead_id>/timeline/", lead_timeline, name="crm-timeline"),
    path("crm/bulk-move/", bulk_move, name="crm-bulk-move"),
    *router.urls,
]
