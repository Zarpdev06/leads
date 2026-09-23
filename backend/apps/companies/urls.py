from rest_framework.routers import DefaultRouter

from .views import CompanyViewSet, IndustryViewSet

router = DefaultRouter()
router.register(r"companies", CompanyViewSet, basename="company")
router.register(r"industries", IndustryViewSet, basename="industry")

urlpatterns = [*router.urls]
