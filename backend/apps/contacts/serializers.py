from rest_framework import serializers

from .models import Contact


class ContactSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = Contact
        fields = ["id", "company", "company_name", "first_name", "last_name", "full_name",
                  "job_title", "seniority", "email", "email_normalized", "phone",
                  "phone_normalized", "phone_type", "mobile", "city", "state",
                  "linkedin_url", "is_primary", "is_decision_maker", "unsubscribed_at",
                  "created_at"]
        read_only_fields = ["id", "email_normalized", "phone_normalized", "created_at"]
