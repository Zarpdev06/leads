from rest_framework import serializers

from .models import CampaignDailyStat, DailyMetric


class DailyMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyMetric
        fields = ["id", "date", "scope", "key", "dimension", "value"]


class CampaignDailyStatSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)

    class Meta:
        model = CampaignDailyStat
        fields = ["id", "campaign", "campaign_name", "date", "sent", "delivered",
                  "opened", "clicked", "replied", "bounced", "unsubscribed", "failed"]
