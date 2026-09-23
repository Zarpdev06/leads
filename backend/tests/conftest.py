"""Shared fixtures for the test suite."""
from __future__ import annotations


import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.campaigns.models import Service, ServiceIndustryMapping
from apps.companies.models import Industry
from apps.email_engine.models import EmailTemplate
from apps.leads.models import EmailStatus, Lead


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(
        email="agent@example.com", password="StrongPass123!", role=User.Role.AGENT,
        first_name="Ada", last_name="Agent",
    )


@pytest.fixture
def admin(db) -> User:
    return User.objects.create_superuser(
        email="admin@example.com", password="AdminPass123!", role=User.Role.ADMIN,
    )


@pytest.fixture
def manager(db) -> User:
    return User.objects.create_user(
        email="manager@example.com", password="ManagerPass123!", role=User.Role.MANAGER,
    )


@pytest.fixture
def viewer(db) -> User:
    return User.objects.create_user(
        email="viewer@example.com", password="ViewerPass123!", role=User.Role.VIEWER,
    )


@pytest.fixture
def api_client(user) -> APIClient:
    """Authenticated API client (JWT header)."""
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


@pytest.fixture
def admin_client(admin) -> APIClient:
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    token = RefreshToken.for_user(admin)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


@pytest.fixture
def anon_client() -> APIClient:
    return APIClient()


@pytest.fixture
def industry(db) -> Industry:
    parent, _ = Industry.objects.get_or_create(
        parent=None, name="Automotive",
        defaults={"slug": "automotive", "keywords": ["auto", "car"]},
    )
    sub, _ = Industry.objects.get_or_create(
        parent=parent, name="Auto Detailing",
        defaults={"slug": "automotive-auto-detailing", "keywords": ["detailing"]},
    )
    return sub


@pytest.fixture
def services(db, industry) -> list[Service]:
    names = ["CRM Development", "AI Lead Follow-up Automation", "Appointment Automation",
             "Website Development"]
    created = []
    for index, name in enumerate(names):
        service, _ = Service.objects.get_or_create(
            name=name,
            defaults={"slug": name.lower().replace(" ", "-"), "sort_order": index,
                      "value_proposition": f"{name} that removes manual work."},
        )
        ServiceIndustryMapping.objects.get_or_create(
            industry=industry, service=service,
            defaults={"priority": index + 1, "reason": f"Common need for {industry.name}"},
        )
        created.append(service)
    return created


@pytest.fixture
def template(db) -> EmailTemplate:
    return EmailTemplate.objects.create(
        name="Cold outreach", slug="cold-outreach",
        subject="Quick idea for {{company_name}}",
        body_html=("<p>Hi {{first_name}},</p>"
                   "<p>I came across {{company_name}} in {{city}}.</p>"
                   "<p>{{personalization}}</p>"
                   "<p>{{cta}}</p>"),
        is_default=True,
    )


@pytest.fixture
def make_lead(db, industry):
    """Factory: make_lead(company_name=..., email=..., **kwargs) -> Lead"""

    def _make(**kwargs) -> Lead:
        email = kwargs.pop("email", "owner@example.com")
        from apps.core.normalizers import normalize_email, normalize_phone, normalize_website

        result = normalize_email(email)
        phone, phone_key = normalize_phone(kwargs.pop("phone", ""))
        website = normalize_website(kwargs.pop("website", ""))
        lead = Lead.objects.create(
            company_name=kwargs.pop("company_name", "Example Auto Spa"),
            company_name_key=kwargs.pop("company_name_key", "example auto spa"),
            contact_name=kwargs.pop("contact_name", "John Owner"),
            first_name=kwargs.pop("first_name", "John"),
            last_name=kwargs.pop("last_name", "Owner"),
            email=email,
            email_normalized=result.normalized,
            email_status=(EmailStatus.VALID if result.is_valid
                          else EmailStatus.INVALID if email else EmailStatus.MISSING),
            email_domain=result.domain,
            phone=phone, phone_normalized=phone_key,
            website=website.normalized, website_normalized=website.normalized,
            website_domain=website.domain,
            city=kwargs.pop("city", "Dallas"),
            state=kwargs.pop("state", "TX"),
            zip_code=kwargs.pop("zip_code", "75201"),
            street_address=kwargs.pop("street_address", "100 Main St"),
            sub_industry=industry if kwargs.pop("with_industry", True) else None,
            industry=industry.parent if kwargs.pop("with_industry", True) else None,
            lead_score=kwargs.pop("lead_score", 0),
            **kwargs,
        )
        from apps.leads.scoring import apply_score

        apply_score(lead)
        return lead

    return _make


@pytest.fixture
def csv_file(tmp_path):
    """Factory that writes a CSV and returns the path."""

    def _write(rows: list[dict], filename: str = "test.csv"):
        import csv

        path = tmp_path / filename
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return str(path)

    return _write


@pytest.fixture
def xlsx_file(tmp_path):
    """Factory that writes an XLSX and returns the path."""

    def _write(rows: list[dict], filename: str = "test.xlsx", sheet: str = "Sheet1"):
        from openpyxl import Workbook

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = sheet
        headers = list(rows[0].keys())
        worksheet.append(headers)
        for row in rows:
            worksheet.append([row.get(header, "") for header in headers])
        path = tmp_path / filename
        workbook.save(path)
        return str(path)

    return _write


@pytest.fixture
def sample_rows() -> list[dict]:
    """A messy, realistic dataset with inconsistent column values."""
    return [
        {"Business Name": "ABC Auto Detailing  ", "Contact Person": "john smith",
         "First Name": "John", "Corporate Email": "John@ABCAutoDetailing.com",
         "Website": "www.abcautodetailing.com/?utm_source=google",
         "Phone": "(214) 555-0100", "Phone Type": "Mobile",
         "Street Address": "1200 Main St", "Zip Code": "75201", "State": "texas",
         "City": "dallas", "Number of Employees": "12"},
        {"Business Name": "Precise Auto Works", "Contact Person": "MARIA GARCIA",
         "First Name": "Maria", "Corporate Email": "info@preciseautoworks.com",
         "Website": "https://preciseautoworks.com", "Phone": "214.555.0188",
         "Phone Type": "Landline", "Street Address": "88 Oak Ave", "Zip Code": "75001",
         "State": "TX", "City": "Addison", "Number of Employees": "5-10"},
        {"Business Name": "Shine Mobile Detail", "Contact Person": "", "First Name": "",
         "Corporate Email": "", "Website": "shinemobiledetail.com",
         "Phone": "(469) 555-2211", "Phone Type": "Mobile",
         "Street Address": "", "Zip Code": "", "State": "Texas", "City": "Plano",
         "Number of Employees": ""},
        {"Business Name": "", "Contact Person": "Ghost", "First Name": "",
         "Corporate Email": "not-an-email", "Website": "", "Phone": "",
         "Phone Type": "", "Street Address": "", "Zip Code": "", "State": "",
         "City": "", "Number of Employees": ""},
        {"Business Name": "ABC Auto Detailing", "Contact Person": "John Smith",
         "First Name": "John", "Corporate Email": "john@abcautodetailing.com",
         "Website": "http://abcautodetailing.com", "Phone": "2145550100",
         "Phone Type": "Mobile", "Street Address": "1200 Main St", "Zip Code": "75201",
         "State": "TX", "City": "Dallas", "Number of Employees": ""},
    ]
