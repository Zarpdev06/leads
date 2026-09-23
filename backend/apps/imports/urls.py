from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ImportFileViewSet,
    ImportJobViewSet,
    LeadSourceViewSet,
    dry_run_mapping,
    import_overview,
)

router = DefaultRouter()
# NOTE: "imports/jobs" must be registered *before* "imports". DRF routes are
# matched in registration order, and the detail route for "imports" is
# r"imports/(?P<pk>[^/.]+)/$" which would otherwise swallow "/imports/jobs/".
router.register(r"imports/jobs", ImportJobViewSet, basename="import-job")
router.register(r"imports", ImportFileViewSet, basename="import-file")
router.register(r"sources", LeadSourceViewSet, basename="source")

urlpatterns = [
    path("imports/overview/", import_overview, name="imports-overview"),
    path("imports/dry-run-mapping/", dry_run_mapping, name="imports-dry-run"),
    *router.urls,
]
