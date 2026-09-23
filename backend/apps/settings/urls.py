from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    SettingChangeLogViewSet,
    SystemSettingViewSet,
    reset_settings,
    seed_all,
    settings_overview,
    smtp_status_view,
    update_settings,
)

router = DefaultRouter()
router.register(r"settings/raw", SystemSettingViewSet, basename="system-setting")
router.register(r"settings/changes", SettingChangeLogViewSet, basename="setting-change")

urlpatterns = [
    path("settings/", settings_overview, name="settings-overview"),
    path("settings/update/", update_settings, name="settings-update"),
    path("settings/smtp/", smtp_status_view, name="settings-smtp"),
    path("settings/reset/", reset_settings, name="settings-reset"),
    path("settings/seed/", seed_all, name="settings-seed"),
    *router.urls,
]
