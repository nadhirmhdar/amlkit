"""Test p45: STR builder auto-populates from org profile.

After p46, goAML XML "reporting entity" section should use operator's saved
org profile rather than hardcoded "Grovisor Consultants" fallback.
"""
from amlkit.db import connect
from amlkit.reporting.goaml import serialize_goaml_xml


def test_goaml_uses_org_profile_when_available():
    """goAML XML should use org profile fields when present in report_data."""

    report_data = {
        "report_type": "STR",
        "entity_reference": "TEST-STR-001",
        "reporting_entity_name": "Dubai Compliance Services LLC",
        "reporting_entity_branch": "Dubai Internet City Branch",
        "reporter_name": "Ahmed Al Mansoori",
        "reporter_email": "ahmed@dcservices.ae",
        # Minimal subject details to pass validation
        "first_name": "Test",
        "last_name": "Customer",
        "customer_type": "natural"
    }

    xml = serialize_goaml_xml(report_data)

    # Should use org profile, not hardcoded fallback
    assert "Dubai Compliance Services LLC" in xml
    assert "Grovisor Consultants" not in xml  # Old hardcoded fallback
    assert "Dubai Internet City Branch" in xml


def test_goaml_falls_back_to_hardcoded_when_profile_missing():
    """goAML XML should use hardcoded defaults when org profile not in report_data."""

    report_data = {
        "report_type": "STR",
        "entity_reference": "TEST-STR-002",
        "reporter_name": "John Doe",
        "reporter_email": "john@example.com",
        # Minimal subject details
        "first_name": "Jane",
        "last_name": "Smith",
        "customer_type": "natural"
    }

    xml = serialize_goaml_xml(report_data)

    # Should fall back to hardcoded defaults
    assert "Grovisor Consultants" in xml  # Current hardcoded fallback
    assert "Dubai HQ" in xml


def test_org_profile_fields_in_database():
    """Verify org profile fields exist and can be queried."""
    db = connect(":memory:")

    # Create org with profile
    db.execute("""
        INSERT INTO organizations (
            name, slug, status, created_at,
            org_address, reporting_person_name,
            reporting_person_title, reporting_person_phone
        ) VALUES (?, ?, ?, datetime('now'), ?, ?, ?, ?)
    """, (
        "Test Compliance Firm",
        "test-firm",
        "active",
        "Sharjah, Al Majaz 2",
        "Mohammed Al Hashimi",
        "Head of Compliance",
        "+971509876543"
    ))
    org_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    db.commit()

    # Fetch org profile
    row = db.execute("""
        SELECT name, org_address, reporting_person_name,
               reporting_person_title, reporting_person_phone
        FROM organizations WHERE id=?
    """, (org_id,)).fetchone()

    assert row is not None
    assert row[0] == "Test Compliance Firm"
    assert row[1] == "Sharjah, Al Majaz 2"
    assert row[2] == "Mohammed Al Hashimi"
    assert row[3] == "Head of Compliance"
    assert row[4] == "+971509876543"

    # These fields can be injected into report_data before calling serialize_goaml_xml
    # as "reporting_entity_name", "reporting_entity_branch", etc.

    db.close()
