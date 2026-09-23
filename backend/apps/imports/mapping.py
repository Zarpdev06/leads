"""
Intelligent column mapping engine.

The importer must never depend on exact column names. Mapping runs five
passes, from most to least certain, and every suggestion carries the method
and a confidence score so the UI can ask a human to confirm anything weak:

    1. exact match            ("email"            -> email)      confidence 1.00
    2. normalized match       ("Email Address"    -> email)      confidence 0.98
    3. alias dictionary       ("Corporate Email"  -> email)      confidence 0.95
    4. fuzzy match (difflib)  ("Busines Name"     -> company_name) 0.70-0.90
    5. semantic / value-shape ("col_7" with 90% '@' -> email)    confidence 0.60-0.85
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, asdict
from typing import Iterable, Sequence

from apps.core.utils import normalize_key

# ---------------------------------------------------------------------------
# Canonical schema
# ---------------------------------------------------------------------------
CANONICAL_FIELDS: list[dict] = [
    {"name": "company_name", "label": "Business / Company name", "aliases": [
        "company", "company name", "business", "business name", "organization",
        "organisation", "org", "org name", "account", "account name", "firm",
        "businessname", "companyname", "name", "entity", "establishment",
        "legal name", "company legal name", "dba", "doing business as", "vendor",
        "employer", "store", "store name", "brand", "practice", "practice name",
    ]},
    {"name": "contact_name", "label": "Contact person", "aliases": [
        "contact", "contact person", "contact name", "owner", "owner name",
        "primary contact", "person", "full name", "name of contact", "contactperson",
        "principal", "manager", "manager name", "decision maker", "decisionmaker",
        "representative", "rep", "customer name", "client name", "member name",
    ]},
    {"name": "first_name", "label": "First name", "aliases": [
        "first name", "firstname", "fname", "given name", "first", "name first",
        "contact first name", "owner first name", "primary first name",
    ]},
    {"name": "last_name", "label": "Last name", "aliases": [
        "last name", "lastname", "lname", "surname", "family name", "last",
        "name last", "contact last name", "owner last name", "primary last name",
    ]},
    {"name": "job_title", "label": "Job title", "aliases": [
        "job title", "title", "position", "role", "designation", "job role",
        "jobtitle", "job position", "occupation", "function", "contact title",
    ]},
    {"name": "email", "label": "Email", "aliases": [
        "email", "email address", "e mail", "e-mail", "e mail address", "mail",
        "primary email", "corporate email", "company email", "business email",
        "work email", "contact email", "emailaddress", "email id", "emailid",
        "electronic mail", "email1", "email 1", "general email", "public email",
        "owner email", "contact email address",
    ]},
    {"name": "phone", "label": "Phone", "aliases": [
        "phone", "phone number", "telephone", "tel", "phone no", "phone1",
        "primary phone", "business phone", "company phone", "work phone",
        "contact phone", "phone_number", "telephone number", "office phone",
        "main phone", "switchboard", "landline", "contact number", "number",
    ]},
    {"name": "mobile", "label": "Mobile", "aliases": [
        "mobile", "mobile phone", "mobile number", "cell", "cell phone",
        "cellphone", "cellular", "mobilephone", "cell number", "m phone",
        "whatsapp", "whatsapp number",
    ]},
    {"name": "phone_type", "label": "Phone type", "aliases": [
        "phone type", "number type", "telephone type", "phone_type", "line type",
        "phone label", "contact type",
    ]},
    {"name": "website", "label": "Website", "aliases": [
        "website", "website url", "web site", "url", "web", "homepage",
        "domain", "site", "web address", "webaddress", "company website",
        "business website", "site url", "page", "landing page",
    ]},
    {"name": "street_address", "label": "Street address", "aliases": [
        "street address", "address", "address line 1", "address1", "street",
        "address 1", "full address", "physical address", "location address",
        "mailing address", "addr", "address line", "streetaddress", "address_1",
    ]},
    {"name": "city", "label": "City", "aliases": [
        "city", "town", "locality", "city name", "municipality", "suburb",
    ]},
    {"name": "state", "label": "State / Province", "aliases": [
        "state", "province", "region", "state province", "st", "state code",
        "county", "state/region", "state or province", "territory",
    ]},
    {"name": "zip_code", "label": "ZIP / Postal code", "aliases": [
        "zip", "zip code", "zipcode", "postal code", "postcode", "post code",
        "postal", "pin code", "zip_code", "zip/postal", "zip4",
    ]},
    {"name": "country", "label": "Country", "aliases": [
        "country", "country code", "nation", "country name", "iso country",
    ]},
    {"name": "employee_count", "label": "Employee count", "aliases": [
        "employees", "employee count", "number of employees", "no of employees",
        "employee size", "company size", "size", "staff", "headcount",
        "employees count", "employee range", "emp count", "num employees",
    ]},
    {"name": "industry", "label": "Industry", "aliases": [
        "industry", "sector", "vertical", "business type", "category",
        "industry type", "niche", "market", "naics", "sic", "business category",
    ]},
    {"name": "sub_industry", "label": "Sub-industry", "aliases": [
        "sub industry", "sub-industry", "subindustry", "sub sector", "subsector",
        "specialty", "specialisation", "specialization", "service type",
        "business sub category", "sub category", "subcategory", "segment",
    ]},
    {"name": "linkedin_url", "label": "LinkedIn URL", "aliases": [
        "linkedin", "linkedin url", "linkedin profile", "linkedin page",
        "linked in", "li profile",
    ]},
    {"name": "revenue", "label": "Annual revenue", "aliases": [
        "revenue", "annual revenue", "sales", "turnover", "revenue range",
        "estimated revenue", "annual sales",
    ]},
    {"name": "notes", "label": "Notes", "aliases": [
        "notes", "note", "comments", "comment", "description", "remarks",
        "about", "details",
    ]},
    {"name": "tags", "label": "Tags", "aliases": [
        "tags", "tag", "labels", "keywords", "groups",
    ]},
    {"name": "source_category", "label": "Source category", "aliases": [
        "source category", "list category", "file category", "dataset",
        "list name", "source type",
    ]},
    {"name": "source_city", "label": "Source city", "aliases": [
        "source city", "list city", "target city", "market city",
    ]},
]

FIELD_LABELS = {f["name"]: f["label"] for f in CANONICAL_FIELDS}
FIELD_NAMES = [f["name"] for f in CANONICAL_FIELDS]

#: alias -> canonical field
ALIAS_INDEX: dict[str, str] = {}
for _field in CANONICAL_FIELDS:
    ALIAS_INDEX[normalize_key(_field["name"])] = _field["name"]
    for _alias in _field["aliases"]:
        ALIAS_INDEX[normalize_key(_alias)] = _field["name"]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
URL_RE = re.compile(r"^(https?://|www\.)[^\s]+\.[A-Za-z]{2,}", re.I)
PHONE_RE = re.compile(r"^\+?[\d][\d\s\(\)\-\.\,x]{6,}$")


@dataclass
class MappingSuggestion:
    source_column: str
    target_field: str | None
    confidence: float
    method: str

    def as_dict(self) -> dict:
        data = asdict(self)
        data["label"] = FIELD_LABELS.get(self.target_field or "", "")
        return data


# ---------------------------------------------------------------------------
# Passes
# ---------------------------------------------------------------------------
def _exact(header: str) -> str | None:
    key = header.strip().lower()
    return next((f["name"] for f in CANONICAL_FIELDS if f["name"] == key), None)


def _normalized(header: str) -> str | None:
    return ALIAS_INDEX.get(normalize_key(header))


def _fuzzy(header: str, threshold: float = 0.86) -> tuple[str | None, float]:
    """Token-set similarity against aliases; tolerant of typos and prefixes."""
    key = normalize_key(header)
    if not key:
        return None, 0.0
    best_field, best_ratio = None, 0.0
    alias_items = list(ALIAS_INDEX.items())
    # difflib on the whole alias space is fast enough for a handful of headers
    close = difflib.get_close_matches(key, [a for a, _ in alias_items], n=12, cutoff=0.6)
    for alias in close:
        ratio = difflib.SequenceMatcher(None, key, alias).ratio()
        if ratio > best_ratio:
            best_field, best_ratio = ALIAS_INDEX[alias], ratio
    if best_ratio >= threshold:
        return best_field, min(0.9, 0.65 + best_ratio * 0.25)
    return None, best_ratio


def sniff_column(values: Sequence[str]) -> tuple[str | None, float]:
    """Infer a field from the *shape of the data* (pass 5)."""
    sample = [str(v).strip() for v in values if v not in (None, "")][:200]
    if len(sample) < 3:
        return None, 0.0

    def ratio(predicate) -> float:
        return sum(1 for v in sample if predicate(v)) / len(sample)

    email_ratio = ratio(lambda v: bool(EMAIL_RE.match(v)))
    if email_ratio >= 0.6:
        return "email", min(0.85, 0.6 + email_ratio * 0.25)

    url_ratio = ratio(lambda v: bool(URL_RE.match(v)) or
                      re.match(r"^[\w-]+(\.[\w-]+)+(/\S*)?$", v or ""))
    if url_ratio >= 0.6:
        return "website", min(0.85, 0.6 + url_ratio * 0.25)

    phone_ratio = ratio(lambda v: bool(PHONE_RE.match(v)) and sum(c.isdigit() for c in v) >= 7)
    if phone_ratio >= 0.6:
        return "phone", min(0.8, 0.55 + phone_ratio * 0.25)

    zip_ratio = ratio(lambda v: bool(re.match(r"^\d{4,5}(-\d{4})?$", v)))
    if zip_ratio >= 0.7:
        return "zip_code", min(0.8, 0.55 + zip_ratio * 0.25)

    state_ratio = ratio(lambda v: bool(re.match(r"^[A-Z]{2}$", v)) or
                        v.lower() in {"texas", "california", "florida", "illinois", "ohio"})
    if state_ratio >= 0.7:
        return "state", min(0.75, 0.5 + state_ratio * 0.25)

    employee_ratio = ratio(lambda v: bool(re.match(r"^\d{1,3}(\s*-\s*\d{1,3})?$", v))
                           or bool(re.search(r"employee", v, re.I)))
    if employee_ratio >= 0.7:
        return "employee_count", 0.6
    return None, 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def suggest_mapping(headers: Iterable[str],
                    sample_rows: Sequence[dict] | None = None) -> list[MappingSuggestion]:
    """Map every source column to a canonical field (or None when unmapped)."""
    columns = [str(h).strip() for h in headers if str(h).strip()]
    sample_rows = sample_rows or []
    taken: set[str] = set()
    suggestions: list[MappingSuggestion] = []

    # Column values (for the semantic pass)
    column_values: dict[str, list[str]] = {
        col: [row.get(col) for row in sample_rows if row.get(col) not in (None, "")]
        for col in columns
    }

    # Pass 1-3: exact / normalized / alias --------------------------------
    pending: list[str] = []
    for column in columns:
        field = _exact(column) or _normalized(column)
        if field and field not in taken:
            suggestions.append(MappingSuggestion(column, field, 0.98, "exact" if _exact(column) else "alias"))
            taken.add(field)
        else:
            pending.append(column)

    # Pass 4: fuzzy --------------------------------------------------------
    still_pending: list[str] = []
    for column in pending:
        field, ratio = _fuzzy(column)
        if field and field not in taken:
            suggestions.append(MappingSuggestion(column, field, round(ratio, 2), "fuzzy"))
            taken.add(field)
        else:
            still_pending.append(column)

    # Pass 5: value-shape sniffing ----------------------------------------
    for column in still_pending:
        field, confidence = sniff_column(column_values.get(column, []))
        if field and field not in taken:
            suggestions.append(MappingSuggestion(column, field, round(confidence, 2), "semantic"))
            taken.add(field)
        else:
            suggestions.append(MappingSuggestion(column, None, 0.0, "none"))

    # Keep the original column order for the UI.
    order = {column: index for index, column in enumerate(columns)}
    suggestions.sort(key=lambda s: order.get(s.source_column, 999))
    return suggestions


def mapping_to_dict(suggestions: Sequence[MappingSuggestion]) -> dict[str, str]:
    """{source_column: canonical_field} for confirmed suggestions only."""
    return {s.source_column: s.target_field for s in suggestions if s.target_field}


def auto_map(headers: Iterable[str], sample_rows: Sequence[dict] | None = None) -> dict:
    """Convenience wrapper returning everything the UI needs in one call."""
    suggestions = suggest_mapping(headers, sample_rows)
    return {
        "suggestions": [s.as_dict() for s in suggestions],
        "mapping": mapping_to_dict(suggestions),
        "unmapped": [s.source_column for s in suggestions if not s.target_field],
        "low_confidence": [
            s.source_column for s in suggestions if s.target_field and s.confidence < 0.9
        ],
        "fields": [{"name": f["name"], "label": f["label"]} for f in CANONICAL_FIELDS],
    }


def apply_mapping(row: dict, mapping: dict[str, str]) -> dict:
    """Project a raw row onto canonical field names."""
    projected: dict[str, str] = {}
    for source_column, value in row.items():
        field = mapping.get(source_column)
        if not field:
            continue
        text = "" if value is None else str(value)
        if field in projected and projected[field]:
            continue  # first non-empty mapping wins
        projected[field] = text
    return projected
