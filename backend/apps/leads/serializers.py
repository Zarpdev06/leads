from __future__ import annotations

from rest_framework import serializers

from apps.companies.models import Industry
from apps.companies.serializers import IndustrySerializer

from .models import Lead, LeadDuplicate, LeadStatus


class LeadListSerializer(serializers.ModelSerializer):
    """Compact row for the Lead Explorer table."""

    industry_name = serializers.CharField(source="industry.name", read_only=True)
    sub_industry_name = serializers.CharField(source="sub_industry.name", read_only=True)
    source_name = serializers.CharField(source="source.name", read_only=True)
    campaign_names = serializers.SerializerMethodField()
    quality_display = serializers.CharField(source="get_lead_quality_display", read_only=True)
    email_status_display = serializers.CharField(source="get_email_status_display",
                                                 read_only=True)
    recommended_service_name = serializers.CharField(
        source="recommended_service.name", read_only=True
    )

    class Meta:
        model = Lead
        fields = [
            "id", "company_name", "contact_name", "first_name", "last_name",
            "email", "email_normalized", "email_status", "email_status_display",
            "phone", "phone_normalized", "website_domain", "city", "state",
            "industry", "industry_name", "sub_industry", "sub_industry_name",
            "lead_score", "lead_quality", "quality_display", "lead_status",
            "crm_stage", "email_status", "source", "source_name", "campaign_names",
            "last_contacted_at", "next_follow_up_at", "times_contacted",
            "is_duplicate", "enrichment_status", "recommended_service",
            "recommended_service_name", "created_at",
        ]

    def get_campaign_names(self, obj) -> list[str]:
        return list(obj.campaign_leads.values_list("campaign__name", flat=True)[:5])


class LeadDetailSerializer(serializers.ModelSerializer):
    industry = IndustrySerializer(read_only=True)
    sub_industry = IndustrySerializer(read_only=True)
    source_name = serializers.CharField(source="source.name", read_only=True)
    source_file_name = serializers.CharField(source="source_file.original_name", read_only=True)
    recommended_service_name = serializers.CharField(
        source="recommended_service.name", read_only=True
    )
    campaigns = serializers.SerializerMethodField()
    quality_display = serializers.CharField(source="get_lead_quality_display", read_only=True)
    counts = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_campaigns(self, obj) -> list[dict]:
        return [
            {"id": cl.campaign_id, "campaign": cl.campaign.name, "status": cl.status,
             "scheduled_at": cl.scheduled_at, "sent_at": cl.sent_at,
             "current_step": cl.current_step}
            for cl in obj.campaign_leads.select_related("campaign")[:20]
        ]

    def get_counts(self, obj) -> dict:
        return {
            "emails": obj.email_messages.count(),
            "activities": obj.activities.count(),
            "notes": obj.notes.count(),
        }


class LeadWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = [
            "id", "company_name", "contact_name", "first_name", "last_name", "job_title",
            "email", "phone", "phone_type", "website", "street_address", "city",
            "state", "zip_code", "country", "employee_count", "industry",
            "sub_industry", "lead_status", "crm_stage", "owner", "tags", "do_not_contact",
        ]


class LeadBulkCampaignSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    campaign_id = serializers.IntegerField()


class LeadBulkStatusSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    status = serializers.ChoiceField(choices=[c[0] for c in LeadStatus.choices])
    note = serializers.CharField(required=False, allow_blank=True, default="")


class LeadBulkOwnerSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    owner_id = serializers.IntegerField(allow_null=True)


class LeadExportSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    filters = serializers.JSONField(required=False)


class LeadDuplicateSerializer(serializers.ModelSerializer):
    lead_company = serializers.CharField(source="lead.company_name", read_only=True)
    lead_email = serializers.CharField(source="lead.email_normalized", read_only=True)
    candidate_company = serializers.CharField(source="candidate.company_name", read_only=True)
    candidate_email = serializers.CharField(source="candidate.email_normalized", read_only=True)
    method_display = serializers.CharField(source="get_method_display", read_only=True)

    class Meta:
        model = LeadDuplicate
        fields = [
            "id", "lead", "candidate", "lead_company", "lead_email",
            "candidate_company", "candidate_email", "confidence", "method",
            "method_display", "resolution", "details", "reviewed_at", "created_at",
        ]


class LeadStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    valid_emails = serializers.IntegerField()
    missing_emails = serializers.IntegerField()
    invalid_emails = serializers.IntegerField()
    hot = serializers.IntegerField()
    warm = serializers.IntegerField()
    cold = serializers.IntegerField()


class IndustryBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Industry
        fields = ["id", "name", "slug", "parent", "full_path"]
