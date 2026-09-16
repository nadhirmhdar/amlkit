"""Test db_index_audit.py script runs without errors."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_db_index_audit_exits_cleanly():
    """db_index_audit.py runs and exits 0 or 1 without touching AMLKIT_DB.

    The script creates its own throwaway database in a tempdir, so it's
    safe to run in CI. Exit code 0 means all hot paths are indexed, 1
    means some fall back to full scans (which gates CI if uncommented).
    """
    result = subprocess.run(
        [sys.executable, "scripts/db_index_audit.py"],
        capture_output=True,
        text=True,
    )

    # Should exit 0 (all covered) or 1 (some full scans found)
    assert result.returncode in (0, 1), f"Unexpected exit code: {result.returncode}"

    # Should produce output
    assert "amlkit DB index audit" in result.stdout
    assert "RESULT:" in result.stdout

    # Should not error
    assert "Traceback" not in result.stderr
