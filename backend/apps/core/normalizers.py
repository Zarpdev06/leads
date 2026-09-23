"""
Data normalization.

Every value that enters the platform goes through these functions so that
"ABC Auto Detailing ", "abc auto detailing," and "ABC AUTO DETAILING" all
collapse to one canonical key, and so deduplication & eligibility have
something stable to work with.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


from .utils import (
    clean_text,
    digits_only,
    normalize_city,
    normalize_company_name,
    normalize_key,
    normalize_person_name,
    normalize_state,
    normalize_zip,
)

# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[A-Za-z]{2,}$")
OBFUSCATION = {
    " at ": "@", " [at] ": "@", "(at)": "@", "{at}": "@", " AT ": "@",
    " dot ": ".", " [dot] ": ".", "(dot)": ".", "{dot}": ".", " DOT ": ".",
}
DOMAIN_TYPOS = {
    "gmial.com": "gmail.com", "gmai.com": "gmail.com", "gmail.co": "gmail.com",
    "gmail.con": "gmail.com", "gnail.com": "gmail.com", "gmail.cm": "gmail.com",
    "hotmial.com": "hotmail.com", "hotmai.com": "hotmail.com",
    "hotmail.co": "hotmail.com", "hotmial.co.uk": "hotmail.co.uk",
    "yaho.com": "yahoo.com", "yahooo.com": "yahoo.com", "yahoo.co": "yahoo.com",
    "outlok.com": "outlook.com", "outllook.com": "outlook.com",
    "iclould.com": "icloud.com", "icloud.co": "icloud.com",
    "comcast.nrt": "comcast.net", "verison.net": "verizon.net",
    "att.ent": "att.net", "msm.com": "msn.com", "me.cpm": "me.com",
}
ROLE_MAILBOXES = {
    "info", "sales", "support", "admin", "contact", "contacts", "hello", "hi",
    "office", "help", "service", "services", "team", "enquiries", "inquiry",
    "billing", "accounts", "accounting", "marketing", "noreply", "no-reply",
    "donotreply", "postmaster", "webmaster", "mail", "mailbox", "reception",
    "frontdesk", "careers", "jobs", "hr", "orders", "customerservice", "cs",
}
DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "yopmail.com", "trashmail.com", "sharklasers.com", "throwawaymail.com",
    "getnada.com", "temp-mail.org", "fakeinbox.com", "maildrop.cc",
    "dispostable.com", "mailnesia.com", "mintemail.com", "mytrashmail.com",
}
FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "me.com", "protonmail.com", "proton.me", "gmx.com",
    "mail.com", "zoho.com", "yandex.com", "live.com", "msn.com", "comcast.net",
    "verizon.net", "att.net", "sbcglobal.net", "bellsouth.net", "cox.net",
    "earthlink.net", "charter.net", "optonline.net",
}

# --------------------------------------------------------------------------
# Website
# --------------------------------------------------------------------------
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_reader", "utm_social", "utm_brand", "gclid",
    "fbclid", "msclkid", "mc_eid", "mc_cid", "igshid", "ref", "ref_src",
    "ref_url", "referrer", "source", "sourceid", "yclid", "_ga", "_gl",
    "si", "feature", "spm", "trk", "trkCampaign", "vero_id", "vero_conv",
}
SOCIAL_DOMAINS = {
    "facebook.com", "m.facebook.com", "www.facebook.com", "fb.com",
    "instagram.com", "www.instagram.com", "linkedin.com", "www.linkedin.com",
    "twitter.com", "x.com", "www.twitter.com", "youtube.com", "www.youtube.com",
    "tiktok.com", "pinterest.com", "yelp.com", "www.yelp.com", "yellowpages.com",
    "manta.com", "bbb.org", "mapquest.com", "nextdoor.com", "angi.com",
    "thumbtack.com", "houzz.com", "alignable.com", "birdeye.com",
}


@dataclass(frozen=True)
class EmailResult:
    raw: str
    normalized: str
    is_valid: bool
    is_role: bool
    is_disposable: bool
    is_free_provider: bool
    domain: str
    reason: str


def normalize_email(raw: str) -> EmailResult:
    """Lowercase, trim, de-obfuscate, fix obvious typos and validate syntax."""
    text = clean_text(raw)
    if not text:
        return EmailResult("", "", False, False, False, False, "", "missing")

    lowered = text.lower()
    for token, replacement in OBFUSCATION.items():
        if token in lowered:
            lowered = lowered.replace(token, replacement)

    # "John Doe <john@x.com>" -> extract the address before stripping spaces,
    # otherwise the name and the address get glued together.
    match = re.search(r"<([^>]+)>", lowered)
    if match:
        lowered = match.group(1)
    cleaned = re.sub(r"\s+", "", lowered)
    cleaned = re.sub(r"^mailto:", "", cleaned)
    cleaned = cleaned.strip("<>()[]{}'\";,")
    cleaned = re.sub(r",+", ",", cleaned)
    # Multiple addresses in one cell: keep the first one.
    for sep in (",", ";", "/", "|"):
        if sep in cleaned:
            candidates = [c for c in cleaned.split(sep) if "@" in c]
            if candidates:
                cleaned = candidates[0]
                break
    cleaned = cleaned.strip(".,;:")
    cleaned = re.sub(r"\.+(?=[^@]*@)", ".", cleaned)  # john..doe@ -> john.doe@
    cleaned = cleaned.lstrip(".")

    if "@" not in cleaned:
        return EmailResult(text, cleaned, False, False, False, False, "", "no-at-sign")

    local, _, domain = cleaned.partition("@")
    domain = domain.strip(".,")
    domain = DOMAIN_TYPOS.get(domain, domain)
    local = local.strip(".")
    normalized = f"{local}@{domain}".lower()

    is_valid = bool(EMAIL_RE.match(normalized)) and not normalized.endswith((".con", ".cm"))
    local_key = local.split("+")[0]
    mailbox = re.sub(r"\d+$", "", local_key)
    return EmailResult(
        raw=text,
        normalized=normalized,
        is_valid=is_valid,
        is_role=local_key in ROLE_MAILBOXES or mailbox in ROLE_MAILBOXES,
        is_disposable=domain in DISPOSABLE_DOMAINS,
        is_free_provider=domain in FREE_EMAIL_DOMAINS,
        domain=domain,
        reason="" if is_valid else "invalid-syntax",
    )


def normalize_phone(raw: str, default_country: str = "US") -> tuple[str, str]:
    """Return (display_number, digits/E164-ish key).

    Uses `phonenumbers` when installed (accurate international formatting);
    otherwise falls back to a conservative NA-focused implementation.
    """
    text = clean_text(raw)
    if not text:
        return "", ""
    text = text.split(";")[0].split(",")[0]
    text = re.sub(r"^\+?\s*", "", text)
    ext = ""
    ext_match = re.search(r"(?:x|ext\.?|extension)\s*(\d{1,6})$", text, flags=re.I)
    if ext_match:
        ext = ext_match.group(1)
        text = text[: ext_match.start()]

    try:  # pragma: no cover - optional dependency
        import phonenumbers  # type: ignore

        parsed = phonenumbers.parse(text, default_country)
        if phonenumbers.is_valid_number(parsed):
            e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            display = phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL
            )
            return display, e164
        digits = digits_only(text)
    except Exception:
        digits = digits_only(text)

    if not digits:
        return "", ""
    if default_country == "US":
        if len(digits) == 10:
            digits = "1" + digits
        elif len(digits) == 11 and digits.startswith("1"):
            pass
        elif len(digits) == 7:  # local number, no area code: keep as-is, no E164
            return text, digits
        if len(digits) == 11 and digits.startswith("1"):
            display = f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
            display += f" x{ext}" if ext else ""
            return display, "+" + digits
    display = f"+{digits}"
    if ext:
        display += f" x{ext}"
    return display, "+" + digits


@dataclass(frozen=True)
class WebsiteResult:
    raw: str
    normalized: str          # https://example.com/path
    domain: str              # example.com  (www stripped, lowercase)
    registrable: str         # best-effort registrable domain (example.co.uk -> example.co.uk)
    is_social: bool
    is_valid: bool


def normalize_website(raw: str) -> WebsiteResult:
    """Add protocol, lowercase host, drop www., strip tracking params."""
    text = clean_text(raw)
    if not text:
        return WebsiteResult("", "", "", "", False, False)
    if text.lower() in {"none", "n/a", "-", "no website"}:
        return WebsiteResult(text, "", "", "", False, False)

    lowered = text.lower().strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", lowered):
        lowered = "https://" + lowered.lstrip("/")
    lowered = re.sub(r"^http://", "https://", lowered)

    try:
        parts = urlsplit(lowered)
    except ValueError:
        return WebsiteResult(text, "", "", "", False, False)

    host = (parts.hostname or "").lower().rstrip(".")
    if not host or "." not in host:
        return WebsiteResult(text, "", "", "", False, False)

    host = re.sub(r"^www\.", "", host)
    if any(ch in host for ch in (" ", "\t")):
        return WebsiteResult(text, "", "", "", False, False)

    query_pairs = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(query_pairs)
    path = re.sub(r"/+$", "", parts.path or "")
    normalized = urlunsplit(("https", host, path, query, ""))
    registrable = _registrable_domain(host)
    return WebsiteResult(
        raw=text,
        normalized=normalized or f"https://{host}",
        domain=host,
        registrable=registrable,
        is_social=host in SOCIAL_DOMAINS or registrable in SOCIAL_DOMAINS,
        is_valid=True,
    )


_TWO_LEVEL_TLDS = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au",
    "co.nz", "com.br", "com.mx", "co.za", "com.sg", "com.hk", "co.in",
    "co.jp", "com.tr", "com.tw", "co.kr", "com.cn", "com.ar",
}


def _registrable_domain(host: str) -> str:
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    if ".".join(labels[-2:]) in _TWO_LEVEL_TLDS and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def normalize_address(street: str = "", city: str = "", state: str = "",
                      zip_code: str = "", country: str = "") -> dict:
    """Canonicalize address parts (whitespace, case, ZIP, state codes)."""
    street_clean = re.sub(r"\s+", " ", clean_text(street)).strip(" ,")
    return {
        "street_address": street_clean,
        "city": normalize_city(city),
        "state": normalize_state(state),
        "zip_code": normalize_zip(zip_code),
        "country": normalize_country(country),
    }


COUNTRY_ALIASES = {
    "usa": "United States", "u.s.a.": "United States", "us": "United States",
    "u.s.": "United States", "united states of america": "United States",
    "america": "United States", "uk": "United Kingdom", "gb": "United Kingdom",
    "great britain": "United Kingdom", "ca": "Canada", "can": "Canada",
    "au": "Australia", "nz": "New Zealand", "in": "India", "de": "Germany",
}


def normalize_country(value: str) -> str:
    text = clean_text(value)
    if not text:
        return ""
    key = normalize_key(text)
    if key in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[key]
    if len(text) == 2:
        return text.upper()
    return text.title() if text.islower() or text.isupper() else text


def normalize_employee_count(value) -> int | None:
    """'51-200 employees', '1,200', '10+' -> integer (lower bound of a range)."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and value == value:
        return int(value)
    text = clean_text(value).lower()
    if not text:
        return None
    text = text.replace("employees", "").replace("employee", "").strip()
    numbers = re.findall(r"\d[\d,\. ]*\d|\d", text)
    if not numbers:
        return None
    first = int(re.sub(r"[^\d]", "", numbers[0]))
    return first


def company_key(name: str, city: str = "", state: str = "") -> str:
    """Blocking key used by the dedupe engine."""
    base = normalize_key(name)
    if not base:
        return ""
    return "|".join([base, normalize_key(city), normalize_key(state)])


class NormalizedRecord(dict):
    """Dict subclass with attribute access - handy in templates/services."""

    def __getattr__(self, item):  # pragma: no cover - convenience
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


__all__ = [
    "EmailResult", "WebsiteResult", "normalize_email", "normalize_phone",
    "normalize_website", "normalize_address", "normalize_country",
    "normalize_employee_count", "normalize_key", "normalize_company_name",
    "normalize_person_name", "company_key", "ROLE_MAILBOXES",
    "DISPOSABLE_DOMAINS", "FREE_EMAIL_DOMAINS", "clean_text",
]
