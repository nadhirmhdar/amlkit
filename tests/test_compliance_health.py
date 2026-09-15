"""Regression tests for the compliance-health / refresh-observability feature.

These cover the exact gap that let a schema bug ship green: the
/admin/compliance dashboard and the record/clear-error helpers were added
with zero test coverage, so `last_error`/`error_at` being absent from the
fresh-install CREATE TABLE (present only in _MIGRATIONS) went unnoticed until
the route was actually hit.

The load-path assertions here are deliberately DB-level (record_dataset_error
/ clear_dataset_error) rather than driving a live adapter, so they stay
hermetic and network-free like the rest of the suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Reuse the wired-up, logged-in-as-MLRO client and the sanctions seeder.
from test_api import client, _seed_sanctions_data, _csrf  # noqa: E402,F401


class TestDatasetErrorColumns:
    """The columns must exist on a FRESH database, not only after a
    migration runs. connect(':memory:') builds from CREATE TABLE and never
    touches _MIGRATIONS, so this is the assertion the original PR lacked."""

    def test_fresh_db_has_error_columns(self) -> None:
        from amlkit.db import connect

        conn = connect(":memory:")
        # Would raise sqlite3.OperationalError: no such column before the fix.
        # (connect() seeds default dataset rows, so we assert the SELECT
        # succeeds rather than asserting an empty result.)
        conn.execute("SELECT key, last_error, error_at FROM datasets").fetchall()
        conn.close()

    def test_record_dataset_error_persists(self) -> None:
        from amlkit.db import connect, upsert_dataset, record_dataset_error

        conn = connect(":memory:")
        upsert_dataset(conn, "ofac_sdn", "OFAC SDN", is_mandatory=True)
        record_dataset_error(conn, "ofac_sdn", "HTTP 429 rate limited")

        row = conn.execute(
            "SELECT last_error, error_at FROM datasets WHERE key='ofac_sdn'"
        ).fetchone()
        assert row["last_error"] == "HTTP 429 rate limited"
        assert row["error_at"] is not None
        conn.close()

    def test_clear_dataset_error_resets(self) -> None:
        from amlkit.db import (
            connect, upsert_dataset, record_dataset_error, clear_dataset_error,
        )

        conn = connect(":memory:")
        upsert_dataset(conn, "un_consolidated", "UN", is_mandatory=True)
        record_dataset_error(conn, "un_consolidated", "boom")
        clear_dataset_error(conn, "un_consolidated")

        row = conn.execute(
            "SELECT last_error, error_at FROM datasets WHERE key='un_consolidated'"
        ).fetchone()
        assert row["last_error"] is None
        assert row["error_at"] is None
        conn.close()

    def test_record_on_missing_dataset_is_noop(self) -> None:
        """A source can fail before its dataset row is ever upserted; the
        UPDATE simply matches nothing rather than raising."""
        from amlkit.db import connect, record_dataset_error

        conn = connect(":memory:")
        before = conn.execute(
            "SELECT COUNT(*) c FROM datasets WHERE key='never_seen'"
        ).fetchone()["c"]
        record_dataset_error(conn, "never_seen", "boom")  # must not raise
        after = conn.execute(
            "SELECT COUNT(*) c FROM datasets WHERE key='never_seen'"
        ).fetchone()["c"]
        assert before == 0 and after == 0  # no row created, no error
        conn.close()


class TestComplianceRoute:
    """The route that actually 500'd. A single GET as an MLRO would have
    caught the shipped bug."""

    def test_compliance_page_renders_for_mlro(self, client) -> None:
        r = client.get("/admin/compliance")
        assert r.status_code == 200
        # Seeded dataset from the fixture is fresh + error-free => OK.
        assert "OK" in r.text

    def test_compliance_page_shows_recorded_error(self, client) -> None:
        import os
        from amlkit.db import connect, record_dataset_error

        conn = connect(os.environ["AMLKIT_DB"])
        record_dataset_error(conn, "test_list", "OFAC: HTTP 429 rate limited")
        conn.close()

        r = client.get("/admin/compliance")
        assert r.status_code == 200
        assert "FAIL" in r.text
        assert "429" in r.text

    def test_compliance_requires_auth(self) -> None:
        """An unauthenticated request is redirected to /login, never served
        the dashboard."""
        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        c = TestClient(app)
        r = c.get("/admin/compliance", follow_redirects=False)
        assert r.status_code in (302, 303)
        assert "/login" in r.headers.get("location", "")
