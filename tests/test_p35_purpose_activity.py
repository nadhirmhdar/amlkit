"""Test p35: purpose_of_relationship + expected_activity fields in customer onboarding.

CDD enhancement: capture the purpose of the business relationship and expected
transaction activity at onboarding time for risk assessment and monitoring.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect, utcnow
from amlkit.cases.manager import onboard


def test_purpose_and_activity_saved_on_onboard(tmp_path):
    """Purpose of relationship and expected activity are saved when provided."""
    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))
    now = utcnow()

    conn.execute(
        "INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1, 'TestOrg', 'testorg', 'active', ?)",
        (now,),
    )
    conn.commit()

    # Seed mandatory datasets so onboard doesn't fail on staleness
    conn.execute(
        """INSERT INTO datasets (key, title, publisher, source_url, is_mandatory,
                                 last_refresh, entity_count)
           VALUES ('un_consolidated', 'UN', 'UN', 'https://example.com', 1, ?, 1)""",
        (now,),
    )
    conn.commit()

    result = onboard(
        conn,
        org_id=1,
        reference="C-001",
        full_name="Test Customer",
        customer_type="legal",
        purpose_of_relationship="Investment advisory services",
        expected_activity="Monthly wire transfers under AED 100,000",
        actor="test-operator",
    )

    assert result.customer_id is not None

    # Verify fields were saved
    row = conn.execute(
        "SELECT purpose_of_relationship, expected_activity FROM customers WHERE id = ?",
        (result.customer_id,),
    ).fetchone()

    assert row is not None
    assert row["purpose_of_relationship"] == "Investment advisory services"
    assert row["expected_activity"] == "Monthly wire transfers under AED 100,000"

    conn.close()


def test_purpose_and_activity_optional(tmp_path):
    """Purpose and activity fields are optional — onboarding works without them."""
    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))
    now = utcnow()

    conn.execute(
        "INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1, 'TestOrg', 'testorg', 'active', ?)",
        (now,),
    )
    conn.commit()

    conn.execute(
        """INSERT INTO datasets (key, title, publisher, source_url, is_mandatory,
                                 last_refresh, entity_count)
           VALUES ('un_consolidated', 'UN', 'UN', 'https://example.com', 1, ?, 1)""",
        (now,),
    )
    conn.commit()

    # Onboard without purpose/activity
    result = onboard(
        conn,
        org_id=1,
        reference="C-002",
        full_name="Another Customer",
        actor="test-operator",
    )

    assert result.customer_id is not None

    row = conn.execute(
        "SELECT purpose_of_relationship, expected_activity FROM customers WHERE id = ?",
        (result.customer_id,),
    ).fetchone()

    # Should be NULL when not provided
    assert row["purpose_of_relationship"] is None
    assert row["expected_activity"] is None

    conn.close()
