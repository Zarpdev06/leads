from __future__ import annotations

from rest_framework import serializers

from apps.companies.models import Industry
from apps.imports.models import LeadSource

from .models import Campaign, CampaignLead, Service, ServiceIndustryMapping


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ["id", "name", "slug", "short_name", "category", "description",
                  "value_proposition", "pain_points", "outcomes", "keywords",
                  "is_active", "sort_order"]


class ServiceIndustryMappingSerializer(serializers.ModelSerializer):
    industry_name = serializers.CharField(source="industry.name", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)

    class Meta:
        model = ServiceIndustryMapping
        fields = ["id", "industry", "industry_name", "service", "service_name",
                  "priority", "reason", "is_active"]


class CampaignListSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source="template.name", read_only=True)
    service_name = serializers.CharField(source="recommended_service.name", read_only=True)
    reply_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = Campaign
        fields = ["id", "name", "status", "total_selected", "total_queued", "total_sent",
                  "total_replied", "total_opened", "total_clicked", "total_failed",
                  "daily_limit", "template_name", "service_name", "start_date",
                  "end_date", "created_at", "reply_rate", "use_ai_personalization"]


class CampaignDetailSerializer(serializers.ModelSerializer):
    target_industry_names = serializers.SerializerMethodField()
    template_name = serializers.CharField(source="template.name", read_only=True)
    service_name = serializers.CharField(source="recommended_service.name", read_only=True)
    sequence_name = serializers.CharField(source="follow_up_sequence.name", read_only=True)
    source_names = serializers.SerializerMethodField()
    reply_rate = serializers.FloatField(read_only=True)
    open_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = Campaign
        fields = "__all__"

    def get_target_industry_names(self, obj) -> list[str]:
        return list(obj.target_industries.values_list("name", flat=True))

    def get_source_names(self, obj) -> list[str]:
        return list(obj.sources.values_list("name", flat=True))


class CampaignWriteSerializer(serializers.ModelSerializer):
    """Writable representation. Many-to-many targets accept ID lists."""

    target_industries = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=Industry.objects.all()
    )
    target_sub_industries = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=Industry.objects.all()
    )
    sources = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=LeadSource.objects.all()
    )

    class Meta:
        model = Campaign
        fields = [
            "id", "name", "description", "status", "target_industries", "target_sub_industries",
            "target_states", "target_cities", "sources", "lead_ids", "min_lead_score",
            "max_lead_score", "require_website", "require_phone",
            "require_contact_person", "exclude_replied", "exclude_ever_contacted",
            "exclude_missing_email", "template", "use_ai_personalization",
            "ai_instructions", "recommended_service", "subject", "preview_text",
            "daily_limit", "send_window_start", "send_window_end", "timezone_name",
            "start_date", "end_date", "follow_up_enabled", "follow_up_sequence",
            "from_name", "from_email", "reply_to",
        ]

    def validate_daily_limit(self, value: int) -> int:
        from apps.settings.services import validate_daily_marketing_limit

        safe, _note = validate_daily_marketing_limit(value)
        return safe


class CampaignStartSerializer(serializers.Serializer):
    dispatch_now = serializers.BooleanField(default=True)


class CampaignLeadSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="lead.company_name", read_only=True)
    email = serializers.CharField(source="lead.email_normalized", read_only=True)
    city = serializers.CharField(source="lead.city", read_only=True)
    state = serializers.CharField(source="lead.state", read_only=True)
    score = serializers.IntegerField(source="lead.lead_score", read_only=True)

    class Meta:
        model = CampaignLead
        fields = ["id", "campaign", "lead", "company_name", "email", "city", "state",
                  "score", "status", "current_step", "scheduled_at", "sent_at",
                  "next_follow_up_at", "stopped_reason", "created_at"]


class AudiencePreviewSerializer(serializers.Serializer):
    """Wizard step 5: how many leads would this campaign reach?"""

    count = serializers.IntegerField(read_only=True)
    by_stage = serializers.DictField(read_only=True)
    sample = serializers.ListField(read_only=True)
    eligible = serializers.IntegerField(read_only=True)
