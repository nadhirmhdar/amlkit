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
              password="a-strong-password-1", invite_code="test-invite"):
    return client.post("/api/v1/auth/register-organization", json={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "invite_code": invite_code,
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


class TestConfiguredMailFailureDoesNotLeakTheToken:
    """Regression: a configured-but-failing mail provider was an auth bypass.

    `mail.send_verification_email` used to return a bool, and False meant both
    "no SMTP configured" (a supported dev state, where handing the link back
    is the point) and "SMTP configured but the send failed" (a production
    outage). Both registration routes branched on `if not emailed`, so in the
    second case they returned the raw verification token to whoever posted the
    form.

    That token activates a fully-privileged MLRO account, and proving control
    of the mailbox is the entire purpose of the check -- so anyone could
    register under an address they did not own and immediately activate it.

    Live, not theoretical: SendGrid withdrew its free tier in May 2025, so a
    deployment whose trial lapsed sits in exactly this state, still accepting
    registrations with every send failing.
    """

    @pytest.fixture()
    def failing_smtp(self, monkeypatch):
        """Mail IS configured; every send raises."""
        import smtplib

        monkeypatch.setenv("AMLKIT_SMTP_HOST", "smtp.example.invalid")
        monkeypatch.setenv("AMLKIT_SMTP_PORT", "587")

        def boom(*a, **k):
            raise smtplib.SMTPException("provider rejected the connection")

        monkeypatch.setattr(smtplib, "SMTP", boom)

    def test_mail_module_distinguishes_failure_from_unconfigured(
        self, failing_smtp
    ) -> None:
        from amlkit import mail

        assert mail.is_configured()
        assert mail.send_verification_email("a@b.test", "A", "tok") == mail.FAILED

    def test_unconfigured_still_reports_not_configured(self, monkeypatch) -> None:
        from amlkit import mail

        monkeypatch.delenv("AMLKIT_SMTP_HOST", raising=False)
        assert mail.send_verification_email("a@b.test", "A", "tok") == mail.NOT_CONFIGURED

    def test_api_does_not_return_the_token_when_the_send_fails(
        self, client, failing_smtp
    ) -> None:
        body = _register(client).json()
        assert "dev_verification_token" not in body, (
            "a live verification token was handed to the caller while mail was "
            "configured -- this is the auth bypass"
        )
        assert body["status"] == "verification_send_failed"

    def test_account_stays_inert_after_a_failed_send(self, client, failing_smtp) -> None:
        # The belt-and-braces check: even with no token leaked, the account
        # must remain unusable rather than quietly activating.
        _register(client)
        r = client.post("/api/v1/auth/login", json={
            "email": "alice@testfirm.ae", "password": "a-strong-password-1",
        })
        assert r.status_code == 401

    def test_web_registration_does_not_render_the_link_when_the_send_fails(
        self, client, failing_smtp
    ) -> None:
        client.get("/register-organization")
        csrf = client.cookies.get("amlkit_csrf")
        r = client.post("/register-organization", data={
            "org_name": "Web Firm", "name": "bob", "email": "bob@webfirm.ae",
            "password": "a-strong-password-1", "csrf_token": csrf,
            "invite_code": "test-invite",
        }, follow_redirects=True)
        assert r.status_code == 200
        assert "/verify-email?token=" not in r.text
        assert "could not be sent" in r.text

    def test_failed_delivery_is_recorded_in_the_audit_log(
        self, client, failing_smtp
    ) -> None:
        # The visibility half of the fix: a provider failing every send is
        # otherwise indistinguishable from nobody signing up.
        import os
        import sqlite3

        _register(client)
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT detail FROM audit_log WHERE action='operator.verification_sent'"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row is not None
        assert '"delivery": "failed"' in row["detail"]

    def test_successful_delivery_is_recorded_too(self, client, monkeypatch) -> None:
        import smtplib

        monkeypatch.setenv("AMLKIT_SMTP_HOST", "smtp.example.invalid")

        class FakeSMTP:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def starttls(self): pass
            def login(self, *a): pass
            def send_message(self, msg): pass

        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

        body = _register(client).json()
        assert body["status"] == "verification_required"
        assert "dev_verification_token" not in body

        import os
        import sqlite3
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT detail FROM audit_log WHERE action='operator.verification_sent'"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert '"delivery": "sent"' in row["detail"]
