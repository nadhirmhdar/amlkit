"""Invite-only organization registration tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from amlkit.api.app import app

INVITE_CODE = "test-invite"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "test.db"))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    return TestClient(app)


def _csrf(client):
    client.get("/register-organization")
    return client.cookies.get("amlkit_csrf")


class TestRegistrationDisabledWhenNotConfigured:
    def test_get_shows_closed_message(self, client, monkeypatch):
        monkeypatch.delenv("AMLKIT_REGISTRATION_INVITE_CODE", raising=False)
        r = client.get("/register-organization")
        assert r.status_code == 200
        assert "not available" in r.text.lower()
        assert "<form" not in r.text.lower() or 'name="invite_code"' not in r.text

    def test_post_returns_403(self, client, monkeypatch):
        csrf = _csrf(client)
        monkeypatch.delenv("AMLKIT_REGISTRATION_INVITE_CODE", raising=False)
        r = client.post("/register-organization", data={
            "org_name": "Evil Corp", "name": "mallory", "email": "mallory@evil.ae",
            "password": "strong-enough-1", "csrf_token": csrf,
        })
        assert r.status_code in (200, 403)
        assert "invalid invite code" in r.text.lower()

    def test_api_returns_403(self, client, monkeypatch):
        monkeypatch.delenv("AMLKIT_REGISTRATION_INVITE_CODE", raising=False)
        r = client.post("/api/v1/auth/register-organization", json={
            "org_name": "Evil Corp", "name": "mallory", "email": "mallory@evil.ae",
            "password": "strong-enough-1",
        })
        assert r.status_code == 403
        assert "invite code" in r.json()["detail"].lower()


class TestWrongInviteCode:
    def test_web_refused_with_wrong_code(self, client):
        csrf = _csrf(client)
        r = client.post("/register-organization", data={
            "org_name": "Evil Corp", "name": "mallory", "email": "mallory@evil.ae",
            "password": "strong-enough-1", "csrf_token": csrf,
            "invite_code": "wrong-code",
        })
        assert "invalid invite code" in r.text.lower()

    def test_web_refused_with_missing_code(self, client):
        csrf = _csrf(client)
        r = client.post("/register-organization", data={
            "org_name": "Evil Corp", "name": "mallory", "email": "mallory@evil.ae",
            "password": "strong-enough-1", "csrf_token": csrf,
        })
        assert "invalid invite code" in r.text.lower()

    def test_api_refused_with_wrong_code(self, client):
        r = client.post("/api/v1/auth/register-organization", json={
            "org_name": "Evil Corp", "name": "mallory", "email": "mallory@evil.ae",
            "password": "strong-enough-1", "invite_code": "wrong-code",
        })
        assert r.status_code == 403

    def test_api_refused_without_code(self, client):
        r = client.post("/api/v1/auth/register-organization", json={
            "org_name": "Evil Corp", "name": "mallory", "email": "mallory@evil.ae",
            "password": "strong-enough-1",
        })
        assert r.status_code == 403


class TestValidInviteCode:
    def test_web_registration_succeeds(self, client):
        csrf = _csrf(client)
        r = client.post("/register-organization", data={
            "org_name": "Good Firm", "name": "alice", "email": "alice@good.ae",
            "password": "strong-enough-1", "csrf_token": csrf,
            "invite_code": INVITE_CODE,
        }, follow_redirects=True)
        assert "check your email" in r.text.lower() or "Check" in r.text

    def test_api_registration_succeeds(self, client):
        r = client.post("/api/v1/auth/register-organization", json={
            "org_name": "Good Firm", "name": "alice", "email": "alice@good.ae",
            "password": "strong-enough-1", "invite_code": INVITE_CODE,
        })
        assert r.status_code == 200
        assert r.json()["status"] == "verification_required"

    def test_invite_code_with_whitespace_accepted(self, client):
        r = client.post("/api/v1/auth/register-organization", json={
            "org_name": "Good Firm", "name": "alice", "email": "alice@good.ae",
            "password": "strong-enough-1", "invite_code": f"  {INVITE_CODE}  ",
        })
        assert r.status_code == 200


class TestFormRendering:
    def test_form_shows_invite_code_field(self, client):
        r = client.get("/register-organization")
        assert 'name="invite_code"' in r.text


class TestAuthEventLogging:
    def test_denied_attempt_logged_to_auth_log(self, client, tmp_path, monkeypatch):
        from amlkit.db import connect
        csrf = _csrf(client)
        client.post("/register-organization", data={
            "org_name": "Evil Corp", "name": "mallory", "email": "mallory@evil.ae",
            "password": "strong-enough-1", "csrf_token": csrf,
            "invite_code": "wrong-code",
        })
        conn = connect(str(tmp_path / "test.db"))
        try:
            row = conn.execute(
                "SELECT * FROM auth_log WHERE event='register_denied' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert row is not None
        finally:
            conn.close()

    def test_denied_attempt_not_visible_on_org_audit_page(self, client, tmp_path, monkeypatch):
        """Privacy: denied registration attempts must NOT appear in any org's
        /audit view, because audit_trail() shows org_id IS NULL rows to
        every tenant."""
        import re
        from amlkit.db import connect

        csrf = _csrf(client)
        client.post("/register-organization", data={
            "org_name": "Good Firm", "name": "alice", "email": "alice@good.ae",
            "password": "strong-enough-1", "csrf_token": csrf,
            "invite_code": INVITE_CODE,
        }, follow_redirects=True)
        m = re.search(r"/verify-email\?token=([^\"&<\s]+)", client.get("/register-organization").text)
        if not m:
            r2 = client.post("/register-organization", data={
                "org_name": "Good Firm", "name": "alice", "email": "alice@good.ae",
                "password": "strong-enough-1", "csrf_token": _csrf(client),
                "invite_code": INVITE_CODE,
            }, follow_redirects=True)
            m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r2.text)

        client.post("/register-organization", data={
            "org_name": "Attacker Inc", "name": "attacker", "email": "attacker@evil.ae",
            "password": "strong-enough-1", "csrf_token": _csrf(client),
            "invite_code": "bad-code",
        })

        conn = connect(str(tmp_path / "test.db"))
        try:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE org_id IS NULL AND action='org.register_denied'"
            ).fetchall()
            assert len(rows) == 0, "Denied registration must not be in audit_log"
        finally:
            conn.close()


class TestNonRegression:
    def test_login_unaffected_by_invite_setting(self, client, monkeypatch):
        """Existing login works regardless of invite code configuration."""
        csrf = _csrf(client)
        r = client.post("/register-organization", data={
            "org_name": "Login Test Firm", "name": "bob", "email": "bob@login.ae",
            "password": "strong-enough-1", "csrf_token": csrf,
            "invite_code": INVITE_CODE,
        }, follow_redirects=True)
        import re
        m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
        if m:
            client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)

        client.get("/login")
        r2 = client.post("/login", data={
            "email": "bob@login.ae", "password": "strong-enough-1",
            "csrf_token": client.cookies.get("amlkit_csrf"),
        }, follow_redirects=True)
        assert r2.status_code == 200

    def test_system_create_operator_unaffected(self, client, monkeypatch):
        """The system API for creating operators doesn't need invite codes."""
        monkeypatch.setenv("ADMIN_API_SECRET", "test-admin-secret")
        csrf = _csrf(client)
        client.post("/register-organization", data={
            "org_name": "System Test Firm", "name": "admin", "email": "admin@sys.ae",
            "password": "strong-enough-1", "csrf_token": csrf,
            "invite_code": INVITE_CODE,
        }, follow_redirects=True)

        r = client.post("/system/create-operator", json={
            "name": "officer", "email": "officer@sys.ae",
            "password": "strong-enough-1", "role": "officer",
            "org_slug": "system-test-firm",
        }, headers={"Authorization": "Bearer test-admin-secret"})
        assert r.status_code == 200
        assert r.json()["status"] == "created"

    def test_api_registration_rate_limited_to_5_per_minute(self, client):
        """POST /api/v1/auth/register-organization is rate-limited to 5/minute."""
        for i in range(5):
            r = client.post("/api/v1/auth/register-organization", json={
                "org_name": f"Firm {i}", "name": f"user{i}", "email": f"user{i}@test.ae",
                "password": "strong-enough-1", "invite_code": INVITE_CODE,
            })
            assert r.status_code == 200, f"attempt {i+1} should succeed: {r.text[:200]}"

        r = client.post("/api/v1/auth/register-organization", json={
            "org_name": "ExtraFirm", "name": "extra", "email": "extra@test.ae",
            "password": "strong-enough-1", "invite_code": INVITE_CODE,
        })
        assert r.status_code == 429, f"6th attempt should be 429 (got {r.status_code})"


class TestConsoleOrgAlerts:
    def test_console_org_alerts_renders_with_zero_alerts(self, monkeypatch, tmp_path):
        """Super-admin viewing /console/org/{id}/alerts for org with no alerts renders 200, not 500."""
        from amlkit.db import connect
        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        db_file = tmp_path / "test.db"
        monkeypatch.setenv("AMLKIT_DB", str(db_file))
        monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

        conn = connect(str(db_file))
        conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES ('Empty Org', 'empty', 'active', datetime('now'))")
        conn.commit()
        org_id = conn.lastrowid
        conn.close()

        client = TestClient(app)
        r = client.get(f"/console/org/{org_id}/alerts")
        assert r.status_code == 200

