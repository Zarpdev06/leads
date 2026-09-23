"""CSV/XLSX import, normalization, invalid emails, duplicates, missing emails."""

from apps.imports.pipeline import normalize_row, preview_stats
from apps.leads.models import EmailStatus, EnrichmentStatus, Lead
from tests.utils import build_import_file, run_import


def test_csv_import_creates_leads(db, csv_file, sample_rows):
    path = csv_file(sample_rows, "Automotive_in_Chicago_Illinois.csv")
    import_file = build_import_file(path)
    job = run_import(import_file)

    assert job.status == "COMPLETED"
    assert Lead.objects.count() == 3  # 5 rows: 1 unnamed, 1 in-file duplicate
    assert job.created_rows >= 3
    assert job.rows_with_email >= 3
    assert job.rows_without_email >= 1


def test_csv_import_normalizes_values(db, csv_file, sample_rows):
    path = csv_file(sample_rows)
    import_file = build_import_file(path)
    run_import(import_file)

    lead = Lead.objects.get(email_normalized="john@abcautodetailing.com")
    assert lead.company_name == "ABC Auto Detailing"
    assert lead.email_status == EmailStatus.VALID
    assert lead.phone_normalized == "+12145550100"
    assert lead.website_domain == "abcautodetailing.com"
    assert lead.city == "Dallas"
    assert lead.state == "TX"           # "texas" normalized to TX
    assert "utm_source" not in lead.website_normalized
    assert lead.first_name == "John"
    assert lead.last_name == "Smith"    # derived from the contact name


def test_xlsx_import(db, xlsx_file, sample_rows):
    path = xlsx_file(sample_rows, sheet="Leads")
    import_file = build_import_file(path)
    assert import_file.file_type == "XLSX"
    assert "Leads" in import_file.available_sheets

    job = run_import(import_file)
    assert job.status == "COMPLETED"
    assert Lead.objects.filter(email_normalized="john@abcautodetailing.com").exists()


def test_invalid_email_is_recorded(db, csv_file, sample_rows):
    path = csv_file(sample_rows)
    import_file = build_import_file(path)
    job = run_import(import_file)

    assert job.invalid_email_rows >= 1
    assert job.error_rows >= 1
    assert job.row_errors.filter(field="email").exists()


def test_duplicate_rows_are_counted_not_created(db, csv_file, sample_rows):
    """Rows 1 and 5 are the same business with the same email."""
    path = csv_file(sample_rows)
    import_file = build_import_file(path)
    job = run_import(import_file)

    assert Lead.objects.filter(email_normalized="john@abcautodetailing.com").count() == 1
    assert job.duplicate_rows >= 1


def test_missing_email_rows_are_imported(db, csv_file, sample_rows):
    path = csv_file(sample_rows)
    import_file = build_import_file(path, name="Shine.csv")
    run_import(import_file)

    no_email = Lead.objects.filter(email_normalized="")
    assert no_email.count() >= 1
    assert all(lead.lead_status == "MISSING_EMAIL" for lead in no_email)
    # A website is available, so enrichment is possible later.
    assert no_email.filter(enrichment_status=EnrichmentStatus.SKIPPED).count() >= 1
    assert no_email.filter(website_domain="shinemobiledetail.com").exists()


def test_import_valid_only_skips_bad_rows(db, csv_file, sample_rows):
    path = csv_file(sample_rows, "valid_only.csv")
    import_file = build_import_file(path)
    job = run_import(import_file, import_valid_only=True, import_rows_without_email=False)

    assert job.skipped_rows >= 1
    assert Lead.objects.filter(email_normalized="").count() == 0


def test_preview_stats(db, sample_rows):
    from apps.imports.mapping import auto_map

    row = sample_rows[0]
    result = normalize_row(row, auto_map(list(row.keys()))["mapping"])
    assert result.data["city"] == "Dallas"

    stats = preview_stats(sample_rows, auto_map(list(sample_rows[0].keys()))["mapping"])
    assert stats["stats"]["rows"] == 5
    assert stats["stats"]["missing_company"] == 1
    assert stats["stats"]["duplicates"] >= 1
    assert len(stats["preview"]) <= 50


def test_large_file_is_chunked_not_loaded(monkeypatch, db, tmp_path):
    """The reader must yield batches, never the whole file at once."""
    import csv

    path = tmp_path / "big.csv"
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Business Name", "Email", "City", "State"])
        for index in range(2500):
            writer.writerow([f"Company {index}", f"owner{index}@example.com",
                             "Dallas", "TX"])

    import_file = build_import_file(str(path))
    import_file.options = {}
    seen_batches = []

    from apps.imports.readers import iter_csv_chunks

    for batch in iter_csv_chunks(str(path), chunk_size=500):
        seen_batches.append(len(batch))
    assert seen_batches == [500, 500, 500, 500, 500]
    assert sum(seen_batches) == 2500

    job = run_import(import_file, chunk_size=500)
    assert job.processed_rows == 2500
    assert Lead.objects.count() == 2500


def test_reimport_same_file_is_idempotent(db, csv_file, sample_rows):
    path = csv_file(sample_rows, "twice.csv")
    first = build_import_file(path, name="one.csv")
    second = build_import_file(path, name="two.csv")
    run_import(first)
    count_after_first = Lead.objects.count()
    job = run_import(second, update_existing=False)
    assert Lead.objects.count() == count_after_first
    assert job.skipped_rows >= 1


def test_headers_with_padded_whitespace_are_mapped_and_read(db, csv_file):
    """Exports often pad headers ('  Contact Person '). usecols must still match."""
    rows = [
        {"  Business Name ": "Acme Auto Detailing", " Contact Person": "John Smith",
         "Corporate Email": "john@acme.com", "City": "Dallas", "State": "TX"},
        {"  Business Name ": "Bravo Detailing", " Contact Person": "Ana Diaz",
         "Corporate Email": "ana@bravo.com", "City": "Austin", "State": "TX"},
    ]
    path = csv_file(rows, "padded.csv")
    import_file = build_import_file(path)
    assert import_file.column_mapping["Business Name"] == "company_name"

    job = run_import(import_file)
    assert job.status == "COMPLETED"
    assert job.created_rows == 2
    assert Lead.objects.filter(email_normalized="john@acme.com").exists()
    assert Lead.objects.get(email_normalized="john@acme.com").contact_name == "John Smith"


def test_unmapped_columns_are_ignored(db, csv_file, sample_rows):
    path = csv_file(sample_rows)
    import_file = build_import_file(path)
    # The internal reference column must never be imported.
    assert "Internal Ref" not in import_file.column_mapping.values()
    run_import(import_file)
    assert all("REF-" not in json.dumps(lead.raw_data) for lead in Lead.objects.all()[:50])


import json  # noqa: E402  (used by the assertion above)
