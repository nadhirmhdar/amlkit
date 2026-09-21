"""STR/goAML draft builder page tests.

The onboarding form's `required` attribute blocks a blank customer name from
the UI, but nothing enforces that at the DB layer -- a customer record
created another way (a script, a future import path, direct API use) can
still have an empty or whitespace-only full_name. The builder page must
render a usable form in that case, not throw an unhandled IndexError from
`full_name.split()[0]`.
"""

from __future__ import annotations

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
    _register(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


def _blank_name_customer_id(org_id: int) -> int:
    import os

    from amlkit.cases.manager import onboard
    from amlkit.db import connect

    conn = connect(os.environ["AMLKIT_DB"])
    result = onboard(conn, org_id=org_id, reference="C-BLANK-1", full_name="   ",
                      customer_type="natural", nationality="ae", actor="tester")
    conn.close()
    return result.customer_id


class TestBuilderHandlesBlankCustomerName:
    def test_build_page_does_not_500_on_blank_full_name(self, client) -> None:
        import os

        from amlkit.db import connect
        db = connect(os.environ["AMLKIT_DB"])
        org_id = db.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
        db.close()

        customer_id = _blank_name_customer_id(org_id)

        r = client.get(f"/reports/build?customer_id={customer_id}&report_type=STR")
        assert r.status_code == 200
        assert "500" not in r.text[:50]
