from django.db.models import Count, Q
from django_filters import rest_framework as filters
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.permissions import CanModify

from .models import Company, Industry
from .serializers import CompanyDetailSerializer, CompanyListSerializer, IndustrySerializer


class IndustryViewSet(viewsets.ModelViewSet):
    queryset = Industry.objects.all()
    serializer_class = IndustrySerializer
    permission_classes = [IsAuthenticated, CanModify]
    filterset_fields = ["parent", "is_active"]
    search_fields = ["name", "keywords"]
    ordering = ["sort_order", "name"]

    @action(detail=False, methods=["get"])
    def tree(self, request):
        roots = Industry.objects.filter(parent__isnull=True, is_active=True).order_by("name")
        return Response(IndustrySerializer(roots, many=True).data)

    @action(detail=False, methods=["post"])
    def seed(self, request):
        from apps.leads.classifier import seed_industries

        created = seed_industries()
        return Response({"created": created})


class CompanyFilter(filters.FilterSet):
    search = filters.CharFilter(method="filter_search")
    industry = filters.NumberFilter(field_name="industry_id")
    sub_industry = filters.NumberFilter(field_name="sub_industry_id")
    state = filters.CharFilter(field_name="state", lookup_expr="iexact")
    city = filters.CharFilter(field_name="city", lookup_expr="iexact")
    has_website = filters.BooleanFilter(method="filter_has_website")

    class Meta:
        model = Company
        fields = ["industry", "sub_industry", "state", "city"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) | Q(domain__icontains=value)
            | Q(city__icontains=value) | Q(state__icontains=value)
        )

    def filter_has_website(self, queryset, name, value):
        return queryset.exclude(domain="") if value else queryset.filter(domain="")


class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.select_related("industry", "sub_industry", "source").all()
    permission_classes = [IsAuthenticated, CanModify]
    filterset_class = CompanyFilter
    search_fields = ["name", "domain", "city", "state"]
    ordering_fields = ["name", "created_at", "lead_count"]
    ordering = ["name"]

    def get_serializer_class(self):
        return CompanyDetailSerializer if self.action in {"retrieve"} else CompanyListSerializer

    @action(detail=True, methods=["get"])
    def leads(self, request, pk=None):
        from apps.core.pagination import StandardResultsSetPagination
        from apps.leads.serializers import LeadListSerializer

        company = self.get_object()
        queryset = company.leads.select_related("industry", "sub_industry")
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(LeadListSerializer(page, many=True).data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        rows = Company.objects.values("industry__name").annotate(
            count=Count("id")
        ).order_by("-count")[:20]
        return Response({
            "total": Company.objects.count(),
            "with_website": Company.objects.exclude(domain="").count(),
            "by_industry": list(rows),
        })
