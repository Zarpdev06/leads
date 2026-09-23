"""Column mapping engine: aliases, fuzzy matching and value-shape inference."""
from apps.imports.mapping import (
    auto_map,
    sniff_column,
    suggest_mapping,
)


def test_exact_and_alias_mapping():
    headers = ["Business Name", "Contact Person", "First Name", "Corporate Email",
               "Website", "Phone", "Street Address", "Zip Code", "State", "City"]
    result = auto_map(headers)
    mapping = result["mapping"]
    assert mapping["Business Name"] == "company_name"
    assert mapping["Contact Person"] == "contact_name"
    assert mapping["First Name"] == "first_name"
    assert mapping["Corporate Email"] == "email"
    assert mapping["Website"] == "website"
    assert mapping["Phone"] == "phone"
    assert mapping["Street Address"] == "street_address"
    assert mapping["Zip Code"] == "zip_code"
    assert mapping["State"] == "state"
    assert mapping["City"] == "city"
    assert result["unmapped"] == []


def test_alternative_aliases():
    headers = ["Company", "Owner Name", "E-mail", "URL", "Telephone", "Address",
               "Postal Code", "State", "City"]
    mapping = auto_map(headers)["mapping"]
    assert mapping["Company"] == "company_name"
    assert mapping["Owner Name"] == "contact_name"
    assert mapping["E-mail"] == "email"
    assert mapping["URL"] == "website"
    assert mapping["Telephone"] == "phone"
    assert mapping["Address"] == "street_address"
    assert mapping["Postal Code"] == "zip_code"


def test_fuzzy_mapping_tolerates_typos():
    headers = ["Busines Name", "Email Adress", "WebSite Url"]
    mapping = auto_map(headers)["mapping"]
    assert mapping["Busines Name"] == "company_name"
    assert mapping["Email Adress"] == "email"
    assert mapping["WebSite Url"] == "website"


def test_semantic_mapping_from_values():
    """Unknown column names are mapped from the shape of the data."""
    headers = ["col_a", "col_b", "col_c"]
    rows = [
        {"col_a": "a@acme.com", "col_b": "https://acme.com", "col_c": "(214) 555-0100"},
        {"col_a": "b@bravo.com", "col_b": "https://bravo.com", "col_c": "972-555-0199"},
        {"col_a": "c@cafe.com", "col_b": "https://cafe.com", "col_c": "469-555-0111"},
        {"col_a": "d@diner.com", "col_b": "https://diner.com", "col_c": "214-555-0188"},
    ]
    mapping = auto_map(headers, rows)["mapping"]
    assert mapping["col_a"] == "email"
    assert mapping["col_b"] == "website"
    assert mapping["col_c"] == "phone"


def test_sniff_zip_and_state():
    assert sniff_column(["75201", "75001", "73301", "78701"])[0] == "zip_code"
    assert sniff_column(["TX", "CA", "FL", "NY"])[0] == "state"


def test_confidence_and_method_reported():
    suggestions = suggest_mapping(["Business Name", "Mystery Column"])
    by_column = {s.source_column: s for s in suggestions}
    assert by_column["Business Name"].confidence >= 0.9
    assert by_column["Business Name"].method in {"exact", "alias", "normalized"}
    assert by_column["Mystery Column"].target_field is None


def test_unmapped_columns_are_reported():
    result = auto_map(["Business Name", "Internal Ref Code"])
    assert "Internal Ref Code" in result["unmapped"]
