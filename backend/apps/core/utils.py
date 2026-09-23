"""Small, dependency-free helpers shared by every app."""
from __future__ import annotations

import hashlib
import re
from typing import Iterable

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^a-z0-9]+")
_NON_DIGIT_RE = re.compile(r"\D+")

TITLE_CASE_SMALL = {
    "a", "an", "and", "as", "at", "but", "by", "for", "in", "nor", "of", "on",
    "or", "the", "to", "up", "via", "with",
}

COMPANY_SUFFIXES = {
    "inc": "Inc", "inc.": "Inc", "llc": "LLC", "l.l.c.": "LLC", "llp": "LLP",
    "ltd": "Ltd", "ltd.": "Ltd", "limited": "Limited", "co": "Co", "co.": "Co",
    "corp": "Corp", "corp.": "Corp", "corporation": "Corporation", "plc": "PLC",
    "gmbh": "GmbH", "s.a.": "S.A.", "pte": "Pte", "pty": "Pty", "bv": "BV",
    "group": "Group", "holdings": "Holdings", "partners": "Partners",
    "associates": "Associates", "services": "Services", "solutions": "Solutions",
    "company": "Company", "the": "The",
}

US_STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}
US_STATE_ABBR = set(US_STATE_NAMES.values())


def clean_text(value) -> str:
    """Collapse whitespace, strip, and return '' for None/NaN."""
    if value is None:
        return ""
    if value != value:  # NaN (pandas / float('nan'))
        return ""
    text = str(value).replace("\u00a0", " ").strip()
    if text.lower() in {"nan", "none", "null", "n/a", "na", "-", "--", "#n/a"}:
        return ""
    return _WS_RE.sub(" ", text)


def normalize_key(value: str) -> str:
    """Aggressive normalization used for matching keys (company names, cities)."""
    text = clean_text(value).lower()
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def normalize_company_name(value: str) -> str:
    """Readable canonical company name: one space between words, tidy casing."""
    text = clean_text(value)
    if not text:
        return ""
    text = _WS_RE.sub(" ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    parts = []
    for i, word in enumerate(text.split(" ")):
        lower = word.lower()
        if lower in COMPANY_SUFFIXES:
            parts.append(COMPANY_SUFFIXES[lower])
        elif word.isupper() and len(word) <= 4 and lower in US_STATE_ABBR:
            parts.append(word.upper())
        elif word.isalpha() and word.isupper() and len(word) > 3:
            parts.append(word.capitalize())  # "DETAILING" -> "Detailing"
        elif i > 0 and lower in TITLE_CASE_SMALL and word.islower():
            parts.append(lower)
        elif lower in TITLE_CASE_SMALL and i == 0:
            parts.append(word.capitalize())
        elif word[:1].isdigit() and word.upper() == word:
            parts.append(word)
        else:
            parts.append(word[:1].upper() + word[1:] if word else word)
    return " ".join(parts)


def normalize_person_name(value: str) -> str:
    """Title-case a person name while preserving particles (de, van, bin, ...)."""
    text = clean_text(value)
    if not text:
        return ""
    keep_lower = {"de", "del", "della", "der", "van", "von", "da", "di", "la", "le",
                  "bin", "ibn", "al", "st", "st."}
    out = []
    for i, part in enumerate(_WS_RE.sub(" ", text).split(" ")):
        if not part:
            continue
        if part.lower() in keep_lower and i > 0:
            out.append(part.lower())
        elif re.match(r"^[A-Za-z]+[-'][A-Za-z]+$", part):
            out.append("-".join(p.capitalize() for p in re.split(r"([-'])", part)))
        else:
            out.append(part[:1].upper() + part[1:].lower() if part.isalpha() else part)
    return " ".join(out)


def split_full_name(full_name: str) -> tuple[str, str]:
    """Return (first_name, last_name) from a full name string."""
    text = clean_text(full_name)
    if not text:
        return "", ""
    if "," in text:  # "Doe, John"
        last, _, first = text.partition(",")
        return clean_text(first), clean_text(last)
    parts = text.split(" ")
    if len(parts) == 1:
        return parts[0], ""
    if len(parts) == 2:
        return parts[0], parts[1]
    # Drop suffixes like Jr / III
    if parts[-1].lower().rstrip(".") in {"jr", "sr", "ii", "iii", "iv", "v", "phd", "md"}:
        parts = parts[:-1]
    return parts[0], " ".join(parts[1:])


def digits_only(value: str) -> str:
    return _NON_DIGIT_RE.sub("", clean_text(value))


def normalize_state(value: str) -> str:
    """Return the 2-letter US state code when recognizable, else a title-cased value."""
    text = clean_text(value)
    if not text:
        return ""
    if len(text) <= 3 and text.upper() in US_STATE_ABBR:
        return text.upper()
    lowered = text.lower().strip(".")
    if lowered in US_STATE_NAMES:
        return US_STATE_NAMES[lowered]
    return text.title() if text.isupper() or text.islower() else text


def normalize_city(value: str) -> str:
    text = clean_text(value)
    if not text:
        return ""
    return text.title() if text.isupper() or text.islower() else text


def normalize_zip(value: str) -> str:
    text = clean_text(value)
    if not text:
        return ""
    digits = digits_only(text.split("-")[0])
    if len(digits) == 4 and digits.isdigit():  # 1234 -> 01234
        return digits.zfill(5)
    if len(digits) == 9:
        return f"{digits[:5]}-{digits[5:]}"
    return text.upper() if any(c.isalpha() for c in text) else digits or text


def token_set(value: str) -> frozenset[str]:
    return frozenset(normalize_key(value).split())


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def batched(iterable, size: int):
    """Yield lists of at most `size` items (stdlib chunking helper)."""
    batch: list = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
