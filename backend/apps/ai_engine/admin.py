from django.contrib import admin

from .models import AIProviderConfig, AIRecommendation


@admin.register(AIProviderConfig)
class AIProviderConfigAdmin(admin.ModelAdmin):
    list_display = ("provider", "label", "model", "is_active", "is_default",
                    "last_test_ok", "last_tested_at")
    list_filter = ("provider", "is_active")


@admin.register(AIRecommendation)
class AIRecommendationAdmin(admin.ModelAdmin):
    list_display = ("lead", "provider", "recommended_service", "status",
                    "safety_passed", "created_at")
    list_filter = ("provider", "status", "safety_passed")
    raw_id_fields = ("lead", "campaign", "service")
