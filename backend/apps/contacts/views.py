from django.db.models import Q
from django_filters import rest_framework as filters
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import CanModify

from .models import Contact
from .serializers import ContactSerializer


class ContactFilter(filters.FilterSet):
    search = filters.CharFilter(method="filter_search")
    company = filters.NumberFilter(field_name="company_id")
    state = filters.CharFilter(field_name="state", lookup_expr="iexact")
    has_email = filters.BooleanFilter(method="filter_has_email")

    class Meta:
        model = Contact
        fields = ["company", "state", "is_primary"]

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(full_name__icontains=value) | Q(email_normalized__icontains=value.lower())
            | Q(phone_normalized__icontains=value) | Q(job_title__icontains=value)
        )

    def filter_has_email(self, queryset, name, value):
        return queryset.exclude(email_normalized="") if value else queryset.filter(
            email_normalized=""
        )


class ContactViewSet(viewsets.ModelViewSet):
    queryset = Contact.objects.select_related("company").all()
    serializer_class = ContactSerializer
    permission_classes = [IsAuthenticated, CanModify]
    filterset_class = ContactFilter
    ordering_fields = ["last_name", "created_at", "company"]
    ordering = ["last_name", "first_name"]
