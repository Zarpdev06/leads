from rest_framework import serializers

from .models import Company, Industry


class IndustrySerializer(serializers.ModelSerializer):
    lead_count = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = Industry
        fields = ["id", "name", "slug", "parent", "full_path", "code", "keywords",
                  "description", "is_active", "sort_order", "lead_count", "children"]

    def get_lead_count(self, obj) -> int:
        if obj.parent_id is None:
            return obj.leads.count() + obj.sub_industry_leads.count()
        return obj.leads.count()

    def get_children(self, obj) -> list[dict]:
        if obj.parent_id is not None:
            return []
        return [
            {"id": child.pk, "name": child.name, "full_path": child.full_path}
            for child in obj.children.filter(is_active=True)
        ]


class CompanyListSerializer(serializers.ModelSerializer):
    industry_name = serializers.CharField(source="industry.name", read_only=True)
    sub_industry_name = serializers.CharField(source="sub_industry.name", read_only=True)
    leads_count = serializers.IntegerField(source="lead_count", read_only=True)

    class Meta:
        model = Company
        fields = ["id", "name", "website", "domain", "email", "phone", "city", "state",
                  "zip_code", "country", "employee_count", "industry", "industry_name",
                  "sub_industry", "sub_industry_name", "leads_count", "created_at"]


class CompanyDetailSerializer(serializers.ModelSerializer):
    industry = IndustrySerializer(read_only=True)
    sub_industry = IndustrySerializer(read_only=True)
    source_name = serializers.CharField(source="source.name", read_only=True)

    class Meta:
        model = Company
        fields = "__all__"
