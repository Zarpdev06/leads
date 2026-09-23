from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.CharField(read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id", "actor", "actor_email", "action", "action_display",
            "entity_type", "entity_id", "description", "metadata",
            "ip_address", "created_at",
        ]

    action_display = serializers.CharField(source="get_action_display", read_only=True)
