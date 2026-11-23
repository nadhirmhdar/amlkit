"""POST /system/grant-trial: owner-granted dated trial (org + first MLRO)
without Stripe Checkout, behind ADMIN_API_SECRET."""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BODY = {"org_name": "Eigen One Real Estate", "name": "Eigen One",
        "email": "Trial@Example.test", "password": "Strong@Pass1", "days": 5}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("ADMIN_API_SECRET", raising=False)
    monkeypatch.delenv("SCHEDULER_SECRET", raising=False)
    from amlkit.db import connect
    connect(db_file).close()
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    return TestClient(app)


@pytest.fixture()
def headers(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_SECRET", "admin-secret")
    return {"Authorization": "Bearer admin-secret"}


def _db():
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


def test_disabled_without_secret(client):
    assert client.post("/system/grant-trial", json=BODY).status_code == 403


def test_wrong_secret(client, headers):
    r = client.post("/system/grant-trial", json=BODY, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_scheduler_secret_does_not_unlock(client, monkeypatch):
    monkeypatch.setenv("SCHEDULER_SECRET", "sched")
    r = client.post("/system/grant-trial", json=BODY, headers={"Authorization": "Bearer sched"})
    assert r.status_code in (401, 403)


def test_creates_dated_trial_org_and_verified_mlro(client, headers):
    r = client.post("/system/grant-trial", json=BODY, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "trial@example.test" and body["role"] == "mlro"
    conn = _db()
    org = conn.execute("SELECT * FROM organizations WHERE id=?", (body["org_id"],)).fetchone()
    op = conn.execute("SELECT * FROM operators WHERE id=?", (body["operator_id"],)).fetchone()
    audits = [r["action"] for r in conn.execute(
        "SELECT action FROM audit_log WHERE org_id=?", (body["org_id"],))]
    conn.close()
    assert org["plan"] == "trial" and org["plan_status"] == "trialing"
    ends = datetime.fromisoformat(org["trial_ends_at"])
    expected = datetime.now(timezone.utc) + timedelta(days=5)
    assert abs((ends - expected).total_seconds()) < 60
    assert op["email_verified_at"] and op["password_hash"] != BODY["password"]
    assert "billing.trial_granted" in audits

    from amlkit.billing import limits
    conn = _db()
    st = limits.org_state(conn, body["org_id"])
    conn.close()
    assert not st.legacy and not st.write_blocked and st.plan.key == "starter"


def test_operator_can_sign_in(client, headers):
    client.post("/system/grant-trial", json=BODY, headers=headers)
    from amlkit import auth
    conn = _db()
    row = conn.execute("SELECT password_hash FROM operators WHERE email='trial@example.test'").fetchone()
    conn.close()
    assert auth.verify_password(BODY["password"], row["password_hash"])


def test_duplicate_email_is_409(client, headers):
    assert client.post("/system/grant-trial", json=BODY, headers=headers).status_code == 200
    r = client.post("/system/grant-trial", json={**BODY, "org_name": "Other Firm"}, headers=headers)
    assert r.status_code == 409


@pytest.mark.parametrize("days", [0, -1, 91, "5", 2.5, True])
def test_bad_days_is_400(client, headers, days):
    r = client.post("/system/grant-trial", json={**BODY, "days": days}, headers=headers)
    assert r.status_code == 400


def test_weak_password_is_400(client, headers):
    r = client.post("/system/grant-trial", json={**BODY, "password": "eigenone@123"}, headers=headers)
    assert r.status_code == 400
    conn = _db()
    assert conn.execute("SELECT COUNT(*) FROM organizations").fetchone()[0] == 0
    conn.close()
