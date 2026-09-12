"""Rate limiting tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from amlkit.api.app import app  # noqa: E402


class TestRateLimiting:
    def test_login_rate_limit_blocks_after_3_attempts(self) -> None:
        """POST /login should be rate-limited to 3 requests per minute."""
        fresh_client = TestClient(app)

        # Get CSRF token
        fresh_client.get("/login")
        csrf = fresh_client.cookies.get("amlkit_csrf")

        # Make 3 login attempts (should succeed or fail normally)
        for i in range(3):
            r = fresh_client.post("/login", data={
                "email": f"user{i}@example.com",
                "password": "wrong",
                "csrf_token": csrf,
            })
            assert r.status_code in [200, 303], f"Attempt {i+1} should not be rate-limited"

        # 4th attempt should be rate-limited
        r = fresh_client.post("/login", data={
            "email": "user4@example.com",
            "password": "wrong",
            "csrf_token": csrf,
        })
        assert r.status_code == 429, "4th login attempt should be rate-limited"

    def test_rate_limiter_configured(self) -> None:
        """Verify rate limiter is properly configured on the FastAPI app."""
        assert hasattr(app.state, 'limiter'), "Limiter should be attached to app.state"
        assert app.state.limiter is not None, "Limiter should be initialized"
