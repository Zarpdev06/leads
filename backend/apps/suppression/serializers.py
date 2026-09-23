from __future__ import annotations

from rest_framework import serializers

from .models import Suppression, SuppressionLog
from .services import add_suppression, normalize_for_lookup


class SuppressionSerializer(serializers.ModelSerializer):
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)

    class Meta:
        model = Suppression
        fields = [
            "id", "email", "email_normalized", "reason", "reason_display", "source",
            "note", "is_active", "lead", "created_by", "created_at", "updated_at",
            "expires_at",
        ]
        read_only_fields = ["id", "email_normalized", "created_at", "updated_at"]


class SuppressionCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    reason = serializers.ChoiceField(choices=Suppression.Reason.choices, required=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_email(self, value: str) -> str:
        key = normalize_for_lookup(value)
        if not key:
            raise serializers.ValidationError("Enter a valid email address.")
        return key

    def create(self, validated_data):
        row, _ = add_suppression(
            validated_data["email"],
            reason=validated_data.get("reason", Suppression.Reason.MANUAL_BLOCK),
            note=validated_data.get("note", ""),
            source="MANUAL",
            actor=self.context.get("request").user if self.context.get("request") else None,
            expires_at=validated_data.get("expires_at"),
        )
        return row


class SuppressionLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.SerializerMethodField()

    class Meta:
        model = SuppressionLog
        fields = ["id", "email_normalized", "action", "reason", "note", "actor_email",
                  "created_at"]

    def get_actor_email(self, obj) -> str:
        return getattr(obj.actor, "email", "") or "system"
