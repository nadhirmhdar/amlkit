"""WP-9 governance and audit gaps: L-55, L-51, L-48, L-44, L-45, L-41, L-50."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit import db as dbm  # noqa: E402
from amlkit.cases import manager  # noqa: E402
from amlkit.cases.manager import disposition_transaction_alert, record_transaction  # noqa: E402
from amlkit.screening.kyt import LARGE_CASH_THRESHOLD_AED  # noqa: E402
from test_api import _csrf, _db, _register, _seed_sanctions_data  # noqa: E402
from tests.test_kyt import conn, customer_id, org_id  # noqa: E402,F401  (fixtures)
from tests.test_mobile_api import api  # noqa: E402,F401  (fixture)


@pytest.fixture()
def web(tmp_path, monkeypatch):
    db_file = tmp_path / "gov.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Gov Firm", "Alice Lead", "alice@gov.ae")
    return c


def _audit(action: str, org_id: int | None = None) -> list[dict]:
    c = _db()
    try:
        rows = c.execute("SELECT * FROM audit_log WHERE action=?", (action,)).fetchall()
        out = [dict(r) | {"detail_json": json.loads(r["detail"] or "{}")} for r in rows]
    finally:
        c.close()
    return [r for r in out if org_id is None or r["org_id"] == org_id]


# ---------------------------------------------------------------- L-55
class TestRiskDowngradeReason:
    def _high_customer(self, ref: str) -> tuple[int, int]:
        c = dbm.connect(os.environ["AMLKIT_DB"])
        try:
            org = c.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()["id"]
            res = manager.onboard(c, org_id=org, reference=ref, full_name="Jane Doe",
                                  jurisdiction_tier="fatf_blacklist")
            assert res.risk.rating == "high"
            return res.customer_id, org
        finally:
            c.close()

    def _assessments(self, cid: int) -> int:
        c = _db()
        try:
            return c.execute("SELECT COUNT(*) FROM risk_assessments WHERE customer_id=?",
                             (cid,)).fetchone()[0]
        finally:
            c.close()

    @pytest.mark.parametrize("body", [
        {"jurisdiction_tier": "standard"},
        {"jurisdiction_tier": "standard", "reason": "   "},
        {"jurisdiction_tier": "standard", "reason": "too short"},
    ])
    def test_downgrade_without_reason_is_400_and_changes_nothing(self, api, body):  # noqa: F811
        client, headers = api
        cid, _ = self._high_customer("L55-1")
        before = self._assessments(cid)
        r = client.patch(f"/api/v1/customers/{cid}/risk-factors", json=body, headers=headers)
        assert r.status_code == 400, r.text
        assert "reason" in r.json()["detail"]
        assert self._assessments(cid) == before
        assert _audit("customer.risk_factors_changed") == []

    def test_downgrade_with_reason_is_audited_with_old_new_and_reason(self, api):  # noqa: F811
        client, headers = api
        cid, org = self._high_customer("L55-2")
        reason = "Re-papered: customer is not a FATF-listed national"
        r = client.patch(f"/api/v1/customers/{cid}/risk-factors",
                         json={"jurisdiction_tier": "standard", "reason": reason},
                         headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["rating"] != "high"
        (row,) = _audit("customer.risk_factors_changed", org)
        d = row["detail_json"]
        assert d["old"]["rating"] == "high"
        assert d["new"]["rating"] == r.json()["rating"]
        assert d["reason"] == reason
        assert d["downgrade"] is True
        assert d["requested"] == {"jurisdiction_tier": "standard"}

    def test_non_downgrade_needs_no_reason(self, api):  # noqa: F811
        client, headers = api
        cid, _ = self._high_customer("L55-3")
        r = client.patch(f"/api/v1/customers/{cid}/risk-factors",
                         json={"delivery_channel": "remote_verified"}, headers=headers)
        assert r.status_code == 200, r.text


# ---------------------------------------------------------------- L-51
class TestTransactionAlertNote:
    def _alert(self, conn, org_id, customer_id) -> int:
        record_transaction(conn, customer_id, org_id, direction="inbound", method="cash",
                           amount=LARGE_CASH_THRESHOLD_AED, actor="tester")
        return conn.execute("SELECT id FROM transaction_alerts WHERE customer_id=?",
                            (customer_id,)).fetchone()["id"]

    @pytest.mark.parametrize("note", ["", "   ", "short"])
    def test_false_positive_needs_a_real_note(self, conn, org_id, customer_id, note):  # noqa: F811
        alert_id = self._alert(conn, org_id, customer_id)
        with pytest.raises(ValueError, match="note"):
            disposition_transaction_alert(conn, alert_id, org_id, status="false_positive",
                                          note=note, actor="reviewer")
        row = conn.execute("SELECT status, disposition FROM transaction_alerts WHERE id=?",
                           (alert_id,)).fetchone()
        assert (row["status"], row["disposition"]) == ("open", None)

    def test_false_positive_with_note_stores_it(self, conn, org_id, customer_id):  # noqa: F811
        alert_id = self._alert(conn, org_id, customer_id)
        disposition_transaction_alert(conn, alert_id, org_id, status="false_positive",
                                      note="  Known payroll run, invoice 4471  ", actor="r")
        row = conn.execute("SELECT status, disposition FROM transaction_alerts WHERE id=?",
                           (alert_id,)).fetchone()
        assert row["status"] == "false_positive"
        assert row["disposition"] == "Known payroll run, invoice 4471"

    def test_mobile_route_surfaces_the_error(self, api):  # noqa: F811
        client, headers = api
        c = dbm.connect(os.environ["AMLKIT_DB"])
        org = c.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()["id"]
        cid = manager.onboard(c, org_id=org, reference="L51-M", full_name="Jane Doe").customer_id
        record_transaction(c, cid, org, direction="inbound", method="cash",
                           amount=LARGE_CASH_THRESHOLD_AED, actor="t")
        aid = c.execute("SELECT id FROM transaction_alerts WHERE customer_id=?",
                        (cid,)).fetchone()["id"]
        c.close()
        r = client.post(f"/api/v1/transaction-alerts/{aid}/disposition",
                        json={"status": "false_positive", "note": ""}, headers=headers)
        assert r.status_code == 400
        assert "note" in r.json()["detail"]


# ---------------------------------------------------------------- L-48
def test_refresh_audit_actor_is_per_org(web, monkeypatch):
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.ingest import loader
    from amlkit.ingest.base import AdapterError

    b = TestClient(app)
    _register(b, "Org B", "Bob Other", "bob@b.test")
    s = dbm.connect(os.environ["AMLKIT_DB"])
    org_a = s.execute("SELECT id FROM organizations WHERE name='Gov Firm'").fetchone()["id"]
    org_b = s.execute("SELECT id FROM organizations WHERE name='Org B'").fetchone()["id"]
    for org, ref, nm in ((org_a, "A-1", "Alpha Customer"), (org_b, "B-1", "Bravo Customer")):
        manager.onboard(s, org_id=org, reference=ref, full_name=nm)
    s.commit()
    s.close()

    def _no_network(conn, adapter, actor="system"):
        raise AdapterError("network disabled")
    monkeypatch.setattr(loader, "load", _no_network)

    r = web.post("/admin/refresh", data={"csrf_token": _csrf(web)}, follow_redirects=True)
    assert r.status_code == 200

    c = _db()
    actors = lambda org: {x[0] for x in c.execute(  # noqa: E731
        "SELECT actor FROM audit_log WHERE org_id=? AND action='screening.run'", (org,))}
    assert "system:scheduled-refresh" in actors(org_b)
    assert "Alice Lead" not in actors(org_b)
    assert "Alice Lead" in actors(org_a)
    # the shared (org_id NULL) rows never carry the operator's name
    shared = {x[0] for x in c.execute("SELECT actor FROM audit_log WHERE org_id IS NULL")}
    assert "Alice Lead" not in shared
    # the trigger is recorded in the operator's own org only
    req = c.execute("SELECT org_id, actor FROM audit_log WHERE action='dataset.refresh_requested'"
                    ).fetchall()
    assert [(x["org_id"], x["actor"]) for x in req] == [(org_a, "Alice Lead")]
    c.close()


# ---------------------------------------------------------------- L-44
class TestDeadlineApi:
    def _create(self, web, **over):
        body = {"title": "FIU review", "due_date": "2026-12-31", "description": "d",
                "recurrence": "none"} | over
        return web.post("/compliance/deadlines", json=body,
                        headers={"X-CSRF-Token": _csrf(web)})

    def _set_role(self, role: str):
        c = _db()
        c.execute("UPDATE operators SET role=?", (role,))
        c.commit()
        c.close()

    def test_patch_changes_due_date_recurrence_description_and_is_audited(self, web):
        d = self._create(web).json()
        r = web.patch(f"/compliance/deadlines/{d['id']}",
                      json={"due_date": "2027-01-15", "recurrence": "monthly",
                            "description": "moved"},
                      headers={"X-CSRF-Token": _csrf(web)})
        assert r.status_code == 200, r.text
        got = r.json()
        assert (got["due_date"], got["recurrence"], got["description"]) == (
            "2027-01-15", "monthly", "moved")
        (row,) = _audit("compliance.deadline_updated")
        assert row["detail_json"]["old"]["due_date"] == "2026-12-31"
        assert row["detail_json"]["new"]["due_date"] == "2027-01-15"

    @pytest.mark.parametrize("bad", ["31/12/2026", "soon", "2026-13-40", ""])
    def test_invalid_due_date_is_400(self, web, bad):
        d = self._create(web).json()
        r = web.patch(f"/compliance/deadlines/{d['id']}", json={"due_date": bad},
                      headers={"X-CSRF-Token": _csrf(web)})
        assert r.status_code == 400
        assert self._create(web, due_date=bad).status_code == 400
        still = web.get("/compliance/deadlines").json()
        assert [x["due_date"] for x in still] == ["2026-12-31"]

    def test_invalid_recurrence_is_400(self, web):
        assert self._create(web, recurrence="whenever").status_code == 400

    def test_delete_is_audited_with_old_values(self, web):
        d = self._create(web).json()
        r = web.delete(f"/compliance/deadlines/{d['id']}", headers={"X-CSRF-Token": _csrf(web)})
        assert r.status_code == 204
        (row,) = _audit("compliance.deadline_deleted")
        assert row["detail_json"]["old"]["title"] == "FIU review"
        assert row["detail_json"]["old"]["due_date"] == "2026-12-31"

    def test_officer_allowed_other_roles_refused(self, web):
        d = self._create(web).json()
        self._set_role("officer")
        assert self._create(web, title="By officer").status_code == 200
        self._set_role("viewer")
        h = {"X-CSRF-Token": _csrf(web)}
        assert self._create(web, title="By viewer").status_code == 403
        assert web.patch(f"/compliance/deadlines/{d['id']}", json={"title": "x"},
                         headers=h).status_code == 403
        assert web.delete(f"/compliance/deadlines/{d['id']}", headers=h).status_code == 403
        assert web.get("/compliance/deadlines").status_code == 403
        c = _db()
        assert c.execute("SELECT COUNT(*) FROM compliance_deadlines").fetchone()[0] == 2
        c.close()


# ---------------------------------------------------------------- L-45
@pytest.mark.parametrize("name", [
    "Line One\nLine Two", 'Quote "Q" \\ back <b>&</b>', "Tab\there\r\nCRLF", "Ünï Ltd   sep",
])
def test_ubo_diagram_survives_awkward_names(conn, org_id, name):  # noqa: F811
    from amlkit.cases.diagram import generate_ubo_diagram

    cid = manager.onboard(conn, org_id=org_id, reference="D-1", full_name=name,
                          customer_type="legal").customer_id
    manager.add_ubo(conn, cid, org_id=org_id, person_name=name, ownership_pct=60.0)
    manager.add_ubo(conn, cid, org_id=org_id, person_name="Second\nOwner", ownership_pct=None,
                    control_type="senior_official")
    svg = generate_ubo_diagram(conn, cid, org_id)
    assert svg is not None and "<svg" in svg
    assert "Line Two" in svg or "Quote" in svg or "CRLF" in svg or "sep" in svg


# ---------------------------------------------------------------- L-41
class TestKytRulePage:
    def test_page_is_linked_formats_amounts_and_warns_above_default(self, web):
        home = web.get("/")
        assert 'href="/admin/rule-config"' in home.text

        page = web.get("/admin/rule-config").text
        assert 'value="55000"' in page and "55000.0" not in page
        assert "55,000" in page
        assert "does not raise a large-cash alert" not in page  # no warning at default

        r = web.post("/admin/rule-config",
                     data={"large_cash_threshold_aed": "250000", "csrf_token": _csrf(web)},
                     follow_redirects=True)
        assert "Warning" in r.text and "250,000" in r.text and "55,000" in r.text
        page = web.get("/admin/rule-config").text
        assert "above the" in page and "default of 55,000 AED" in page

    def test_unparseable_number_gets_readable_message(self, web):
        r = web.post("/admin/rule-config",
                     data={"large_cash_threshold_aed": "lots", "csrf_token": _csrf(web)},
                     follow_redirects=True)
        assert "could not convert" not in r.text
        assert "Large cash threshold must be a number" in r.text

    def test_audit_has_old_and_new_values(self, web):
        web.post("/admin/rule-config",
                 data={"large_cash_threshold_aed": "60000", "csrf_token": _csrf(web)})
        (row,) = _audit("settings.kyt_rules_update")
        assert row["detail_json"]["old"]["large_cash_threshold_aed"] == LARGE_CASH_THRESHOLD_AED
        assert row["detail_json"]["new"]["large_cash_threshold_aed"] == 60000.0

    def test_alert_detail_amounts_have_no_trailing_float(self, web):
        from amlkit.api.app import _fmt_amount
        assert _fmt_amount(55000.0) == "55,000"
        assert _fmt_amount(1234.5) == "1,234.50"
        assert _fmt_amount("x") == "x"

    def test_nan_threshold_rejected(self, web):
        r = web.post("/admin/rule-config",
                     data={"large_cash_threshold_aed": "nan", "csrf_token": _csrf(web)},
                     follow_redirects=True)
        assert "finite" in r.text


# ---------------------------------------------------------------- L-50
class TestUaePassIdentityMatch:
    def _profile(self, **over):
        from amlkit.uaepass import UaePassProfile
        base = dict(sub="s", uuid="u-1", idn="784-1990-1234567-1", fullname_en="Jane Doe",
                    fullname_ar=None, firstname_en=None, lastname_en=None, gender="Female",
                    mobile="971500000001", email="jane@x.ae", nationality_en="ARE",
                    nationality_ar=None, user_type="SOP3", raw={})
        return UaePassProfile(**(base | over))

    def _cust(self, conn, org_id, ref, name, **cols):
        cid = manager.onboard(conn, org_id=org_id, reference=ref, full_name=name).customer_id
        for k, v in cols.items():
            conn.execute(f"UPDATE customers SET {k}=? WHERE id=?", (v, cid))
        conn.commit()
        return cid

    def _status(self, conn, vid):
        return conn.execute("SELECT match_status, match_detail FROM uaepass_verifications"
                            " WHERE id=?", (vid,)).fetchone()

    def test_matching_name_reordered_is_match(self, conn, org_id):  # noqa: F811
        cid = self._cust(conn, org_id, "U-1", "Doe Jane")
        vid = manager.record_uaepass_verification(
            conn, cid, org_id, self._profile(), actor="a", verified_by=None)
        assert self._status(conn, vid)["match_status"] == "match"

    def test_name_mismatch_is_flagged_and_nothing_backfilled(self, conn, org_id):  # noqa: F811
        cid = self._cust(conn, org_id, "U-2", "Somebody Else")
        vid = manager.record_uaepass_verification(
            conn, cid, org_id, self._profile(), actor="a", verified_by=None)
        st = self._status(conn, vid)
        assert st["match_status"] == "mismatch" and "name" in st["match_detail"]
        row = conn.execute("SELECT id_number, email, phone FROM customers WHERE id=?",
                           (cid,)).fetchone()
        assert (row["id_number"], row["email"], row["phone"]) == (None, None, None)
        (a,) = [r for r in conn.execute(
            "SELECT detail FROM audit_log WHERE action='customer.uaepass_verify'")]
        assert json.loads(a["detail"])["match_status"] == "mismatch"

    def test_id_mismatch_is_flagged(self, conn, org_id):  # noqa: F811
        cid = self._cust(conn, org_id, "U-3", "Jane Doe",
                         id_number="784-1985-7654321-0", id_type="emirates_id")
        vid = manager.record_uaepass_verification(
            conn, cid, org_id, self._profile(), actor="a", verified_by=None)
        st = self._status(conn, vid)
        assert st["match_status"] == "mismatch" and "Emirates ID" in st["match_detail"]
        assert conn.execute("SELECT id_number FROM customers WHERE id=?",
                            (cid,)).fetchone()[0] == "784-1985-7654321-0"

    def test_duplicate_idn_not_backfilled(self, conn, org_id):  # noqa: F811
        self._cust(conn, org_id, "U-4a", "Other Person",
                   id_number="784199012345671", id_type="emirates_id")
        cid = self._cust(conn, org_id, "U-4b", "Jane Doe")
        vid = manager.record_uaepass_verification(
            conn, cid, org_id, self._profile(), actor="a", verified_by=None)
        st = self._status(conn, vid)
        assert st["match_status"] == "mismatch" and "another customer" in st["match_detail"]
        row = conn.execute("SELECT id_number, id_type FROM customers WHERE id=?", (cid,)).fetchone()
        assert (row["id_number"], row["id_type"]) == (None, None)

    def test_clean_new_customer_still_backfills(self, conn, org_id):  # noqa: F811
        cid = self._cust(conn, org_id, "U-5", "Jane Doe")
        vid = manager.record_uaepass_verification(
            conn, cid, org_id, self._profile(), actor="a", verified_by=None)
        assert self._status(conn, vid)["match_status"] == "match"
        row = conn.execute("SELECT id_number, id_type FROM customers WHERE id=?", (cid,)).fetchone()
        assert row["id_number"] == "784-1990-1234567-1" and row["id_type"] == "emirates_id"

    def test_customer_page_shows_mismatch_warning(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "up.db"))
        monkeypatch.setenv("UAEPASS_CLIENT_ID", "sandbox_stage")
        monkeypatch.setenv("UAEPASS_CLIENT_SECRET", "sandbox_stage")
        _seed_sanctions_data(tmp_path / "up.db")
        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        c = TestClient(app)
        _register(c, "Up Firm", "alice", "alice@up.ae")
        s = dbm.connect(os.environ["AMLKIT_DB"])
        org = s.execute("SELECT id FROM organizations").fetchone()["id"]
        cid = manager.onboard(s, org_id=org, reference="U-6", full_name="Somebody Else").customer_id
        s.commit()
        s.close()
        from test_uaepass import _SAMPLE_USERINFO, _extract_state, _mock_uaepass_exchange
        _mock_uaepass_exchange(monkeypatch, userinfo=dict(_SAMPLE_USERINFO))
        start = c.get(f"/customers/{cid}/uaepass/start", follow_redirects=False)
        state = _extract_state(start.headers["location"])
        r = c.get(f"/customers/{cid}/uaepass/callback?code=x&state={state}", follow_redirects=True)
        assert "does NOT match" in r.text
        page = c.get(f"/customers/{cid}").text
        assert "does not match the customer file" in page
