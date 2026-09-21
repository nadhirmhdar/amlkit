"""MFA login enforcement for MLRO operators (p15).

An MLRO session is issued locked at /login: an un-enrolled MLRO is sent to
/mfa/setup, an enrolled one to /mfa/verify, and tenant routes stay closed
until the TOTP (or a backup code) has been presented. Officers are untouched.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pyotp
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASSWORD = "a-strong-password-1"
EMAIL = "alice@testfirm.ae"


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _rejected(resp) -> bool:
    """True when the challenge bounced back with an error flash (Issue #102 keeps
    error text out of the URL, so the redirect target alone says nothing)."""
    return (resp.status_code == 303 and resp.headers["location"] == "/mfa/verify"
            and "amlkit_flash" in resp.headers.get("set-cookie", ""))


def _register(client, name: str, email: str, password: str = PASSWORD) -> None:
    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": "Test Firm", "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert "Check your email" in r.text
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m
    client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)


def _logout(client) -> None:
    client.post("/logout", follow_redirects=False)


def _login(client, email: str = EMAIL, password: str = PASSWORD):
    client.get("/login")
    return client.post("/login", data={
        "email": email, "password": password, "csrf_token": _csrf(client),
    }, follow_redirects=False)


def _enrol(client) -> tuple[str, list[str]]:
    """Complete /mfa/setup; returns (totp secret, backup codes)."""
    page = client.get("/mfa/setup", follow_redirects=False)
    assert page.status_code == 200
    secret = re.search(r"\b([A-Z2-7]{32})\b", page.text).group(1)
    backup_codes = re.findall(r"<span>([0-9a-f]{8})</span>", page.text)
    assert len(backup_codes) == 10
    assert "api.qrserver.com" not in page.text, "QR must be rendered locally"
    assert 'src="data:image/svg+xml;base64,' in page.text
    r = client.post("/mfa/setup", data={
        "code": pyotp.TOTP(secret).now(), "csrf_token": _csrf(client),
    }, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    return secret, backup_codes


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from amlkit.db import connect

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    connect(str(db_file)).close()

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "alice", EMAIL)  # first operator of an org is the MLRO
    _logout(c)
    return c


def test_unenrolled_mlro_is_forced_to_setup_and_locked_out(client):
    r = _login(client)
    assert r.status_code == 303 and r.headers["location"] == "/mfa/setup"
    # session cookie exists but tenant routes stay closed until enrolment completes
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"].startswith("/login")


def test_enrolment_unlocks_session_and_later_logins_need_totp(client):
    _login(client)
    secret, _ = _enrol(client)
    assert client.get("/dashboard", follow_redirects=False).status_code == 200

    _logout(client)
    r = _login(client)
    assert r.status_code == 303 and r.headers["location"] == "/mfa/verify"
    assert client.get("/dashboard", follow_redirects=False).status_code in (302, 303)

    bad = client.post("/mfa/verify", data={"code": "000000", "csrf_token": _csrf(client)},
                      follow_redirects=False)
    assert _rejected(bad)
    assert client.get("/dashboard", follow_redirects=False).status_code in (302, 303)

    good = client.post("/mfa/verify", data={"code": pyotp.TOTP(secret).now(),
                                            "csrf_token": _csrf(client)}, follow_redirects=False)
    assert good.status_code == 303 and good.headers["location"] == "/"
    assert client.get("/dashboard", follow_redirects=False).status_code == 200


def test_backup_code_unlocks_once(client):
    _login(client)
    _, codes = _enrol(client)
    _logout(client)

    _login(client)
    r = client.post("/mfa/verify", data={"code": codes[0], "csrf_token": _csrf(client)},
                    follow_redirects=False)
    assert r.headers["location"] == "/"
    assert client.get("/dashboard", follow_redirects=False).status_code == 200

    _logout(client)
    _login(client)
    r = client.post("/mfa/verify", data={"code": codes[0], "csrf_token": _csrf(client)},
                    follow_redirects=False)
    assert _rejected(r), "a backup code must not work twice"
    assert client.get("/dashboard", follow_redirects=False).status_code in (302, 303)


def test_abandoned_setup_page_does_not_count_as_enrolment(client):
    _login(client)
    page = client.get("/mfa/setup", follow_redirects=False)
    assert page.status_code == 200
    # Closing the tab here must not strand the MLRO behind /mfa/verify.
    assert client.get("/mfa/verify", follow_redirects=False).headers["location"] == "/mfa/setup"
    _logout(client)
    r = _login(client)
    assert r.headers["location"] == "/mfa/setup"
    # a fresh secret is issued and enrolment completes normally
    secret, _ = _enrol(client)
    assert client.get("/dashboard", follow_redirects=False).status_code == 200
    _logout(client)
    assert _login(client).headers["location"] == "/mfa/verify"


def test_setup_cannot_overwrite_an_existing_enrolment(client):
    _login(client)
    secret, _ = _enrol(client)
    _logout(client)
    _login(client)
    r = client.get("/mfa/setup", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/mfa/verify"
    # the original secret still works
    r = client.post("/mfa/verify", data={"code": pyotp.TOTP(secret).now(),
                                         "csrf_token": _csrf(client)}, follow_redirects=False)
    assert r.headers["location"] == "/"


def test_officer_login_is_not_challenged(client):
    _login(client)
    _enrol(client)
    client.post("/admin/operators", data={
        "name": "bob", "email": "bob@testfirm.ae", "password": "a-strong-password-2",
        "role": "officer", "csrf_token": _csrf(client),
    })
    _logout(client)
    r = _login(client, "bob@testfirm.ae", "a-strong-password-2")
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert client.get("/dashboard", follow_redirects=False).status_code == 200
