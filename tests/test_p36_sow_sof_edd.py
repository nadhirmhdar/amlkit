"""Test p36: Source of Wealth and Source of Funds EDD fields gated by risk_level.

Enhanced due diligence: capture Source of Wealth and Source of Funds for high-risk
customers only (risk_level=='high'). Fields are optional for low/medium risk.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect, utcnow
from amlkit.cases.manager import onboard


def test_risk_level_and_edd_fields_saved_on_onboard(tmp_path):
    """risk_level, source_of_wealth, source_of_funds saved when provided."""
    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))
    now = utcnow()

    conn.execute(
        "INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1, 'TestOrg', 'testorg', 'active', ?)",
        (now,),
    )
    conn.commit()

    # Seed mandatory datasets
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
        reference="C-HIGH-001",
        full_name="High Risk Customer",
        customer_type="legal",
        risk_level="high",
        source_of_wealth="Inheritance from family business proceeds",
        source_of_funds="Bank account in UAE - Emirates NBD",
        actor="test-operator",
    )

    assert result.customer_id is not None

    # Verify fields were saved
    row = conn.execute(
        "SELECT risk_level, source_of_wealth, source_of_funds FROM customers WHERE id = ?",
        (result.customer_id,),
    ).fetchone()

    assert row is not None
    assert row["risk_level"] == "high"
    assert row["source_of_wealth"] == "Inheritance from family business proceeds"
    assert row["source_of_funds"] == "Bank account in UAE - Emirates NBD"


def test_edd_fields_optional_when_not_high_risk(tmp_path):
    """SoW/SoF fields can be NULL when risk_level is not 'high'."""
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

    # Onboard a low-risk customer without SoW/SoF
    result = onboard(
        conn,
        org_id=1,
        reference="C-LOW-001",
        full_name="Low Risk Customer",
        customer_type="natural",
        risk_level="low",
        actor="test-operator",
    )

    assert result.customer_id is not None

    row = conn.execute(
        "SELECT risk_level, source_of_wealth, source_of_funds FROM customers WHERE id = ?",
        (result.customer_id,),
    ).fetchone()

    assert row is not None
    assert row["risk_level"] == "low"
    # SoW/SoF should be NULL
    assert row["source_of_wealth"] is None
    assert row["source_of_funds"] is None


def test_onboard_works_without_risk_level(tmp_path):
    """Onboarding works when risk_level not provided (backward compat)."""
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

    result = onboard(
        conn,
        org_id=1,
        reference="C-LEGACY-001",
        full_name="Legacy Customer",
        customer_type="legal",
        actor="test-operator",
    )

    assert result.customer_id is not None

    row = conn.execute(
        "SELECT risk_level, source_of_wealth, source_of_funds FROM customers WHERE id = ?",
        (result.customer_id,),
    ).fetchone()

    assert row is not None
    assert row["risk_level"] is None
    assert row["source_of_wealth"] is None
    assert row["source_of_funds"] is None
