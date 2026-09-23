"""Seed reference data: industries, services, mapping rules and templates.

    python manage.py seed_demo [--with-demo-leads 500]
"""
from __future__ import annotations

import random

from django.core.management.base import BaseCommand

from apps.campaigns.models import seed_service_mappings, seed_services
from apps.email_engine.seeds import seed_default_templates
from apps.leads.classifier import seed_industries


class Command(BaseCommand):
    help = "Seed industries, services, service/industry rules and email templates."

    def add_arguments(self, parser):
        parser.add_argument("--with-demo-leads", type=int, default=0,
                            help="Also generate N synthetic leads for local development.")

    def handle(self, *args, **options):
        self.stdout.write("Seeding industries…")
        industries = seed_industries()
        self.stdout.write("Seeding services…")
        services = seed_services()
        self.stdout.write("Seeding service/industry rules…")
        mappings = seed_service_mappings()
        self.stdout.write("Seeding email templates…")
        templates = seed_default_templates()

        count = options["with_demo_leads"]
        if count:
            self.stdout.write(f"Generating {count} demo leads…")
            self._demo_leads(count)

        self.stdout.write(self.style.SUCCESS(
            f"Done: {industries} industries, {services} services, "
            f"{mappings} rules, {templates} templates"
            + (f", {count} demo leads" if count else "")
        ))

    def _demo_leads(self, count: int) -> None:
        """Deterministic synthetic data - only for local development."""
        from apps.companies.models import Industry
        from apps.core.normalizers import normalize_email, normalize_phone, normalize_website
        from apps.leads.models import EmailStatus, Lead, LeadStatus
        from apps.leads.scoring import apply_score

        cities = [("Dallas", "TX"), ("Fort Worth", "TX"), ("Austin", "TX"),
                  ("Plano", "TX"), ("Irving", "TX"), ("Arlington", "TX")]
        first = ["John", "Maria", "David", "Sarah", "Mike", "Ashley", "Carlos", "Emily"]
        last = ["Smith", "Garcia", "Johnson", "Williams", "Brown", "Davis", "Miller", "Wilson"]
        industries = list(Industry.objects.filter(parent__isnull=False))

        leads = []
        for index in range(count):
            industry = random.choice(industries) if industries else None
            city, state = random.choice(cities)
            company = f"{random.choice(last)} {industry.name if industry else 'Business'} {index}"
            email_raw = f"owner{index}@{company.replace(' ', '').lower()}.com"
            email = normalize_email(email_raw)
            phone, phone_key = normalize_phone("(214) 555-01" + f"{index % 100:02d}")
            site = normalize_website(f"https://{company.replace(' ', '').lower()}.com")
            leads.append(Lead(
                company_name=company,
                company_name_key=company.lower(),
                contact_name=f"{random.choice(first)} {random.choice(last)}",
                first_name=random.choice(first), last_name=random.choice(last),
                email=email.normalized, email_normalized=email.normalized,
                email_status=EmailStatus.VALID if email.is_valid else EmailStatus.INVALID,
                email_domain=email.domain,
                phone=phone, phone_normalized=phone_key,
                website=site.normalized, website_normalized=site.normalized,
                website_domain=site.domain,
                city=city, state=state, zip_code="75201",
                street_address=f"{100 + index} Main St",
                sub_industry=industry,
                industry=industry.parent if industry and industry.parent_id else None,
                lead_status=LeadStatus.VALID if email.is_valid
                else LeadStatus.MISSING_EMAIL,
                dedupe_key=f"{company.lower()}|{site.domain}|{city.lower()}|{state.lower()}",
            ))
        Lead.objects.bulk_create(leads, batch_size=500)
        for lead in Lead.objects.all().iterator(chunk_size=500):
            apply_score(lead)
