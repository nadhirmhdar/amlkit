"""One password/identity rule at every entry point (WP-7).

Closes L-47 (admin reset 500, admin create skips complexity), L-58 (org
registration checks length only), L-67 (mobile /auth/setup: duplicate email
500 and token consumed, no email/name checks), L-80 (new == current), L-13,
L-59 (blank/overlong/NUL names), L-14 (case-variant operator names), L-57
(non-Latin org names collide on the slug) and L-68 (missing rate limits).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from test_api import _add_operator, _csrf, _login, _register, client  # noqa: F401

STRONG = "A-strong-password-1"


def _conn() -> sqlite3.Connection:
    import os
    c = sqlite3.connect(os.environ["AMLKIT_DB"])
    c.row_factory = sqlite3.Row
    return c


def _op(email: str):
    c = _conn()
    try:
        return c.execute("SELECT * FROM operators WHERE email=?", (email,)).fetchone()
    finally:
        c.close()


def _mk_setup_token(raw: str) -> None:
    c = _conn()
    org_id = c.execute("SELECT org_id FROM operators LIMIT 1").fetchone()["org_id"]
    exp = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(timespec="seconds")
    c.execute("INSERT INTO setup_tokens (org_id, token_hash, created_at, expires_at) VALUES (?,?,?,?)",
              (org_id, sha256(raw.encode()).hexdigest(), exp, exp))
    c.commit()
    c.close()


def _token_unused(raw: str) -> bool:
    c = _conn()
    try:
        return c.execute("SELECT used_at IS NULL u FROM setup_tokens WHERE token_hash=?",
                         (sha256(raw.encode()).hexdigest(),)).fetchone()["u"] == 1
    finally:
        c.close()


@pytest.fixture()
def mobile(client):  # noqa: F811 - reuse the web fixture's DB
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    return TestClient(app, raise_server_exceptions=False)


# ------------------------------------------------------------ helper unit
class TestCheckNewPassword:
    def test_full_rule_and_readable_messages(self) -> None:
        from amlkit import auth
        for weak, word in [("short1!A", "10 characters"), ("aaaaaaaaaa", "uppercase"),
                           ("Aaaaaaaaaa", "digit"), ("Aaaaaaaaa1", "special")]:
            with pytest.raises(auth.PasswordComplexityError, match=word):
                auth.check_new_password(weak)
        auth.check_new_password(STRONG)

    def test_rejects_nul_and_control_characters(self) -> None:
        from amlkit import auth
        with pytest.raises(auth.PasswordComplexityError):
            auth.check_new_password("A-strong-pass\x00-1")

    def test_refuses_same_as_current(self) -> None:
        from amlkit import auth
        h = auth.hash_password(STRONG)
        with pytest.raises(auth.PasswordComplexityError, match="different"):
            auth.check_new_password(STRONG, current_hash=h)
        auth.check_new_password("A-strong-password-9", current_hash=h)


# ------------------------------------------------------------- admin web
class TestAdminWeb:
    def test_reset_with_weak_password_is_a_message_not_a_500(self, client) -> None:  # noqa: F811
        _add_operator(client, "bob", "bob@testfirm.ae")
        bob = _op("bob@testfirm.ae")
        r = client.post(f"/admin/operators/{bob['id']}/reset-password",
                        data={"new_password": "1234567890", "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert r.status_code == 200
        assert "uppercase" in r.text
        assert _op("bob@testfirm.ae")["password_hash"] == bob["password_hash"]

    def test_create_with_weak_password_is_refused(self, client) -> None:  # noqa: F811
        _add_operator(client, "carol", "carol@testfirm.ae", password="aaaaaaaaaa")
        assert _op("carol@testfirm.ae") is None

    def test_create_rejects_bad_email_blank_and_long_name_and_nul(self, client) -> None:  # noqa: F811
        for name, email in [("dave", "not-an-email"), ("   ", "d@testfirm.ae"),
                            ("x" * 121, "d@testfirm.ae"), ("da\x00ve", "d@testfirm.ae")]:
            _add_operator(client, name, email)
        c = _conn()
        assert c.execute("SELECT COUNT(*) n FROM operators").fetchone()["n"] == 1
        c.close()

    def test_rename_to_case_variant_is_refused(self, client) -> None:  # noqa: F811
        _add_operator(client, "Bob Smith", "bob@testfirm.ae")
        _add_operator(client, "Carol", "carol@testfirm.ae")
        carol = _op("carol@testfirm.ae")
        r = client.post(f"/admin/operators/{carol['id']}/rename",
                        data={"name": "BOB  smith", "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "already has that name" in r.text
        assert _op("carol@testfirm.ae")["name"] == "Carol"

    def test_create_with_case_variant_name_is_refused(self, client) -> None:  # noqa: F811
        _add_operator(client, "Bob Smith", "bob@testfirm.ae")
        _add_operator(client, "bob smith", "bob2@testfirm.ae")
        assert _op("bob2@testfirm.ae") is None


# ------------------------------------------------------------ self change
class TestSelfChange:
    def test_change_to_same_password_is_refused(self, client) -> None:  # noqa: F811
        r = client.post("/account/password", data={
            "current_password": STRONG, "new_password": STRONG, "confirm_password": STRONG,
            "csrf_token": _csrf(client)}, follow_redirects=True)
        assert "different from the current password" in r.text

    def test_profile_change_to_same_password_is_refused(self, client) -> None:  # noqa: F811
        r = client.post("/profile/change-password", data={
            "old_password": STRONG, "new_password": STRONG, "csrf_token": _csrf(client)},
            follow_redirects=True)
        assert "different from the current password" in r.text


# ----------------------------------------------------------- registration
class TestRegistration:
    def test_web_length_only_password_is_refused(self, client) -> None:  # noqa: F811
        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        c = TestClient(app)
        c.get("/register-organization")
        r = c.post("/register-organization", data={
            "org_name": "Weak Org", "name": "w", "email": "w@weak.ae", "password": "xxxxxxxxxx",
            "csrf_token": _csrf(c), "invite_code": "test-invite"})
        assert "uppercase" in r.text
        assert _op("w@weak.ae") is None

    def test_mobile_length_only_password_is_refused(self, mobile) -> None:
        r = mobile.post("/api/v1/auth/register-organization", json={
            "org_name": "Weak Org", "name": "w", "email": "w@weak.ae",
            "password": "xxxxxxxxxx", "invite_code": "test-invite"})
        assert r.status_code == 400 and "uppercase" in r.json()["detail"]
        assert _op("w@weak.ae") is None

    def test_mobile_register_validates_identity(self, mobile) -> None:
        for org, name, email in [("Org", "w", "nope"), ("Org", "  ", "a@b.ae"),
                                 ("O" * 201, "w", "a@b.ae"), ("Or\x00g", "w", "a@b.ae"),
                                 ("Org", "w" * 121, "a@b.ae")]:
            r = mobile.post("/api/v1/auth/register-organization", json={
                "org_name": org, "name": name, "email": email,
                "password": STRONG, "invite_code": "test-invite"})
            assert r.status_code == 400, (org, name, email, r.text)

    def test_two_arabic_named_orgs_both_register(self, client) -> None:  # noqa: F811
        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        c = TestClient(app)
        for i, org in enumerate(["شركة الأمل", "مكتب النور"]):
            c.get("/register-organization")
            r = c.post("/register-organization", data={
                "org_name": org, "name": f"Op{i}", "email": f"op{i}@ar.ae", "password": STRONG,
                "csrf_token": _csrf(c), "invite_code": "test-invite"})
            assert "Check your email" in r.text, r.text[:300]
        conn = _conn()
        slugs = [r["slug"] for r in conn.execute("SELECT slug FROM organizations WHERE name IN (?,?)",
                                                 ("شركة الأمل", "مكتب النور"))]
        conn.close()
        assert len(set(slugs)) == 2

    def test_same_arabic_name_twice_is_still_refused(self, mobile) -> None:
        body = {"org_name": "شركة الأمل", "name": "A", "email": "a1@ar.ae",
                "password": STRONG, "invite_code": "test-invite"}
        assert mobile.post("/api/v1/auth/register-organization", json=body).status_code == 200
        body["email"] = "a2@ar.ae"
        assert mobile.post("/api/v1/auth/register-organization", json=body).status_code == 400

    def test_latin_org_slug_is_unchanged(self, mobile) -> None:
        mobile.post("/api/v1/auth/register-organization", json={
            "org_name": "Gulf Traders LLC", "name": "A", "email": "g@gulf.ae",
            "password": STRONG, "invite_code": "test-invite"})
        c = _conn()
        assert c.execute("SELECT 1 FROM organizations WHERE slug='gulf-traders-llc'").fetchone()
        c.close()


# ------------------------------------------------------------ mobile admin
class TestMobileAdmin:
    def _headers(self, mobile):
        r = mobile.post("/api/v1/auth/register-organization", json={
            "org_name": "Mob Firm", "name": "mia", "email": "mia@mobfirm.ae",
            "password": STRONG, "invite_code": "test-invite"})
        r = mobile.post("/api/v1/auth/verify-email", json={"token": r.json()["dev_verification_token"]})
        token = r.json()["token"]
        from conftest import unlock_mobile_mfa
        unlock_mobile_mfa(mobile, token)
        return {"Authorization": f"Bearer {token}"}

    def test_reset_and_create_enforce_the_rule(self, client, mobile) -> None:  # noqa: F811
        h = self._headers(mobile)
        r = mobile.post("/api/v1/admin/operators", headers=h, json={
            "name": "Bob", "email": "bob@testfirm.ae", "password": "aaaaaaaaaa"})
        assert r.status_code == 400
        r = mobile.post("/api/v1/admin/operators", headers=h, json={
            "name": "Bob", "email": "bob@testfirm.ae", "password": "Another-pw-123"})
        assert r.status_code == 200
        bob = _op("bob@testfirm.ae")["id"]
        r = mobile.post(f"/api/v1/admin/operators/{bob}/reset-password", headers=h,
                        json={"new_password": "1234567890"})
        assert r.status_code == 400 and "uppercase" in r.json()["detail"]


# ------------------------------------------------------------ mobile setup
class TestMobileSetup:
    def test_duplicate_email_is_409_and_token_stays_unused(self, client, mobile) -> None:  # noqa: F811
        _mk_setup_token("tok-dup")
        r = mobile.post("/api/v1/auth/setup", json={
            "token": "tok-dup", "name": "Dup", "email": "alice@testfirm.ae", "password": STRONG})
        assert r.status_code == 409
        assert _token_unused("tok-dup")

    def test_not_an_email_is_400_and_token_stays_unused(self, client, mobile) -> None:  # noqa: F811
        _mk_setup_token("tok-bad")
        r = mobile.post("/api/v1/auth/setup", json={
            "token": "tok-bad", "name": "B", "email": "not-an-email", "password": STRONG})
        assert r.status_code == 400
        assert _op("not-an-email") is None
        assert _token_unused("tok-bad")

    def test_weak_password_and_blank_name_are_400(self, client, mobile) -> None:  # noqa: F811
        _mk_setup_token("tok-weak")
        for name, pw in [("Ok", "xxxxxxxxxx"), ("  ", STRONG)]:
            r = mobile.post("/api/v1/auth/setup", json={
                "token": "tok-weak", "name": name, "email": "n@testfirm.ae", "password": pw})
            assert r.status_code == 400
        assert _token_unused("tok-weak")

    def test_valid_claim_still_works(self, client, mobile) -> None:  # noqa: F811
        _mk_setup_token("tok-ok")
        r = mobile.post("/api/v1/auth/setup", json={
            "token": "tok-ok", "name": "Good", "email": "good@testfirm.ae", "password": STRONG})
        assert r.status_code == 200
        assert not _token_unused("tok-ok")

    def test_web_setup_duplicate_email_keeps_form_and_token(self, client) -> None:  # noqa: F811
        _mk_setup_token("tok-web")
        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        c = TestClient(app, raise_server_exceptions=False)
        c.get(f"/setup?token=tok-web")
        r = c.post("/setup", data={"token": "tok-web", "name": "W", "email": "alice@testfirm.ae",
                                   "password": STRONG, "csrf_token": _csrf(c)})
        assert r.status_code == 200 and "already exists" in r.text
        assert _token_unused("tok-web")


# ------------------------------------------------------------- rate limits
class TestRateLimits:
    @pytest.fixture(autouse=True)
    def _limiter_on(self):
        from amlkit.api.app import app
        app.state.limiter.enabled = True
        app.state.limiter.reset()
        yield
        app.state.limiter.reset()
        app.state.limiter.enabled = False

    @pytest.mark.parametrize("method,path,payload", [
        ("post", "/api/v1/auth/resend-verification", {"email": "x@y.ae"}),
        ("post", "/api/v1/auth/verify-email", {"token": "nope"}),
        ("get", "/api/v1/auth/setup?token=nope", None),
    ])
    def test_eleventh_request_in_a_minute_is_429(self, mobile, method, path, payload) -> None:
        codes = []
        for _ in range(11):
            r = mobile.post(path, json=payload) if method == "post" else mobile.get(path)
            codes.append(r.status_code)
        assert codes[-1] == 429, codes
        assert 429 not in codes[:10]

    def test_web_resend_verification_is_limited(self, mobile) -> None:
        codes = [mobile.post("/resend-verification", data={"email": "x@y.ae"}).status_code for _ in range(11)]
        assert codes[-1] == 429, codes
