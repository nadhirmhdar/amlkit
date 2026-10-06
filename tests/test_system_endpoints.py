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

def _seed_overdue_freeze(db_file, *, hours_old=36, with_mlro=True, org_slug="frz-org",
                         org_name="Freeze Org", mlro_email="mlro@freeze.test",
                         status="pending_execution"):
    from datetime import datetime, timedelta, timezone
    from amlkit.db import connect, utcnow

    conn = connect(db_file)
    now = utcnow()
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?, ?, 'active', ?)",
                 (org_name, org_slug, now))
    org_id = conn.execute("SELECT id FROM organizations WHERE slug=?", (org_slug,)).fetchone()[0]
    if with_mlro:
        conn.execute(
            """INSERT INTO operators (org_id, name, email, password_hash, role, is_active,
               failed_login_count, created_at) VALUES (?, 'MLRO', ?, 'x', 'mlro', 1, 0, ?)""",
            (org_id, mlro_email, now))
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
           VALUES (?, ?, 'sanctions', 'critical', ?, 'mlro', ?)""",
        (org_id, cust_id, identified, status))
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


# ----------------------------------- review fixes (PR #419): delivery semantics
#
# The mark (overdue_notified_at) must only be written for a delivered email;
# the write lock must never be held across an SMTP call; a lock error while
# marking must not 500 the route (Cloud Scheduler would retry up to 3x and
# re-send each time).

def _notified_at(db_file, ob_id):
    from amlkit.db import connect
    conn = connect(db_file)
    try:
        return conn.execute(
            "SELECT overdue_notified_at FROM freeze_obligations WHERE id=?", (ob_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def _fast_fail_connect(monkeypatch):
    """Make the route's own connection give up on a lock immediately instead of
    waiting out the production 30s busy_timeout."""
    import amlkit.db as dbmod
    real = dbmod.connect

    def connect(path=None):
        c = real(path)
        c.execute("PRAGMA busy_timeout=0")
        return c

    monkeypatch.setattr(dbmod, "connect", connect)


class TestDeliverySemantics:
    URL = "/system/check-freeze-obligations"
    HEADERS = {"Authorization": "Bearer scheduler-secret"}

    @pytest.fixture(autouse=True)
    def _secret(self, client, monkeypatch):
        monkeypatch.setenv("SCHEDULER_SECRET", "scheduler-secret")

    def test_not_configured_is_not_marked_and_is_retried(self, client, tmp_path, monkeypatch, caplog) -> None:
        from amlkit import mail
        outcomes = [mail.NOT_CONFIGURED, mail.NOT_CONFIGURED, mail.SENT]
        calls: list[int] = []

        def fake(**kw):
            calls.append(kw["freeze_obligation_id"])
            return outcomes[len(calls) - 1]

        monkeypatch.setattr(mail, "send_freeze_obligation_alert", fake)
        db_file = tmp_path / "test.db"
        org_id, ob_id = _seed_overdue_freeze(db_file)

        with caplog.at_level("WARNING"):
            first = client.post(self.URL, data="", headers=self.HEADERS).json()
        assert first["newly_notified"] == 0 and first["unsent"] == 1 and first["overdue"] == 1
        assert _notified_at(db_file, ob_id) is None
        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert any(str(org_id) in w and str(ob_id) in w and "not_configured" in w for w in warnings)

        second = client.post(self.URL, data="", headers=self.HEADERS).json()
        assert second["newly_notified"] == 0 and second["unsent"] == 1
        third = client.post(self.URL, data="", headers=self.HEADERS).json()
        assert third["newly_notified"] == 1 and third["unsent"] == 0
        assert _notified_at(db_file, ob_id) is not None
        assert len(calls) == 3
        # Delivered: no more sends.
        assert client.post(self.URL, data="", headers=self.HEADERS).json()["unsent"] == 0
        assert len(calls) == 3

    def test_unsent_counts_no_mlro_and_failed(self, client, tmp_path, monkeypatch) -> None:
        from amlkit import mail
        monkeypatch.setattr(mail, "send_freeze_obligation_alert", lambda **kw: mail.FAILED)
        _seed_overdue_freeze(tmp_path / "test.db", org_slug="a", org_name="A")
        _seed_overdue_freeze(tmp_path / "test.db", org_slug="b", org_name="B", with_mlro=False)
        body = client.post(self.URL, data="", headers=self.HEADERS).json()
        assert body["overdue"] == 2 and body["newly_notified"] == 0 and body["unsent"] == 2
        assert body["unmarked"] == 0

    def test_send_happens_before_mark_and_outside_a_write_transaction(self, tmp_path, monkeypatch) -> None:
        """At send time the row is still unmarked (send-then-mark) and the
        connection holds no open transaction (no write lock across SMTP)."""
        from amlkit import mail
        from amlkit.db import connect
        from amlkit.cases.manager import check_unexecuted_freeze_obligations
        db_file = tmp_path / "t.db"
        org_id, ob_id = _seed_overdue_freeze(db_file)
        conn = connect(db_file)
        seen: list[tuple] = []

        def fake(**kw):
            seen.append((conn.in_transaction, _notified_at(db_file, kw["freeze_obligation_id"])))
            return mail.SENT

        monkeypatch.setattr(mail, "send_freeze_obligation_alert", fake)
        result = check_unexecuted_freeze_obligations(conn, org_id)
        assert seen == [(False, None)]
        assert result[0]["newly_notified"] is True
        assert conn.in_transaction is False  # committed, nothing left open
        assert _notified_at(db_file, ob_id) is not None
        conn.close()

    def test_no_transaction_open_before_each_send_with_several_obligations(self, tmp_path, monkeypatch) -> None:
        """The first mark must not leave a write transaction open through the
        remaining sends (each can take ~15s)."""
        from amlkit import mail
        from amlkit.db import connect
        from amlkit.cases.manager import check_unexecuted_freeze_obligations
        db_file = tmp_path / "t.db"
        org_id, _ = _seed_overdue_freeze(db_file)
        conn = connect(db_file)
        cust_id = conn.execute("SELECT id FROM customers WHERE org_id=?", (org_id,)).fetchone()[0]
        for _ in range(2):
            conn.execute(
                """INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
                   identified_at, identified_by, status)
                   VALUES (?, ?, 'sanctions', 'high', '2020-01-01T00:00:00+00:00', 'mlro', 'pending_execution')""",
                (org_id, cust_id))
        conn.commit()
        states: list[bool] = []

        def fake(**kw):
            states.append(conn.in_transaction)
            return mail.SENT

        monkeypatch.setattr(mail, "send_freeze_obligation_alert", fake)
        result = check_unexecuted_freeze_obligations(conn, org_id)
        assert len(result) == 3 and states == [False, False, False]
        conn.close()

    def test_lock_before_send_defers_without_emailing(self, client, tmp_path, sent_alerts, monkeypatch) -> None:
        """Another writer holds the lock for the whole Cloud Scheduler retry
        sequence: no 500, no email at all (so no duplicates), and the first run
        after the lock clears sends exactly once."""
        import sqlite3
        db_file = tmp_path / "test.db"
        _org, ob_id = _seed_overdue_freeze(db_file)
        _fast_fail_connect(monkeypatch)
        holder = sqlite3.connect(db_file, timeout=0, isolation_level=None, check_same_thread=False)
        holder.execute("BEGIN IMMEDIATE")
        try:
            for _ in range(3):  # Cloud Scheduler: first attempt + retries
                r = client.post(self.URL, data="", headers=self.HEADERS)
                assert r.status_code == 200
                assert r.json()["unsent"] == 1 and r.json()["newly_notified"] == 0
            assert sent_alerts == []
        finally:
            holder.execute("ROLLBACK")
            holder.close()
        body = client.post(self.URL, data="", headers=self.HEADERS).json()
        assert body["newly_notified"] == 1 and len(sent_alerts) == 1
        assert _notified_at(db_file, ob_id) is not None
        client.post(self.URL, data="", headers=self.HEADERS)
        assert len(sent_alerts) == 1

    def test_lock_arriving_between_send_and_mark_does_not_500(self, client, tmp_path, monkeypatch, caplog) -> None:
        """The lock lands during the SMTP call (after the pre-send probe), so
        the mark fails after the email went out. The route must not 500 (that
        is what made Cloud Scheduler retry and re-send); it reports `unmarked`
        and the next run, once the lock clears, re-sends once and marks."""
        import sqlite3
        from amlkit import mail
        db_file = tmp_path / "test.db"
        _org, ob_id = _seed_overdue_freeze(db_file)
        _fast_fail_connect(monkeypatch)
        holder = sqlite3.connect(db_file, timeout=0, isolation_level=None, check_same_thread=False)
        sent: list[int] = []

        def fake(**kw):
            sent.append(kw["freeze_obligation_id"])
            if len(sent) == 1:
                holder.execute("BEGIN IMMEDIATE")  # lock lands mid-send
            return mail.SENT

        monkeypatch.setattr(mail, "send_freeze_obligation_alert", fake)
        try:
            with caplog.at_level("ERROR"):
                r = client.post(self.URL, data="", headers=self.HEADERS)
            assert r.status_code == 200
            body = r.json()
            assert body["unmarked"] == 1 and body["unsent"] == 1 and body["newly_notified"] == 0
            assert body["failures"] == []
            assert any(str(ob_id) in rec.getMessage() for rec in caplog.records)
            # Next run while the lock is STILL held: the probe defers, no email.
            still = client.post(self.URL, data="", headers=self.HEADERS).json()
            assert still["newly_notified"] == 0 and still["unsent"] == 1 and len(sent) == 1
        finally:
            holder.execute("ROLLBACK")
            holder.close()
        assert _notified_at(db_file, ob_id) is None
        again = client.post(self.URL, data="", headers=self.HEADERS).json()
        assert again["newly_notified"] == 1 and again["unmarked"] == 0
        assert len(sent) == 2  # one bounded re-send, not one per scheduler retry
        client.post(self.URL, data="", headers=self.HEADERS)
        assert len(sent) == 2

    def test_executed_or_resolved_obligation_is_not_alerted(self, client, tmp_path, sent_alerts) -> None:
        db_file = tmp_path / "test.db"
        _seed_overdue_freeze(db_file, org_slug="ex", org_name="Ex", mlro_email="e@x.test", status="executed_pending_report")
        _seed_overdue_freeze(db_file, org_slug="rep", org_name="Rep", mlro_email="r@x.test", status="reported")
        _seed_overdue_freeze(db_file, org_slug="res", org_name="Res", mlro_email="s@x.test", status="resolved")
        body = client.post(self.URL, data="", headers=self.HEADERS).json()
        assert body["overdue"] == 0 and body["unsent"] == 0 and body["newly_notified"] == 0
        assert sent_alerts == []

    def test_multi_org_isolation_of_failure_recipients_and_audit(self, client, tmp_path, sent_alerts, monkeypatch) -> None:
        import json
        from amlkit.cases import manager
        from amlkit.db import connect
        db_file = tmp_path / "test.db"
        org_a, ob_a = _seed_overdue_freeze(db_file, org_slug="a", org_name="Org A", mlro_email="mlro-a@a.test")
        org_b, ob_b = _seed_overdue_freeze(db_file, org_slug="b", org_name="Org B", mlro_email="mlro-b@b.test")
        org_c, ob_c = _seed_overdue_freeze(db_file, org_slug="c", org_name="Org C", mlro_email="mlro-c@c.test")
        real = manager.check_unexecuted_freeze_obligations

        def selective(conn, org_id):
            if org_id == org_a:
                # leave a write transaction open, then blow up: must not
                # poison org B / C.
                conn.execute("UPDATE freeze_obligations SET notes='x' WHERE id=?", (ob_a,))
                raise RuntimeError("org A exploded")
            return real(conn, org_id)

        monkeypatch.setattr(manager, "check_unexecuted_freeze_obligations", selective)
        r = client.post(self.URL, data="", headers=self.HEADERS)
        assert r.status_code == 500
        body = r.json()
        assert len(body["failures"]) == 1 and "Org A" in body["failures"][0]
        assert body["newly_notified"] == 2

        by_ob = {kw["freeze_obligation_id"]: kw["to_email"] for kw in sent_alerts}
        assert by_ob == {ob_b: "mlro-b@b.test", ob_c: "mlro-c@c.test"}  # each MLRO: only their own org
        assert _notified_at(db_file, ob_a) is None
        assert _notified_at(db_file, ob_b) is not None and _notified_at(db_file, ob_c) is not None

        conn = connect(db_file)
        rows = conn.execute(
            "SELECT org_id, detail FROM audit_log WHERE action='freeze.overdue_check'").fetchall()
        conn.close()
        got = sorted((r_["org_id"], json.loads(r_["detail"])["notified_ids"][0]) for r_ in rows)
        assert got == sorted([(org_b, ob_b), (org_c, ob_c)])
        for r_ in rows:
            assert json.loads(r_["detail"])["org_id"] == r_["org_id"]

        # Scheduler retry (500) once org A recovers: only A is alerted now.
        monkeypatch.setattr(manager, "check_unexecuted_freeze_obligations", real)
        sent_alerts.clear()
        body = client.post(self.URL, data="", headers=self.HEADERS).json()
        assert body["failures"] == [] and body["newly_notified"] == 1
        assert [(kw["freeze_obligation_id"], kw["to_email"]) for kw in sent_alerts] == [(ob_a, "mlro-a@a.test")]


class TestOverdueNotifiedAtMigration:
    def test_migration_adds_column_to_a_db_that_lacks_it(self, tmp_path) -> None:
        import sqlite3
        from amlkit.db import connect, _migrate
        db_file = tmp_path / "old.db"
        connect(db_file).close()
        raw = sqlite3.connect(db_file)
        raw.row_factory = sqlite3.Row
        raw.execute("ALTER TABLE freeze_obligations DROP COLUMN overdue_notified_at")
        raw.commit()
        cols = {r["name"] for r in raw.execute("PRAGMA table_info(freeze_obligations)")}
        assert "overdue_notified_at" not in cols
        _migrate(raw)
        raw.commit()
        cols = {r["name"] for r in raw.execute("PRAGMA table_info(freeze_obligations)")}
        assert "overdue_notified_at" in cols
        _migrate(raw)  # idempotent
        raw.close()
