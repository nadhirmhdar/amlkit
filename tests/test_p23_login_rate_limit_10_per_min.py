"""Rate limiting test for p23 - login endpoint 10/min per IP.

Tests that the login endpoint rate limit is set to 10 attempts per minute per IP.
This is the IP-based ceiling to prevent brute force attacks from a single IP.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from amlkit.api.app import app  # noqa: E402


class TestP23LoginRateLimit:
    """Test login endpoint has 10/min per-IP rate limit."""

    def test_login_rate_limit_10_per_minute_per_ip(self) -> None:
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
