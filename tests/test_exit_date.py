"""Relationship exit date + exit reason (AML AI design doc, recommendation 3)."""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import (  # noqa: E402
    EXIT_REASONS,
    close_relationship,
    onboard,
    reactivate_customer,
    retention_from,
)
from amlkit.db import connect, utcnow  # noqa: E402
from tests.test_mobile_api import api  # noqa: E402,F401  (fixture)
from tests.test_reactivate import (  # noqa: E402,F401  (mlro_client is a fixture)
    _csrf,
    _db,
    _onboard_customer,
    mlro_client,
)


def _ten_years(d: date) -> str:
    return date(d.year + 10, d.month, d.day if (d.month, d.day) != (2, 29) else 28).isoformat()


def _row(conn, cid):
    return conn.execute(
        "SELECT status, exit_date, exit_reason, retention_until FROM customers WHERE id=?",
        (cid,),
    ).fetchone()


def _audit(conn, action, cid):
    rows = conn.execute(
        "SELECT org_id, detail FROM audit_log WHERE action=? AND object_id=? ORDER BY id",
        (action, str(cid)),
    ).fetchall()
    return [(r["org_id"], json.loads(r["detail"])) for r in rows]


# ------------------------------------------------------------------ manager


class TestManager:
    def test_close_sets_exit_fields_and_retention_from_exit_date(self, conn, org_id):
        cid = onboard(conn, org_id=org_id, reference="X-1", full_name="Ordinary Person").customer_id
        until = close_relationship(conn, cid, org_id=org_id, reason="risk_appetite",
                                   note="Declined EDD", actor="alice")
        row = _row(conn, cid)
        assert row["status"] == "closed"
        assert row["exit_date"] == date.today().isoformat()
        assert row["exit_reason"] == "risk_appetite"
        assert until == row["retention_until"] == _ten_years(date.fromisoformat(row["exit_date"]))

        [(audit_org, detail)] = _audit(conn, "customer.close", cid)
        assert audit_org == org_id
        assert detail["exit_reason"] == "risk_appetite"
        assert detail["exit_date"] == row["exit_date"]
        assert detail["note"] == "Declined EDD"

    @pytest.mark.parametrize("reason", ["", "bored", "unspecified", "CUSTOMER_REQUEST"])
    def test_invalid_reason_rejected_and_nothing_changes(self, conn, org_id, reason):
        cid = onboard(conn, org_id=org_id, reference="X-2", full_name="Ordinary Person").customer_id
        with pytest.raises(ValueError, match="exit reason"):
            close_relationship(conn, cid, org_id=org_id, reason=reason)
        row = _row(conn, cid)
        assert row["status"] == "active"
        assert row["exit_date"] is None and row["exit_reason"] is None
        assert _audit(conn, "customer.close", cid) == []

    def test_every_listed_reason_is_accepted(self, conn, org_id):
        for i, reason in enumerate(EXIT_REASONS):
            cid = onboard(conn, org_id=org_id, reference=f"R-{i}", full_name="Ordinary Person").customer_id
            close_relationship(conn, cid, org_id=org_id, reason=reason)
            assert _row(conn, cid)["exit_reason"] == reason

    def test_already_closed_cannot_be_reclosed(self, conn, org_id):
        cid = onboard(conn, org_id=org_id, reference="X-3", full_name="Ordinary Person").customer_id
        close_relationship(conn, cid, org_id=org_id, reason="str_filed")
        with pytest.raises(ValueError, match="already closed"):
            close_relationship(conn, cid, org_id=org_id, reason="other")
        assert _row(conn, cid)["exit_reason"] == "str_filed"

    def test_reactivate_clears_exit_fields_and_audits_history(self, conn, org_id):
        cid = onboard(conn, org_id=org_id, reference="X-4", full_name="Ordinary Person").customer_id
        close_relationship(conn, cid, org_id=org_id, reason="no_cdd")
        exit_date = _row(conn, cid)["exit_date"]
        reactivate_customer(conn, cid, org_id=org_id, reason="CDD completed", actor="mlro")

        row = _row(conn, cid)
        assert row["status"] == "active"
        assert row["exit_date"] is None and row["exit_reason"] is None

        [(audit_org, detail)] = _audit(conn, "customer.reactivated", cid)
        assert audit_org == org_id
        assert detail["previous_exit_date"] == exit_date
        assert detail["previous_exit_reason"] == "no_cdd"
        assert detail["reason"] == "CDD completed"
        # the original close is still on record
        assert _audit(conn, "customer.close", cid)[0][1]["exit_reason"] == "no_cdd"

    def test_other_org_customer_rejected(self, conn, org_id):
        cid = onboard(conn, org_id=org_id, reference="X-5", full_name="Ordinary Person").customer_id
        other = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id",
            ("Other Firm", "other-firm", "active", utcnow()),
        ).fetchone()["id"]
        conn.commit()
        with pytest.raises(ValueError, match="not found"):
            close_relationship(conn, cid, org_id=other, reason="customer_request")
        assert _row(conn, cid)["status"] == "active"
        assert _audit(conn, "customer.close", cid) == []

    def test_retention_from_leap_day(self):
        assert retention_from(date(2028, 2, 29)) == "2038-02-28"
        assert retention_from(date(2026, 9, 21)) == "2036-09-21"


