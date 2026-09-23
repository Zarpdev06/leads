from __future__ import annotations

from rest_framework import serializers

from .models import AIProviderConfig, AIRecommendation


class AIProviderConfigSerializer(serializers.ModelSerializer):
    """Never exposes api_key - only whether one is configured."""

    has_key = serializers.BooleanField(read_only=True)
    provider_label = serializers.CharField(source="get_provider_display", read_only=True)

    class Meta:
        model = AIProviderConfig
        fields = ["id", "provider", "provider_label", "label", "model", "base_url",
                  "is_active", "is_default", "temperature", "max_tokens", "has_key",
                  "last_tested_at", "last_test_ok", "last_error"]
        read_only_fields = ["last_tested_at", "last_test_ok", "last_error"]


class AIProviderConfigWriteSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = AIProviderConfig
        fields = ["id", "provider", "label", "model", "base_url", "api_key",
                  "is_active", "is_default", "temperature", "max_tokens"]


class AIRecommendationSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="lead.company_name", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)

    class Meta:
        model = AIRecommendation
        fields = ["id", "lead", "company_name", "campaign", "service", "service_name",
                  "provider", "model", "subject", "opening_sentence", "personalization",
                  "value_proposition", "cta", "body_html", "recommended_service",
                  "rationale", "confidence", "status", "safety_passed", "safety_notes",
                  "tokens_used", "created_at", "used_at"]
        read_only_fields = ["id", "created_at"]


class GenerateSerializer(serializers.Serializer):
    lead_id = serializers.IntegerField()
    campaign_id = serializers.IntegerField(required=False, allow_null=True)
    template_id = serializers.IntegerField(required=False, allow_null=True)
    instructions = serializers.CharField(required=False, allow_blank=True, default="")
    regenerate = serializers.BooleanField(default=False)


class ServiceMatchSerializer(serializers.Serializer):
    lead_id = serializers.IntegerField()
    use_ai = serializers.BooleanField(default=True)
