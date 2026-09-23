from __future__ import annotations

from rest_framework import serializers

from apps.leads.models import CRMStage

from .models import CRMActivity, LeadNote


class CRMActivitySerializer(serializers.ModelSerializer):
    actor_email = serializers.SerializerMethodField()
    type_display = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = CRMActivity
        fields = ["id", "lead", "type", "type_display", "title", "description",
                  "metadata", "actor", "actor_email", "occurred_at", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_actor_email(self, obj) -> str:
        return getattr(obj.actor, "email", "") or "system"


class LeadNoteSerializer(serializers.ModelSerializer):
    author_email = serializers.SerializerMethodField()

    class Meta:
        model = LeadNote
        fields = ["id", "lead", "body", "author", "author_email", "is_pinned",
                  "created_at", "updated_at"]
        read_only_fields = ["id", "author", "created_at", "updated_at"]

    def get_author_email(self, obj) -> str:
        return getattr(obj.author, "email", "") or "system"


class StageMoveSerializer(serializers.Serializer):
    stage = serializers.ChoiceField(choices=CRMStage.choices)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    deal_value = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, allow_null=True
    )
    expected_close_date = serializers.DateField(required=False, allow_null=True)
    lost_reason = serializers.CharField(required=False, allow_blank=True, default="")


class BulkStageSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    stage = serializers.ChoiceField(choices=CRMStage.choices)
    note = serializers.CharField(required=False, allow_blank=True, default="")
