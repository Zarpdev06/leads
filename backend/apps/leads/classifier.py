"""
Industry / niche classification.

Three cooperating strategies, cheapest first:
  1. Explicit source metadata (the folder / file name, e.g.
     "Automotive_in_Chicago_Illinois.csv" or a source category "Auto Detailing").
  2. Rule matching against `Industry.keywords` (configurable in admin).
  3. Keyword inference over the company name + website text.

The classifier never guesses a niche it cannot justify: if nothing matches it
returns (None, None, 0.0) and the lead simply stays uncategorized.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from apps.core.utils import normalize_key

from .models import Industry

# Fallback taxonomy used to seed `Industry` rows on a fresh install.
SEED_TAXONOMY: dict[str, list[str]] = {
    "Automotive": ["Auto Repair", "Auto Detailing", "Car Dealership", "Towing",
                   "Auto Body Shop", "Tire Shop", "Car Wash", "Motorcycle Repair"],
    "Health & Wellness": ["Chiropractors", "Dentists", "Physical Therapy", "Optometrists",
                          "Med Spa", "Veterinary", "Pharmacy", "Gyms & Fitness"],
    "Professional Services": ["Accountants", "Architects", "Law Firms", "Consultants",
                              "Insurance Agencies", "Marketing Agencies", "Staffing"],
    "Home Services": ["Plumbing", "HVAC", "Electrical", "Roofing", "Landscaping",
                      "Cleaning Services", "Pest Control", "Painting", "Remodeling"],
    "Food & Hospitality": ["Restaurants", "Cafes", "Coffee Shops", "Bakeries",
                           "Catering", "Bars", "Hotels"],
    "Real Estate": ["Real Estate Agents", "Property Management", "Mortgage Brokers",
                    "Commercial Real Estate"],
    "Retail": ["Boutiques", "Ecommerce", "Grocery", "Furniture", "Electronics"],
    "Construction": ["General Contractors", "Concrete", "Flooring", "Fencing"],
    "Beauty & Personal Care": ["Hair Salons", "Barbers", "Nail Salons", "Spas"],
    "Education": ["Tutoring", "Childcare", "Training", "Schools"],
    "Technology": ["Software Companies", "IT Services", "Managed Service Providers"],
    "Finance": ["Financial Advisors", "Bookkeeping", "Tax Services"],
    "Logistics": ["Freight", "Courier", "Warehousing"],
    "Manufacturing": ["Fabrication", "Printing", "Food Manufacturing"],
    "Nonprofit": ["Charities", "Religious Organizations"],
}

# keyword -> (industry, sub industry) inference table (lowercased keywords)
INFERENCE_RULES: list[tuple[str, str, str]] = [
    ("auto detailing", "Automotive", "Auto Detailing"),
    ("detailing", "Automotive", "Auto Detailing"),
    ("auto repair", "Automotive", "Auto Repair"),
    ("collision", "Automotive", "Auto Body Shop"),
    ("body shop", "Automotive", "Auto Body Shop"),
    ("tire", "Automotive", "Tire Shop"),
    ("car wash", "Automotive", "Car Wash"),
    ("dealership", "Automotive", "Car Dealership"),
    ("chiroprac", "Health & Wellness", "Chiropractors"),
    ("dental", "Health & Wellness", "Dentists"),
    ("dentist", "Health & Wellness", "Dentists"),
    ("physical therapy", "Health & Wellness", "Physical Therapy"),
    ("optometr", "Health & Wellness", "Optometrists"),
    ("med spa", "Health & Wellness", "Med Spa"),
    ("veterinar", "Health & Wellness", "Veterinary"),
    ("animal hospital", "Health & Wellness", "Veterinary"),
    ("accounting", "Professional Services", "Accountants"),
    ("accountant", "Professional Services", "Accountants"),
    ("cpa", "Professional Services", "Accountants"),
    ("bookkeep", "Finance", "Bookkeeping"),
    ("architect", "Professional Services", "Architects"),
    ("law firm", "Professional Services", "Law Firms"),
    ("attorney", "Professional Services", "Law Firms"),
    ("insurance", "Professional Services", "Insurance Agencies"),
    ("consulting", "Professional Services", "Consultants"),
    ("consultant", "Professional Services", "Consultants"),
    ("marketing agency", "Professional Services", "Marketing Agencies"),
    ("plumb", "Home Services", "Plumbing"),
    ("hvac", "Home Services", "HVAC"),
    ("heating and air", "Home Services", "HVAC"),
    ("electric", "Home Services", "Electrical"),
    ("roofing", "Home Services", "Roofing"),
    ("landscap", "Home Services", "Landscaping"),
    ("lawn care", "Home Services", "Landscaping"),
    ("cleaning service", "Home Services", "Cleaning Services"),
    ("pest control", "Home Services", "Pest Control"),
    ("painting", "Home Services", "Painting"),
    ("remodel", "Home Services", "Remodeling"),
    ("restaurant", "Food & Hospitality", "Restaurants"),
    ("cafe", "Food & Hospitality", "Cafes"),
    ("coffee", "Food & Hospitality", "Coffee Shops"),
    ("bakery", "Food & Hospitality", "Bakeries"),
    ("catering", "Food & Hospitality", "Catering"),
    ("hotel", "Food & Hospitality", "Hotels"),
    ("real estate", "Real Estate", "Real Estate Agents"),
    ("realtor", "Real Estate", "Real Estate Agents"),
    ("property management", "Real Estate", "Property Management"),
    ("mortgage", "Real Estate", "Mortgage Brokers"),
    ("salon", "Beauty & Personal Care", "Hair Salons"),
    ("barber", "Beauty & Personal Care", "Barbers"),
    ("nail", "Beauty & Personal Care", "Nail Salons"),
    ("spa", "Beauty & Personal Care", "Spas"),
    ("gym", "Health & Wellness", "Gyms & Fitness"),
    ("fitness", "Health & Wellness", "Gyms & Fitness"),
    ("tutor", "Education", "Tutoring"),
    ("childcare", "Education", "Childcare"),
    ("daycare", "Education", "Childcare"),
    ("software", "Technology", "Software Companies"),
    ("it services", "Technology", "IT Services"),
    ("managed service", "Technology", "Managed Service Providers"),
    ("contractor", "Construction", "General Contractors"),
    ("concrete", "Construction", "Concrete"),
    ("flooring", "Construction", "Flooring"),
    ("financial advisor", "Finance", "Financial Advisors"),
    ("tax service", "Finance", "Tax Services"),
    ("freight", "Logistics", "Freight"),
    ("courier", "Logistics", "Courier"),
    ("warehouse", "Logistics", "Warehousing"),
    ("printing", "Manufacturing", "Printing"),
    ("fabricat", "Manufacturing", "Fabrication"),
    ("boutique", "Retail", "Boutiques"),
    ("furniture", "Retail", "Furniture"),
    ("grocery", "Retail", "Grocery"),
    ("store", "Retail", "Boutiques"),
]

# Location words that must never be mistaken for an industry.
STOP_WORDS = {"llc", "inc", "company", "co", "the", "and", "group", "services",
              "service", "solutions", "national", "usa", "america"}


@dataclass
class Classification:
    industry: Industry | None
    sub_industry: Industry | None
    confidence: float
    method: str

    def as_dict(self) -> dict:
        return {
            "industry_id": self.industry_id if self.industry else None,
            "industry": self.industry.name if self.industry else "",
            "sub_industry_id": self.sub_industry_id if self.sub_industry else None,
            "sub_industry": self.sub_industry.name if self.sub_industry else "",
            "confidence": round(self.confidence, 2),
            "method": self.method,
        }

    @property
    def industry_id(self):  # pragma: no cover - convenience
        return self.industry.pk if self.industry else None

    @property
    def sub_industry_id(self):  # pragma: no cover - convenience
        return self.sub_industry.pk if self.sub_industry else None


@lru_cache(maxsize=1)
def _industry_index() -> tuple[dict[str, Industry], dict[str, Industry]]:
    """(by_name_key, by_keyword) lookups, cached per process."""
    by_name: dict[str, Industry] = {}
    by_keyword: dict[str, Industry] = {}
    for industry in Industry.objects.filter(is_active=True).select_related("parent"):
        by_name.setdefault(normalize_key(industry.name), industry)
        for keyword in industry.keywords or []:
            by_keyword.setdefault(normalize_key(keyword), industry)
    return by_name, by_keyword


def clear_industry_cache() -> None:
    _industry_index.cache_clear()


def _lookup_pair(industry_name: str, sub_industry_name: str) -> Classification | None:
    by_name, _ = _industry_index()
    industry = by_name.get(normalize_key(industry_name))
    sub = by_name.get(normalize_key(sub_industry_name)) if sub_industry_name else None
    if industry is None and sub is not None and sub.parent_id:
        industry = sub.parent
    if sub is None and industry is not None and industry.parent_id:
        industry, sub = industry.parent, industry
    if industry is None and sub is None:
        return None
    return Classification(industry, sub, 0.95, "taxonomy")


def classify_from_source(source_category: str = "", source_name: str = "",
                         source_city: str = "") -> Classification | None:
    """Folder/file names such as "Automotive_in_Chicago_Illinois.csv"."""
    text = f"{source_category} {source_name}".strip()
    if not text:
        return None
    # "Automotive_in_Chicago_Illinois" -> "Automotive in Chicago Illinois"
    cleaned = re.sub(r"[_\-/]+", " ", text)
    cleaned = re.sub(r"\.(csv|xlsx|xls)$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(in|of|and|the)\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    _, by_keyword = _industry_index()
    by_name, _ = _industry_index()

    # Longest keyword match wins ("auto detailing" before "detailing").
    key = normalize_key(cleaned)
    best = None
    for industry in Industry.objects.filter(is_active=True).select_related("parent"):
        name_key = normalize_key(industry.name)
        if name_key and (name_key == key or f" {name_key} " in f" {key} "):
            if best is None or len(name_key) > len(normalize_key(best.name)):
                best = industry
    if best is not None:
        if best.parent_id:
            return Classification(best.parent, best, 0.9, "source-metadata")
        return Classification(best, None, 0.9, "source-metadata")
    return None


def classify_text(*parts: str) -> Classification | None:
    """Keyword inference over company name / website / description text."""
    blob = normalize_key(" ".join(p for p in parts if p))
    if not blob:
        return None
    for keyword, industry_name, sub_name in INFERENCE_RULES:
        if keyword in blob:
            result = _lookup_pair(industry_name, sub_name)
            if result:
                return Classification(result.industry, result.sub_industry, 0.75, "keyword")
    # Second pass: configured keywords on Industry rows.
    _, by_keyword = _industry_index()
    best: tuple[int, Industry] | None = None
    for keyword, industry in by_keyword.items():
        if keyword and keyword in blob:
            if best is None or len(keyword) > best[0]:
                best = (len(keyword), industry)
    if best:
        industry = best[1]
        if industry.parent_id:
            return Classification(industry.parent, industry, 0.6, "keyword-config")
        return Classification(industry, None, 0.6, "keyword-config")
    return None


def classify_company(company_name: str = "", website: str = "", description: str = "",
                     source_category: str = "", source_name: str = "") -> Classification:
    """Run every strategy and return the best classification (or an empty one)."""
    result = classify_from_source(source_category, source_name)
    if result is None:
        result = classify_text(company_name, description)
    if result is None and website:
        domain = re.sub(r"^https?://(www\.)?", "", website).split("/")[0]
        domain_words = re.split(r"[-.]", domain)
        domain_words = [w for w in domain_words if w not in STOP_WORDS and len(w) > 2]
        result = classify_text(" ".join(domain_words))
        if result:
            result.confidence = 0.5
            result.method = "domain"
    return result or Classification(None, None, 0.0, "none")


def seed_industries(*, reset: bool = False) -> int:
    """Create the starter taxonomy (idempotent)."""
    created = 0
    for industry_name, sub_names in SEED_TAXONOMY.items():
        industry, new = Industry.objects.get_or_create(
            parent=None, name=industry_name,
            defaults={"slug": _slugify_unique(industry_name)},
        )
        created += int(new)
        for sub_name in sub_names:
            sub, new = Industry.objects.get_or_create(
                parent=industry, name=sub_name,
                defaults={"slug": _slugify_unique(f"{industry_name}-{sub_name}")},
            )
            created += int(new)
    clear_industry_cache()
    return created


def _slugify_unique(value: str) -> str:
    from django.utils.text import slugify

    base = slugify(value)[:190] or "industry"
    slug, index = base, 1
    while Industry.objects.filter(slug=slug).exists():
        index += 1
        slug = f"{base}-{index}"
    return slug
