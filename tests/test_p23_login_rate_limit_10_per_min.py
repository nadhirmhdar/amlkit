"""Rate limiting test for p23 - login endpoint 10/min per IP.

Tests that the login endpoint rate limit is set to 10 attempts per minute per IP.
This is the IP-based ceiling to prevent brute force attacks from a single IP.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from amlkit.api.app import app  # noqa: E402


@pytest.fixture()
def _enable_limiter():
    """Re-enable slowapi for tests that verify 429 behaviour.

    The session-scoped _disable_rate_limiter autouse fixture in conftest.py
    sets limiter.enabled = False.  Tests that verify rate limiting opt in here.
    Storage is reset so prior enabled-limiter tests don't pollute counters.
    """
    app.state.limiter._storage.reset()
    app.state.limiter.enabled = True
    yield
    app.state.limiter.enabled = False


class TestP23LoginRateLimit:
    """Test login endpoint has 10/min per-IP rate limit."""

    def test_login_rate_limit_10_per_minute_per_ip(self, _enable_limiter) -> None:
        """POST /login should be limited to 10 requests/minute per IP."""
        fresh_client = TestClient(app)

        # Get CSRF token
        fresh_client.get("/login")
        csrf = fresh_client.cookies.get("amlkit_csrf")

        # Make 10 login attempts (should be allowed - within 10/min limit)
        for i in range(10):
            r = fresh_client.post("/login", data={
                "email": f"user{i}@example.com",
                "password": "wrong",
                "csrf_token": csrf,
            })
            # Should not be rate-limited yet
            # Expect 200 (login page) or 303 (redirect), but NOT 429
            assert r.status_code != 429, f"Request {i+1}/10 should not be rate-limited"

        # 11th attempt should be rate-limited (exceeds 10/min per IP)
        r = fresh_client.post("/login", data={
            "email": "user11@example.com",
            "password": "wrong",
            "csrf_token": csrf,
        })
        assert r.status_code == 429, "11th login attempt should be rate-limited (10/min per IP)"
