"""Test p38: UBO last_verified_at tracking.

UBOs require periodic re-verification per Cabinet Resolution 134/2025.
Track when each UBO record was last verified and flag stale records.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect, utcnow
from amlkit.cases.manager import onboard


def test_ubo_has_last_verified_at_column(tmp_path):
    """UBO table has last_verified_at column."""
    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))

    # Check column exists
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(ubo_links)")}
    assert "last_verified_at" in cols


def test_onboarding_sets_last_verified_at_to_now(tmp_path):
    """New UBOs get last_verified_at set to onboarding time."""
    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))
    now = utcnow()

    conn.execute(
        "INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1, 'TestOrg', 'testorg', 'active', ?)",
        (now,),
    )
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
        full_name="Test Company",
        customer_type="legal",
        ubos=[{"person_name": "John Doe", "ownership_pct": 100, "control_type": "ownership"}],
        actor="test-operator",
    )

    ubo = conn.execute(
        "SELECT last_verified_at FROM ubo_links WHERE customer_id = ?",
        (result.customer_id,),
    ).fetchone()

    assert ubo is not None
    assert ubo["last_verified_at"] is not None
    # Should be set to approximately now (within 5 seconds)
    verified_at = datetime.fromisoformat(ubo["last_verified_at"].replace("Z", "+00:00"))
    now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
    assert abs((verified_at - now_dt).total_seconds()) < 5


def test_stale_ubo_detection(tmp_path):
    """UBOs not verified in >12 months are flagged as stale."""
    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))
    now = utcnow()

    conn.execute(
        "INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1, 'TestOrg', 'testorg', 'active', ?)",
        (now,),
    )
    # Create dummy customers
    conn.execute(
        """INSERT INTO customers
           (id, org_id, reference, customer_type, full_name, canonical_key, onboarded_at, created_at, updated_at)
           VALUES (1, 1, 'C-1', 'legal', 'Customer 1', 'customer-1', ?, ?, ?)""",
        (now, now, now),
    )
    conn.execute(
        """INSERT INTO customers
           (id, org_id, reference, customer_type, full_name, canonical_key, onboarded_at, created_at, updated_at)
           VALUES (2, 1, 'C-2', 'legal', 'Customer 2', 'customer-2', ?, ?, ?)""",
        (now, now, now),
    )
    conn.commit()

    # Create UBO with old last_verified_at
    old_verified = (datetime.now() - timedelta(days=400)).isoformat() + "Z"
    conn.execute(
        """INSERT INTO ubo_links
           (org_id, customer_id, person_name, canonical_key, control_type, created_at, last_verified_at)
           VALUES (1, 1, 'Old UBO', 'old-ubo', 'ownership', ?, ?)""",
        (now, old_verified),
    )

    # Create UBO with recent last_verified_at
    recent_verified = (datetime.now() - timedelta(days=30)).isoformat() + "Z"
    conn.execute(
        """INSERT INTO ubo_links
           (org_id, customer_id, person_name, canonical_key, control_type, created_at, last_verified_at)
           VALUES (1, 2, 'Recent UBO', 'recent-ubo', 'ownership', ?, ?)""",
        (now, recent_verified),
    )
    conn.commit()

    # Query for stale UBOs (>12 months)
    stale = conn.execute(
        """SELECT person_name, last_verified_at
           FROM ubo_links
           WHERE julianday('now') - julianday(last_verified_at) > 365
           ORDER BY person_name"""
    ).fetchall()

    assert len(stale) == 1
    assert stale[0]["person_name"] == "Old UBO"
