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
