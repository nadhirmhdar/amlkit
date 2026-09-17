"""Dashboard 24-hour-rule breach banner tests.

The banner previously told the operator to run `scripts/refresh.py`. That
script only touches the machine it runs on -- on the hosted Cloud Run
deployment that is a different database than the one this page reads, so
following the instruction looks like a fix and does nothing. The banner
must point to the actual in-app remedy instead (Admin -> "Refresh sanctions
lists now"), which updates this deployment's real data on every deployment
model (local or hosted) alike.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name: str, name: str, email: str, password: str = "a-strong-password-1",
              invite_code: str = "test-invite"):
    """Registers, then completes email verification via the dev-fallback
    link the response renders (no SMTP configured in tests -- see
    amlkit/mail.py), so callers still get back a signed-in client."""
    import re

    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client), "invite_code": invite_code,
    }, follow_redirects=True)
    assert "Check your email" in r.text, f"registration failed: {r.text[:300]}"
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m, f"no dev verification link in registration response: {r.text[:500]}"
    r2 = client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    assert "Dashboard" in r2.text or "24-hour" in r2.text, f"verification failed: {r2.text[:300]}"
    return client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import os

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, upsert_dataset

    c = TestClient(app)
    _register(c, "Test Firm", "alice", "alice@testfirm.ae")

    conn = connect(os.environ["AMLKIT_DB"])
    upsert_dataset(conn, "un_sc_sanctions", "UN Consolidated Sanctions List",
                    is_mandatory=True)
    conn.execute("UPDATE datasets SET last_refresh = '2020-01-01T00:00:00+00:00' "
                 "WHERE key = 'un_sc_sanctions'")
    conn.commit()
    conn.close()
    return c


class TestBreachBanner:
    def test_banner_points_to_admin_refresh_not_local_script(self, client) -> None:
        # The dashboard (where this banner lives) moved from "/" to
        # "/dashboard" in a later PR -- "/" is now the home/orientation
        # screen (see test_api.py::TestHomePage).
        r = client.get("/dashboard")
        assert r.status_code == 200
        assert "24-HOUR RULE BREACHED" in r.text
        assert "scripts/refresh.py" not in r.text
        assert "/admin" in r.text
        assert "Refresh sanctions lists now" in r.text
