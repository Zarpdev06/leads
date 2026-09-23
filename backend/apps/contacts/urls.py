from rest_framework.routers import DefaultRouter

from .views import ContactViewSet

router = DefaultRouter()
router.register(r"contacts", ContactViewSet, basename="contact")

urlpatterns = [*router.urls]
