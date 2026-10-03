"""Report types offered/accepted for creation must match what goAML export supports.

report_new.html used to hard-code eight report types (STR, SAR, PNMR, FFR,
HRCT, HRCA, DPMSR, REAR) while goaml.SUPPORTED_REPORT_TYPES only exports
STR/SAR/FFR, and POST /reports saved any report_type string at all (a probe
saved "BOGUS" as goAML-BOGUS-1). The picker is now derived from
goaml.CREATABLE_REPORT_TYPES and save_report (plus the mobile API) rejects
anything outside it. FFR stays out of the generic form: it is filed via
/freeze-obligations/{id}/file-ffr, and its export needs a
freeze_obligation_id the generic form never sets.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_report_save_flow import NATURAL_PERSON_FORM, _csrf, _customer_id, _register  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    from test_api import _seed_sanctions_data
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


def _report_rows(customer_id: int) -> list:
    from amlkit.db import connect
    conn = connect(os.environ["AMLKIT_DB"])
    rows = conn.execute(
        "SELECT report_type, reference FROM reports WHERE customer_id=?", (customer_id,)
    ).fetchall()
    conn.close()
    return rows


def test_creatable_types_are_exportable_and_exclude_freeze_only_ffr() -> None:
    from amlkit.reporting.goaml import CREATABLE_REPORT_TYPES, SUPPORTED_REPORT_TYPES
    assert set(CREATABLE_REPORT_TYPES) <= SUPPORTED_REPORT_TYPES
    assert CREATABLE_REPORT_TYPES == ("STR", "SAR")


def test_new_report_form_lists_only_creatable_types(client) -> None:
    from amlkit.reporting.goaml import CREATABLE_REPORT_TYPES
    r = client.get("/reports/new")
    assert r.status_code == 200
    select = re.search(r'<select name="report_type".*?</select>', r.text, re.S).group(0)
    offered = re.findall(r'<option value="([^"]*)"', select)
    assert offered == list(CREATABLE_REPORT_TYPES)
    assert "STR — Suspicious Transaction Report" in select
    assert "SAR — Suspicious Activity Report" in select
    for gone in ("PNMR", "HRCT", "HRCA", "DPMSR", "REAR", "FFR"):
        assert gone not in select


@pytest.mark.parametrize("report_type", ["BOGUS", "PNMR", "FFR"])
def test_post_reports_rejects_non_creatable_type(client, report_type) -> None:
    customer_id = _customer_id(client)
    r = client.post("/reports", data={
        "customer_id": customer_id, "report_type": report_type,
        "csrf_token": _csrf(client), **NATURAL_PERSON_FORM,
    }, follow_redirects=True)
    assert r.status_code != 500
    assert "is not supported" in r.text
    assert _report_rows(customer_id) == []


def test_post_reports_still_saves_str(client) -> None:
    customer_id = _customer_id(client)
    client.post("/reports", data={
        "customer_id": customer_id, "report_type": "STR",
        "csrf_token": _csrf(client), **NATURAL_PERSON_FORM,
    })
    rows = _report_rows(customer_id)
    assert len(rows) == 1
    assert rows[0]["report_type"] == "STR"


def test_legacy_rows_of_other_types_still_display(client) -> None:
    """Rows saved before this check (e.g. PNMR) must still list and open."""
    from amlkit.db import connect, utcnow
    customer_id = _customer_id(client)
    conn = connect(os.environ["AMLKIT_DB"])
    org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
    with conn:
        cur = conn.execute(
            "INSERT INTO reports (org_id, customer_id, report_type, status, payload, created_at, reference)"
            " VALUES (?,?,?,?,?,?,?)",
            (org_id, customer_id, "PNMR", "draft", "{}", utcnow(), "goAML-PNMR-legacy"),
        )
    rid = cur.lastrowid
    conn.close()

    r = client.get("/reports")
    assert r.status_code == 200
    assert "goAML-PNMR-legacy" in r.text
    r = client.get(f"/reports/{rid}")
    assert r.status_code == 200


def test_mobile_api_rejects_non_creatable_type(tmp_path, monkeypatch) -> None:
    db_file = tmp_path / "mobile.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    from test_api import _seed_sanctions_data
    _seed_sanctions_data(db_file)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from conftest import unlock_mobile_mfa

    client = TestClient(app)
    r = client.post("/api/v1/auth/register-organization", json={
        "org_name": "Test Firm", "name": "alice", "email": "alice@testfirm.ae",
        "password": "a-strong-password-1", "invite_code": "test-invite",
    })
    r = client.post("/api/v1/auth/verify-email", json={"token": r.json()["dev_verification_token"]})
    token = r.json()["token"]
    unlock_mobile_mfa(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    cid = client.post("/api/v1/customers", headers=headers, json={
        "reference": "CUST-T", "full_name": "Report Subject",
    }).json()["customer_id"]
    body = {
        "customer_id": cid, "reporting_entity_name": "Test Firm", "entity_reference": "TF-1",
        "reporter_name": "alice", "reporter_email": "alice@testfirm.ae",
        "first_name": "Report", "last_name": "Subject",
    }
    for bad in ("BOGUS", "PNMR"):
        r = client.post("/api/v1/reports", headers=headers, json={**body, "report_type": bad})
        assert r.status_code == 400, r.text
    assert _report_rows(cid) == []
    r = client.post("/api/v1/reports", headers=headers, json={**body, "report_type": "STR"})
    assert r.status_code == 200, r.text
