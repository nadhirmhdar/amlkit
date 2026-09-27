"""Test A-02-3 issue-259: auto_rescreen per-org exception isolation.

Regression test for the main loop in scripts/auto_rescreen.py. When rescreen_all
raises for one org, subsequent orgs must still run.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit import db
from scripts import auto_rescreen


def test_per_org_exception_does_not_kill_entire_run():
    """Issue 259: One org raising should not prevent other orgs from rescreening.

    Before fix: org-1 raises → script dies → org-2 never runs.
    After fix: org-1 raises → logged → org-2 runs normally.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        conn = db.connect(db_path)
        # Create two orgs
        conn.execute(
            "INSERT INTO organizations (id, name, slug, status, created_at) "
            "VALUES (1, 'Org One', 'org1', 'active', '2024-01-01')"
        )
        conn.execute(
            "INSERT INTO organizations (id, name, slug, status, created_at) "
            "VALUES (2, 'Org Two', 'org2', 'active', '2024-01-01')"
        )
        conn.commit()

        # Create mandatory dataset so staleness check passes
        conn.execute(
            "INSERT INTO datasets (key, title, publisher, licence, is_mandatory, "
            "last_refresh) VALUES ('un', 'UN', 'UN', 'open', 1, ?)",
            (db.utcnow(),)
        )
        conn.execute(
            "INSERT INTO entities (dataset_id, source_id, schema_type, caption, "
            "first_seen, last_seen) VALUES (1, 's1', 'Person', 'Test', '2024-01-01', '2024-01-01')"
        )
        conn.commit()
        conn.close()

        # Mock rescreen_all to raise for org-1, succeed for org-2
        call_log = []
        def mock_rescreen_all(conn, org_id, actor):
            call_log.append(org_id)
            if org_id == 1:
                raise ValueError("Simulated failure for org-1")
            # Org-2 succeeds
            return {"screened": 10, "alerts": 0}

        with patch("scripts.auto_rescreen.rescreen_all", side_effect=mock_rescreen_all):
            test_conn = db.connect(db_path)
            with patch("scripts.auto_rescreen.connect", return_value=test_conn):
                # Skip the refresh step so test focuses on rescreen loop isolation
                with patch("scripts.auto_rescreen._lists_are_current", return_value=True):
                    exit_code = auto_rescreen.main()
            test_conn.close()

        # Before fix: call_log == [1] (org-1 raised, org-2 never ran)
        # After fix: call_log == [1, 2] (org-1 raised but logged, org-2 ran)
        assert len(call_log) == 2, \
            f"Expected rescreen_all called 2x (both orgs), got {len(call_log)}x: {call_log}"
        assert call_log == [1, 2], f"Expected orgs [1, 2], got {call_log}"

        # After fix: exit code should be non-zero since org-1 failed
        assert exit_code != 0, \
            "Script should return non-zero exit code when any org fails"


