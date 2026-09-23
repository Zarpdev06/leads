"""
Root URL configuration.

/api/...            REST API (JWT or session auth)
/admin/...          Django admin
/t/o/<uid>.png      open tracking pixel       (public, token based)
/t/c/<uid>          click tracking redirect   (public, token based)
/unsubscribe/<t>/   unsubscribe (also /api/unsubscribe/<t>/)
"""
from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.views import health

api_urlpatterns = [
    # --- health & meta ---------------------------------------------------
    path("health/", health, name="health"),
    # --- auth & users ----------------------------------------------------
    path("", include("apps.accounts.urls")),
    # --- core ------------------------------------------------------------
    path("", include("apps.core.urls")),
    # --- data ------------------------------------------------------------
    path("", include("apps.imports.urls")),
    path("", include("apps.companies.urls")),
    path("", include("apps.contacts.urls")),
    path("", include("apps.leads.urls")),
    # --- outreach --------------------------------------------------------
    path("", include("apps.campaigns.urls")),
    path("", include("apps.email_engine.urls")),
    path("", include("apps.ai_engine.urls")),
    path("", include("apps.suppression.urls")),
    # --- crm / analytics / settings --------------------------------------
    path("", include("apps.crm.urls")),
    path("", include("apps.analytics.urls")),
    path("", include("apps.settings.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(api_urlpatterns)),
    # Public tracking + unsubscribe (mounted at the root so links stay short)
    path("", include("apps.email_engine.tracking_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(_request):
    """Index of the available API namespaces."""
    return Response({
        "api": "/api/",
        "health": "/api/health/",
        "groups": [
            "/api/auth/", "/api/imports/", "/api/sources/", "/api/leads/",
            "/api/companies/", "/api/contacts/", "/api/campaigns/", "/api/email/",
            "/api/follow-ups/", "/api/crm/", "/api/analytics/", "/api/suppression/",
            "/api/ai/", "/api/settings/", "/api/audit-logs/",
        ],
    })


urlpatterns.insert(0, path("api/", api_root, name="api-root"))
