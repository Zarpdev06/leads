"""Normalization: emails, phones, websites, names, addresses."""
import pytest

from apps.core.normalizers import (
    normalize_address,
    normalize_company_name,
    normalize_email,
    normalize_employee_count,
    normalize_person_name,
    normalize_phone,
    normalize_website,
)
from apps.core.utils import normalize_key, normalize_state, normalize_zip, split_full_name


@pytest.mark.parametrize("raw,expected", [
    ("  John@Example.COM ", "john@example.com"),
    ("john [at] example [dot] com", "john@example.com"),
    ("John Doe <john.doe@example.com>", "john.doe@example.com"),
    ("mailto:SALES@ACME.CO.UK", "sales@acme.co.uk"),
    ("john@gmial.com", "john@gmail.com"),
    ("john.doe@example.com, jane@example.com", "john.doe@example.com"),
])
def test_email_normalization(raw, expected):
    assert normalize_email(raw).normalized == expected


@pytest.mark.parametrize("raw,valid", [
    ("john@example.com", True),
    ("john.doe+tag@sub.example.co.uk", True),
    ("not-an-email", False),
    ("john@", False),
    ("@example.com", False),
    ("", False),
])
def test_email_validity(raw, valid):
    assert normalize_email(raw).is_valid is valid


def test_email_role_and_free_detection():
    assert normalize_email("info@acme.com").is_role is True
    assert normalize_email("john.smith@acme.com").is_role is False
    assert normalize_email("john@gmail.com").is_free_provider is True
    assert normalize_email("john@acmecorp.com").is_free_provider is False


@pytest.mark.parametrize("raw,expected_key", [
    ("(214) 555-0100", "+12145550100"),
    ("214-555-0100", "+12145550100"),
    ("+1 214 555 0100", "+12145550100"),
    ("214.555.0100 x22", "+12145550100"),
])
def test_phone_normalization(raw, expected_key):
    display, key = normalize_phone(raw)
    assert key == expected_key
    assert display.startswith("+1")


def test_phone_empty():
    assert normalize_phone("") == ("", "")


@pytest.mark.parametrize("raw,host", [
    ("www.Example.com/", "example.com"),
    ("https://example.com/path/?utm_source=x&fbclid=1", "example.com"),
    ("http://sub.example.com/a#frag", "sub.example.com"),
    ("example.com", "example.com"),
])
def test_website_normalization(raw, host):
    result = normalize_website(raw)
    assert result.domain == host
    assert result.normalized.startswith("https://")
    assert "utm_source" not in result.normalized


def test_website_social_detection():
    assert normalize_website("https://facebook.com/pages/abc").is_social is True
    assert normalize_website("https://acme.com").is_social is False


def test_company_and_person_names():
    assert normalize_company_name("  abc   auto DETAILING llc ") == "Abc Auto Detailing LLC"
    assert normalize_person_name("JOHN VAN DERBERG") == "John van Derberg"
    assert normalize_company_name("Auto Detailing, Inc.") == "Auto Detailing, Inc"


def test_name_splitting():
    assert split_full_name("John Smith") == ("John", "Smith")
    assert split_full_name("Smith, John") == ("John", "Smith")
    assert split_full_name("Ana Maria Torres Jr") == ("Ana", "Maria Torres")


def test_address_normalization():
    result = normalize_address("  1200  main   st ", "dallas", "texas", "1234", "usa")
    assert result["street_address"] == "1200 main st"
    assert result["city"] == "Dallas"
    assert result["state"] == "TX"
    assert result["zip_code"] == "01234"
    assert result["country"] == "United States"


def test_state_and_zip():
    assert normalize_state("texas") == "TX"
    assert normalize_state("TX") == "TX"
    assert normalize_zip("752011234") == "75201-1234"
    assert normalize_key("ABC Auto Detailing!!") == "abc auto detailing"


@pytest.mark.parametrize("raw,expected", [
    ("51-200", 51), ("1,200", 1200), ("12 employees", 12), ("", None), (None, None),
])
def test_employee_count(raw, expected):
    assert normalize_employee_count(raw) == expected
