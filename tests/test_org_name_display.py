"""Test that organization name is displayed on every authenticated page."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _csrf(client) -> str:
    """The middleware sets a CSRF cookie on every response."""
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name: str, name: str, email: str, password: str = "a-strong-password-1"):
    """Registers, completes email verification and signs in."""
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


def _login(client, email: str, password: str = "a-strong-password-1"):
    """Log in as an existing operator."""
    client.get("/login")
    r = client.post("/login", data={
        "email": email, "password": password, "csrf_token": _csrf(client),
    }, follow_redirects=True)
    from conftest import settle_mfa  # p15: MLRO sessions start locked
    settle_mfa(client)
    return r


@pytest.fixture()
def org_a_client(tmp_path, monkeypatch):
    """Client logged in as Organization A."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Acme Corp", "alice", "alice@acme.ae")
    return c


@pytest.fixture()
def org_b_client(tmp_path, monkeypatch):
    """Client logged in as Organization B."""
    db_file = tmp_path / "test_b.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Beta LLC", "bob", "bob@beta.ae")
    return c


class TestOrgNameDisplay:
    """Test that every authenticated page shows the organization name."""

    def test_org_name_on_home_page(self, org_a_client) -> None:
        """Home page should show org name for logged-in user."""
        r = org_a_client.get("/")
        assert r.status_code == 200
        assert "Acme Corp" in r.text, "Expected org name 'Acme Corp' to appear on home page"

    def test_org_name_on_dashboard(self, org_a_client) -> None:
        """Dashboard should show org name."""
        r = org_a_client.get("/dashboard")
        assert r.status_code == 200
        assert "Acme Corp" in r.text, "Expected org name 'Acme Corp' to appear on dashboard"

    def test_org_name_on_customers_page(self, org_a_client) -> None:
        """Customers page should show org name."""
        r = org_a_client.get("/customers")
        assert r.status_code == 200
        assert "Acme Corp" in r.text, "Expected org name 'Acme Corp' to appear on customers page"

    def test_org_name_on_alerts_page(self, org_a_client) -> None:
        """Alerts page should show org name."""
        r = org_a_client.get("/alerts")
        assert r.status_code == 200
        assert "Acme Corp" in r.text, "Expected org name 'Acme Corp' to appear on alerts page"

    def test_org_name_on_screen_page(self, org_a_client) -> None:
        """Screen page should show org name."""
        r = org_a_client.get("/screen")
        assert r.status_code == 200
        assert "Acme Corp" in r.text, "Expected org name 'Acme Corp' to appear on screen page"

    def test_different_orgs_show_different_names(self, tmp_path, monkeypatch) -> None:
        """Operators from different orgs should see their own org name."""
        # Create org A
        db_a = tmp_path / "test_a.db"
        monkeypatch.setenv("AMLKIT_DB", str(db_a))

        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        client_a = TestClient(app)
        _register(client_a, "Acme Corp", "alice", "alice@acme.ae")

        r_a = client_a.get("/")
        assert "Acme Corp" in r_a.text, "Org A should see 'Acme Corp'"
        assert "Beta LLC" not in r_a.text, "Org A should not see 'Beta LLC'"

        # Create org B in a separate database
        db_b = tmp_path / "test_b.db"
        monkeypatch.setenv("AMLKIT_DB", str(db_b))

        client_b = TestClient(app)
        _register(client_b, "Beta LLC", "bob", "bob@beta.ae")

        r_b = client_b.get("/")
        assert "Beta LLC" in r_b.text, "Org B should see 'Beta LLC'"
        assert "Acme Corp" not in r_b.text, "Org B should not see 'Acme Corp'"


class TestOrgNameInEmptyStates:
    """Test that empty states mention the organization name."""

    def test_customers_empty_state_mentions_org(self, org_a_client) -> None:
        """Empty customers list should mention the org name."""
        r = org_a_client.get("/customers")
        assert r.status_code == 200
        # Should see both "No customers" and org name in the empty state
        assert "No customers" in r.text
        assert "Acme Corp" in r.text

    def test_alerts_empty_state_mentions_org(self, org_a_client) -> None:
        """Empty alerts list should mention the org name."""
        r = org_a_client.get("/alerts")
        assert r.status_code == 200
        # Should see both "No alerts" and org name
        assert "No alerts" in r.text
        assert "Acme Corp" in r.text
