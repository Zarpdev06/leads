"""Authentication, permissions and the main REST endpoints."""
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.imports.models import ImportFile
from apps.leads.models import Lead


def test_login_returns_jwt_and_profile(db, anon_client):
    User.objects.create_user(email="user@example.com", password="StrongPass123!")
    response = anon_client.post("/api/auth/login/",
                                {"email": "user@example.com", "password": "StrongPass123!"},
                                format="json")
    assert response.status_code == 200
    assert "access" in response.data and "refresh" in response.data
    assert response.data["user"]["email"] == "user@example.com"


def test_login_rejects_bad_credentials(db, anon_client):
    User.objects.create_user(email="user@example.com", password="StrongPass123!")
    response = anon_client.post("/api/auth/login/",
                                {"email": "user@example.com", "password": "wrong"},
                                format="json")
    assert response.status_code in {400, 401, 403}


def test_refresh_rotates_token(db, anon_client):
    User.objects.create_user(email="user@example.com", password="StrongPass123!")
    login = anon_client.post("/api/auth/login/",
                             {"email": "user@example.com", "password": "StrongPass123!"},
                             format="json")
    response = anon_client.post("/api/auth/refresh/",
                                {"refresh": login.data["refresh"]}, format="json")
    assert response.status_code == 200
    assert "access" in response.data


def test_protected_endpoints_require_auth(db, anon_client):
    for url in ["/api/leads/", "/api/campaigns/", "/api/imports/", "/api/analytics/",
                "/api/suppression/", "/api/settings/"]:
        response = anon_client.get(url)
        assert response.status_code in {401, 403}, url


def test_viewer_cannot_modify(db, viewer):
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(viewer).access_token}")
    response = client.post("/api/campaigns/", {"name": "Nope"}, format="json")
    assert response.status_code == 403
    response = client.post("/api/leads/bulk-add-campaign/",
                           {"ids": [1], "campaign_id": 1}, format="json")
    assert response.status_code == 403


def test_admin_only_endpoints(db, api_client, admin_client):
    # Settings require MANAGER+
    assert api_client.get("/api/settings/").status_code == 403
    assert admin_client.get("/api/settings/").status_code == 200
    # Audit logs require ADMIN
    assert api_client.get("/api/audit-logs/").status_code == 403
    assert admin_client.get("/api/audit-logs/").status_code == 200


def test_me_and_bootstrap(db, api_client, user):
    me = api_client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.data["email"] == user.email

    bootstrap = api_client.get("/api/auth/bootstrap/")
    assert bootstrap.status_code == 200
    assert "settings" in bootstrap.data
    # SMTP secrets are never exposed.
    assert "EMAIL_HOST_PASSWORD" not in str(bootstrap.data)
    assert bootstrap.data["settings"]["smtp"]["password_set"] in {True, False}


def test_health_endpoint(db, anon_client):
    response = anon_client.get("/api/health/")
    assert response.status_code == 200
    assert response.data["status"] == "ok"


def test_leads_list_and_filters(db, api_client, make_lead):
    make_lead(email="a@x.com", state="TX", city="Dallas")
    make_lead(email="b@x.com", state="CA", city="Fresno")
    make_lead(email="", state="TX", city="Austin")

    response = api_client.get("/api/leads/", {"state": "TX"})
    assert response.data["count"] == 2

    response = api_client.get("/api/leads/", {"has_email": "false"})
    assert response.data["count"] == 1

    response = api_client.get("/api/leads/", {"search": "Fresno"})
    assert response.data["count"] == 1

    response = api_client.get("/api/leads/", {"page_size": 1})
    assert len(response.data["results"]) == 1
    assert response.data["total_pages"] == 3


def test_lead_detail_and_bulk_actions(db, api_client, make_lead, template):
    from apps.campaigns.models import Campaign

    leads = [make_lead(email=f"lead{index}@x.com") for index in range(3)]
    campaign = Campaign.objects.create(name="C", template=template)

    response = api_client.get(f"/api/leads/{leads[0].pk}/")
    assert response.status_code == 200
    assert response.data["company_name"]

    response = api_client.post("/api/leads/bulk-add-campaign/",
                               {"ids": [lead.pk for lead in leads],
                                "campaign_id": campaign.pk}, format="json")
    assert response.status_code == 200
    assert response.data["added"] == 3

    response = api_client.post("/api/leads/bulk-remove-campaign/",
                               {"ids": [lead.pk for lead in leads],
                                "campaign_id": campaign.pk}, format="json")
    assert response.data["removed"] == 3


def test_global_search(db, api_client, make_lead):
    make_lead(email="owner@acmedetail.com", company_name="Acme Detailing")
    response = api_client.get("/api/search/", {"q": "Acme"})
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["title"] == "Acme Detailing"


def test_email_usage_endpoint(db, api_client):
    response = api_client.get("/api/email-usage/")
    assert response.status_code == 200
    assert response.data["today"]["limit"] == 90
    assert response.data["today"]["remaining"] == 90


