"""
Import pipeline: raw row -> normalized canonical record -> Lead/Company/Contact.

The pipeline is chunk-oriented and idempotent:

* rows are normalized (emails, phones, websites, names, addresses),
* companies/contacts are upserted with a per-job cache,
* leads are matched with a *blocking key* (email, or company+domain+city+state,
  or company+phone, ...) queried in ONE statement per chunk, so the number of
  queries per chunk stays constant instead of growing with the chunk size,
* duplicates are counted and recorded, never silently dropped.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.companies.models import Company
from apps.contacts.models import Contact
from apps.core.normalizers import (
    normalize_address,
    normalize_email,
    normalize_employee_count,
    normalize_phone,
    normalize_website,
)
from apps.core.utils import (
    clean_text,
    normalize_company_name,
    normalize_key,
    normalize_person_name,
    split_full_name,
)
from apps.imports.mapping import apply_mapping
from apps.leads.classifier import classify_company
from apps.leads.models import EmailStatus, EnrichmentStatus, Lead, LeadStatus

DEFAULT_COUNTRY = "United States"


@dataclass
class RowStats:
    rows: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    duplicates: int = 0
    invalid: int = 0
    with_email: int = 0
    without_email: int = 0
    invalid_emails: int = 0
    missing_company: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "rows": self.rows, "created": self.created, "updated": self.updated,
            "skipped": self.skipped, "duplicates": self.duplicates,
            "invalid": self.invalid, "with_email": self.with_email,
            "without_email": self.without_email, "invalid_emails": self.invalid_emails,
            "missing_company": self.missing_company, "errors": self.errors,
        }

    def merge(self, other: "RowStats") -> None:
        for name, value in other.as_dict().items():
            setattr(self, name, getattr(self, name) + value)


@dataclass
class NormalizedRow:
    data: dict[str, Any]
    errors: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors


def normalize_row(raw: dict, mapping: dict[str, str], *,
                  source_category: str = "", source_name: str = "",
                  source_city: str = "", default_country: str = DEFAULT_COUNTRY) -> NormalizedRow:
    """Project + normalize one raw row into the canonical lead schema."""
    projected = apply_mapping(raw, mapping)
    errors: list[dict] = []
    warnings: list[str] = []

    company_name = normalize_company_name(projected.get("company_name", ""))
    contact_name = normalize_person_name(projected.get("contact_name", ""))
    first_name = normalize_person_name(projected.get("first_name", ""))
    last_name = normalize_person_name(projected.get("last_name", ""))

    if not contact_name and (first_name or last_name):
        contact_name = " ".join(p for p in (first_name, last_name) if p).strip()
    if contact_name and (not first_name or not last_name):
        # Fill the missing half from the full contact name ("John Smith" -> Smith).
        derived_first, derived_last = split_full_name(contact_name)
        first_name = first_name or derived_first
        last_name = last_name or derived_last

    raw_email = clean_text(projected.get("email", ""))
    email = normalize_email(raw_email)
    if raw_email and not email.is_valid:
        errors.append({"field": "email", "message": f"Invalid email syntax: {raw_email}"})
    if email.is_disposable:
        warnings.append("Disposable email domain")

    phone_display, phone_key = normalize_phone(projected.get("phone", "") or projected.get("mobile", ""))
    mobile_display, mobile_key = normalize_phone(projected.get("mobile", ""))
    phone_type = clean_text(projected.get("phone_type", "")).title()
    if mobile_display and not phone_display:
        phone_display, phone_key = mobile_display, mobile_key
        phone_type = phone_type or "Mobile"

    website = normalize_website(projected.get("website", ""))
    if projected.get("website") and not website.is_valid:
        warnings.append("Unparseable website")

    address = normalize_address(
        street=projected.get("street_address", ""),
        city=projected.get("city", ""),
        state=projected.get("state", ""),
        zip_code=projected.get("zip_code", ""),
        country=projected.get("country", "") or default_country,
    )

    employee_count = normalize_employee_count(projected.get("employee_count", ""))

    industry_name = clean_text(projected.get("industry", ""))
    sub_industry_name = clean_text(projected.get("sub_industry", ""))

    if not company_name:
        errors.append({"field": "company_name", "message": "Missing business name"})

    data = {
        "company_name": company_name,
        "company_name_key": normalize_key(company_name),
        "contact_name": contact_name,
        "first_name": first_name,
        "last_name": last_name,
        "job_title": clean_text(projected.get("job_title", "")),
        "email": email.normalized or raw_email,
        "email_normalized": email.normalized,
        "email_status": (
            EmailStatus.VALID if email.is_valid
            else (EmailStatus.INVALID if raw_email else EmailStatus.MISSING)
        ),
        "email_domain": email.domain,
        "email_is_role": email.is_role,
        "email_is_free_provider": email.is_free_provider,
        "phone": phone_display,
        "phone_normalized": phone_key,
        "phone_type": phone_type,
        "mobile": mobile_display,
        "website": website.normalized or clean_text(projected.get("website", "")),
        "website_normalized": website.normalized,
        "website_domain": website.domain,
        "street_address": address["street_address"],
        "city": address["city"],
        "state": address["state"],
        "zip_code": address["zip_code"],
        "country": address["country"],
        "employee_count": employee_count,
        "employee_range": clean_text(projected.get("employee_count", ""))
        if employee_count is None else "",
        "revenue": clean_text(projected.get("revenue", "")),
        "linkedin_url": clean_text(projected.get("linkedin_url", "")),
        "notes": clean_text(projected.get("notes", "")),
        "tags": [t.strip() for t in clean_text(projected.get("tags", "")).split(",") if t.strip()],
        "industry_name": industry_name,
        "sub_industry_name": sub_industry_name,
        "source_category": clean_text(projected.get("source_category", "")) or source_category,
        "source_city": clean_text(projected.get("source_city", "")) or source_city,
        "source_name": source_name,
        "raw": {k: v for k, v in raw.items() if str(v).strip()},
    }
    return NormalizedRow(data=data, errors=errors, warnings=warnings)


def preview_stats(rows: list[dict], mapping: dict[str, str], **kwargs) -> dict:
    """STEP 8: total / valid / invalid / with email / without email / duplicates."""
    stats = RowStats()
    seen_emails: set[str] = set()
    seen_companies: set[str] = set()
    preview: list[dict] = []

    for row in rows:
        stats.rows += 1
        normalized = normalize_row(row, mapping, **kwargs)
        data = normalized.data
        if len(preview) < 50:
            preview.append({
                "company_name": data["company_name"],
                "contact_name": data["contact_name"],
                "email": data["email_normalized"] or data["email"],
                "phone": data["phone"],
                "website": data["website_domain"],
                "city": data["city"],
                "state": data["state"],
                "errors": normalized.errors,
                "warnings": normalized.warnings,
            })

        if normalized.errors:
            stats.invalid += 1
        if data["email_normalized"]:
            stats.with_email += 1
            if data["email_normalized"] in seen_emails:
                stats.duplicates += 1
            seen_emails.add(data["email_normalized"])
        else:
            stats.without_email += 1
        if data["email_status"] == EmailStatus.INVALID:
            stats.invalid_emails += 1
        if not data["company_name_key"]:
            stats.missing_company += 1
        key = "|".join([data["company_name_key"], data["website_domain"],
                        normalize_key(data["city"])])
        if key in seen_companies:
            stats.duplicates += 1
        seen_companies.add(key)

    stats.errors = stats.invalid
    return {"stats": stats.as_dict(), "preview": preview}


class LeadBuilder:
    """Creates/updates Company, Contact and Lead rows for one import job."""

    def __init__(self, *, source, import_file, job=None, options: dict | None = None,
                 user=None):
        self.source = source
        self.import_file = import_file
        self.job = job
        self.options = options or {}
        self.user = user
        self.stats = RowStats()
        self._company_cache: OrderedDict[str, Company] = OrderedDict()
        self._contact_cache: OrderedDict[str, Contact] = OrderedDict()
        self._industry_cache: dict[str, tuple[int | None, int | None]] = {}
        self._errors_buffer: list[Any] = []

    # ------------------------------------------------------------------
    # Companies / contacts
    # ------------------------------------------------------------------
    def _get_or_create_company(self, data: dict) -> Company | None:
        name_key = data["company_name_key"]
        if not name_key:
            return None
        cache_key = "|".join([
            name_key, data["website_domain"], normalize_key(data["city"]),
            normalize_key(data["state"]),
        ])
        if cache_key in self._company_cache:
            return self._company_cache[cache_key]

        defaults = {
            "name": data["company_name"],
            "name_normalized": name_key,
            "website": data["website"],
            "website_normalized": data["website_normalized"],
            "domain": data["website_domain"],
            "phone": data["phone"],
            "phone_normalized": data["phone_normalized"],
            "email": data["email_normalized"],
            "street_address": data["street_address"],
            "city": data["city"],
            "state": data["state"],
            "zip_code": data["zip_code"],
            "country": data["country"],
            "employee_count": data["employee_count"],
            "linkedin_url": data["linkedin_url"],
            "source": self.source,
            "source_file": self.import_file,
            "created_by": self.user,
        }
        company, created = Company.objects.get_or_create(
            name_normalized=name_key,
            domain=data["website_domain"] or "",
            city=data["city"],
            state=data["state"],
            defaults=defaults,
        )
        if not created and self.options.get("update_existing", True):
            changed = False
            for field_name, value in defaults.items():
                if field_name in {"source", "source_file", "created_by"}:
                    continue
                if value and not getattr(company, field_name):
                    setattr(company, field_name, value)
                    changed = True
            if changed:
                company.save()

        self._company_cache[cache_key] = company
        if len(self._company_cache) > 5000:  # bounded memory
            self._company_cache.popitem(last=False)
        return company

    def _get_or_create_contact(self, data: dict, company: Company | None) -> Contact | None:
        key = data["email_normalized"] or normalize_key(
            f"{data['first_name']} {data['last_name']}"
        )
        if not key:
            return None
        cache_key = f"{company.pk if company else 0}|{key}"
        if cache_key in self._contact_cache:
            return self._contact_cache[cache_key]

        defaults = {
            "company": company,
            "first_name": data["first_name"],
            "last_name": data["last_name"],
            "full_name": data["contact_name"],
            "job_title": data["job_title"],
            "email": data["email"] or "",
            "email_normalized": data["email_normalized"],
            "phone": data["phone"],
            "phone_normalized": data["phone_normalized"],
            "phone_type": data["phone_type"],
            "mobile": data.get("mobile", ""),
            "city": data["city"],
            "state": data["state"],
            "linkedin_url": data["linkedin_url"],
            "source": self.source,
            "source_file": self.import_file,
            "created_by": self.user,
        }
        lookup = {"company": company} if company else {"company__isnull": True}
        if data["email_normalized"]:
            lookup["email_normalized"] = data["email_normalized"]
            contact, created = Contact.objects.get_or_create(defaults=defaults, **lookup)
        else:
            lookup["full_name"] = data["contact_name"]
            contact = Contact.objects.filter(**lookup).first()
            created = False
            if contact is None:
                contact = Contact.objects.create(**defaults)
                created = True
        if not created and self.options.get("update_existing", True):
            changed = False
            for field_name in ("job_title", "phone", "phone_normalized", "phone_type",
                               "email", "email_normalized", "mobile"):
                value = defaults.get(field_name)
                if value and not getattr(contact, field_name):
                    setattr(contact, field_name, value)
                    changed = True
            if changed:
                contact.save()

        self._contact_cache[cache_key] = contact
        if len(self._contact_cache) > 5000:
            self._contact_cache.popitem(last=False)
        return contact

    # ------------------------------------------------------------------
    # Industry
    # ------------------------------------------------------------------
    def _resolve_industry(self, data: dict) -> tuple[int | None, int | None]:
        cache_key = "|".join([data["industry_name"], data["sub_industry_name"],
                              data["company_name"], data["website_domain"],
                              data["source_category"]])
        if cache_key in self._industry_cache:
            return self._industry_cache[cache_key]

        from apps.companies.models import Industry

        industry = sub_industry = None
        explicit_industry = explicit_sub = None
        if data["industry_name"]:
            explicit_industry = Industry.objects.filter(
                name__iexact=data["industry_name"]
            ).first()
        if data["sub_industry_name"]:
            explicit_sub = Industry.objects.filter(
                name__iexact=data["sub_industry_name"]
            ).first()
            if explicit_sub and explicit_sub.parent_id:
                explicit_industry = explicit_industry or explicit_sub.parent

        if explicit_industry or explicit_sub:
            if explicit_sub and explicit_sub.parent_id:
                industry, sub_industry = explicit_sub.parent_id, explicit_sub.id
            elif explicit_industry and explicit_industry.parent_id:
                industry, sub_industry = explicit_industry.parent_id, explicit_industry.id
            else:
                industry, sub_industry = (
                    explicit_industry.id if explicit_industry else None,
                    explicit_sub.id if explicit_sub else None,
                )
        else:
            classification = classify_company(
                company_name=data["company_name"],
                website=data["website_domain"],
                description=data.get("notes", ""),
                source_category=data["source_category"],
                source_name=data["source_name"],
            )
            if classification.industry_id or classification.sub_industry_id:
                industry = classification.industry_id
                sub_industry = classification.sub_industry_id

        result = (industry, sub_industry)
        self._industry_cache[cache_key] = result
        if len(self._industry_cache) > 10000:
            self._industry_cache.clear()
        return result

    # ------------------------------------------------------------------
    # Chunk processing
    # ------------------------------------------------------------------
    @transaction.atomic
    def process_chunk(self, rows: list[dict], mapping: dict[str, str], *,
                      start_row: int = 0) -> RowStats:
        chunk_stats = RowStats()
        normalized_rows: list[tuple[int, dict, NormalizedRow]] = []

        # ---- 1. Normalize -------------------------------------------------
        for offset, raw in enumerate(rows):
            row_number = start_row + offset
            chunk_stats.rows += 1
            normalized = normalize_row(
                raw, mapping,
                source_category=(self.source.category if self.source else ""),
                source_name=(self.source.name if self.source else ""),
                source_city=(self.source.city if self.source else ""),
            )
            data = normalized.data

            if data["email_normalized"]:
                chunk_stats.with_email += 1
            else:
                chunk_stats.without_email += 1
            if data["email_status"] == EmailStatus.INVALID:
                chunk_stats.invalid_emails += 1
            if not data["company_name_key"]:
                chunk_stats.missing_company += 1

            # Row-level validation ------------------------------------------
            if normalized.errors:
                chunk_stats.invalid += 1
                chunk_stats.errors += 1
                self._record_error(row_number, normalized)
                if self.options.get("import_valid_only"):
                    chunk_stats.skipped += 1
                    continue
                if not data["company_name_key"]:
                    chunk_stats.skipped += 1
                    continue
                if self.options.get("skip_invalid_emails") and \
                        data["email_status"] == EmailStatus.INVALID:
                    chunk_stats.skipped += 1
                    continue
            if not data["email_normalized"] and not self.options.get(
                    "import_rows_without_email", True):
                chunk_stats.skipped += 1
                continue

            normalized_rows.append((row_number, data, normalized))

        if not normalized_rows:
            return chunk_stats

        # ---- 2. Blocking lookup: ONE query for the whole chunk -------------
        email_keys = {d["email_normalized"] for _, d, _ in normalized_rows if d["email_normalized"]}
        company_keys = {
            "|".join([d["company_name_key"], d["website_domain"], normalize_key(d["city"]),
                      normalize_key(d["state"])])
            for _, d, _ in normalized_rows if d["company_name_key"]
        }
        phone_keys = {
            d["phone_normalized"] for _, d, _ in normalized_rows if d["phone_normalized"]
        }

        from django.db.models import Q

        conditions = Q()
        if email_keys:
            conditions |= Q(email_normalized__in=email_keys)
        if phone_keys:
            conditions |= Q(phone_normalized__in=phone_keys)
        if company_keys:
            conditions |= Q(dedupe_key__in=company_keys)

        existing_by_email: dict[str, Lead] = {}
        existing_by_key: dict[str, Lead] = {}
        if conditions:
            for lead in Lead.objects.filter(conditions).only(
                "id", "email_normalized", "phone_normalized", "dedupe_key"
            ):
                if lead.email_normalized:
                    existing_by_email.setdefault(lead.email_normalized, lead)
                if lead.dedupe_key:
                    existing_by_key.setdefault(lead.dedupe_key, lead)

        # ---- 3. Upsert ------------------------------------------------------
        to_create: list[Lead] = []
        to_update: list[Lead] = []
        updates_fields: dict[int, dict] = {}
        # Keys created *within this chunk* (bulk_create happens after the loop).
        in_flight_emails: set[str] = set()
        in_flight_keys: set[str] = set()

        for row_number, data, normalized in normalized_rows:
            blocking_key = "|".join([
                data["company_name_key"], data["website_domain"],
                normalize_key(data["city"]), normalize_key(data["state"]),
            ])
            data["dedupe_key"] = blocking_key

            existing = None
            if data["email_normalized"] and data["email_normalized"] in existing_by_email:
                existing = existing_by_email[data["email_normalized"]]
            elif blocking_key in existing_by_key:
                existing = existing_by_key[blocking_key]
            elif (data["email_normalized"] and data["email_normalized"] in in_flight_emails) \
                    or blocking_key in in_flight_keys:
                # Same file contains the same business twice.
                chunk_stats.duplicates += 1
                chunk_stats.skipped += 1
                continue

            if existing is not None:
                chunk_stats.duplicates += 1
                if not self.options.get("update_existing", False):
                    chunk_stats.skipped += 1
                    continue
                updates_fields[existing.pk] = (row_number, data)
                to_update.append(existing)
                continue

            company = self._get_or_create_company(data)
            contact = self._get_or_create_contact(data, company)
            industry_id, sub_industry_id = self._resolve_industry(data)
            if data["email_normalized"]:
                in_flight_emails.add(data["email_normalized"])
            in_flight_keys.add(blocking_key)

            lead = Lead(
                company=company,
                contact=contact,
                source=self.source,
                source_file=self.import_file,
                source_row_number=row_number,
                company_name=data["company_name"],
                company_name_key=data["company_name_key"],
                industry_id=industry_id,
                sub_industry_id=sub_industry_id,
                contact_name=data["contact_name"],
                first_name=data["first_name"],
                last_name=data["last_name"],
                job_title=data["job_title"],
                email=data["email"],
                email_normalized=data["email_normalized"],
                email_status=data["email_status"],
                email_domain=data["email_domain"],
                email_is_role=data["email_is_role"],
                email_is_free_provider=data["email_is_free_provider"],
                phone=data["phone"],
                phone_normalized=data["phone_normalized"],
                phone_type=data["phone_type"],
                website=data["website"],
                website_normalized=data["website_normalized"],
                website_domain=data["website_domain"],
                street_address=data["street_address"],
                city=data["city"],
                state=data["state"],
                zip_code=data["zip_code"],
                country=data["country"],
                employee_count=data["employee_count"],
                employee_range=data["employee_range"],
                source_name=data["source_name"] or (self.source.name if self.source else ""),
                source_category=data["source_category"],
                source_city=data["source_city"],
                lead_status=(
                    LeadStatus.MISSING_EMAIL if not data["email_normalized"]
                    else LeadStatus.INVALID
                    if data["email_status"] == EmailStatus.INVALID
                    else LeadStatus.VALID
                ),
                dedupe_key=blocking_key,
                enrichment_status=(
                    EnrichmentStatus.SKIPPED if data["website_domain"]
                    else EnrichmentStatus.NOT_PROCESSED
                ) if not data["email_normalized"] else EnrichmentStatus.NOT_PROCESSED,
                raw_data=data["raw"],
                tags=data["tags"],
            )
            to_create.append(lead)

        # ---- 4. Persist ------------------------------------------------------
        if to_create:
            # Score before inserting so the query count stays flat.
            from apps.leads.scoring import apply_score

            for lead in to_create:
                apply_score(lead, save=False)
            Lead.objects.bulk_create(to_create, batch_size=500, ignore_conflicts=False)
            chunk_stats.created += len(to_create)
            # Cache the new rows so duplicates inside the same chunk are caught.
            for lead in to_create:
                if lead.email_normalized:
                    existing_by_email.setdefault(lead.email_normalized, lead)
                if lead.dedupe_key:
                    existing_by_key.setdefault(lead.dedupe_key, lead)

        if to_update:
            for lead in to_update:
                row_number, data = updates_fields[lead.pk]
                changed = False
                for field_name in ("phone", "phone_normalized", "website",
                                   "website_normalized", "website_domain", "city",
                                   "state", "street_address", "zip_code", "job_title",
                                   "contact_name", "first_name", "last_name"):
                    value = data[field_name]
                    if value and not getattr(lead, field_name):
                        setattr(lead, field_name, value)
                        changed = True
                if changed:
                    lead.save(update_fields=[
                        "phone", "phone_normalized", "website", "website_normalized",
                        "website_domain", "city", "state", "street_address", "zip_code",
                        "job_title", "contact_name", "first_name", "last_name", "updated_at",
                    ])
                    chunk_stats.updated += 1
                else:
                    chunk_stats.skipped += 1

        return chunk_stats

    def flush_errors(self, job) -> None:
        from apps.imports.models import ImportRowError

        if not self._errors_buffer:
            return
        ImportRowError.objects.bulk_create(self._errors_buffer, batch_size=200)
        self._errors_buffer = []

    def _record_error(self, row_number: int, normalized: NormalizedRow) -> None:
        from django.conf import settings

        from apps.imports.models import ImportRowError

        if self.job is None:
            return
        limit = int(settings.IMPORT_ERROR_SAMPLE_LIMIT)
        if ImportRowError.objects.filter(job=self.job).count() >= limit:
            return
        for error in normalized.errors:
            self._errors_buffer.append(
                ImportRowError(
                    job=self.job,
                    row_number=row_number,
                    severity="ERROR",
                    field=error.get("field", ""),
                    message=error.get("message", "")[:500],
                    raw_data=normalized.data.get("raw", {}),
                )
            )
        if len(self._errors_buffer) >= 100:
            self.flush_errors(self.job)


def finalize_job_stats(job, stats: RowStats) -> None:
    job.processed_rows = stats.rows
    job.created_rows = stats.created
    job.updated_rows = stats.updated
    job.skipped_rows = stats.skipped
    job.duplicate_rows = stats.duplicates
    job.invalid_rows = stats.invalid
    job.rows_with_email = stats.with_email
    job.rows_without_email = stats.without_email
    job.invalid_email_rows = stats.invalid_emails
    job.missing_company_rows = stats.missing_company
    job.error_rows = stats.errors
    job.progress_percent = 100
    job.finished_at = timezone.now()
    job.save(update_fields=[
        "processed_rows", "created_rows", "updated_rows", "skipped_rows",
        "duplicate_rows", "invalid_rows", "rows_with_email", "rows_without_email",
        "invalid_email_rows", "missing_company_rows", "error_rows",
        "progress_percent", "finished_at", "updated_at",
    ])
    if job.import_file.source_id:
        job.import_file.source.recalculate_stats()
