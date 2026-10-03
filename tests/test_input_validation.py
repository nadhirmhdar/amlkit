"""Server-side input validation regressions.

Each of these inputs used to be accepted and saved verbatim because only the
HTML form (a `<select>`, `type="email"`, `type="date"`) constrained it -- a
hand-crafted POST or a mobile-API call bypassed that entirely:

- POST /admin/operators saved an unknown role ('superadmin') and an invalid
  email.
- Onboarding (web and mobile, both through cases.manager.onboard) saved a
  5,000-character name, an impossible birth date and an unknown
  customer_type.
- POST /reports (and the mobile report API) saved a negative amount.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_api import _csrf, _flash_parse, _register, _seed_sanctions_data  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


def _conn():
    from amlkit.db import connect
    return connect(os.environ["AMLKIT_DB"])


def _flash_err(r) -> str:
    raw = r.cookies.get("amlkit_flash")
    assert raw, f"no flash cookie on response {r.status_code}"
    flash = _flash_parse(raw)
    assert flash["type"] == "err", flash
    return flash["text"]


def _org_id() -> int:
    conn = _conn()
    try:
        return conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
    finally:
        conn.close()


# --------------------------------------------------------------------------
# /admin/operators
# --------------------------------------------------------------------------

def _operator_count() -> int:
    conn = _conn()
    try:
        return conn.execute("SELECT COUNT(*) c FROM operators").fetchone()["c"]
    finally:
        conn.close()


class TestAdminCreateOperator:
    def _post(self, client, **overrides):
        data = {"name": "bob", "email": "bob@testfirm.ae",
                "password": "a-strong-password-2", "role": "officer",
                "csrf_token": _csrf(client)}
        data.update(overrides)
        return client.post("/admin/operators", data=data, follow_redirects=False)

    def test_unknown_role_is_rejected(self, client):
        before = _operator_count()
        r = self._post(client, role="superadmin")
        assert r.status_code == 303
        assert "role" in _flash_err(r).lower()
        assert _operator_count() == before

    def test_invalid_email_is_rejected(self, client):
        before = _operator_count()
        r = self._post(client, email="not-an-email")
        assert r.status_code == 303
        assert "email" in _flash_err(r).lower()
        assert _operator_count() == before

    @pytest.mark.parametrize("role", ["officer", "mlro"])
    def test_supported_roles_still_create(self, client, role):
        r = self._post(client, role=role, email=f"bob-{role}@testfirm.ae", name=f"bob-{role}")
        assert r.status_code == 303
        conn = _conn()
        try:
            row = conn.execute("SELECT role FROM operators WHERE email=?",
                               (f"bob-{role}@testfirm.ae",)).fetchone()
        finally:
            conn.close()
        assert row is not None and row["role"] == role


# --------------------------------------------------------------------------
# Onboarding: shared write layer (cases.manager.onboard)
# --------------------------------------------------------------------------

def _customer_count() -> int:
    conn = _conn()
    try:
        return conn.execute("SELECT COUNT(*) c FROM customers").fetchone()["c"]
    finally:
        conn.close()


class TestOnboardValidation:
    def _post(self, client, **overrides):
        data = {"reference": "C-1", "full_name": "Ordinary Person",
                "customer_type": "natural", "nationality": "AE",
                "csrf_token": _csrf(client)}
        data.update(overrides)
        return client.post("/customers", data=data, follow_redirects=False)

    @pytest.mark.parametrize("overrides, needle", [
        ({"full_name": "A" * 5000}, "full_name"),
        ({"name_arabic": "أ" * 5000}, "name_arabic"),
        ({"birth_date": "2030-13-45"}, "birth_date"),
        ({"birth_date": "not-a-date"}, "birth_date"),
        ({"birth_date": "2999-01-01"}, "future"),
        ({"customer_type": "alien"}, "customer_type"),
    ])
    def test_web_onboarding_rejects(self, client, overrides, needle):
        before = _customer_count()
        r = self._post(client, **overrides)
        assert r.status_code == 303
        assert r.headers["location"].startswith("/customers/new")
        assert needle in _flash_err(r)
        assert _customer_count() == before

    def test_valid_inputs_still_onboard(self, client):
        from amlkit.datamodel import MAX_NAME_LENGTH
        r = self._post(client, full_name="B" * MAX_NAME_LENGTH, birth_date="1990-01-01")
        assert r.status_code == 303
        assert r.headers["location"] != "/customers/new"
        conn = _conn()
        try:
            row = conn.execute("SELECT birth_date FROM customers WHERE reference='C-1'").fetchone()
        finally:
            conn.close()
        assert row is not None and row["birth_date"] == "1990-01-01"

    def test_direct_onboard_call_rejects_bad_customer_type(self, client):
        """Validation lives in the shared write layer, not just the route."""
        from amlkit.cases.manager import onboard
        conn = _conn()
        try:
            with pytest.raises(ValueError, match="customer_type"):
                onboard(conn, org_id=_org_id(), reference="C-X", full_name="X Y",
                        customer_type="alien")
        finally:
            conn.close()


@pytest.fixture()
def api(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    r = c.post("/api/v1/auth/register-organization", json={
        "org_name": "Test Firm", "name": "alice", "email": "alice@testfirm.ae",
        "password": "a-strong-password-1", "invite_code": "test-invite",
    })
    assert r.status_code == 200, r.text
    r2 = c.post("/api/v1/auth/verify-email",
                json={"token": r.json()["dev_verification_token"]})
    token = r2.json()["token"]
    from conftest import unlock_mobile_mfa
    unlock_mobile_mfa(c, token)
    return c, {"Authorization": f"Bearer {token}"}


class TestMobileOnboardValidation:
    @pytest.mark.parametrize("overrides", [
        {"full_name": "A" * 5000},
        {"birth_date": "2030-13-45"},
        {"customer_type": "alien"},
    ])
    def test_mobile_onboarding_rejects(self, api, overrides):
        client, headers = api
        before = _customer_count()
        body = {"reference": "M-1", "full_name": "Ordinary Person"}
        body.update(overrides)
        r = client.post("/api/v1/customers", headers=headers, json=body)
        assert r.status_code == 422, r.text
        assert _customer_count() == before


# --------------------------------------------------------------------------
# Reports: negative amounts
# --------------------------------------------------------------------------

REPORT_FORM = {
    "report_type": "STR",
    "reporting_entity_name": "Test Firm", "entity_reference": "LIC-1",
    "reporter_name": "Alice MLRO", "reporter_email": "alice@testfirm.ae",
    "first_name": "Ahmed", "last_name": "Al Mansoori", "nationality": "AE",
    "transaction_type": "Wire Transfer",
    "reason_description": "Large wire inconsistent with declared income.",
}


def _onboarded_customer_id() -> int:
    from amlkit.cases.manager import onboard
    conn = _conn()
    try:
        return onboard(conn, org_id=_org_id(), reference="R-1", full_name="Ahmed Al Mansoori",
                       customer_type="natural", nationality="AE", actor="tester").customer_id
    finally:
        conn.close()


def _report_count() -> int:
    conn = _conn()
    try:
        return conn.execute("SELECT COUNT(*) c FROM reports").fetchone()["c"]
    finally:
        conn.close()


class TestReportAmount:
    @pytest.mark.parametrize("amount", ["-500", "-0.01", "nan", "inf"])
    def test_web_report_rejects_negative_or_non_finite_amount(self, client, amount):
        cid = _onboarded_customer_id()
        before = _report_count()
        r = client.post("/reports", data={
            "customer_id": cid, "amount": amount, "csrf_token": _csrf(client), **REPORT_FORM,
        }, follow_redirects=False)
        assert r.status_code == 303
        assert "amount" in _flash_err(r).lower()
        assert _report_count() == before

    @pytest.mark.parametrize("amount", ["0", "75000", ""])
    def test_web_report_accepts_zero_positive_or_blank(self, client, amount):
        cid = _onboarded_customer_id()
        before = _report_count()
        r = client.post("/reports", data={
            "customer_id": cid, "amount": amount, "csrf_token": _csrf(client), **REPORT_FORM,
        }, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].startswith("/reports/")
        assert _report_count() == before + 1

    def test_save_report_rejects_negative_amount(self, client):
        from amlkit.cases.reports import save_report
        cid = _onboarded_customer_id()
        conn = _conn()
        try:
            f = REPORT_FORM
            result = save_report(
                conn, _org_id(), "tester", cid, f["report_type"], f["reporting_entity_name"],
                f["entity_reference"], f["reporter_name"], f["reporter_email"],
                f["first_name"], f["last_name"], f["nationality"], "", "", "", "",
                "-500", f["transaction_type"], "", "", "", f["reason_description"],
                "", "", None,
            )
        finally:
            conn.close()
        assert result.success is False
        assert "amount" in result.error.lower()

    def test_mobile_report_rejects_negative_amount(self, api):
        client, headers = api
        r = client.post("/api/v1/customers", headers=headers,
                        json={"reference": "R-M", "full_name": "Ahmed Al Mansoori"})
        assert r.status_code == 200, r.text
        cid = r.json()["customer_id"]
        before = _report_count()
        body = {k: v for k, v in REPORT_FORM.items()}
        body.update({"customer_id": cid, "amount": -500})
        r = client.post("/api/v1/reports", headers=headers, json=body)
        assert r.status_code in (400, 422), r.text
        assert _report_count() == before
