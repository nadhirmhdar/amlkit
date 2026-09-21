"""Test t11: Rate limiting on /verify-email."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    from amlkit.db import connect
    connect(db_file).close()

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    app.state.limiter._storage.reset()
    app.state.limiter.enabled = True
    yield TestClient(app)
    app.state.limiter.enabled = False


def test_verify_email_rapid_enumeration_blocked(client):
    """Rapid enumeration attempt (11 requests with different tokens) → 429."""

    # Generate fake tokens (they won't exist in DB but that's fine for rate limit test)
    import secrets

    # First 10 requests should not be rate limited
    for i in range(10):
        token = secrets.token_urlsafe(32)
        resp = client.get(f"/verify-email?token={token}")
        # Should return 200, 303, or 400 (invalid token), but NOT 429
        assert resp.status_code != 429, f"Request {i+1} was rate limited (should not be)"

    # 11th request should be rate limited
    token = secrets.token_urlsafe(32)
    resp = client.get(f"/verify-email?token={token}")
    assert resp.status_code == 429, "11th request should be rate limited"
