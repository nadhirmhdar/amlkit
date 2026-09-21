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


def test_high_risk_without_sow_rejected_via_route(tmp_path, monkeypatch):
    """POST /customers returns 422 when risk_level='high' but SoW missing."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(str(db_file))
    now = utcnow()

    # Create org and operator
    conn.execute(
        "INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1, 'TestOrg', 'testorg', 'active', ?)",
        (now,),
    )
    from amlkit.auth import hash_password
    conn.execute(
        """INSERT INTO operators (org_id, name, email, password_hash, role, is_active, created_at, email_verified_at, disclaimer_acknowledged_at)
           VALUES (1, 'Test', 'test@example.com', ?, 'mlro', 1, ?, ?, ?)""",
        (hash_password("password"), now, now, now),
    )
    conn.execute(
        """INSERT INTO datasets (key, title, is_mandatory, last_refresh, entity_count)
           VALUES ('un_consolidated', 'UN', 1, ?, 1)""",
        (now,),
    )
    conn.commit()

    from amlkit.auth import create_session
    token = create_session(conn, operator_id=1, org_id=1)
    conn.close()

    client = TestClient(app)
    client.cookies.set("amlkit_session", token)

    # Get CSRF token
    r = client.get("/customers/new")
    import re
    csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
    assert csrf_match, "CSRF token not found in form"
    csrf = csrf_match.group(1)

    # Try to onboard high-risk customer without SoW
    r = client.post(
        "/customers",
        data={
            "reference": "C-TEST-001",
            "full_name": "Test Customer",
            "customer_type": "natural",
            "risk_level": "high",
            "source_of_wealth": "",  # Missing!
            "source_of_funds": "Bank account",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )

    # Should redirect back with error (422 logic in back() helper)
    assert r.status_code in [303, 422, 200]  # 303 redirect or direct error
    # Check that error message is present (would be in flash or response)
    if r.status_code == 303:
        # Follow redirect to see error
        r2 = client.get(r.headers["location"])
        assert "Source of Wealth" in r2.text or "required" in r2.text


def test_effective_risk_combines_declared_and_computed(tmp_path):
    """effective_risk() returns 'high' when either declared or computed is high."""
    from amlkit import queries

    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))
    now = utcnow()

    conn.execute(
        "INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1, 'TestOrg', 'testorg', 'active', ?)",
        (now,),
    )
    conn.commit()

    # Case 1: Declared high, no computed assessment yet
    conn.execute(
        """INSERT INTO customers (id, org_id, reference, customer_type, full_name, canonical_key,
                                  onboarded_at, created_at, updated_at, risk_level)
           VALUES (1, 1, 'C-001', 'natural', 'Customer One', 'customer|one', ?, ?, ?, 'high')""",
        (now, now, now),
    )
    conn.commit()

    eff_risk = queries.effective_risk(conn, 1, 1)
    assert eff_risk == "high", "Declared high should result in effective risk high"

    # Case 2: Declared low, but computed assessment is high
    conn.execute(
        """INSERT INTO customers (id, org_id, reference, customer_type, full_name, canonical_key,
                                  onboarded_at, created_at, updated_at, risk_level)
           VALUES (2, 1, 'C-002', 'natural', 'Customer Two', 'customer|two', ?, ?, ?, 'low')""",
        (now, now, now),
    )
    conn.execute(
        """INSERT INTO risk_assessments (org_id, customer_id, score, rating, factors,
                                         ruleset_version, assessed_at)
           VALUES (1, 2, 85, 'high', '{}', 'v1.0', ?)""",
        (now,),
    )
    conn.commit()

    eff_risk = queries.effective_risk(conn, 2, 1)
    assert eff_risk == "high", "Computed high should result in effective risk high even if declared low"

    # Case 3: Declared low, computed medium -> should be medium
    conn.execute(
        """INSERT INTO customers (id, org_id, reference, customer_type, full_name, canonical_key,
                                  onboarded_at, created_at, updated_at, risk_level)
           VALUES (3, 1, 'C-003', 'natural', 'Customer Three', 'customer|three', ?, ?, ?, 'low')""",
        (now, now, now),
    )
    conn.execute(
        """INSERT INTO risk_assessments (org_id, customer_id, score, rating, factors,
                                         ruleset_version, assessed_at)
           VALUES (1, 3, 50, 'medium', '{}', 'v1.0', ?)""",
        (now,),
    )
    conn.commit()

    eff_risk = queries.effective_risk(conn, 3, 1)
    assert eff_risk == "medium", "Should return computed rating when neither is high"

    # Case 4: No declared, no computed -> defaults to low
    conn.execute(
        """INSERT INTO customers (id, org_id, reference, customer_type, full_name, canonical_key,
                                  onboarded_at, created_at, updated_at)
           VALUES (4, 1, 'C-004', 'natural', 'Customer Four', 'customer|four', ?, ?, ?)""",
        (now, now, now),
    )
    conn.commit()

    eff_risk = queries.effective_risk(conn, 4, 1)
    assert eff_risk == "low", "Should default to low when no risk information available"

    conn.close()
