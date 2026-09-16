"""UBO ownership validation tests.

Test for H-01 from QA triage report (2026-09-17):
Server-side validation that UBO ownership percentages cannot exceed 100%.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _create_fresh_dataset(conn):
    """Helper to create a fresh mandatory dataset for tests."""
    from amlkit.db import utcnow
    conn.execute(
        """INSERT INTO datasets (key, title, publisher, is_mandatory, last_refresh, entity_count, max_age_hours)
           VALUES ('test_list', 'Test List', 'Test', 1, ?, 1, 24)""",
        (utcnow(),)
    )


def test_ubo_ownership_sum_cannot_exceed_100_percent(tmp_path, monkeypatch):
    """H-01: Server must reject UBO ownership totaling more than 100%.

    The QA test created customer QA-UBO-TEST-001 with 3 UBOs at 60% each
    (180% total). This was accepted by the server, corrupting the ownership
    structure.

    A company cannot be 180% owned. The sum must be validated server-side.
    """
    from amlkit.db import connect
    from amlkit.cases.manager import onboard

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    # Initialize database with org and mandatory dataset
    conn = connect(str(db_file))
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES ('Test Org', 'test', 'active', datetime('now'))"
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Add a mandatory dataset so datasets_fresh() passes
    _create_fresh_dataset(conn)
    conn.commit()

    # Attempt to onboard with 3 UBOs at 60% each (180% total)
    with pytest.raises(ValueError, match=r"[Tt]otal.*[Oo]wnership.*100"):
        onboard(
            conn,
            org_id=org_id,
            reference="TEST-180",
            full_name="Over Corp",
            ubos=[
                {"person_name": "Alice", "ownership_pct": 60.0},
                {"person_name": "Bob", "ownership_pct": 60.0},
                {"person_name": "Charlie", "ownership_pct": 60.0},
            ],
            actor="test",
        )

    # Verify no customer was created
    customer_count = conn.execute(
        "SELECT COUNT(*) FROM customers WHERE reference='TEST-180'"
    ).fetchone()[0]
    assert customer_count == 0, "Customer should not have been created"

    # Verify no UBOs were created
    ubo_count = conn.execute("SELECT COUNT(*) FROM ubo_links").fetchone()[0]
    assert ubo_count == 0, "No UBO records should have been created"

    conn.close()


def test_ubo_ownership_sum_exactly_100_percent_is_valid(tmp_path, monkeypatch):
    """UBO ownership totaling exactly 100% should be accepted."""
    from amlkit.db import connect
    from amlkit.cases.manager import onboard

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(str(db_file))
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES ('Test Org', 'test', 'active', datetime('now'))"
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Add mandatory dataset
    _create_fresh_dataset(conn)
    conn.commit()

    # Onboard with 4 UBOs at 25% each (100% total) - should succeed
    result = onboard(
        conn,
        org_id=org_id,
        reference="TEST-100",
        full_name="Exact Corp",
        ubos=[
            {"person_name": "Alice", "ownership_pct": 25.0},
            {"person_name": "Bob", "ownership_pct": 25.0},
            {"person_name": "Charlie", "ownership_pct": 25.0},
            {"person_name": "Diana", "ownership_pct": 25.0},
        ],
        actor="test",
    )

    # Verify customer was created
    assert result.customer_id is not None
    customer = conn.execute(
        "SELECT * FROM customers WHERE reference='TEST-100'"
    ).fetchone()
    assert customer is not None

    # Verify all 4 UBOs were created
    ubo_count = conn.execute(
        "SELECT COUNT(*) FROM ubo_links WHERE customer_id=?",
        (result.customer_id,)
    ).fetchone()[0]
    assert ubo_count == 4, "All 4 UBOs should have been created"

    conn.close()


def test_ubo_ownership_sum_under_100_percent_is_valid(tmp_path, monkeypatch):
    """UBO ownership totaling less than 100% should be accepted.

    This is valid because not all ownership may be disclosed, or there may
    be shareholders under the 25% reporting threshold.
    """
    from amlkit.db import connect
    from amlkit.cases.manager import onboard

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(str(db_file))
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES ('Test Org', 'test', 'active', datetime('now'))"
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Add mandatory dataset
    _create_fresh_dataset(conn)
    conn.commit()

    # Onboard with 2 UBOs at 30% each (60% total) - should succeed
    result = onboard(
        conn,
        org_id=org_id,
        reference="TEST-60",
        full_name="Partial Corp",
        ubos=[
            {"person_name": "Alice", "ownership_pct": 30.0},
            {"person_name": "Bob", "ownership_pct": 30.0},
        ],
        actor="test",
    )

    # Verify customer was created
    assert result.customer_id is not None

    # Verify UBOs were created
    ubo_count = conn.execute(
        "SELECT COUNT(*) FROM ubo_links WHERE customer_id=?",
        (result.customer_id,)
    ).fetchone()[0]
    assert ubo_count == 2

    conn.close()


def test_ubo_ownership_sum_slightly_over_100_percent_rejected(tmp_path, monkeypatch):
    """Even slight excess over 100% should be rejected (e.g., 100.1%)."""
    from amlkit.db import connect
    from amlkit.cases.manager import onboard

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(str(db_file))
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES ('Test Org', 'test', 'active', datetime('now'))"
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Add mandatory dataset
    _create_fresh_dataset(conn)
    conn.commit()

    # Attempt 50.5% + 50.5% = 101%
    with pytest.raises(ValueError, match=r"[Tt]otal.*[Oo]wnership.*100"):
        onboard(
            conn,
            org_id=org_id,
            reference="TEST-101",
            full_name="Slight Over Corp",
            ubos=[
                {"person_name": "Alice", "ownership_pct": 50.5},
                {"person_name": "Bob", "ownership_pct": 50.5},
            ],
            actor="test",
        )

    conn.close()


def test_ubo_ownership_floating_point_rounding(tmp_path, monkeypatch):
    """Floating point edge case: 33.34 + 33.33 + 33.33 = 100.00 should be accepted."""
    from amlkit.db import connect
    from amlkit.cases.manager import onboard

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(str(db_file))
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES ('Test Org', 'test', 'active', datetime('now'))"
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    _create_fresh_dataset(conn)
    conn.commit()

    # This sums to exactly 100.00 when rounded to 2 decimal places
    result = onboard(
        conn,
        org_id=org_id,
        reference="TEST-FP",
        full_name="Float Corp",
        ubos=[
            {"person_name": "Alice", "ownership_pct": 33.34},
            {"person_name": "Bob", "ownership_pct": 33.33},
            {"person_name": "Charlie", "ownership_pct": 33.33},
        ],
        actor="test",
    )

    assert result.customer_id is not None
    ubo_count = conn.execute(
        "SELECT COUNT(*) FROM ubo_links WHERE customer_id=?",
        (result.customer_id,)
    ).fetchone()[0]
    assert ubo_count == 3

    conn.close()


def test_indirect_ubo_chain_does_not_trigger_limit(tmp_path, monkeypatch):
    """Indirect UBOs (parent_ubo_id set) should not count toward the 100% direct limit.

    A corporate shareholder at 60% has its own UBOs. The indirect chain members
    don't count against the customer's direct ownership limit.
    """
    from amlkit.db import connect
    from amlkit.cases.manager import onboard, add_ubo

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(str(db_file))
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES ('Test Org', 'test', 'active', datetime('now'))"
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    _create_fresh_dataset(conn)
    conn.commit()

    # Onboard with 60% direct ownership
    result = onboard(
        conn,
        org_id=org_id,
        reference="TEST-INDIRECT",
        full_name="Corp With Chain",
        ubos=[
            {"person_name": "Corporate Shareholder", "ownership_pct": 60.0},
        ],
        actor="test",
    )

    # Get the UBO ID for the corporate shareholder (direct link)
    corporate_ubo_id = conn.execute(
        "SELECT id FROM ubo_links WHERE customer_id=? AND person_name=?",
        (result.customer_id, "Corporate Shareholder")
    ).fetchone()[0]

    # Add indirect UBOs (children of the corporate shareholder)
    # These have parent_ubo_id set, so they're indirect links
    # Total indirect: 50 + 50 = 100%, but doesn't count against customer's direct limit
    add_ubo(
        conn, result.customer_id, org_id=org_id,
        person_name="Ultimate Owner A", ownership_pct=50.0,
        parent_ubo_id=corporate_ubo_id, actor="test"
    )
    add_ubo(
        conn, result.customer_id, org_id=org_id,
        person_name="Ultimate Owner B", ownership_pct=50.0,
        parent_ubo_id=corporate_ubo_id, actor="test"
    )

    # Should have 3 total UBO links: 1 direct + 2 indirect
    total_ubos = conn.execute(
        "SELECT COUNT(*) FROM ubo_links WHERE customer_id=?",
        (result.customer_id,)
    ).fetchone()[0]
    assert total_ubos == 3

    # Verify direct ownership is only 60% (corporate shareholder)
    direct_total = conn.execute(
        "SELECT SUM(ownership_pct) FROM ubo_links WHERE customer_id=? AND parent_ubo_id IS NULL",
        (result.customer_id,)
    ).fetchone()[0]
    assert direct_total == 60.0

    # Now add another direct UBO at 40% - should succeed (60 + 40 = 100)
    add_ubo(
        conn, result.customer_id, org_id=org_id,
        person_name="Direct UBO", ownership_pct=40.0,
        actor="test"
    )

    # Direct total should now be 100%
    direct_total = conn.execute(
        "SELECT SUM(ownership_pct) FROM ubo_links WHERE customer_id=? AND parent_ubo_id IS NULL",
        (result.customer_id,)
    ).fetchone()[0]
    assert direct_total == 100.0

    conn.close()


