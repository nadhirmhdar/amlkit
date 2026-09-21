"""End-to-end route tests for transaction monitoring, e-signature, and the
identity-verification authenticity signal -- exercised as real HTTP requests
through the actual FastAPI app, the same way a browser session would, rather
than by calling the underlying engine functions directly (already covered in
test_kyt.py / test_signatures.py / test_ocr.py).

This is the verification path used in place of logging into the live Cloud
Run deployment with a real operator's credentials -- entering someone's
password to authenticate on their behalf isn't something this assistant
does, even when the credential is handed over directly for that purpose. A
throwaway org/operator created by this fixture, purely for this test run,
raises none of that concern.

Fixture setup duplicates test_api.py's `client`/`_csrf`/`_register`/`_login`
helpers rather than importing them -- consistent with this test suite's
existing style of per-file fixtures (see test_cases.py, test_kyt.py).
"""

from __future__ import annotations

import os
import sqlite3
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
        "csrf_token": _csrf(client), "invite_code": "test-invite",
    }, follow_redirects=True)
    assert "Check your email" in r.text, f"registration failed: {r.text[:300]}"
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m, f"no dev verification link in registration response: {r.text[:500]}"
    r2 = client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    from conftest import settle_mfa  # p15: MLRO sessions start locked
    settle_mfa(client)
    assert any(s in r2.text for s in ("Dashboard", "24-hour", "Two-Factor")), f"verification failed: {r2.text[:300]}"
    return client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    # Seed fresh dataset so onboard() passes the staleness guard
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_api import _seed_sanctions_data
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "E2E Test Firm", "shahabas", "shahabas@e2e-test.invalid")
    return c


@pytest.fixture()
def customer_id(client) -> int:
    r = client.post("/customers", data={
        "reference": "E2E-1", "full_name": "Test Customer", "customer_type": "natural",
        "sector": "real_estate", "csrf_token": _csrf(client), "invite_code": "test-invite",
    }, follow_redirects=True)
    assert r.status_code == 200
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id FROM customers WHERE reference='E2E-1'").fetchone()
    conn.close()
    assert row is not None
    return row["id"]


