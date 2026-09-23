from django.contrib import admin

from .models import Contact


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "phone", "company", "job_title", "city")
    search_fields = ("full_name", "email", "email_normalized", "phone")
    raw_id_fields = ("company", "source")