# ---------------------------------------------------------------- migration


class TestBackfill:
    def test_pre_existing_closed_customer_is_backfilled(self, tmp_path):
        db_file = tmp_path / "legacy.db"
        c = connect(db_file)
        org = c.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id",
            ("Legacy Firm", "legacy-firm", "active", utcnow()),
        ).fetchone()["id"]
        now = "2024-03-15T09:30:00+00:00"
        for ref, status in (("OLD-CLOSED", "closed"), ("OLD-ACTIVE", "active")):
            c.execute(
                "INSERT INTO customers (org_id, reference, customer_type, full_name, canonical_key,"
                " status, onboarded_at, retention_until, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (org, ref, "natural", "Legacy Person", "legacy person", status,
                 "2020-01-01T00:00:00+00:00", "2034-03-15", now, now),
            )
        # Reproduce a database from before this migration existed.
        c.execute("ALTER TABLE customers DROP COLUMN exit_reason")
        c.execute("ALTER TABLE customers DROP COLUMN exit_date")
        c.commit()
        c.close()

        c = connect(db_file)
        closed = c.execute(
            "SELECT exit_date, exit_reason, retention_until FROM customers WHERE reference='OLD-CLOSED'"
        ).fetchone()
        active = c.execute(
            "SELECT exit_date, exit_reason FROM customers WHERE reference='OLD-ACTIVE'"
        ).fetchone()
        assert closed["exit_date"] == "2024-03-15"
        assert closed["exit_reason"] == "unspecified"
        assert closed["retention_until"] == "2034-03-15"
        assert active["exit_date"] is None and active["exit_reason"] is None
        c.close()

        # Idempotent: a second open changes nothing.
        c = connect(db_file)
        again = c.execute(
            "SELECT exit_date, exit_reason FROM customers WHERE reference='OLD-CLOSED'"
        ).fetchone()
        assert (again["exit_date"], again["exit_reason"]) == ("2024-03-15", "unspecified")
        c.close()


# ---------------------------------------------------------------------- web


class TestWeb:
    def test_close_with_reason_sets_fields_and_shows_on_page(self, mlro_client):
        cid = _onboard_customer(mlro_client, name="Web Close")
        page = mlro_client.get(f"/customers/{cid}").text
        assert 'name="exit_reason"' in page and 'value="deceased_or_dissolved"' in page

        r = mlro_client.post(f"/customers/{cid}/close", data={
            "exit_reason": "deceased_or_dissolved", "exit_note": "Death certificate on file",
            "csrf_token": _csrf(mlro_client),
        }, follow_redirects=True)
        assert r.status_code == 200

        conn = _db()
        row = _row(conn, cid)
        audit = _audit(conn, "customer.close", cid)
        conn.close()
        assert row["status"] == "closed"
        assert row["exit_reason"] == "deceased_or_dissolved"
        assert row["exit_date"] == date.today().isoformat()
        assert row["retention_until"] == _ten_years(date.today())
        assert audit[0][1]["note"] == "Death certificate on file"

        page = mlro_client.get(f"/customers/{cid}").text
        assert f"Relationship closed on <strong>{row['exit_date']}</strong>" in page
        assert "Deceased / dissolved" in page

    @pytest.mark.parametrize("data", [{}, {"exit_reason": ""}, {"exit_reason": "whim"}])
    def test_missing_or_invalid_reason_rejected(self, mlro_client, data):
        cid = _onboard_customer(mlro_client, name="Web Reject")
        r = mlro_client.post(f"/customers/{cid}/close",
                             data=data | {"csrf_token": _csrf(mlro_client)},
                             follow_redirects=True)
        assert "valid exit reason" in r.text
        conn = _db()
        row = _row(conn, cid)
        conn.close()
        assert row["status"] == "active" and row["exit_date"] is None

    def test_close_without_csrf_rejected(self, mlro_client):
        cid = _onboard_customer(mlro_client, name="Web Csrf")
        mlro_client.post(f"/customers/{cid}/close",
                         data={"exit_reason": "customer_request", "csrf_token": "bogus"},
                         follow_redirects=True)
        conn = _db()
        assert _row(conn, cid)["status"] == "active"
        conn.close()

    def test_reactivate_clears_fields(self, mlro_client):
        cid = _onboard_customer(mlro_client, name="Web React")
        mlro_client.post(f"/customers/{cid}/close", data={
            "exit_reason": "customer_request", "csrf_token": _csrf(mlro_client),
        }, follow_redirects=True)
        mlro_client.post(f"/customers/{cid}/reactivate", data={
            "reason": "Returned", "csrf_token": _csrf(mlro_client),
        }, follow_redirects=True)
        conn = _db()
        row = _row(conn, cid)
        conn.close()
        assert row["status"] == "active"
        assert row["exit_date"] is None and row["exit_reason"] is None
        assert "Relationship closed on" not in mlro_client.get(f"/customers/{cid}").text


