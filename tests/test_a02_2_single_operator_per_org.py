"""Test A-02-2 / Issue #258: single_operator_mode must be per-org, not process-wide.

Bug: AMLKIT_SINGLE_OPERATOR_MODE env var is process-wide. Setting it for one
solo-officer tenant disables four-eyes review for all tenants on the instance,
including multi-operator orgs that should require independent review.

Fix: Store per-org config in DB (org_settings.single_operator_mode), resolve
from org_id at call site. Env var becomes instance-wide default only, never
overriding explicit per-org setting.
"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_single_operator_mode_respects_per_org_db_config(tmp_path, monkeypatch):
    """Per-org DB config takes precedence over env var."""
    from amlkit.db import connect
    from amlkit.cases.review import single_operator_mode

    # Set process-wide env var
    monkeypatch.setenv("AMLKIT_SINGLE_OPERATOR_MODE", "1")

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)

    # Create two orgs
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Org 1", "org1", "active", "2026-01-01T00:00:00+00:00"))
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Org 2", "org2", "active", "2026-01-01T00:00:00+00:00"))
    conn.commit()

    # Org 1: no DB config (should fall back to env var = True)
    assert single_operator_mode(conn, org_id=1) is True, "Org 1 should use env var default (True)"

    # Org 2: explicitly set to False in DB (overrides env var)
    conn.execute("INSERT INTO org_settings (org_id, updated_at, single_operator_mode) VALUES (?,?,?)",
                 (2, "2026-01-01T00:00:00+00:00", 0))
    conn.commit()
    assert single_operator_mode(conn, org_id=2) is False, "Org 2 DB config (False) should override env var"

    # Org 2: change DB config to True
    conn.execute("UPDATE org_settings SET single_operator_mode = 1 WHERE org_id = 2")
    conn.commit()
    assert single_operator_mode(conn, org_id=2) is True, "Org 2 DB config (True) should override env var"

    conn.close()


def test_single_operator_mode_defaults_to_false_without_env_or_db(tmp_path, monkeypatch):
    """Without env var or DB config, default to False (stricter control)."""
    from amlkit.db import connect
    from amlkit.cases.review import single_operator_mode

    # NO env var set
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Test Org", "test", "active", "2026-01-01T00:00:00+00:00"))
    conn.commit()

    # No env var, no DB config → default False
    assert single_operator_mode(conn, org_id=1) is False, "Should default to False (stricter control)"

    conn.close()


def test_per_org_config_isolates_orgs_in_shared_process(tmp_path, monkeypatch):
    """Two orgs in same process must have independent single_operator_mode settings.

    This is the core regression test for Issue #258.
    """
    from amlkit.db import connect
    from amlkit.cases.review import single_operator_mode

    # Set env var to True (would affect all orgs in buggy version)
    monkeypatch.setenv("AMLKIT_SINGLE_OPERATOR_MODE", "1")

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    conn = connect(db_file)

    # Create Org 1 (solo) and Org 2 (multi-operator)
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Solo Firm", "solo", "active", "2026-01-01T00:00:00+00:00"))
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 ("Multi Firm", "multi", "active", "2026-01-01T00:00:00+00:00"))

    # Org 2 explicitly disables single_operator_mode (has multiple operators)
    conn.execute("INSERT INTO org_settings (org_id, updated_at, single_operator_mode) VALUES (?,?,?)",
                 (2, "2026-01-01T00:00:00+00:00", 0))
    conn.commit()

    # Org 1 inherits env var (True) - solo operator org
    assert single_operator_mode(conn, org_id=1) is True, "Org 1 should use env var (solo operator)"

    # Org 2 has DB config (False) - multi-operator org MUST NOT be affected by env var
    assert single_operator_mode(conn, org_id=2) is False, (
        "Org 2 must enforce four-eyes (DB config False) despite env var True. "
        "Bug: process-wide env var was disabling four-eyes for all orgs."
    )

    conn.close()
