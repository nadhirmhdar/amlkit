"""Test p46: Organization reporting-entity profile fields in admin panel.

Operators need to fill in goAML reporting entity details in admin settings.
These fields populate the reporting entity section of goAML XML exports.
"""
import sqlite3
from amlkit.db import connect


def test_organizations_table_has_profile_fields():
    """Organizations table should have org profile columns for goAML reporting."""
    db = connect(":memory:")

    # Check schema for new columns
    cursor = db.execute("PRAGMA table_info(organizations)")
    columns = {row[1] for row in cursor.fetchall()}

    # Should have reporting entity profile fields
    assert "org_address" in columns, "Missing org_address column"
    assert "reporting_person_name" in columns, "Missing reporting_person_name column"
    assert "reporting_person_title" in columns, "Missing reporting_person_title column"
    assert "reporting_person_phone" in columns, "Missing reporting_person_phone column"

    db.close()


def test_save_org_profile_to_database():
    """Should be able to save org profile fields to organizations table."""
    db = connect(":memory:")

    # Create an organization
    db.execute("""
        INSERT INTO organizations (name, slug, status, created_at)
        VALUES ('Test Firm', 'test-firm', 'active', datetime('now'))
    """)
    org_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Update org profile fields
    db.execute("""
        UPDATE organizations
        SET org_address = ?,
            reporting_person_name = ?,
            reporting_person_title = ?,
            reporting_person_phone = ?
        WHERE id = ?
    """, (
        "Dubai Internet City, Building 5",
        "Ahmed Al Mansoori",
        "Chief Compliance Officer",
        "+971501234567",
        org_id
    ))
    db.commit()

    # Verify saved
    row = db.execute("""
        SELECT org_address, reporting_person_name, reporting_person_title, reporting_person_phone
        FROM organizations WHERE id=?
    """, (org_id,)).fetchone()

    assert row is not None
    assert row[0] == "Dubai Internet City, Building 5"
    assert row[1] == "Ahmed Al Mansoori"
    assert row[2] == "Chief Compliance Officer"
    assert row[3] == "+971501234567"

    db.close()


def test_org_profile_fields_nullable():
    """Org profile fields should be nullable (not required initially)."""
    db = connect(":memory:")

    # Create org without profile fields
    db.execute("""
        INSERT INTO organizations (name, slug, status, created_at)
        VALUES ('Test Firm', 'test-firm', 'active', datetime('now'))
    """)
    org_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.commit()

    # Should succeed (fields are NULL)
    row = db.execute("""
        SELECT org_address, reporting_person_name, reporting_person_title, reporting_person_phone
        FROM organizations WHERE id=?
    """, (org_id,)).fetchone()

    assert row is not None
    assert row[0] is None  # org_address
    assert row[1] is None  # reporting_person_name
    assert row[2] is None  # reporting_person_title
    assert row[3] is None  # reporting_person_phone

    db.close()
