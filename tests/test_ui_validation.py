"""Tests for progress indicators and HTML5 form validation attributes.

Verifies that key forms have the expected validation attributes and
data-loading hints for the spinner system.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _seed_sanctions_data(db_file) -> None:
    from amlkit.db import connect, upsert_dataset, utcnow
    from amlkit.names.arabic import blocking_keys, canonical_key

    conn = connect(db_file)
    ds = upsert_dataset(conn, "test_list", "Test Sanctions List", is_mandatory=True)
    conn.commit()
    conn.close()


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name, name, email, password="a-strong-password-1"):
    import re as _re
    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    m = _re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    if m:
        client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
        from conftest import settle_mfa  # p15: MLRO sessions start locked
        settle_mfa(client)
    return client


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


@pytest.fixture()
def anon_client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    from amlkit.db import connect
    connect(db_file).close()
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    return TestClient(app)


class TestProgressIndicators:
    def test_screen_button_has_data_loading(self, client) -> None:
        r = client.get("/screen")
        assert 'data-loading="Screening' in r.text

    def test_admin_refresh_has_data_loading(self, client) -> None:
        r = client.get("/admin")
        assert 'data-loading="Refreshing' in r.text

    def test_onboard_button_has_data_loading(self, client) -> None:
        r = client.get("/customers/new")
        assert 'data-loading="Onboarding' in r.text

    def test_base_template_has_spinner_js(self, client) -> None:
        # Spinner JS moved to app.js (CSP no-unsafe-inline compliance)
        app_js_path = Path(__file__).resolve().parent.parent / "amlkit/web/static/js/app.js"
        app_js_content = app_js_path.read_text()
        assert 'is-submitting' in app_js_content
        assert 'spinner' in app_js_content

    def test_login_has_data_loading(self, anon_client) -> None:
        r = anon_client.get("/login")
        assert 'data-loading="Signing in' in r.text


class TestHTML5Validation:
    def test_login_email_required(self, anon_client) -> None:
        r = anon_client.get("/login")
        assert 'type="email"' in r.text
        assert re.search(r'name="email"[^>]*required', r.text)

    def test_login_password_required(self, anon_client) -> None:
        r = anon_client.get("/login")
        assert re.search(r'name="password"[^>]*required', r.text)

    def test_register_email_type(self, anon_client) -> None:
        r = anon_client.get("/register-organization")
        assert re.search(r'type="email"[^>]*name="email"', r.text)

    def test_register_password_minlength(self, anon_client) -> None:
        r = anon_client.get("/register-organization")
        assert re.search(r'name="password"[^>]*minlength="10"', r.text)

    def test_screen_name_required(self, client) -> None:
        r = client.get("/screen")
        assert re.search(r'name="name"[^>]*required', r.text)

    def test_screen_country_pattern(self, client) -> None:
        r = client.get("/screen")
        assert re.search(r'name="country"[^>]*pattern=', r.text)

    def test_onboard_nationality_pattern(self, client) -> None:
        r = client.get("/customers/new")
        assert re.search(r'name="nationality"[^>]*pattern=', r.text)
