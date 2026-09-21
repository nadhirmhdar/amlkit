"""Rate limiting tests for POST /api/v1/auth/login (finding #11, 2026-09-21
deployed-site review).

Mobile login had no rate limit at all while web /login has a 10/min IP
ceiling plus a 3/min per-account limit. Combined with the 8-failure/15-minute
account lockout, an unthrottled mobile login enables mass account-lockout
denial of service: an attacker can lock out every operator in an org by
POSTing wrong passwords for each of their emails as fast as the network
allows. These tests mirror test_p23_login_rate_limit_10_per_min.py and
test_login_rate_limit_keying.py, which cover the same two limits on the web
route.
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
    sets limiter.enabled = False.  Tests that verify rate limiting opt in
    here. Storage is reset so prior enabled-limiter tests don't pollute
    counters.
    """
    app.state.limiter._storage.reset()
    app.state.limiter.enabled = True
    yield
    app.state.limiter.enabled = False


class TestMobileLoginIpCeiling:
    def test_mobile_login_rate_limit_10_per_minute_per_ip(self, _enable_limiter) -> None:
        """POST /api/v1/auth/login should be limited to 10 requests/minute per IP."""
        client = TestClient(app)

        for i in range(10):
            r = client.post("/api/v1/auth/login", json={
                "email": f"user{i}@example.com", "password": "wrong",
            })
            assert r.status_code != 429, f"Request {i+1}/10 should not be rate-limited"

        r = client.post("/api/v1/auth/login", json={
            "email": "user11@example.com", "password": "wrong",
        })
        assert r.status_code == 429, "11th mobile login attempt should be rate-limited (10/min per IP)"


class TestMobileLoginPerAccountKeying:
    def test_different_emails_have_separate_rate_limits(self, _enable_limiter) -> None:
        """Multiple accounts from the same IP each get their own 3/minute budget."""
        client = TestClient(app)

        for i in range(3):
            r = client.post("/api/v1/auth/login", json={
                "email": "alice@mobiletest.com", "password": "wrong",
            })
            assert r.status_code != 429, f"Alice attempt {i+1} should not be rate-limited"

        r = client.post("/api/v1/auth/login", json={
            "email": "alice@mobiletest.com", "password": "wrong",
        })
        assert r.status_code == 429, "Alice's 4th attempt should be rate-limited"

        r = client.post("/api/v1/auth/login", json={
            "email": "bob@mobiletest.com", "password": "wrong",
        })
        assert r.status_code != 429, "Bob's first attempt should not be rate-limited (different email)"

    def test_same_email_shares_rate_limit_across_clients(self, _enable_limiter) -> None:
        """The same email from the same IP shares its rate limit budget
        across separate mobile client sessions (finding #11's exact scenario:
        an attacker doesn't need to reuse a client to exhaust an account)."""
        client1 = TestClient(app)
        client2 = TestClient(app)

        for _ in range(2):
            r = client1.post("/api/v1/auth/login", json={
                "email": "carol@mobiletest.com", "password": "wrong",
            })
            assert r.status_code != 429

        r = client2.post("/api/v1/auth/login", json={
            "email": "carol@mobiletest.com", "password": "wrong",
        })
        assert r.status_code != 429, "Carol's 3rd attempt should work"

        r = client2.post("/api/v1/auth/login", json={
            "email": "carol@mobiletest.com", "password": "wrong",
        })
        assert r.status_code == 429, "Carol's 4th attempt should be rate-limited across both clients"
