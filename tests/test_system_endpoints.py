"""Tests for the trusted system-level endpoints -- /system/refresh and
/system/create-operator. Both exist specifically because some actions need
to happen without an interactive browser session (a Cloud Scheduler call,
provisioning a test account on a deployment nobody is logged into), so what
matters most here is that they're correctly locked down by default and that
their secrets are independent of each other.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("SCHEDULER_SECRET", raising=False)
    monkeypatch.delenv("ADMIN_API_SECRET", raising=False)

    from amlkit.db import connect
    connect(db_file).close()  # initialize schema before any request touches the file

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    return TestClient(app)


class TestSystemRefreshAuth:
    def test_disabled_without_secret_configured(self, client) -> None:
        r = client.post("/system/refresh", data="")
        assert r.status_code == 403
        assert "SCHEDULER_SECRET" in r.json()["error"]

    def test_rejects_missing_bearer_token(self, client, monkeypatch) -> None:
        monkeypatch.setenv("SCHEDULER_SECRET", "correct-secret")
        r = client.post("/system/refresh", data="")
        assert r.status_code == 401

    def test_rejects_wrong_bearer_token(self, client, monkeypatch) -> None:
        monkeypatch.setenv("SCHEDULER_SECRET", "correct-secret")
        r = client.post("/system/refresh", data="", headers={"Authorization": "Bearer wrong-secret"})
        assert r.status_code == 401

    def test_admin_api_secret_does_not_also_unlock_refresh(self, client, monkeypatch) -> None:
        """The two endpoints must not share a secret -- provisioning a
        login is a materially more sensitive capability than re-running a
        read-mostly sanctions refresh, so a leaked refresh secret must not
        also be able to create operator accounts, or vice versa."""
        monkeypatch.setenv("ADMIN_API_SECRET", "admin-secret")
        r = client.post("/system/refresh", data="", headers={"Authorization": "Bearer admin-secret"})
        assert r.status_code in (401, 403)


class TestSystemCreateOperatorAuth:
    def test_disabled_without_secret_configured(self, client) -> None:
        r = client.post("/system/create-operator", json={"name": "x", "email": "x@test.invalid", "password": "a-strong-password-1"})
        assert r.status_code == 403
        assert "ADMIN_API_SECRET" in r.json()["error"]

    def test_rejects_wrong_bearer_token(self, client, monkeypatch) -> None:
        monkeypatch.setenv("ADMIN_API_SECRET", "correct-secret")
        r = client.post(
            "/system/create-operator",
            json={"name": "x", "email": "x@test.invalid", "password": "a-strong-password-1"},
            headers={"Authorization": "Bearer wrong-secret"},
        )
        assert r.status_code == 401

    def test_scheduler_secret_does_not_also_unlock_operator_creation(self, client, monkeypatch) -> None:
        monkeypatch.setenv("SCHEDULER_SECRET", "scheduler-secret")
        r = client.post(
            "/system/create-operator",
            json={"name": "x", "email": "x@test.invalid", "password": "a-strong-password-1"},
            headers={"Authorization": "Bearer scheduler-secret"},
        )
        assert r.status_code in (401, 403)


class TestSystemCreateOperatorBehavior:
    @pytest.fixture(autouse=True)
    def _secret(self, client, monkeypatch):
        # Depends on `client` explicitly so it resolves (and clears both
        # secret env vars as part of DB setup) BEFORE this sets one --
        # otherwise fixture ordering could let client's unconditional
        # delenv wipe out the secret this sets.
        monkeypatch.setenv("ADMIN_API_SECRET", "test-admin-secret")
        self.headers = {"Authorization": "Bearer test-admin-secret"}

    @pytest.fixture()
    def seeded_org(self, client):
        """create-operator needs an existing active org to attach to --
        seed one directly, the same way test_api.py's fixtures do, rather
        than going through the full registration flow."""
        import sqlite3
        from amlkit.db import utcnow

        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
            ("Test Org", "test-org", "active", utcnow()),
        )
        conn.commit()
        conn.close()
        return "test-org"

    def test_creates_operator_with_hashed_password(self, client, seeded_org) -> None:
        r = client.post(
            "/system/create-operator",
            json={"name": "Fawaz", "email": "fawaz@grovisor.test",
                  "password": "Fawaz@2025", "role": "officer", "org_slug": seeded_org},
            headers=self.headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "created"
        assert body["email"] == "fawaz@grovisor.test"
        assert body["role"] == "officer"

        import sqlite3
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM operators WHERE email='fawaz@grovisor.test'").fetchone()
        conn.close()
        assert row is not None
        assert row["password_hash"] != "Fawaz@2025"  # never stored raw

        from amlkit.auth import verify_password
        assert verify_password("Fawaz@2025", row["password_hash"])

    def test_rejects_short_password(self, client, seeded_org) -> None:
        r = client.post(
            "/system/create-operator",
            json={"name": "x", "email": "x@grovisor.test", "password": "short", "org_slug": seeded_org},
            headers=self.headers,
        )
        assert r.status_code == 400

    def test_rejects_invalid_role(self, client, seeded_org) -> None:
        r = client.post(
            "/system/create-operator",
            json={"name": "x", "email": "x@grovisor.test", "password": "a-strong-password-1",
                  "role": "superuser", "org_slug": seeded_org},
            headers=self.headers,
        )
        assert r.status_code == 400

    def test_duplicate_email_rejected(self, client, seeded_org) -> None:
        payload = {"name": "x", "email": "dup@grovisor.test", "password": "a-strong-password-1", "org_slug": seeded_org}
        r1 = client.post("/system/create-operator", json=payload, headers=self.headers)
        assert r1.status_code == 200
        r2 = client.post("/system/create-operator", json=payload, headers=self.headers)
        assert r2.status_code == 409

    def test_unknown_org_slug_rejected(self, client, seeded_org) -> None:
        r = client.post(
            "/system/create-operator",
            json={"name": "x", "email": "x@grovisor.test", "password": "a-strong-password-1",
                  "org_slug": "does-not-exist"},
            headers=self.headers,
        )
        assert r.status_code == 404

    def test_defaults_to_the_only_active_org_when_slug_omitted(self, client, seeded_org) -> None:
        r = client.post(
            "/system/create-operator",
            json={"name": "x", "email": "noorg@grovisor.test", "password": "a-strong-password-1"},
            headers=self.headers,
        )
        assert r.status_code == 200
        assert r.json()["organization"] == "Test Org"