def test_per_org_exception_summary_in_output(capsys):
    """Issue 259: Failed orgs should be summarized in final output."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        conn = db.connect(db_path)
        # Create org that will fail
        conn.execute(
            "INSERT INTO organizations (id, name, slug, status, created_at) "
            "VALUES (1, 'Failing Org', 'fail', 'active', '2024-01-01')"
        )
        conn.commit()

        # Create mandatory dataset
        conn.execute(
            "INSERT INTO datasets (key, title, publisher, licence, is_mandatory, "
            "last_refresh) VALUES ('un', 'UN', 'UN', 'open', 1, ?)",
            (db.utcnow(),)
        )
        conn.execute(
            "INSERT INTO entities (dataset_id, source_id, schema_type, caption, "
            "first_seen, last_seen) VALUES (1, 's1', 'Person', 'Test', '2024-01-01', '2024-01-01')"
        )
        conn.commit()
        conn.close()

        def mock_rescreen_all(conn, org_id, actor):
            raise RuntimeError("Test failure")

        test_conn = db.connect(db_path)
        with patch("scripts.auto_rescreen.rescreen_all", side_effect=mock_rescreen_all):
            with patch("scripts.auto_rescreen.connect", return_value=test_conn):
                with patch("scripts.auto_rescreen._lists_are_current", return_value=True):
                    exit_code = auto_rescreen.main()
        test_conn.close()

        captured = capsys.readouterr()
        output = captured.out + captured.err

        # After fix: should mention the failed org
        assert "Failing Org" in output or "fail" in output or "org-1" in output or "1 org(s) failed" in output, \
            "Output should mention the failed org or failure count"

        assert exit_code != 0, "Exit code should be non-zero when org fails"


def test_reassessment_happens_even_on_org_failure():
    """After org A fails, customers with new alerts in org A are still re-rated.

    Before fix: org A commits alerts, then raises → reassessment skipped →
    those customers keep stale risk ratings.

    After fix: org A fails → rollback → best-effort reassessment of customers
    with committed alerts → those customers get re-rated anyway.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        conn = db.connect(db_path)
        try:
            # Create two orgs
            conn.execute(
                "INSERT INTO organizations (id, name, slug, status, created_at) "
                "VALUES (1, 'Org A', 'orga', 'active', '2024-01-01')"
            )
            conn.execute(
                "INSERT INTO organizations (id, name, slug, status, created_at) "
                "VALUES (2, 'Org B', 'orgb', 'active', '2024-01-01')"
            )

            # Create a customer in org A
            conn.execute(
                "INSERT INTO customers (org_id, name, created_at) "
                "VALUES (1, 'Customer A', '2024-01-01')"
            )

            # Create mandatory dataset
            conn.execute(
                "INSERT INTO datasets (key, title, publisher, licence, is_mandatory, "
                "last_refresh) VALUES ('un', 'UN', 'UN', 'open', 1, ?)",
                (db.utcnow(),)
            )
            conn.execute(
                "INSERT INTO entities (dataset_id, source_id, schema_type, caption, "
                "first_seen, last_seen) VALUES (1, 's1', 'Person', 'Test', '2024-01-01', '2024-01-01')"
            )
            conn.commit()
        finally:
            conn.close()

        # Track reassessment and rescreen calls
        reassess_calls = []
        rescreen_calls = []

        def mock_reassess_risk(conn, customer_id, org_id, actor):
            reassess_calls.append((customer_id, org_id))
            return True

        def mock_rescreen_all(conn, org_id, actor):
            rescreen_calls.append(org_id)
            if org_id == 1:
                # Org A: create an alert (simulates commit), then raise
                conn.execute(
                    "INSERT INTO screenings (customer_id, org_id, list_key, created_at) "
                    "VALUES (1, 1, 'un', ?)",
                    (db.utcnow(),)
                )
                screening_id = conn.lastrowid
                conn.execute(
                    "INSERT INTO alerts (screening_id, org_id, created_at, status) "
                    "VALUES (?, 1, ?, 'open')",
                    (screening_id, db.utcnow())
                )
                conn.commit()
                # Now raise to simulate failure after commit
                raise ValueError("Simulated failure in org A")
            # Org B succeeds
            return {"screened": 10, "alerts": 0}

        with patch("scripts.auto_rescreen.rescreen_all", side_effect=mock_rescreen_all):
            with patch("scripts.auto_rescreen.reassess_risk", side_effect=mock_reassess_risk):
                with patch("scripts.auto_rescreen.connect", return_value=db.connect(db_path)):
                    with patch("scripts.auto_rescreen._lists_are_current", return_value=True):
                        exit_code = auto_rescreen.main()

        # Verify both orgs were called for rescreen
        assert rescreen_calls == [1, 2], f"Expected rescreen for both orgs, got {rescreen_calls}"

        # Verify reassessment happened even after org A failed (best-effort)
        assert len(reassess_calls) > 0, \
            "reassess_risk should be called for customers with committed alerts even after org failure"
        assert (1, 1) in reassess_calls, \
            "reassess_risk should be called for customer 1 in org 1"

        # Verify audit entry exists for the failure
        conn = db.connect(db_path)
        try:
            audit_entry = conn.execute(
                "SELECT * FROM audit_log WHERE action='rescreen.org_failed' AND org_id=1"
            ).fetchone()
            assert audit_entry is not None, \
                "rescreen.org_failed audit entry should exist for org A"
        finally:
            conn.close()

        # Verify exit code is 1 (failure)
        assert exit_code == 1, f"Expected exit code 1 (failure), got {exit_code}"
