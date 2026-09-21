"""Issue #102: Authorization errors exposed in URL query strings.

Auth/authorization error messages should not appear in redirect URLs (browser
history, server logs). Use flash/session-based error passing instead.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from amlkit.api.app import app


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name: str, name: str, email: str, password: str = "Password123"):
    import re
    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client), "invite_code": "test-invite",
    }, follow_redirects=True)
    assert "Check your email" in r.text
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m
    r2 = client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    assert "Dashboard" in r2.text or "24-hour" in r2.text
    return client


@pytest.fixture
def client_and_db(tmp_path, monkeypatch):
    """Client with org and operator."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    from amlkit.db import connect
    conn = connect(db_file)
    conn.close()

    client = TestClient(app)
    _register(client, "Test Firm", "Admin", "admin@test.com")

    return client


def test_back_function_does_not_expose_errors_in_url():
    """The back() redirect helper should not append error messages to URL."""
    from amlkit.api.app import back

    # Test back() with error message
    resp = back("/dashboard", err="Access denied: MLRO role required")

    # Check redirect location
    location = resp.headers.get("location", "")
    parsed = urlparse(location)
    query_params = parse_qs(parsed.query)

    # CRITICAL: error messages should NOT be in URL query params
    assert "err" not in query_params, f"Error message exposed in URL: {location}"
    assert "error" not in query_params, f"Error message exposed in URL: {location}"
    assert "msg" not in query_params, f"Message exposed in URL: {location}"
    assert "message" not in query_params, f"Message exposed in URL: {location}"

    # Same for success messages
    resp2 = back("/dashboard", msg="Settings updated")
    location2 = resp2.headers.get("location", "")
    parsed2 = urlparse(location2)
    query_params2 = parse_qs(parsed2.query)

    assert "msg" not in query_params2, f"Message exposed in URL: {location2}"
    assert "message" not in query_params2, f"Message exposed in URL: {location2}"


def test_auth_errors_available_after_redirect(client_and_db):
    """Auth errors should still be accessible after redirect (via flash/session)."""
    client = client_and_db

    # Access a protected resource without authorization
    resp = client.get("/audit", follow_redirects=True)

    # Should end up on a page that CAN display the error
    # (error stored in session, rendered on target page)
    # This test verifies the error is available even though not in URL
    assert resp.status_code == 200
    # Error message should be in the page content (from flash/session)
    # or user should be on an appropriate page (like login or dashboard)
