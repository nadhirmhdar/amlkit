"""Issue #162: CSRF protection and rate limiting on POST /api/ai/draft-narrative.

The AI narrative endpoint accepts Form data but was missing both the
CSRF synchronizer-token check and a rate-limit decorator, making it
vulnerable to cross-site POST forgery and abuse.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_api import _seed_sanctions_data  # noqa: E402


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


@pytest.fixture()
def web(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)

    c.get("/register-organization")
    import re
    r = c.post("/register-organization", data={
        "org_name": "Test Firm", "name": "alice",
        "email": "alice@testfirm.ae", "password": "a-strong-password-1",
        "csrf_token": _csrf(c),
    }, follow_redirects=True)
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m, f"No verification token found in response: {r.text[:200]}"
    c.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)

    c.get("/login")
    c.post("/login", data={
        "email": "alice@testfirm.ae", "password": "a-strong-password-1",
        "csrf_token": _csrf(c),
    }, follow_redirects=True)

    import sqlite3
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    org = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()
    org_id = org["id"]
    from amlkit.db import utcnow
    now = utcnow()
    conn.execute(
        "INSERT INTO customers (org_id, reference, customer_type, full_name,"
        " canonical_key, status, onboarded_at, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (org_id, "CUST-AI", "natural", "AI Test Person", "ai test person",
         "active", now, now, now),
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()

    return c, customer_id


@pytest.fixture()
def _enable_limiter():
    """Temporarily re-enable the rate limiter for tests that verify 429 behaviour.

    The session-scoped _disable_rate_limiter fixture in conftest.py sets
    limiter.enabled = False to prevent test-suite registrations from hitting
    the 10/min ceiling.  test_rate_limited depends on the limiter being on,
    so it opts in by declaring this fixture.
    """
    from amlkit.api.app import app
    app.state.limiter.enabled = True
    yield
    app.state.limiter.enabled = False


class TestAiNarrativeCsrf:
    def test_missing_csrf_token_rejected(self, web) -> None:
        """POST without csrf_token must fail (PermissionError → 401 or redirect)."""
        client, customer_id = web
        r = client.post("/api/ai/draft-narrative", data={
            "customer_id": str(customer_id),
        })
        assert r.status_code != 200, (
            f"Expected rejection without CSRF token, got {r.status_code}"
        )

    def test_with_csrf_token_accepted(self, web) -> None:
        """POST with valid csrf_token proceeds (may 503 if no Gemini key)."""
        client, customer_id = web
        r = client.post("/api/ai/draft-narrative", data={
            "customer_id": str(customer_id),
            "csrf_token": _csrf(client),
        })
        assert r.status_code in (200, 503), (
            f"Expected 200 or 503 with valid CSRF, got {r.status_code}"
        )

    def test_rate_limited(self, web, _enable_limiter) -> None:
        """Rapid requests must eventually receive 429."""
        client, customer_id = web
        statuses = []
        for _ in range(12):
            r = client.post("/api/ai/draft-narrative", data={
                "customer_id": str(customer_id),
                "csrf_token": _csrf(client),
            })
            statuses.append(r.status_code)
        assert 429 in statuses, (
            f"Expected at least one 429 in {len(statuses)} requests, got {set(statuses)}"
        )
