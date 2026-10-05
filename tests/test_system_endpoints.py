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


# ------------------------------------------------ /system/check-freeze-obligations
#
# Hourly Cloud Scheduler call that emails MLROs about TFS freeze obligations
# still pending execution after 24h (compliance finding 2.2). Real SQLite;
# only the outbound email function is replaced so sends can be counted.

def _seed_overdue_freeze(db_file, *, hours_old=36, with_mlro=True, org_slug="frz-org"):
    from datetime import datetime, timedelta, timezone
    from amlkit.db import connect, utcnow

    conn = connect(db_file)
    now = utcnow()
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?, ?, 'active', ?)",
                 ("Freeze Org", org_slug, now))
    org_id = conn.execute("SELECT id FROM organizations WHERE slug=?", (org_slug,)).fetchone()[0]
    if with_mlro:
        conn.execute(
            """INSERT INTO operators (org_id, name, email, password_hash, role, is_active,
               failed_login_count, created_at) VALUES (?, 'MLRO', 'mlro@freeze.test', 'x', 'mlro', 1, 0, ?)""",
            (org_id, now))
    conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
           onboarded_at, status, created_at, updated_at)
           VALUES (?, 'C-001', 'Test Customer', 'natural', 'test', ?, 'active', ?, ?)""",
        (org_id, now, now, now))
    cust_id = conn.execute("SELECT id FROM customers WHERE org_id=?", (org_id,)).fetchone()[0]
    identified = (datetime.now(timezone.utc) - timedelta(hours=hours_old)).isoformat()
    conn.execute(
        """INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
           identified_at, identified_by, status)
           VALUES (?, ?, 'sanctions', 'critical', ?, 'mlro', 'pending_execution')""",
        (org_id, cust_id, identified))
    conn.commit()
    ob_id = conn.execute("SELECT id FROM freeze_obligations WHERE org_id=?", (org_id,)).fetchone()[0]
    conn.close()
    return org_id, ob_id


@pytest.fixture()
def sent_alerts(monkeypatch):
    """Count freeze alert emails instead of sending/printing them."""
    from amlkit import mail
    sent: list[dict] = []

    def fake(**kw):
        sent.append(kw)
        return mail.SENT

    monkeypatch.setattr(mail, "send_freeze_obligation_alert", fake)
    return sent


class TestSystemCheckFreezeObligationsAuth:
    URL = "/system/check-freeze-obligations"

    def test_disabled_without_secret_configured(self, client) -> None:
        r = client.post(self.URL, data="")
        assert r.status_code == 403
        assert "SCHEDULER_SECRET" in r.json()["error"]

    def test_rejects_missing_bearer_token(self, client, monkeypatch) -> None:
        monkeypatch.setenv("SCHEDULER_SECRET", "correct-secret")
        assert client.post(self.URL, data="").status_code == 401

    def test_rejects_wrong_bearer_token(self, client, monkeypatch) -> None:
        monkeypatch.setenv("SCHEDULER_SECRET", "correct-secret")
        r = client.post(self.URL, data="", headers={"Authorization": "Bearer wrong-secret"})
        assert r.status_code == 401

    def test_admin_api_secret_does_not_unlock_it(self, client, monkeypatch) -> None:
        monkeypatch.setenv("ADMIN_API_SECRET", "admin-secret")
        r = client.post(self.URL, data="", headers={"Authorization": "Bearer admin-secret"})
        assert r.status_code in (401, 403)
        monkeypatch.setenv("SCHEDULER_SECRET", "scheduler-secret")
        r = client.post(self.URL, data="", headers={"Authorization": "Bearer admin-secret"})
        assert r.status_code == 401

    def test_scheduler_secret_unlocks_it(self, client, monkeypatch) -> None:
        monkeypatch.setenv("SCHEDULER_SECRET", "scheduler-secret")
        r = client.post(self.URL, data="", headers={"Authorization": "Bearer scheduler-secret"})
        assert r.status_code == 200
        assert r.json()["overdue"] == 0


class TestSystemCheckFreezeObligations:
    URL = "/system/check-freeze-obligations"
    HEADERS = {"Authorization": "Bearer scheduler-secret"}

    @pytest.fixture(autouse=True)
    def _secret(self, client, monkeypatch):
        # depends on `client` so its delenv runs first, then we set the secret
        monkeypatch.setenv("SCHEDULER_SECRET", "scheduler-secret")

    def test_returns_counts_and_alerts_mlro_for_overdue_obligation(self, client, tmp_path, sent_alerts) -> None:
        _org, ob_id = _seed_overdue_freeze(tmp_path / "test.db")
        r = client.post(self.URL, data="", headers=self.HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "complete"
        assert body["overdue"] == 1
        assert body["newly_notified"] == 1
        assert body["orgs_with_overdue"] == 1
        assert body["failures"] == []
        assert len(sent_alerts) == 1
        assert sent_alerts[0]["to_email"] == "mlro@freeze.test"
        assert sent_alerts[0]["freeze_obligation_id"] == ob_id

    def test_does_not_renotify_on_second_call(self, client, tmp_path, sent_alerts) -> None:
        _seed_overdue_freeze(tmp_path / "test.db")
        first = client.post(self.URL, data="", headers=self.HEADERS).json()
        second = client.post(self.URL, data="", headers=self.HEADERS).json()
        third = client.post(self.URL, data="", headers=self.HEADERS).json()
        assert first["newly_notified"] == 1
        # Still reported as overdue (the gap is real) but not re-emailed.
        assert second["overdue"] == 1 and second["newly_notified"] == 0
        assert third["overdue"] == 1 and third["newly_notified"] == 0
        assert len(sent_alerts) == 1

    def test_not_yet_overdue_obligation_is_ignored(self, client, tmp_path, sent_alerts) -> None:
        _seed_overdue_freeze(tmp_path / "test.db", hours_old=2)
        body = client.post(self.URL, data="", headers=self.HEADERS).json()
        assert body["overdue"] == 0 and body["newly_notified"] == 0
        assert sent_alerts == []

    def test_obligation_becoming_overdue_later_is_alerted_then(self, client, tmp_path, sent_alerts) -> None:
        """Not overdue on one call; alerted on the first call after it
        crosses 24h, and only then."""
        from amlkit.db import connect
        from datetime import datetime, timedelta, timezone
        db_file = tmp_path / "test.db"
        _org, ob_id = _seed_overdue_freeze(db_file, hours_old=2)
        assert client.post(self.URL, data="", headers=self.HEADERS).json()["newly_notified"] == 0
        conn = connect(db_file)
        conn.execute("UPDATE freeze_obligations SET identified_at=? WHERE id=?",
                     ((datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(), ob_id))
        conn.commit()
        conn.close()
        assert client.post(self.URL, data="", headers=self.HEADERS).json()["newly_notified"] == 1
        assert client.post(self.URL, data="", headers=self.HEADERS).json()["newly_notified"] == 0
        assert len(sent_alerts) == 1

    def test_failed_send_is_retried_next_call(self, client, tmp_path, monkeypatch) -> None:
        from amlkit import mail
        outcomes = [mail.FAILED, mail.SENT]
        calls: list[int] = []

        def flaky(**kw):
            calls.append(kw["freeze_obligation_id"])
            return outcomes[len(calls) - 1]

        monkeypatch.setattr(mail, "send_freeze_obligation_alert", flaky)
        _seed_overdue_freeze(tmp_path / "test.db")
        first = client.post(self.URL, data="", headers=self.HEADERS).json()
        second = client.post(self.URL, data="", headers=self.HEADERS).json()
        third = client.post(self.URL, data="", headers=self.HEADERS).json()
        assert [first["newly_notified"], second["newly_notified"], third["newly_notified"]] == [0, 1, 0]
        assert len(calls) == 2

    def test_no_active_mlro_means_no_mark_and_retry(self, client, tmp_path, sent_alerts) -> None:
        from amlkit.db import connect
        db_file = tmp_path / "test.db"
        org_id, ob_id = _seed_overdue_freeze(db_file, with_mlro=False)
        body = client.post(self.URL, data="", headers=self.HEADERS).json()
        assert body["overdue"] == 1 and body["newly_notified"] == 0
        conn = connect(db_file)
        row = conn.execute("SELECT overdue_notified_at FROM freeze_obligations WHERE id=?", (ob_id,)).fetchone()
        assert row["overdue_notified_at"] is None
        conn.execute(
            """INSERT INTO operators (org_id, name, email, password_hash, role, is_active,
               failed_login_count, created_at) VALUES (?, 'MLRO', 'late@freeze.test', 'x', 'mlro', 1, 0, '2026-01-01')""",
            (org_id,))
        conn.commit()
        conn.close()
        assert client.post(self.URL, data="", headers=self.HEADERS).json()["newly_notified"] == 1
        assert [a["to_email"] for a in sent_alerts] == ["late@freeze.test"]

    def test_audit_row_written_once_not_per_call(self, client, tmp_path, sent_alerts) -> None:
        from amlkit.db import connect
        db_file = tmp_path / "test.db"
        _seed_overdue_freeze(db_file)
        for _ in range(3):
            client.post(self.URL, data="", headers=self.HEADERS)
        conn = connect(db_file)
        n = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='freeze.overdue_check'").fetchone()[0]
        conn.close()
        assert n == 1

    def test_returns_500_when_the_check_blows_up(self, client, monkeypatch) -> None:
        def boom(conn):
            raise RuntimeError("db exploded")
        monkeypatch.setattr("amlkit.cases.scheduler.run_freeze_obligation_check", boom)
        r = client.post(self.URL, data="", headers=self.HEADERS)
        assert r.status_code == 500
        assert r.json()["status"] == "error"

    def test_org_failure_returns_500_with_failure_listed(self, client, tmp_path, sent_alerts, monkeypatch) -> None:
        from amlkit.cases import manager
        db_file = tmp_path / "test.db"
        bad_org, _ = _seed_overdue_freeze(db_file, org_slug="bad-org")
        real = manager.check_unexecuted_freeze_obligations

        def selective(conn, org_id):
            if org_id == bad_org:
                raise RuntimeError("bad org")
            return real(conn, org_id)

        monkeypatch.setattr(manager, "check_unexecuted_freeze_obligations", selective)
        r = client.post(self.URL, data="", headers=self.HEADERS)
        assert r.status_code == 500
        assert len(r.json()["failures"]) == 1