# ------------------------------------------------------------------- mobile


def _other_org_customer() -> int:
    c = connect(os.environ["AMLKIT_DB"])
    other = c.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id",
        ("Other Firm", "other-firm", "active", utcnow()),
    ).fetchone()["id"]
    c.commit()
    cid = onboard(c, org_id=other, reference="OTHER-1", full_name="Their Customer").customer_id
    c.close()
    return cid


class TestMobile:
    def _new(self, client, headers, ref):
        return client.post("/api/v1/customers", headers=headers, json={
            "reference": ref, "full_name": "Mobile Person",
        }).json()["customer_id"]

    def test_close_with_reason(self, api):
        client, headers = api
        cid = self._new(client, headers, "M-1")
        r = client.post(f"/api/v1/customers/{cid}/close", headers=headers,
                        json={"reason": "str_filed", "note": "STR ref 123"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["exit_reason"] == "str_filed"
        assert body["exit_date"] == date.today().isoformat()
        assert body["retention_until"] == _ten_years(date.today())

        cust = client.get(f"/api/v1/customers/{cid}", headers=headers).json()["customer"]
        assert cust["exit_reason"] == "str_filed" and cust["exit_date"] == body["exit_date"]

    def test_invalid_reason_is_400(self, api):
        client, headers = api
        cid = self._new(client, headers, "M-2")
        r = client.post(f"/api/v1/customers/{cid}/close", headers=headers, json={"reason": "nope"})
        assert r.status_code == 400
        assert "exit reason" in r.json()["detail"]

    def test_missing_reason_is_422(self, api):
        client, headers = api
        cid = self._new(client, headers, "M-3")
        assert client.post(f"/api/v1/customers/{cid}/close", headers=headers).status_code == 422
        assert client.post(f"/api/v1/customers/{cid}/close", headers=headers, json={}).status_code == 422
        cust = client.get(f"/api/v1/customers/{cid}", headers=headers).json()["customer"]
        assert cust["status"] == "active"

    def test_other_org_customer_is_404(self, api):
        client, headers = api
        cid = _other_org_customer()
        r = client.post(f"/api/v1/customers/{cid}/close", headers=headers,
                        json={"reason": "customer_request"})
        assert r.status_code == 404
        conn = _db()
        assert _row(conn, cid)["status"] == "active"
        conn.close()

    def test_exit_reasons_listed(self, api):
        client, headers = api
        r = client.get("/api/v1/exit-reasons", headers=headers)
        assert r.status_code == 200
        assert [x["code"] for x in r.json()["exit_reasons"]] == list(EXIT_REASONS)


def test_web_other_org_close_rejected(mlro_client):
    cid = _other_org_customer()
    r = mlro_client.post(f"/customers/{cid}/close", data={
        "exit_reason": "customer_request", "csrf_token": _csrf(mlro_client),
    }, follow_redirects=True)
    assert "not found" in r.text.lower()
    conn = _db()
    row = _row(conn, cid)
    conn.close()
    assert row["status"] == "active" and row["exit_date"] is None
