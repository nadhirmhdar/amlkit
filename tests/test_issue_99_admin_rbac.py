"""Tests for Issue #99: Admin endpoints should return 403 for non-MLRO roles.

QA Finding R-001: Officer-role users who POST to admin action endpoints receive
HTTP 200 responses instead of HTTP 403, even though the actions are blocked.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _csrf(client):
    """Extract CSRF token from any page."""
    r = client.get("/")
    if 'name="csrf_token" value="' not in r.text:
        return "test-csrf-token"
    start = r.text.index('name="csrf_token" value="') + len('name="csrf_token" value="')
    end = r.text.index('"', start)
    return r.text[start:end]


def _db() -> sqlite3.Connection:
    """Get connection to test database."""
    conn = sqlite3.Connection(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


class TestAdminRBAC Enforcement:
    """Admin POST endpoints must return HTTP 403 for non-MLRO roles."""

    def test_officer_reset_password_returns_403(self, client) -> None:
        """Officer POST to /admin/operators/{id}/reset-password should return 403."""
        # Create officer account
        conn = _db()
        conn.execute(
            "INSERT INTO operators (email, password_hash, role, org_id, status, created_at) "
            "VALUES ('officer@test.com', ?, 'officer', 1, 'active', datetime('now'))",
            ("dummy-hash",),
        )
        conn.commit()
        conn.close()

        # Login as officer (use existing client to get csrf, then make new request)
        r = client.post(
            "/admin/operators/1/reset-password",
            data={"new_password": "HackerPass1!", "csrf_token": _csrf(client)},
        )
        assert r.status_code == 403, f"Expected 403 Forbidden, got {r.status_code}"

    def test_officer_create_operator_returns_403(self, client) -> None:
        """Officer POST to /admin/operators should return 403."""
        r = client.post(
            "/admin/operators",
            data={
                "email": "hacker@test.com",
                "password": "Password1!",
                "role": "mlro",
                "csrf_token": _csrf(client),
            },
        )
        assert r.status_code == 403, f"Expected 403 Forbidden, got {r.status_code}"
