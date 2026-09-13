"""End-to-end STR/SAR report save + export flow tests.

`report_save` (POST /reports) declared `customer_id` and `report_type`
without `Annotated[..., Form()]`, so FastAPI treated them as required QUERY
parameters -- but str_builder.html's <form method="post" action="/reports">
sends them as hidden form fields, with no query string in the action URL.
Every real submission of the report builder therefore 422'd ("Field
required": query customer_id, report_type) and no report was ever saved.
Zero test coverage on this route meant this had never been caught. This
file locks in the fix and the full build -> save -> export path behind it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name: str, name: str, email: str, password: str = "a-strong-password-1"):
    """Registers, then completes email verification via the dev-fallback
    link the response renders (no SMTP configured in tests -- see
    amlkit/mail.py), so callers still get back a signed-in client."""
    import re

    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert "Check your email" in r.text, f"registration failed: {r.text[:300]}"
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m, f"no dev verification link in registration response: {r.text[:500]}"
    r2 = client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    assert "Dashboard" in r2.text or "24-hour" in r2.text, f"verification failed: {r2.text[:300]}"
    return client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_api import _seed_sanctions_data

    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


def _customer_id(client, **overrides) -> int:
    from amlkit.cases.manager import onboard
    from amlkit.db import connect

    conn = connect(os.environ["AMLKIT_DB"])
    org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
    kwargs = {"reference": "C-1", "full_name": "Ahmed Al Mansoori",
              "customer_type": "natural", "nationality": "ae"}
    kwargs.update(overrides)
    result = onboard(conn, org_id=org_id, actor="tester", **kwargs)
    conn.close()
    return result.customer_id


NATURAL_PERSON_FORM = {
    "reporting_entity_name": "Test Firm", "entity_reference": "LIC-1",
    "reporter_name": "Alice MLRO", "reporter_email": "alice@testfirm.ae",
    "first_name": "Ahmed", "last_name": "Al Mansoori", "nationality": "AE",
    "amount": "75000", "transaction_type": "Wire Transfer",
    "source_account": "AE070331234567890123456",
    "destination_account": "AE070339876543210987654",
    "reason_description": "Large wire inconsistent with declared income.",
}


class TestReportSave:
    def test_customer_id_and_report_type_are_read_from_the_form_body(self, client) -> None:
        """Regression test: str_builder.html sends customer_id/report_type as
        hidden form fields (no query string in the form's action URL) -- the
        save route must accept that, not require them as URL query params."""
        customer_id = _customer_id(client)
        r = client.post("/reports", data={
            "customer_id": customer_id, "report_type": "STR",
            "csrf_token": _csrf(client), **NATURAL_PERSON_FORM,
        })
        assert r.status_code != 422, r.text

    def test_saved_report_is_persisted_and_exportable(self, client) -> None:
        customer_id = _customer_id(client)
        client.post("/reports", data={
            "customer_id": customer_id, "report_type": "STR",
            "csrf_token": _csrf(client), **NATURAL_PERSON_FORM,
        })

        from amlkit.db import connect
        conn = connect(os.environ["AMLKIT_DB"])
        row = conn.execute(
            "SELECT id FROM reports WHERE customer_id=? ORDER BY id DESC LIMIT 1", (customer_id,)
        ).fetchone()
        conn.close()
        assert row is not None, "no report row was saved"

        r = client.get(f"/reports/{row['id']}/export")
        assert r.status_code == 200
        assert "<report_code>STR</report_code>" in r.text
        assert "Ahmed" in r.text

    def test_legal_entity_report_exports_correct_entity_name(self, client) -> None:
        customer_id = _customer_id(client, reference="C-2", full_name="Desert Rose Trading LLC",
                                    customer_type="legal", sector="real_estate")
        form = dict(NATURAL_PERSON_FORM)
        form["first_name"] = "Desert Rose Trading LLC"
        del form["last_name"]

        client.post("/reports", data={
            "customer_id": customer_id, "report_type": "STR",
            "csrf_token": _csrf(client), **form,
        })

        from amlkit.db import connect
        conn = connect(os.environ["AMLKIT_DB"])
        row = conn.execute(
            "SELECT id FROM reports WHERE customer_id=? ORDER BY id DESC LIMIT 1", (customer_id,)
        ).fetchone()
        conn.close()

        r = client.get(f"/reports/{row['id']}/export")
        assert r.status_code == 200
        assert "<name>Desert Rose Trading LLC</name>" in r.text
        assert "Unknown Entity" not in r.text

    def test_export_blocks_on_missing_source_account_instead_of_500(self, client) -> None:
        customer_id = _customer_id(client)
        form = dict(NATURAL_PERSON_FORM)
        form["source_account"] = ""

        client.post("/reports", data={
            "customer_id": customer_id, "report_type": "SAR",
            "csrf_token": _csrf(client), **form,
        })

        from amlkit.db import connect
        conn = connect(os.environ["AMLKIT_DB"])
        row = conn.execute(
            "SELECT id FROM reports WHERE customer_id=? ORDER BY id DESC LIMIT 1", (customer_id,)
        ).fetchone()
        conn.close()

        r = client.get(f"/reports/{row['id']}/export")
        assert r.status_code == 400
        assert "source account" in r.json()["detail"]

    def test_malformed_amount_returns_form_error_instead_of_500(self, client) -> None:
        """A non-numeric amount (e.g. "12,000" with a thousands separator)
        must not 500 and discard the whole draft -- every other field on
        this route already fails this way, amount didn't."""
        customer_id = _customer_id(client)
        form = dict(NATURAL_PERSON_FORM)
        form["amount"] = "12,000"

        r = client.post("/reports", data={
            "customer_id": customer_id, "report_type": "STR",
            "csrf_token": _csrf(client), **form,
        }, follow_redirects=False)
        assert r.status_code != 500

        from amlkit.db import connect
        conn = connect(os.environ["AMLKIT_DB"])
        row = conn.execute(
            "SELECT id FROM reports WHERE customer_id=?", (customer_id,)
        ).fetchone()
        conn.close()
        assert row is None, "a report was saved despite the malformed amount"

    def test_rejects_customer_id_belonging_to_another_org(self, client) -> None:
        """A customer_id from another org must not silently default to
        "natural" and get a report saved against it under this session's
        org_id -- that would let an operator build an STR/SAR draft (and
        later a goAML export) against another tenant's customer."""
        customer_id = _customer_id(client)

        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        other = TestClient(app, cookies={})
        _register(other, "Other Firm", "bob", "bob@otherfirm.ae")

        r = other.post("/reports", data={
            "customer_id": customer_id, "report_type": "STR",
            "csrf_token": _csrf(other), **NATURAL_PERSON_FORM,
        })
        assert "not found" in r.text

        from amlkit.db import connect
        conn = connect(os.environ["AMLKIT_DB"])
        row = conn.execute(
            "SELECT id FROM reports WHERE customer_id=?", (customer_id,)
        ).fetchone()
        conn.close()
        assert row is None, "a report was saved against another org's customer"
