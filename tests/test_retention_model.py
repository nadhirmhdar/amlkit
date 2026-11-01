"""WP-16: retention extension script (#79), latest-of retention model, purge guards (#267)."""

from __future__ import annotations

import inspect
import os
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases import manager  # noqa: E402
from amlkit.cases.manager import (  # noqa: E402
    RETENTION_YEARS, close_relationship, extend_closed_retention,
    purge_expired, recompute_retention, record_transaction, retention_from,
    utc_today)
from amlkit.db import audit, connect, upsert_dataset, utcnow  # noqa: E402
from amlkit.names.arabic import canonical_key  # noqa: E402

OLD = "2020-01-01"


@pytest.fixture()
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def _org(conn, slug):
    r = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
        " RETURNING id", (slug, slug, "active", utcnow())).fetchone()
    conn.commit()
    return r["id"]


def _customer(conn, org_id, ref, *, status="closed", retention=OLD, exit_date=None):
    now = utcnow()
    cur = conn.execute(
        """INSERT INTO customers (org_id, reference, customer_type, full_name,
           canonical_key, status, exit_date, onboarded_at, retention_until,
           created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (org_id, ref, "natural", "Test Person", canonical_key("Test Person"),
         status, exit_date, now, retention, now, now))
    conn.commit()
    return cur.lastrowid


def _ret(conn, cid):
    return conn.execute("SELECT retention_until FROM customers WHERE id=?", (cid,)).fetchone()[0]


def _ext_audits(conn, org_id=None):
    sql = "SELECT * FROM audit_log WHERE action='retention.extended'"
    if org_id is not None:
        sql += f" AND org_id={int(org_id)}"
    return conn.execute(sql).fetchall()


def _close_audit(conn, org_id, cid, ts):
    conn.execute(
        "INSERT INTO audit_log (org_id, ts, actor, action, object_type, object_id, detail)"
        " VALUES (?,?,?,?,?,?,?)",
        (org_id, ts, "tester", "customer.close", "customer", str(cid), "{}"))
    conn.commit()


# ------------------------------------------------------------ #79 acceptance
class TestExtendClosedRetention:
    def test_five_year_row_is_extended(self, conn) -> None:
        org = _org(conn, "a")
        cid = _customer(conn, org, "C-1001", retention="2031-08-11")
        _close_audit(conn, org, cid, "2026-08-11T10:00:00Z")
        changes = extend_closed_retention(conn, apply=True)
        assert changes[org] == [{"id": cid, "reference": "C-1001",
                                 "from": "2031-08-11", "to": "2036-08-11"}]
        assert _ret(conn, cid) == "2036-08-11"
        rows = _ext_audits(conn, org)
        assert len(rows) == 1
        assert "Test Person" not in (rows[0]["detail"] or "")

    def test_longer_row_unchanged(self, conn) -> None:
        org = _org(conn, "a")
        cid = _customer(conn, org, "C-1", retention="2040-01-01")
        _close_audit(conn, org, cid, "2026-08-11T10:00:00Z")
        assert extend_closed_retention(conn, apply=True) == {}
        assert _ret(conn, cid) == "2040-01-01"
        assert _ext_audits(conn) == []

    def test_idempotent(self, conn) -> None:
        org = _org(conn, "a")
        cid = _customer(conn, org, "C-1", retention="2031-08-11")
        _close_audit(conn, org, cid, "2026-08-11T10:00:00Z")
        extend_closed_retention(conn, apply=True)
        n = len(_ext_audits(conn))
        assert extend_closed_retention(conn, apply=True) == {}
        assert len(_ext_audits(conn)) == n == 1

    def test_other_org_unaffected_and_audit_scoped(self, conn) -> None:
        a, b = _org(conn, "a"), _org(conn, "b")
        ca = _customer(conn, a, "C-A", retention="2031-08-11")
        cb = _customer(conn, b, "C-B", retention="2031-08-11")
        _close_audit(conn, a, ca, "2026-08-11T10:00:00Z")
        # org b's customer has an audit row too, but only org a is processed
        _close_audit(conn, b, cb, "2026-08-11T10:00:00Z")
        extend_closed_retention(conn, apply=True, org_id=a)
        assert _ret(conn, ca) == "2036-08-11"
        assert _ret(conn, cb) == "2031-08-11"
        assert len(_ext_audits(conn, a)) == 1 and _ext_audits(conn, b) == []

    def test_close_audit_is_org_scoped(self, conn) -> None:
        """A customer.close row in another org with a colliding id is ignored."""
        a, b = _org(conn, "a"), _org(conn, "b")
        ca = _customer(conn, a, "C-A", retention="2031-08-11", exit_date="2026-01-01")
        _close_audit(conn, b, ca, "2030-01-01T00:00:00Z")  # wrong org
        changes = extend_closed_retention(conn, apply=False)
        assert changes[a][0]["to"] == "2036-01-01"  # from exit_date, not org b's row

    def test_fallbacks_exit_date_then_today(self, conn) -> None:
        org = _org(conn, "a")
        c1 = _customer(conn, org, "C-X", retention="2031-01-01", exit_date="2027-03-04")
        c2 = _customer(conn, org, "C-T", retention=OLD, exit_date=None)
        ch = {i["id"]: i for i in extend_closed_retention(conn)[org]}
        assert ch[c1]["to"] == "2037-03-04"
        assert ch[c2]["to"] == retention_from(utc_today())

    def test_dry_run_writes_nothing(self, conn) -> None:
        org = _org(conn, "a")
        cid = _customer(conn, org, "C-1", retention="2031-08-11")
        _close_audit(conn, org, cid, "2026-08-11T10:00:00Z")
        assert extend_closed_retention(conn)[org]
        assert _ret(conn, cid) == "2031-08-11"
        assert _ext_audits(conn) == []

    def test_script_dry_run_default_and_apply(self, tmp_path, capsys) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import extend_retention
        db = tmp_path / "t.db"
        c = connect(str(db))
        org = _org(c, "a")
        cid = _customer(c, org, "C-9", retention="2031-08-11")
        _close_audit(c, org, cid, "2026-08-11T10:00:00Z")
        c.close()
        assert extend_retention.main(["--db", str(db)]) == 0
        out = capsys.readouterr().out
        assert "C-9: 2031-08-11 -> 2036-08-11" in out and "Test Person" not in out
        assert _ret(connect(str(db)), cid) == "2031-08-11"
        assert extend_retention.main(["--db", str(db), "--apply"]) == 0
        assert _ret(connect(str(db)), cid) == "2036-08-11"


# ------------------------------------------------------- latest-of model
class TestRecomputeRetention:
    def test_close_uses_exit_date(self, conn) -> None:
        org = _org(conn, "a")
        cid = _customer(conn, org, "C-1", status="active", retention="2030-01-01")
        until = close_relationship(conn, cid, org, "customer_request")
        assert until == retention_from(utc_today()) == _ret(conn, cid)

    def test_close_keeps_later_transaction_anchor(self, conn) -> None:
        org = _org(conn, "a")
        cid = _customer(conn, org, "C-1", status="active", retention="2030-01-01")
        conn.execute(
            "INSERT INTO transactions (org_id, customer_id, direction, method, amount,"
            " currency, amount_aed, occurred_at, recorded_by, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (org, cid, "in", "cash", 10, "AED", 10, "2099-06-01T00:00:00Z", "t", utcnow()))
        conn.commit()
        until = close_relationship(conn, cid, org, "customer_request")
        assert until == f"{2099 + RETENTION_YEARS}-06-01" == _ret(conn, cid)

    def test_record_transaction_extends(self, conn) -> None:
        org = _org(conn, "a")
        cid = _customer(conn, org, "C-1", status="active", retention=OLD)
        record_transaction(conn, cid, org, direction="in", method="cash", amount=100,
                           occurred_at="2031-05-05T00:00:00Z")
        assert _ret(conn, cid) == f"{2031 + RETENTION_YEARS}-05-05"
        assert len(_ext_audits(conn, org)) == 1

    def test_backdated_transaction_never_shortens(self, conn) -> None:
        org = _org(conn, "a")
        cid = _customer(conn, org, "C-1", status="active", retention="2060-01-01")
        record_transaction(conn, cid, org, direction="in", method="cash", amount=100,
                           occurred_at="2021-05-05T00:00:00Z")
        assert _ret(conn, cid) == "2060-01-01"
        assert _ext_audits(conn) == []

    def test_only_finalised_reports_count(self, conn) -> None:
        org = _org(conn, "a")
        cid = _customer(conn, org, "C-1", status="active", retention=OLD)
        conn.execute(
            "INSERT INTO reports (org_id, customer_id, report_type, status, payload,"
            " created_at, submitted_at) VALUES (?,?,?,?,?,?,?)",
            (org, cid, "STR", "draft", "{}", utcnow(), "2040-01-01T00:00:00Z"))
        conn.commit()
        assert recompute_retention(conn, org, cid) is None
        conn.execute("UPDATE reports SET status='submitted'")
        assert recompute_retention(conn, org, cid) == f"{2040 + RETENTION_YEARS}-01-01"
        assert recompute_retention(conn, org, cid) is None  # idempotent

    def test_tenant_scoped(self, conn) -> None:
        a, b = _org(conn, "a"), _org(conn, "b")
        cid = _customer(conn, a, "C-1", status="closed", retention=OLD, exit_date="2030-01-01")
        assert recompute_retention(conn, b, cid) is None
        assert _ret(conn, cid) == OLD

    def test_report_finalise_routes_call_recompute(self) -> None:
        from amlkit.api import app as web, mobile
        assert "recompute_retention" in inspect.getsource(web.report_submit)
        assert "recompute_retention" in inspect.getsource(mobile.api_report_submit)

    def test_mobile_report_finalise_extends(self, tmp_path, monkeypatch) -> None:
        from fastapi.testclient import TestClient
        from tests.test_api import _seed_sanctions_data
        from conftest import unlock_mobile_mfa
        db_file = tmp_path / "t.db"
        monkeypatch.setenv("AMLKIT_DB", str(db_file))
        _seed_sanctions_data(db_file)
        from amlkit.api.app import app
        c = TestClient(app)
        r = c.post("/api/v1/auth/register-organization", json={
            "org_name": "Test Firm", "name": "alice", "email": "alice@testfirm.ae",
            "password": "A-strong-password-1", "invite_code": "test-invite"})
        r2 = c.post("/api/v1/auth/verify-email", json={"token": r.json()["dev_verification_token"]})
        tok = r2.json()["token"]
        unlock_mobile_mfa(c, tok)
        h = {"Authorization": f"Bearer {tok}"}
        cid = c.post("/api/v1/customers", headers=h, json={
            "reference": "CUST-RPT", "full_name": "Report Subject"}).json()["customer_id"]
        rid = c.post("/api/v1/reports", headers=h, json={
            "customer_id": cid, "report_type": "STR", "reporting_entity_name": "Test Firm",
            "entity_reference": "TF-1", "reporter_name": "alice",
            "reporter_email": "alice@testfirm.ae", "first_name": "Report",
            "last_name": "Subject"}).json()["report_id"]
        d = connect(str(db_file))
        d.execute("UPDATE customers SET retention_until=? WHERE id=?", (OLD, cid))
        d.commit()
        d.close()
        assert c.post(f"/api/v1/reports/{rid}/submit", headers=h).status_code == 200
        d = connect(str(db_file))
        assert _ret(d, cid) >= retention_from(utc_today())
        d.close()


# ----------------------------------------------------------- purge guards
def _freeze(conn, org, cid, status="executed_pending_report"):
    conn.execute(
        "INSERT INTO freeze_obligations (org_id, customer_id, obligation_type,"
        " risk_category, identified_at, identified_by, status) VALUES (?,?,?,?,?,?,?)",
        (org, cid, "sanctions", "high", utcnow(), "t", status))


def _report(conn, org, cid, status):
    conn.execute(
        "INSERT INTO reports (org_id, customer_id, report_type, status, payload, created_at)"
        " VALUES (?,?,?,?,?,?)", (org, cid, "STR", status, "{}", utcnow()))


def _alert(conn, org, cid, status="open"):
    ds = upsert_dataset(conn, "tl", "Test List", is_mandatory=False)
    now = utcnow()
    eid = conn.execute(
        "INSERT INTO entities (dataset_id, source_id, schema_type, caption, countries,"
        " topics, raw, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?,?)",
        (ds, "S1", "Person", "X", "[]", "[]", "{}", now, now)).lastrowid
    sid = conn.execute(
        "INSERT INTO screenings (org_id, customer_id, query_name, trigger, algorithm,"
        " threshold, run_at) VALUES (?,?,?,?,?,?,?)",
        (org, cid, "X", "periodic", "t", 0.8, now)).lastrowid
    conn.execute(
        "INSERT INTO alerts (org_id, screening_id, entity_id, score, score_detail,"
        " matched_name, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (org, sid, eid, 0.9, "{}", "X", status, now))


def _txn_alert(conn, org, cid, status="open"):
    now = utcnow()
    tid = conn.execute(
        "INSERT INTO transactions (org_id, customer_id, direction, method, amount, currency,"
        " amount_aed, occurred_at, recorded_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (org, cid, "in", "cash", 1, "AED", 1, OLD, "t", now)).lastrowid
    conn.execute(
        "INSERT INTO transaction_alerts (org_id, transaction_id, customer_id, rule_key,"
        " detail, status, created_at) VALUES (?,?,?,?,?,?,?)",
        (org, tid, cid, "large_cash", "{}", status, now))


GUARDS = [
    ("unresolved_freeze", lambda c, o, i: _freeze(c, o, i)),
    ("unfinalised_report", lambda c, o, i: _report(c, o, i, "draft")),
    ("open_alert", lambda c, o, i: _alert(c, o, i, "open")),
    ("open_alert", lambda c, o, i: _alert(c, o, i, "pending_review")),
    ("open_alert", lambda c, o, i: _txn_alert(c, o, i)),
]


class TestPurgeGuards:
    @pytest.mark.parametrize("reason,setup", GUARDS)
    def test_guarded_customer_skipped_and_data_intact(self, conn, reason, setup) -> None:
        org = _org(conn, "a")
        cid = _customer(conn, org, "C-G", exit_date="2000-01-01", retention="2001-01-01")
        free = _customer(conn, org, "C-FREE", exit_date="2000-01-01", retention="2001-01-01")
        setup(conn, org, cid)
        _report(conn, org, cid, "submitted")
        conn.commit()
        before_f = conn.execute("SELECT count(*) FROM freeze_obligations").fetchone()[0]
        before_r = conn.execute("SELECT count(*) FROM reports").fetchone()[0]

        dry = purge_expired(conn, org, dry_run=True)
        assert [s["reference"] for s in dry["skipped"]] == ["C-G"]
        assert reason in dry["skipped"][0]["reasons"]
        assert [d["reference"] for d in dry["details"]] == ["C-FREE"]

        res = purge_expired(conn, org, actor="t")
        assert res["purged"] == 1
        assert conn.execute("SELECT 1 FROM customers WHERE id=?", (cid,)).fetchone()
        assert conn.execute("SELECT 1 FROM customers WHERE id=?", (free,)).fetchone() is None
        assert conn.execute("SELECT count(*) FROM freeze_obligations").fetchone()[0] == before_f
        assert conn.execute("SELECT count(*) FROM reports WHERE customer_id=?",
                            (cid,)).fetchone()[0] == before_r
        assert conn.execute(
            "SELECT 1 FROM audit_log WHERE action='retention.purge_skipped' AND object_id=?",
            (str(cid),)).fetchone()

    def test_resolved_state_allows_purge(self, conn) -> None:
        org = _org(conn, "a")
        cid = _customer(conn, org, "C-OK", exit_date="2000-01-01", retention="2001-01-01")
        _freeze(conn, org, cid, "resolved")
        _report(conn, org, cid, "submitted")
        _alert(conn, org, cid, "false_positive")
        conn.commit()
        assert purge_expired(conn, org)["purged"] == 1

    def test_dry_run_writes_nothing(self, conn) -> None:
        org = _org(conn, "a")
        cid = _customer(conn, org, "C-G", exit_date="2000-01-01", retention="2001-01-01")
        _customer(conn, org, "C-FREE", exit_date="2000-01-01", retention="2001-01-01")
        _freeze(conn, org, cid)
        conn.commit()
        n_audit = conn.execute("SELECT count(*) FROM audit_log").fetchone()[0]
        n_cust = conn.execute("SELECT count(*) FROM customers").fetchone()[0]
        res = purge_expired(conn, org, dry_run=True)
        assert res["dry_run"] and res["purged"] == 1 and len(res["skipped"]) == 1
        assert conn.execute("SELECT count(*) FROM audit_log").fetchone()[0] == n_audit
        assert conn.execute("SELECT count(*) FROM customers").fetchone()[0] == n_cust