def test_import_upload_and_process_api(db, api_client, csv_file, sample_rows):
    from django.core.files.uploadedfile import SimpleUploadedFile

    path = csv_file(sample_rows, "api_upload.csv")
    with open(path, "rb") as handle:
        upload = SimpleUploadedFile("api_upload.csv", handle.read(),
                                    content_type="text/csv")

    response = api_client.post("/api/imports/upload/",
                               {"file": upload, "source_name": "API source",
                                "category": "Public Contacts"}, format="multipart")
    assert response.status_code == 201, response.data
    import_file_id = response.data["id"]
    assert response.data["column_mapping"]["Business Name"] == "company_name"

    preview = api_client.get(f"/api/imports/{import_file_id}/preview/")
    assert preview.status_code == 200
    assert preview.data["stats"]["rows"] == 5
    assert len(preview.data["preview"]) == 5

    process = api_client.post(f"/api/imports/{import_file_id}/process/", {}, format="json")
    assert process.status_code == 202
    job_id = process.data["id"]

    job = api_client.get(f"/api/imports/jobs/{job_id}/")
    assert job.status_code == 200
    assert job.data["status"] == "COMPLETED"
    assert job.data["created_rows"] >= 3
    assert Lead.objects.count() >= 3
    assert ImportFile.objects.filter(pk=import_file_id, status="COMPLETED").exists()


def test_import_jobs_list_route_is_not_shadowed_by_import_files(db, api_client,
                                                                csv_file, sample_rows):
    """Regression: "/api/imports/jobs/" is a nested router prefix.

    DRF matches routes in registration order, so if "imports" is registered
    before "imports/jobs" the detail route r"imports/(?P<pk>[^/.]+)/$" catches
    the literal "jobs" and the list endpoint 404s (the UI's job-progress panel
    depends on it). Both the list and the filtered list must resolve.
    """
    from django.core.files.uploadedfile import SimpleUploadedFile

    path = csv_file(sample_rows, "jobs_route.csv")
    with open(path, "rb") as handle:
        upload = SimpleUploadedFile("jobs_route.csv", handle.read(),
                                    content_type="text/csv")
    created = api_client.post("/api/imports/upload/",
                              {"file": upload, "source_name": "Jobs route source"},
                              format="multipart")
    assert created.status_code == 201, created.data
    import_file_id = created.data["id"]

    processed = api_client.post(f"/api/imports/{import_file_id}/process/", {},
                                format="json")
    assert processed.status_code == 202
    job_id = processed.data["id"]

    listing = api_client.get("/api/imports/jobs/")
    assert listing.status_code == 200, listing.data
    assert any(row["id"] == job_id for row in listing.data["results"])

    filtered = api_client.get("/api/imports/jobs/", {"import_file": import_file_id,
                                                     "page_size": 5})
    assert filtered.status_code == 200, filtered.data
    assert [row["id"] for row in filtered.data["results"]] == [job_id]

    # The parent resource must still resolve by primary key.
    detail = api_client.get(f"/api/imports/{import_file_id}/")
    assert detail.status_code == 200
    assert detail.data["id"] == import_file_id


def test_import_rejects_unsupported_file(db, api_client, tmp_path):
    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile("brochure.pdf", b"%PDF-1.4 fake",
                                content_type="application/pdf")
    response = api_client.post("/api/imports/upload/", {"file": upload}, format="multipart")
    assert response.status_code == 400
    assert "Unsupported file type" in str(response.data)


def test_settings_update_clamps_limit(db, admin_client):
    response = admin_client.patch("/api/settings/update/",
                                  {"sending.daily_marketing_limit": 500}, format="json")
    assert response.status_code == 200
    assert response.data["values"]["sending.daily_marketing_limit"] <= 100
    # Restore
    admin_client.patch("/api/settings/update/",
                       {"sending.daily_marketing_limit": 90}, format="json")


def test_settings_never_expose_secrets(db, admin_client):
    from apps.ai_engine.models import AIProviderConfig
    from apps.settings.services import set_setting

    set_setting("ai.api_key", "sk-secret-value")
    AIProviderConfig.objects.create(provider="openai", api_key="sk-secret-value",
                                    model="gpt-4o-mini")

    response = admin_client.get("/api/settings/")
    assert response.status_code == 200
    assert "sk-secret-value" not in str(response.data)
    assert response.data["values"]["ai.api_key"] == "***"

    providers = admin_client.get("/api/ai/providers/")
    assert "sk-secret-value" not in str(providers.data)
    results = providers.data["results"] if "results" in providers.data else providers.data
    assert results[0]["has_key"] is True


def test_crm_pipeline_and_move(db, api_client, make_lead):
    lead = make_lead(email="owner@x.com")
    response = api_client.get("/api/crm/pipeline/")
    assert response.status_code == 200
    assert any(stage["count"] >= 1 for stage in response.data["stages"])

    response = api_client.post(f"/api/crm/leads/{lead.pk}/move/",
                               {"stage": "PROPOSAL", "note": "Sent proposal",
                                "deal_value": "15000.00"}, format="json")
    assert response.status_code == 200
    lead.refresh_from_db()
    assert lead.crm_stage == "PROPOSAL"
    assert float(lead.deal_value) == 15000.0
    assert lead.activities.filter(type="STAGE_CHANGE").exists()


def test_lead_export_streams_csv(db, api_client, make_lead):
    make_lead(email="owner@x.com")
    response = api_client.get("/api/leads/export/")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    content = b"".join(response.streaming_content).decode()
    assert "company_name" in content
    assert "Example Auto Spa" in content
