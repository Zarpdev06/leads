from __future__ import annotations

from django.db.models import Q
from django_filters import rest_framework as filters

from .models import CRMStage, EmailStatus, EnrichmentStatus, Lead, LeadQuality, LeadStatus


class LeadFilter(filters.FilterSet):
    """Server-side filtering for millions of rows (never filtered in the UI)."""

    search = filters.CharFilter(method="filter_search", label="Search")
    industry = filters.NumberFilter(field_name="industry_id")
    sub_industry = filters.NumberFilter(field_name="sub_industry_id")
    industry_in = filters.BaseInFilter(field_name="industry_id")
    state = filters.CharFilter(field_name="state", lookup_expr="iexact")
    state_in = filters.BaseInFilter(field_name="state")
    city = filters.CharFilter(field_name="city", lookup_expr="iexact")
    city_in = filters.BaseInFilter(field_name="city")
    has_email = filters.BooleanFilter(method="filter_has_email")
    has_website = filters.BooleanFilter(method="filter_has_website")
    has_phone = filters.BooleanFilter(method="filter_has_phone")
    no_email = filters.BooleanFilter(method="filter_no_email")
    min_score = filters.NumberFilter(field_name="lead_score", lookup_expr="gte")
    max_score = filters.NumberFilter(field_name="lead_score", lookup_expr="lte")
    quality = filters.ChoiceFilter(choices=LeadQuality.choices, field_name="lead_quality")
    lead_status = filters.MultipleChoiceFilter(choices=LeadStatus.choices)
    email_status = filters.MultipleChoiceFilter(choices=EmailStatus.choices)
    crm_stage = filters.MultipleChoiceFilter(choices=CRMStage.choices)
    source = filters.NumberFilter(field_name="source_id")
    source_in = filters.BaseInFilter(field_name="source_id")
    campaign = filters.NumberFilter(method="filter_campaign")
    no_campaign = filters.BooleanFilter(method="filter_no_campaign")
    owner = filters.NumberFilter(field_name="owner_id")
    is_duplicate = filters.BooleanFilter(field_name="is_duplicate")
    enrichment_status = filters.MultipleChoiceFilter(choices=EnrichmentStatus.choices)
    date_from = filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    contacted_before = filters.DateFilter(field_name="last_contacted_at", lookup_expr="lte")
    tag = filters.CharFilter(method="filter_tag")

    class Meta:
        model = Lead
        fields = [
            "industry", "sub_industry", "state", "city", "lead_status", "email_status",
            "crm_stage", "source", "quality", "is_duplicate", "owner",
        ]

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(company_name__icontains=value)
            | Q(contact_name__icontains=value)
            | Q(first_name__icontains=value)
            | Q(last_name__icontains=value)
            | Q(email_normalized__icontains=value.lower())
            | Q(phone_normalized__icontains=value)
            | Q(website_domain__icontains=value.lower())
            | Q(city__icontains=value)
            | Q(state__icontains=value)
            | Q(industry__name__icontains=value)
            | Q(sub_industry__name__icontains=value)
        )

    def filter_has_email(self, queryset, name, value):
        return queryset.exclude(email_normalized="") if value else queryset.filter(
            email_normalized=""
        )

    def filter_no_email(self, queryset, name, value):
        return queryset.filter(email_normalized="") if value else queryset

    def filter_has_website(self, queryset, name, value):
        return queryset.exclude(website_domain="") if value else queryset.filter(
            website_domain=""
        )

    def filter_has_phone(self, queryset, name, value):
        return queryset.exclude(phone_normalized="") if value else queryset.filter(
            phone_normalized=""
        )

    def filter_campaign(self, queryset, name, value):
        return queryset.filter(campaign_leads__campaign_id=value)

    def filter_no_campaign(self, queryset, name, value):
        return queryset.exclude(campaign_leads__isnull=False) if value else queryset

    def filter_tag(self, queryset, name, value):
        return queryset.filter(tags__contains=[value])
