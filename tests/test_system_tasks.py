"""Tests for POST /system/tasks/<job> — Cloud Tasks handler endpoint.

Verifies auth, cross-org rejection, idempotency, and payload validation.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.setenv("SCHEDULER_SECRET", "test-task-secret")

    from amlkit.db import connect
    connect(db_file).close()

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    return TestClient(app)


@pytest.fixture()
def seeded_org(client):
    """Seed an active org so task handler can validate org_id."""
    from amlkit.db import utcnow

    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
        ("Test Org", "test-org", "active", utcnow()),
    )
    conn.commit()
    org_id = conn.execute("SELECT id FROM organizations WHERE slug='test-org'").fetchone()["id"]
    conn.close()
    return org_id


AUTH_HEADERS = {"Authorization": "Bearer test-task-secret"}


class TestTaskHandlerAuth:
    def test_rejects_missing_auth(self, client):
        r = client.post("/system/tasks/rescreen", json={"job_name": "rescreen", "org_id": 1})
        assert r.status_code == 401

    def test_rejects_wrong_bearer_token(self, client):
        r = client.post(
            "/system/tasks/rescreen",
            json={"job_name": "rescreen", "org_id": 1},
            headers={"Authorization": "Bearer wrong-secret"},
        )
        assert r.status_code == 401

    def test_accepts_correct_bearer_token(self, client, seeded_org):
        r = client.post(
            "/system/tasks/rescreen",
            json={"job_name": "rescreen", "org_id": seeded_org},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200


class TestTaskHandlerValidation:
    def test_rejects_missing_job_name(self, client):
        r = client.post(
            "/system/tasks/rescreen",
            json={"org_id": 1},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 400
        assert "job_name" in r.json()["error"]

    def test_rejects_missing_org_id(self, client):
        r = client.post(
            "/system/tasks/rescreen",
            json={"job_name": "rescreen"},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 400
        assert "org_id" in r.json()["error"]

    def test_rejects_job_name_mismatch(self, client, seeded_org):
        r = client.post(
            "/system/tasks/rescreen",
            json={"job_name": "adverse_media", "org_id": seeded_org},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 400
        assert "mismatch" in r.json()["error"]

    def test_rejects_pii_in_payload(self, client, seeded_org):
        r = client.post(
            "/system/tasks/adverse_media",
            json={"job_name": "adverse_media", "org_id": seeded_org, "name": "John Doe"},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 400
        assert "PII" in r.json()["error"]

    def test_rejects_unknown_org_id(self, client):
        r = client.post(
            "/system/tasks/rescreen",
            json={"job_name": "rescreen", "org_id": 99999},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 404

    def test_rejects_unknown_job_name(self, client, seeded_org):
        r = client.post(
            "/system/tasks/nonexistent_job",
            json={"job_name": "nonexistent_job", "org_id": seeded_org},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 500


class TestTaskHandlerExecution:
    def test_rescreen_runs_successfully(self, client, seeded_org):
        r = client.post(
            "/system/tasks/rescreen",
            json={"job_name": "rescreen", "org_id": seeded_org},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "complete"

    def test_adverse_media_requires_customer_id(self, client, seeded_org):
        r = client.post(
            "/system/tasks/adverse_media",
            json={"job_name": "adverse_media", "org_id": seeded_org},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 500
        assert "customer_id" in r.json()["error"]

    def test_invalid_json_rejected(self, client):
        r = client.post(
            "/system/tasks/rescreen",
            content=b"not json",
            headers={**AUTH_HEADERS, "Content-Type": "application/json"},
        )
        assert r.status_code == 400
