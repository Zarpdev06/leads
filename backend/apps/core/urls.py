from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AuditLogViewSet, content_types, global_search

router = DefaultRouter()
router.register(r"audit-logs", AuditLogViewSet, basename="audit-log")

urlpatterns = [
    path("search/", global_search, name="global-search"),
    path("meta/content-types/", content_types, name="content-types"),
    *router.urls,
]
