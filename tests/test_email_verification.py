"""Registration email verification.

Before this, `/auth/register-organization` created a fully usable, MLRO-role
account and logged the caller straight in -- no check that the email address
was real, reachable, or even shaped like an email server-side (the mobile
app only checked the shape client-side). This exercises the fix: the
account exists but is inert until the link mailed to it (or, with no SMTP
configured as in these tests, handed back directly -- see amlkit/mail.py)
is redeemed.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_api import _seed_sanctions_data  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    return TestClient(app)


def _register(client, email="alice@testfirm.ae", org_name="Test Firm", name="alice",
              password="a-strong-password-1"):
    return client.post("/api/v1/auth/register-organization", json={
        "org_name": org_name, "name": name, "email": email, "password": password,
    })


class TestRegistrationDoesNotGrantAccess:
    def test_registration_returns_no_token(self, client) -> None:
        r = _register(client)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "verification_required"
        assert "token" not in body

    def test_unverified_account_cannot_log_in(self, client) -> None:
        _register(client)
        r = client.post("/api/v1/auth/login", json={
            "email": "alice@testfirm.ae", "password": "a-strong-password-1",
        })
        assert r.status_code == 401
        assert "verify your email" in r.json()["detail"].lower()

    def test_dev_verification_token_present_with_no_smtp_configured(self, client) -> None:
        """No AMLKIT_SMTP_HOST is set in these tests, so mail.py falls back
        to console-logging the link -- and the API hands the same token back
        directly (see api_register_organization), which is what makes every
        other test in this file able to complete the flow without a real
        mailbox."""
        r = _register(client)
        assert r.json()["dev_verification_token"]


class TestVerifyEmail:
    def test_valid_token_activates_and_returns_usable_session(self, client) -> None:
        token = _register(client).json()["dev_verification_token"]
        r = client.post("/api/v1/auth/verify-email", json={"token": token})
        assert r.status_code == 200, r.text
        bearer = r.json()["token"]
        assert client.get("/api/v1/dashboard", headers={"Authorization": f"Bearer {bearer}"}).status_code == 200

    def test_verified_account_can_then_log_in_normally(self, client) -> None:
        token = _register(client).json()["dev_verification_token"]
        client.post("/api/v1/auth/verify-email", json={"token": token})
        r = client.post("/api/v1/auth/login", json={
            "email": "alice@testfirm.ae", "password": "a-strong-password-1",
        })
        assert r.status_code == 200
        assert r.json()["token"]

    def test_token_is_single_use(self, client) -> None:
        token = _register(client).json()["dev_verification_token"]
        first = client.post("/api/v1/auth/verify-email", json={"token": token})
        assert first.status_code == 200
        second = client.post("/api/v1/auth/verify-email", json={"token": token})
        assert second.status_code == 400
        assert "invalid, expired, or already used" in second.json()["detail"]

    def test_garbage_token_is_rejected(self, client) -> None:
        r = client.post("/api/v1/auth/verify-email", json={"token": "not-a-real-token"})
        assert r.status_code == 400

    def test_expired_token_is_rejected(self, client) -> None:
        """Same fail-closed treatment as setup_tokens (see
        test_setup_tokens.py) -- exercised directly against the DB rather
        than waiting three real days for EMAIL_VERIFY_TOKEN_LIFETIME."""
        import os

        token = _register(client).json()["dev_verification_token"]

        from amlkit.db import connect
        conn = connect(os.environ["AMLKIT_DB"])
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds")
        conn.execute(
            "UPDATE email_verify_tokens SET expires_at=? WHERE token_hash=?",
            (past, sha256(token.encode()).hexdigest()),
        )
        conn.commit()
        conn.close()

        r = client.post("/api/v1/auth/verify-email", json={"token": token})
        assert r.status_code == 400


class TestResendVerification:
    def test_resend_issues_a_new_token_and_invalidates_the_old_one(self, client) -> None:
        old_token = _register(client).json()["dev_verification_token"]

        # Force the cooldown out of the way rather than sleeping in a test.
        import os
        from amlkit.db import connect
        conn = connect(os.environ["AMLKIT_DB"])
        stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(timespec="seconds")
        conn.execute("UPDATE email_verify_tokens SET created_at=?", (stale,))
        conn.commit()
        conn.close()

        r = client.post("/api/v1/auth/resend-verification", json={"email": "alice@testfirm.ae"})
        assert r.status_code == 200
        assert "verification link has been sent" in r.json()["message"]

        assert client.post("/api/v1/auth/verify-email", json={"token": old_token}).status_code == 400

    def test_resend_within_cooldown_is_a_silent_no_op(self, client) -> None:
        token = _register(client).json()["dev_verification_token"]
        client.post("/api/v1/auth/resend-verification", json={"email": "alice@testfirm.ae"})
        # Original link (issued seconds ago) must still work -- the cooldown
        # means the resend didn't actually rotate the token.
        assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200

    def test_resend_for_unknown_email_gives_the_same_generic_message(self, client) -> None:
        """No enumeration: whether or not the address belongs to a real
        (or already-verified) account, the response is identical -- same
        reasoning as auth.login()'s single error string."""
        r1 = client.post("/api/v1/auth/resend-verification", json={"email": "nobody@nowhere.test"})
        assert r1.status_code == 200

        token = _register(client).json()["dev_verification_token"]
        client.post("/api/v1/auth/verify-email", json={"token": token})
        r2 = client.post("/api/v1/auth/resend-verification", json={"email": "alice@testfirm.ae"})
        assert r2.status_code == 200
        assert r1.json() == r2.json()


class TestEmailFormatValidation:
    def test_garbage_email_is_rejected_server_side(self, client) -> None:
        """The mobile app already checks this client-side, but the API must
        not trust that -- anything can call it directly."""
        r = _register(client, email="not-an-email-at-all")
        assert r.status_code == 400
        assert "valid email" in r.json()["detail"].lower()
