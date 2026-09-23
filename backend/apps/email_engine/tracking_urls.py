"""Public (token-based) tracking + unsubscribe routes, mounted at the site root."""
from django.urls import path

from .views import track_click, track_open, unsubscribe

urlpatterns = [
    path("t/o/<str:uid>.png", track_open, name="track-open"),
    path("t/c/<str:uid>", track_click, name="track-click"),
    path("t/unsubscribe/<str:token>", unsubscribe, name="unsubscribe-tracking"),
    path("unsubscribe/<str:token>", unsubscribe, name="unsubscribe-public"),
]
