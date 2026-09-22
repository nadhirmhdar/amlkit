"""Tests for two related additions:

1. /system/super-admin -- the only way anywhere in the app to set
   operators.super_admin on an existing operator. Modeled exactly on
   /system/create-operator: gated behind ADMIN_API_SECRET, out-of-band only.
   No authenticated in-app route can reach this (nothing here tests such a
   route, because none exists -- that absence is the point). The flag must
   also render visibly in admin.html to every operator in the org, never
   hidden.

2. "Remember this device" MFA trusted-device tokens (auth.py, /mfa/verify's
   remember_device checkbox): a 30-day cookie that lets a recognised browser
   skip the TOTP challenge, scoped to one operator, and revoked on password
   change or via the explicit /account/forget-devices action.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path

import pyotp
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASSWORD = "a-strong-password-1"


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _register_and_login(client, org_name: str, name: str, email: str, password: str = PASSWORD):
    """Registers an org (first operator = MLRO), verifies email, and settles
    the resulting locked MFA session by enrolling."""
    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client), "invite_code": "test-invite",
    }, follow_redirects=True)
    assert "Check your email" in r.text
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m
    client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    from conftest import settle_mfa  # p15: MLRO sessions start locked
    settle_mfa(client)
    return client


def _add_operator(client, name: str, email: str, password: str = "a-strong-password-2", role: str = "officer"):
    return client.post("/admin/operators", data={
        "name": name, "email": email, "password": password, "role": role,
        "csrf_token": _csrf(client),
    })


def _login(client, email: str, password: str = PASSWORD, follow_redirects: bool = False):
    client.get("/login")
    return client.post("/login", data={
        "email": email, "password": password, "csrf_token": _csrf(client),
    }, follow_redirects=follow_redirects)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from amlkit.db import connect

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    monkeypatch.delenv("ADMIN_API_SECRET", raising=False)
    connect(str(db_file)).close()

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    return TestClient(app)


# ------------------------------------------------------------ /system/super-admin

class TestSuperAdminEndpointAuth:
    def test_disabled_without_secret_configured(self, client) -> None:
        r = client.post("/system/super-admin", json={"email": "x@test.invalid"})
        assert r.status_code == 403
        assert "ADMIN_API_SECRET" in r.json()["error"]

    def test_rejects_wrong_bearer_token(self, client, monkeypatch) -> None:
        monkeypatch.setenv("ADMIN_API_SECRET", "correct-secret")
        r = client.post(
            "/system/super-admin", json={"email": "x@test.invalid"},
            headers={"Authorization": "Bearer wrong-secret"},
        )
        assert r.status_code == 401


class TestSuperAdminEndpointBehavior:
    @pytest.fixture(autouse=True)
    def _setup(self, client, monkeypatch):
        # `client` first (clears ADMIN_API_SECRET as part of DB setup), then
        # set the secret -- same ordering concern as test_system_endpoints.py.
        _register_and_login(client, "Test Firm", "alice", "alice@testfirm.ae")
        monkeypatch.setenv("ADMIN_API_SECRET", "test-admin-secret")
        self.headers = {"Authorization": "Bearer test-admin-secret"}
        self.client = client

    def test_unknown_email_404(self) -> None:
        r = self.client.post(
            "/system/super-admin", json={"email": "nobody@testfirm.ae"}, headers=self.headers,
        )
        assert r.status_code == 404

    def test_grant_returns_200_and_flag_and_audits(self) -> None:
        r = self.client.post(
            "/system/super-admin",
            json={"email": "alice@testfirm.ae", "grant": True},
            headers=self.headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["super_admin"] is True
        assert body["email"] == "alice@testfirm.ae"
        assert body["organization"] == "Test Firm"

        conn = _db()
        op = conn.execute("SELECT super_admin FROM operators WHERE email='alice@testfirm.ae'").fetchone()
        assert op["super_admin"] == 1
        audit_row = conn.execute(
            "SELECT * FROM audit_log WHERE action='operator.super_admin_granted' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert audit_row is not None
        assert "alice@testfirm.ae" in (audit_row["detail"] or "")

    def test_revoke_after_grant_returns_false_and_audits(self) -> None:
        self.client.post(
            "/system/super-admin", json={"email": "alice@testfirm.ae", "grant": True}, headers=self.headers,
        )
        r = self.client.post(
            "/system/super-admin", json={"email": "alice@testfirm.ae", "grant": False}, headers=self.headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["super_admin"] is False

        conn = _db()
        op = conn.execute("SELECT super_admin FROM operators WHERE email='alice@testfirm.ae'").fetchone()
        assert op["super_admin"] == 0
        audit_row = conn.execute(
            "SELECT * FROM audit_log WHERE action='operator.super_admin_revoked' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert audit_row is not None


# --------------------------------------------------------------- admin.html badge

class TestSuperAdminBadgeVisibility:
    """The flag must render to every operator who can see the admin page --
    never hidden, never conditional on who's viewing."""

    def test_badge_shown_for_super_admin_and_not_for_others(self, client, monkeypatch) -> None:
        _register_and_login(client, "Test Firm", "alice", "alice@testfirm.ae")
        _add_operator(client, "bob", "bob@testfirm.ae")

        monkeypatch.setenv("ADMIN_API_SECRET", "test-admin-secret")
        r = client.post(
            "/system/super-admin",
            json={"email": "alice@testfirm.ae", "grant": True},
            headers={"Authorization": "Bearer test-admin-secret"},
        )
        assert r.status_code == 200, r.text

        page = client.get("/admin", follow_redirects=False)
        assert page.status_code == 200

        rows = page.text.split('<div class="list-row">')[1:]
        alice_row = next(row for row in rows if "alice@testfirm.ae" in row)
        bob_row = next(row for row in rows if "bob@testfirm.ae" in row)
        assert "Super admin" in alice_row
        assert "Super admin" not in bob_row


