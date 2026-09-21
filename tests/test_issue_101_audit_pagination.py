"""Issue #101: Audit log pagination - currently loads all records at once.

Add pagination to /audit endpoint to handle large audit trails efficiently.
Default: 50 records per page.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

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
    from conftest import settle_mfa  # p15: MLRO sessions start locked
    settle_mfa(client)
    assert any(s in r2.text for s in ("Dashboard", "24-hour", "Two-Factor"))
    return client


def _seed_audit_entries(db_file, org_id: int, count: int):
    """Insert N audit entries for testing pagination."""
    import json
    from amlkit.db import connect, utcnow
    conn = connect(db_file)
    now = utcnow()
    for i in range(count):
        conn.execute(
            """INSERT INTO audit_log (ts, actor, action, object_type, object_id, detail, org_id)
               VALUES (?,?,?,?,?,?,?)""",
            (now, "test-operator", f"test.action.{i}", "test", i, json.dumps({"entry": i}), org_id)
        )
    conn.commit()
    conn.close()


@pytest.fixture
def client_with_many_audit_entries(tmp_path, monkeypatch):
    """Client with 100+ audit entries to test pagination."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))

    from amlkit.db import connect
    conn = connect(db_file)
    conn.close()

    client = TestClient(app)
    _register(client, "Test Firm", "Admin", "admin@test.com")

    # Get org ID and create 120 audit entries
    conn = connect(db_file)
    org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()[0]
    conn.close()

    _seed_audit_entries(db_file, org_id, 120)

    return client


def test_audit_pagination_default_shows_50_entries(client_with_many_audit_entries):
    """Default /audit page should show 50 most recent entries."""
    client = client_with_many_audit_entries

    resp = client.get("/audit")
    assert resp.status_code == 200
    html = resp.text

    # Count audit rows (each has class="list-row")
    import re
    rows = re.findall(r'class="list-row"', html)
    assert len(rows) == 50, f"Expected 50 rows on page 1, got {len(rows)}"

    # Should show "Next" link
    assert "Next" in html or "next" in html or "page=2" in html


def test_audit_pagination_page_2_shows_next_50(client_with_many_audit_entries):
    """Page 2 should show entries 51-100."""
    client = client_with_many_audit_entries

    resp = client.get("/audit?page=2")
    assert resp.status_code == 200
    html = resp.text

    import re
    rows = re.findall(r'class="list-row"', html)
    assert len(rows) == 50, f"Expected 50 rows on page 2, got {len(rows)}"

    # Should show "Previous" link
    assert "Previous" in html or "previous" in html or "page=1" in html


def test_audit_pagination_last_page_shows_remaining(client_with_many_audit_entries):
    """Last page should show only remaining entries."""
    client = client_with_many_audit_entries

    # 120 test entries + 5 from registration (org created, email verified,
    # first login, MFA enrolled, ...) = 125 total -> 3 pages (50, 50, 25)
    resp = client.get("/audit?page=3")
    assert resp.status_code == 200
    html = resp.text

    import re
    rows = re.findall(r'class="list-row"', html)
    assert len(rows) == 25, f"Expected 25 rows on page 3 (last page), got {len(rows)}"

    # Should NOT show "Next" link (last page)
    # But should show "Previous"
    assert "Previous" in html or "previous" in html or "page=2" in html
