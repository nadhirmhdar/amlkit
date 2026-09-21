"""Rate limiting tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from amlkit.api.app import app  # noqa: E402


import pytest


@pytest.fixture()
def _enable_limiter():
    """Enable rate limiter for tests that verify 429 behaviour."""
    app.state.limiter._storage.reset()
    app.state.limiter.enabled = True
    yield
    app.state.limiter.enabled = False


class TestRateLimiting:
    def test_login_rate_limit_blocks_same_account_after_3_attempts(self, _enable_limiter) -> None:
        """POST /login should be rate-limited to 3 attempts per account (IP:email)."""
        fresh_client = TestClient(app)

        # Get CSRF token
        fresh_client.get("/login")
        csrf = fresh_client.cookies.get("amlkit_csrf")

        # Make 3 login attempts with SAME email (should succeed or fail normally)
        for i in range(3):
            r = fresh_client.post("/login", data={
                "email": "sameuser@example.com",
                "password": "wrong",
                "csrf_token": csrf,
            })
            assert r.status_code in [200, 303], f"Attempt {i+1} should not be rate-limited"

        # 4th attempt with SAME email should be rate-limited (per-account limit)
        r = fresh_client.post("/login", data={
            "email": "sameuser@example.com",
            "password": "wrong",
            "csrf_token": csrf,
        })
        assert r.status_code == 429, "4th login attempt for same account should be rate-limited"

    def test_rate_limiter_configured(self) -> None:
        """Verify rate limiter is properly configured on the FastAPI app."""
        assert hasattr(app.state, 'limiter'), "Limiter should be attached to app.state"
        assert app.state.limiter is not None, "Limiter should be initialized"
