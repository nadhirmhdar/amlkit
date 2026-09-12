"""Tests for the /health endpoint.

Returns overall system health based on sanctions list staleness.
A mandatory list older than its max_age_hours marks the system degraded.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    from amlkit.db import connect
    connect(db_file).close()

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    return TestClient(app)


def _db():
    import sqlite3
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


class TestHealthEndpoint:
    def test_returns_200_json(self, client) -> None:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert "status" in body

    def test_healthy_when_mandatory_lists_fresh(self, client) -> None:
        conn = _db()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO datasets (key, title, is_mandatory, last_refresh, entity_count, max_age_hours) "
            "VALUES (?,?,?,?,?,?)",
            ("test_list", "Test List", 1, now, 100, 24),
        )
        conn.commit()
        conn.close()

        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "healthy"

    def test_degraded_when_mandatory_list_stale(self, client) -> None:
        conn = _db()
        stale = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO datasets (key, title, is_mandatory, last_refresh, entity_count, max_age_hours) "
            "VALUES (?,?,?,?,?,?)",
            ("test_list", "Test List", 1, stale, 100, 24),
        )
        conn.commit()
        conn.close()

        r = client.get("/health")
        body = r.json()
        assert body["status"] == "degraded"
        assert any(d["breach"] for d in body["datasets"])

    def test_degraded_when_mandatory_list_never_refreshed(self, client) -> None:
        conn = _db()
        conn.execute(
            "INSERT INTO datasets (key, title, is_mandatory, last_refresh, entity_count, max_age_hours) "
            "VALUES (?,?,?,?,?,?)",
            ("test_list", "Test List", 1, None, 0, 24),
        )
        conn.commit()
        conn.close()

        r = client.get("/health")
        body = r.json()
        assert body["status"] == "degraded"

    def test_healthy_when_only_non_mandatory_stale(self, client) -> None:
        conn = _db()
        stale = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO datasets (key, title, is_mandatory, last_refresh, entity_count, max_age_hours) "
            "VALUES (?,?,?,?,?,?)",
            ("optional_list", "Optional List", 0, stale, 50, 24),
        )
        conn.commit()
        conn.close()

        r = client.get("/health")
        body = r.json()
        assert body["status"] == "healthy"

    def test_no_auth_required(self, client) -> None:
        """Health checks must work without a session — monitoring tools won't have one."""
        r = client.get("/health")
        assert r.status_code == 200
