"""Test H1: Rate limiter respects X-Forwarded-For when AMLKIT_BEHIND_PROXY=1.

Without the fix, all requests share the same rate limit bucket regardless of
client IP, causing one tenant to lock out all others on Cloud Run.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient with rate limiting enabled and AMLKIT_BEHIND_PROXY=1."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.setenv("AMLKIT_BEHIND_PROXY", "1")
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    from amlkit.db import connect
    connect(db_file).close()

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    app.state.limiter._storage.reset()
    app.state.limiter.enabled = True
    yield TestClient(app)
    app.state.limiter.enabled = False


def test_different_xff_ips_get_separate_rate_limit_buckets(client):
    """Two distinct X-Forwarded-For IPs should not share a rate limit bucket.

    Without the fix: all requests share one bucket, so 5 requests from IP1
    exhaust the 5/min limit, and the 6th from IP2 returns 429.

    With the fix: IP1 and IP2 each get 5/min, so 5 from IP1 + 1 from IP2 = no 429.
    """
    # Get CSRF token
    client.get("/register-organization")
    csrf = client.cookies.get("amlkit_csrf")

    # 5 requests from IP 10.0.0.1 (should exhaust this IP's bucket)
    for i in range(5):
        resp = client.post(
            "/register-organization",
            data={
                "org_name": f"Org {i}",
                "name": f"User {i}",
                "email": f"user{i}@example.ae",
                "password": f"Pass{i}123!",
                "csrf_token": csrf,
                "invite_code": "test-invite",
            },
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        assert resp.status_code != 429, f"Request {i+1} from IP1 should not be rate limited yet"

    # 1 request from a different IP (10.0.0.2) should succeed
    # because it has its own rate limit bucket
    resp = client.post(
        "/register-organization",
        data={
            "org_name": "Org from IP2",
            "name": "User from IP2",
            "email": "user_ip2@example.ae",
            "password": "PassIP2123!",
            "csrf_token": csrf,
            "invite_code": "test-invite",
        },
        headers={"X-Forwarded-For": "10.0.0.2"},
    )
    assert resp.status_code != 429, (
        "Request from IP2 should not be rate limited - "
        "different IPs should have separate rate limit buckets"
    )