# ---------------------------------------------------------------- trusted devices

def _enrol(client) -> str:
    """Complete /mfa/setup for whichever session is currently locked at it;
    returns the TOTP secret."""
    page = client.get("/mfa/setup", follow_redirects=False)
    assert page.status_code == 200
    secret = re.search(r"\b([A-Z2-7]{32})\b", page.text).group(1)
    r = client.post("/mfa/setup", data={
        "code": pyotp.TOTP(secret).now(), "csrf_token": _csrf(client),
    }, follow_redirects=False)
    assert r.status_code == 200, r.headers.get("location")
    return secret


class TestTrustedDevice:
    def test_remember_device_sets_cookie_and_new_session_skips_challenge(self, client) -> None:
        _register_and_login(client, "Test Firm", "alice", "alice@testfirm.ae")
        # _register_and_login's settle_mfa already enrolled+unlocked this
        # session via a fresh TOTP; log out and log back in to get a freshly
        # LOCKED session so /mfa/verify + remember_device can be exercised.
        client.post("/logout", follow_redirects=False)
        r = _login(client, "alice@testfirm.ae")
        assert r.status_code == 303 and r.headers["location"] == "/mfa/verify"

        secret = client._amlkit_mfa_secrets[0]
        verify = client.post("/mfa/verify", data={
            "code": pyotp.TOTP(secret).now(),
            "csrf_token": _csrf(client),
            "remember_device": "1",
        }, follow_redirects=False)
        assert verify.status_code == 303 and verify.headers["location"] == "/"
        device_token = client.cookies.get("amlkit_trusted_device")
        assert device_token, "remember_device=1 must set the trusted-device cookie"

        # A brand-new TestClient == a fresh browser session on the same
        # machine: it carries the remembered device cookie but no session.
        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        fresh = TestClient(app)
        fresh.cookies.set("amlkit_trusted_device", device_token)
        fresh.get("/login")
        login_resp = fresh.post("/login", data={
            "email": "alice@testfirm.ae", "password": PASSWORD,
            "csrf_token": fresh.cookies.get("amlkit_csrf"),
        }, follow_redirects=False)
        assert login_resp.status_code == 303 and login_resp.headers["location"] == "/"
        assert fresh.get("/dashboard", follow_redirects=False).status_code == 200

    def test_trusted_device_of_one_operator_does_not_bypass_another(self, client) -> None:
        _register_and_login(client, "Test Firm", "alice", "alice@testfirm.ae")
        client.post("/logout", follow_redirects=False)
        _login(client, "alice@testfirm.ae")
        secret = client._amlkit_mfa_secrets[0]
        verify = client.post("/mfa/verify", data={
            "code": pyotp.TOTP(secret).now(),
            "csrf_token": _csrf(client),
            "remember_device": "1",
        }, follow_redirects=False)
        alice_device_token = client.cookies.get("amlkit_trusted_device")
        assert alice_device_token

        # A second, unrelated org with its own MLRO.
        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        carol_client = TestClient(app)
        _register_and_login(carol_client, "Other Firm", "carol", "carol@otherfirm.ae")
        carol_client.post("/logout", follow_redirects=False)

        # Fresh session for carol, but presenting alice's device cookie.
        intruder = TestClient(app)
        intruder.cookies.set("amlkit_trusted_device", alice_device_token)
        intruder.get("/login")
        r = intruder.post("/login", data={
            "email": "carol@otherfirm.ae", "password": PASSWORD,
            "csrf_token": intruder.cookies.get("amlkit_csrf"),
        }, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/mfa/verify", \
            "a device token bound to a different operator must not bypass MFA"

    def test_expired_or_garbage_cookie_falls_through_to_challenge(self, client) -> None:
        _register_and_login(client, "Test Firm", "alice", "alice@testfirm.ae")
        client.post("/logout", follow_redirects=False)

        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        fresh = TestClient(app)
        fresh.cookies.set("amlkit_trusted_device", "not-a-real-token-at-all")
        fresh.get("/login")
        r = fresh.post("/login", data={
            "email": "alice@testfirm.ae", "password": PASSWORD,
            "csrf_token": fresh.cookies.get("amlkit_csrf"),
        }, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/mfa/verify"

    def test_password_change_revokes_trusted_devices(self, client) -> None:
        _register_and_login(client, "Test Firm", "alice", "alice@testfirm.ae")
        client.post("/logout", follow_redirects=False)
        _login(client, "alice@testfirm.ae")
        secret = client._amlkit_mfa_secrets[0]
        client.post("/mfa/verify", data={
            "code": pyotp.TOTP(secret).now(),
            "csrf_token": _csrf(client),
            "remember_device": "1",
        }, follow_redirects=False)
        device_token = client.cookies.get("amlkit_trusted_device")
        assert device_token

        new_password = "Another-strong-pw-2"
        r = client.post("/account/password", data={
            "current_password": PASSWORD,
            "new_password": new_password,
            "confirm_password": new_password,
            "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r.status_code == 303

        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        fresh = TestClient(app)
        fresh.cookies.set("amlkit_trusted_device", device_token)
        fresh.get("/login")
        login_resp = fresh.post("/login", data={
            "email": "alice@testfirm.ae", "password": new_password,
            "csrf_token": fresh.cookies.get("amlkit_csrf"),
        }, follow_redirects=False)
        assert login_resp.status_code == 303 and login_resp.headers["location"] == "/mfa/verify", \
            "a password change must revoke previously remembered devices"

    def test_forget_devices_revokes_trusted_devices(self, client) -> None:
        _register_and_login(client, "Test Firm", "alice", "alice@testfirm.ae")
        client.post("/logout", follow_redirects=False)
        _login(client, "alice@testfirm.ae")
        secret = client._amlkit_mfa_secrets[0]
        client.post("/mfa/verify", data={
            "code": pyotp.TOTP(secret).now(),
            "csrf_token": _csrf(client),
            "remember_device": "1",
        }, follow_redirects=False)
        device_token = client.cookies.get("amlkit_trusted_device")
        assert device_token

        r = client.post("/account/forget-devices", data={
            "csrf_token": _csrf(client),
        }, follow_redirects=False)
        assert r.status_code == 303

        conn = _db()
        row = conn.execute(
            "SELECT 1 FROM audit_log WHERE action='mfa.devices_forgotten' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row is not None

        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        fresh = TestClient(app)
        fresh.cookies.set("amlkit_trusted_device", device_token)
        fresh.get("/login")
        login_resp = fresh.post("/login", data={
            "email": "alice@testfirm.ae", "password": PASSWORD,
            "csrf_token": fresh.cookies.get("amlkit_csrf"),
        }, follow_redirects=False)
        assert login_resp.status_code == 303 and login_resp.headers["location"] == "/mfa/verify", \
            "/account/forget-devices must revoke previously remembered devices"
