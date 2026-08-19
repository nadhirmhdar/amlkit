"""Connection-level configuration tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect  # noqa: E402


class TestBusyTimeout:
    def test_busy_timeout_is_configured(self) -> None:
        """Without this, two connections writing at once fail immediately
        with 'database is locked' instead of one waiting for the other --
        exactly what happened in production when a scheduled refresh
        (which now holds a connection open for the whole synchronous
        refresh) overlapped with another write."""
        conn = connect(":memory:")
        try:
            timeout_ms = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            assert timeout_ms >= 30000
        finally:
            conn.close()