class TestTransactionMonitoringE2E:
    def test_large_cash_transaction_raises_a_visible_alert(self, client, customer_id) -> None:
        r = client.post(f"/customers/{customer_id}/transactions", data={
            "direction": "inbound", "method": "cash", "amount": "60000",
            "csrf_token": _csrf(client), "invite_code": "test-invite",
        }, follow_redirects=True)
        assert r.status_code == 200
        assert "large cash" in r.text.lower()
        assert "1 rule" in r.text.lower() or "rule(s) triggered" in r.text.lower()

        page = client.get(f"/customers/{customer_id}")
        assert "large cash" in page.text.lower()
        assert "60,000.00" in page.text

    def test_small_cash_transaction_raises_no_alert(self, client, customer_id) -> None:
        r = client.post(f"/customers/{customer_id}/transactions", data={
            "direction": "inbound", "method": "cash", "amount": "500",
            "csrf_token": _csrf(client), "invite_code": "test-invite",
        }, follow_redirects=True)
        assert "no rules triggered" in r.text.lower()

    def test_dashboard_shows_open_transaction_alert_count(self, client, customer_id) -> None:
        client.post(f"/customers/{customer_id}/transactions", data={
            "direction": "inbound", "method": "cash", "amount": "60000",
            "csrf_token": _csrf(client), "invite_code": "test-invite",
        })
        dash = client.get("/dashboard")
        assert "Transaction alerts open" in dash.text

    def test_disposition_clears_the_alert_from_the_customer_page(self, client, customer_id) -> None:
        client.post(f"/customers/{customer_id}/transactions", data={
            "direction": "inbound", "method": "cash", "amount": "60000",
            "csrf_token": _csrf(client), "invite_code": "test-invite",
        })
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        conn.row_factory = sqlite3.Row
        alert_id = conn.execute(
            "SELECT id FROM transaction_alerts ORDER BY id DESC LIMIT 1"
        ).fetchone()["id"]
        conn.close()

        r = client.post(f"/transaction-alerts/{alert_id}/disposition", data={
            "status": "false_positive", "note": "Verified payroll run",
            "customer_id": str(customer_id), "csrf_token": _csrf(client), "invite_code": "test-invite",
        }, follow_redirects=True)
        assert r.status_code == 200
        assert "dispositioned" in r.text.lower()

        page = client.get(f"/customers/{customer_id}")
        assert "false positive" in page.text.lower()

    def test_missing_session_redirects_to_login(self, client, customer_id) -> None:
        client.cookies.delete("amlkit_session")
        r = client.post(f"/customers/{customer_id}/transactions", data={
            "direction": "inbound", "method": "cash", "amount": "1000",
            "csrf_token": _csrf(client), "invite_code": "test-invite",
        }, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"

    def test_other_orgs_customer_is_not_reachable(self, client, customer_id) -> None:
        """Same cross-tenant boundary test_api.py already applies to
        alerts/ubo/notes -- a second org's operator must not be able to post
        a transaction against this org's customer."""
        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        other = TestClient(app)
        _register(other, "Other Firm", "bob", "bob@other-e2e-test.invalid")
        r = other.post(f"/customers/{customer_id}/transactions", data={
            "direction": "inbound", "method": "cash", "amount": "60000",
            "csrf_token": _csrf(other),
        }, follow_redirects=True)
        assert "not found" in r.text.lower()


class TestSignatureE2E:
    def test_signature_capture_appears_on_customer_page(self, client, customer_id) -> None:
        r = client.post(f"/customers/{customer_id}/signatures", data={
            "purpose": "Risk acknowledgment",
            "statement": "I acknowledge the assigned risk rating and CDD outcome.",
            "signer_name": "Test Customer", "signer_role": "customer",
            "csrf_token": _csrf(client), "invite_code": "test-invite",
        }, follow_redirects=True)
        assert r.status_code == 200
        assert "Signed by Test Customer" in r.text

        page = client.get(f"/customers/{customer_id}")
        assert "Risk acknowledgment" in page.text
        assert "sha256:" in page.text

    def test_empty_statement_is_rejected(self, client, customer_id) -> None:
        r = client.post(f"/customers/{customer_id}/signatures", data={
            "purpose": "x", "statement": "   ", "signer_name": "Test Customer",
            "csrf_token": _csrf(client), "invite_code": "test-invite",
        }, follow_redirects=True)
        assert "required" in r.text.lower()

    def test_hash_recorded_in_database_matches_content(self, client, customer_id) -> None:
        import hashlib

        client.post(f"/customers/{customer_id}/signatures", data={
            "purpose": "P", "statement": "S", "signer_name": "N",
            "csrf_token": _csrf(client), "invite_code": "test-invite",
        })
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT content_hash, ip_address FROM signatures ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        expected = hashlib.sha256("\x1f".join(["P", "S", "N"]).encode()).hexdigest()
        assert row["content_hash"] == expected
        assert row["ip_address"] is not None  # TestClient sets a client host


class TestIdentityVerificationE2E:
    def test_scan_passport_response_includes_authenticity_field(self, client) -> None:
        """Doesn't require a real passport image. `extract_passport_data`
        swallows both MRZ-read and OCR-fallback failures internally (existing
        behavior, unchanged here) rather than raising, so garbage bytes exercise
        the same code path a blurry real-world phone photo would: the route
        responds 200 with mostly-null fields, and `authenticity` is present
        (None, since no MRZ was read) rather than missing from the response
        entirely -- confirming the new field is actually wired into the JSON
        contract the onboarding page's JS reads."""
        import io
        r = client.post(
            "/customers/scan-passport",
            files={"passport_file": ("test.jpg", io.BytesIO(b"not a real image"), "image/jpeg")},
            data={"csrf_token": _csrf(client)},
        )
        assert r.status_code == 200
        data = r.json()
        assert "authenticity" in data
        assert data["authenticity"] is None
        assert data["full_name"] is None

    def test_scan_passport_rejects_missing_csrf_token(self, client) -> None:
        """The only mutating POST route that used to skip require_csrf --
        must now match every sibling route in app.py."""
        import io
        r = client.post(
            "/customers/scan-passport",
            files={"passport_file": ("test.jpg", io.BytesIO(b"not a real image"), "image/jpeg")},
        )
        assert r.status_code == 403
