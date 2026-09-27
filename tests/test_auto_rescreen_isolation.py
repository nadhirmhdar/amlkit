"""Test A-02-3 issue-259: auto_rescreen per-org exception isolation.

Regression test for the main loop in scripts/auto_rescreen.py. When rescreen_all
raises for one org, subsequent orgs must still run. Also verifies that alerts
committed before the failure are still re-assessed for risk.
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit import db
from amlkit.match import engine
from scripts import auto_rescreen


def test_per_org_exception_does_not_kill_entire_run():
    """Issue 259: One org raising should not prevent other orgs from rescreening.

    Before fix: org-1 raises → script dies → org-2 never runs.
    After fix: org-1 raises → logged → org-2 runs normally.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        conn = db.connect(db_path)
        try:
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
        finally:
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
            with patch("scripts.auto_rescreen.connect", return_value=db.connect(db_path)):
                # Skip the refresh step so test focuses on rescreen loop isolation
                with patch("scripts.auto_rescreen._lists_are_current", return_value=True):
                    exit_code = auto_rescreen.main()

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
        try:
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
        finally:
            conn.close()

        def mock_rescreen_all(conn, org_id, actor):
            raise RuntimeError("Test failure")

        with patch("scripts.auto_rescreen.rescreen_all", side_effect=mock_rescreen_all):
            with patch("scripts.auto_rescreen.connect", return_value=db.connect(db_path)):
                with patch("scripts.auto_rescreen._lists_are_current", return_value=True):
                    exit_code = auto_rescreen.main()

        captured = capsys.readouterr()
        output = captured.out + captured.err

        # After fix: should mention the failed org
        assert "Failing Org" in output or "fail" in output or "org-1" in output or "1 org(s) failed" in output, \
            "Output should mention the failed org or failure count"

        assert exit_code != 0, "Exit code should be non-zero when org fails"


def test_partial_failure_still_reassesses_new_alerts():
    """Issue 259: Alerts committed before failure must still be re-assessed.

    When rescreen_all for org A creates alerts (via _persist which commits them)
    but then raises, the customer who got the alert must still have risk
    re-assessed, even though the exception was caught. This test verifies:

    1. Org A raises after creating an alert
    2. Org B still rescreens successfully
    3. Org A's customer has a new risk_assessments row (reassess_risk was called)
    4. A rescreen.org_failed audit row was created for org A
    5. Exit code is 1 (failure)
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

            # Create customers in each org
            now = db.utcnow()
            conn.execute(
                "INSERT INTO customers (org_id, reference, customer_type, full_name, "
                "canonical_key, status, onboarded_at, created_at, updated_at) "
                "VALUES (1, 'REF-A', 'individual', 'Customer A', 'customer_a', "
                "'active', ?, ?, ?)",
                (now, now, now)
            )
            conn.execute(
                "INSERT INTO customers (org_id, reference, customer_type, full_name, "
                "canonical_key, status, onboarded_at, created_at, updated_at) "
                "VALUES (2, 'REF-B', 'individual', 'Customer B', 'customer_b', "
                "'active', ?, ?, ?)",
                (now, now, now)
            )

            # Create mandatory dataset
            conn.execute(
                "INSERT INTO datasets (key, title, publisher, licence, is_mandatory, "
                "last_refresh) VALUES ('un', 'UN', 'UN', 'open', 1, ?)",
                (db.utcnow(),)
            )
            conn.execute(
                "INSERT INTO entities (dataset_id, source_id, schema_type, caption, "
                "first_seen, last_seen) VALUES (1, 's1', 'Person', 'Sanction Match', '2024-01-01', '2024-01-01')"
            )
            conn.commit()

            # Get the actual customer IDs
            customer_a_id = conn.execute(
                "SELECT id FROM customers WHERE org_id = 1 LIMIT 1"
            ).fetchone()["id"]
        finally:
            conn.close()

        # Track which orgs were rescreened and how many times reassess_risk was called
        orgs_rescreened = []
        reassess_calls = []

        def mock_rescreen_all(conn, org_id, actor):
            orgs_rescreened.append(org_id)
            if org_id == 1:
                # Org A: simulate creating a new alert, then failing
                # In the real code, _persist() commits the screening/alert
                now = db.utcnow()
                cursor = conn.execute(
                    "INSERT INTO screenings (org_id, customer_id, query_name, trigger, "
                    "algorithm, threshold, run_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (1, customer_a_id, 'test', 'manual', 'fuzzy', 0.85, now)
                )
                screening_id = cursor.lastrowid
                # Small delay to ensure alert created_at is >= run_ts
                time.sleep(0.01)
                alert_ts = db.utcnow()
                conn.execute(
                    "INSERT INTO alerts (screening_id, org_id, entity_id, score, "
                    "score_detail, matched_name, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (screening_id, 1, 1, 95.5, 'test', 'Test Entity', 'open', alert_ts)
                )
                # Commit the alert (simulating what _persist does in the real code)
                conn.commit()
                # Now raise to simulate rescreen_all failing mid-way
                raise RuntimeError("Simulated failure in org A")
            else:
                # Org B: succeed normally
                return {"screened": 10, "alerts": 0}

        def mock_reassess_risk(conn, customer_id, org_id, actor):
            reassess_calls.append((customer_id, org_id))
            # Record that reassessment happened by creating a dummy risk_assessments row
            now = db.utcnow()
            conn.execute(
                "INSERT INTO risk_assessments (org_id, customer_id, score, rating, "
                "factors, ruleset_version, assessed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (org_id, customer_id, 50.0, 'medium', '{}', '1.0', now)
            )
            return True  # Updated

        with patch("scripts.auto_rescreen.rescreen_all", side_effect=mock_rescreen_all):
            with patch("scripts.auto_rescreen.reassess_risk", side_effect=mock_reassess_risk):
                with patch("scripts.auto_rescreen.connect", return_value=db.connect(db_path)):
                    with patch("scripts.auto_rescreen._lists_are_current", return_value=True):
                        exit_code = auto_rescreen.main()

        # Verify both orgs were attempted
        assert len(orgs_rescreened) == 2, \
            f"Both orgs should be attempted, got {len(orgs_rescreened)}: {orgs_rescreened}"
        assert orgs_rescreened == [1, 2], f"Expected [1, 2], got {orgs_rescreened}"

        # Verify Org A's customer was reassessed (the critical fix)
        assert (customer_a_id, 1) in reassess_calls, \
            f"Customer {customer_a_id} in org 1 should have been reassessed, calls: {reassess_calls}"

        # Verify the rescreen.org_failed audit row was created
        conn = db.connect(db_path)
        try:
            audit_rows = conn.execute(
                "SELECT * FROM audit_log WHERE action = 'rescreen.org_failed' AND object_id = '1'"
            ).fetchall()
            assert len(audit_rows) > 0, \
                "Should have audit row for rescreen.org_failed for org 1"
        finally:
            conn.close()

        # Verify exit code is 1 (failure)
        assert exit_code == 1, f"Expected exit code 1 (failure), got {exit_code}"
