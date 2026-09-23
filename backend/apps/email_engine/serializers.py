from __future__ import annotations

from rest_framework import serializers

from .models import DailyEmailUsage, EmailEvent, EmailMessage, EmailTemplate
from .models import FollowUpSequence, FollowUpStep


class EmailTemplateSerializer(serializers.ModelSerializer):
    detected_variables = serializers.SerializerMethodField()

    class Meta:
        model = EmailTemplate
        fields = ["id", "name", "slug", "category", "subject", "preheader",
                  "body_html", "body_text", "description", "is_active", "is_default",
                  "variables", "usage_count", "detected_variables", "created_at",
                  "updated_at"]

    def get_detected_variables(self, obj) -> list[str]:
        from .render import extract_variables

        return sorted(set(extract_variables(obj.subject) +
                          extract_variables(obj.body_html)))


class FollowUpStepSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source="template.name", read_only=True)

    class Meta:
        model = FollowUpStep
        fields = ["id", "sequence", "order", "delay_days", "delay_hours", "condition",
                  "template", "template_name", "subject", "body_html", "use_ai",
                  "ai_instructions", "is_active"]


class FollowUpSequenceSerializer(serializers.ModelSerializer):
    steps = FollowUpStepSerializer(many=True, read_only=True)

    class Meta:
        model = FollowUpSequence
        fields = ["id", "name", "description", "is_active", "stop_on_reply",
                  "stop_on_bounce", "stop_on_unsubscribe", "stop_on_click",
                  "stop_on_converted", "max_steps", "steps"]


class EmailEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailEvent
        fields = ["id", "message", "type", "url", "metadata", "ip_address",
                  "user_agent", "occurred_at"]


class EmailMessageListSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="lead.company_name", read_only=True)
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = EmailMessage
        fields = ["id", "campaign", "campaign_name", "lead", "company_name", "to_email",
                  "subject", "status", "status_display", "step_number", "scheduled_at",
                  "sent_at", "opened_at", "clicked_at", "replied_at", "bounced_at",
                  "attempt_count", "is_ai_generated", "recommended_service", "created_at"]


class EmailMessageDetailSerializer(serializers.ModelSerializer):
    events = EmailEventSerializer(many=True, read_only=True)
    company_name = serializers.CharField(source="lead.company_name", read_only=True)
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)

    class Meta:
        model = EmailMessage
        fields = "__all__"


class DailyEmailUsageSerializer(serializers.ModelSerializer):
    remaining = serializers.IntegerField(read_only=True)
    percent_used = serializers.FloatField(read_only=True)

    class Meta:
        model = DailyEmailUsage
        fields = ["id", "date", "sent_count", "failed_count", "bounced_count",
                  "skipped_count", "transactional_count", "limit", "smtp_limit",
                  "remaining", "percent_used"]


class SendNowSerializer(serializers.Serializer):
    lead_id = serializers.IntegerField()
    campaign_id = serializers.IntegerField(required=False, allow_null=True)
    template_id = serializers.IntegerField(required=False, allow_null=True)
    subject = serializers.CharField(required=False, allow_blank=True, default="")
    body_html = serializers.CharField(required=False, allow_blank=True, default="")
    use_ai = serializers.BooleanField(default=True)
    send_immediately = serializers.BooleanField(default=False)


class TestEmailSerializer(serializers.Serializer):
    to_email = serializers.EmailField()
    subject = serializers.CharField(required=False, default="SMTP test message")
    body = serializers.CharField(required=False, allow_blank=True, default="")
