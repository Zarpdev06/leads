from rest_framework import serializers

from .models import SettingChangeLog, SystemSetting


class SystemSettingSerializer(serializers.ModelSerializer):
    value = serializers.SerializerMethodField()

    class Meta:
        model = SystemSetting
        fields = ["id", "key", "value", "category", "label", "description",
                  "is_secret", "is_public", "updated_at"]

    def get_value(self, obj):
        return "***" if obj.is_secret else obj.value


class SettingChangeLogSerializer(serializers.ModelSerializer):
    changed_by_email = serializers.SerializerMethodField()

    class Meta:
        model = SettingChangeLog
        fields = ["id", "key", "old_value", "new_value", "changed_by",
                  "changed_by_email", "note", "created_at"]

    def get_changed_by_email(self, obj) -> str:
        return getattr(obj.changed_by, "email", "") or "system"
