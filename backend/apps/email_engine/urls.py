from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    DailyEmailUsageViewSet,
    EmailEventViewSet,
    EmailMessageViewSet,
    EmailTemplateViewSet,
    FollowUpSequenceViewSet,
    FollowUpStepViewSet,
    email_usage,
    send_now,
    smtp_test,
    track_click,
    track_open,
    unsubscribe,
)

router = DefaultRouter()
router.register(r"email/templates", EmailTemplateViewSet, basename="email-template")
router.register(r"email/messages", EmailMessageViewSet, basename="email-message")
router.register(r"email/events", EmailEventViewSet, basename="email-event")
router.register(r"email/usage", DailyEmailUsageViewSet, basename="email-usage")
router.register(r"follow-ups/sequences", FollowUpSequenceViewSet, basename="followup-sequence")
router.register(r"follow-ups/steps", FollowUpStepViewSet, basename="followup-step")

urlpatterns = [
    path("email-usage/", email_usage, name="email-usage"),
    path("email/send-now/", send_now, name="email-send-now"),
    path("email/smtp-test/", smtp_test, name="email-smtp-test"),
    path("unsubscribe/<str:token>/", unsubscribe, name="unsubscribe"),
    *router.urls,
]

# Public tracking endpoints are mounted at /t/... in config/urls.py
tracking_urlpatterns = [
    path("t/o/<str:uid>.png", track_open, name="track-open"),
    path("t/c/<str:uid>", track_click, name="track-click"),
    path("t/unsubscribe/<str:token>", unsubscribe, name="unsubscribe-tracking"),
]
