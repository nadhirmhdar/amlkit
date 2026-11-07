"""WP-29 launch blockers: sign-up enumeration (L-115), honest email-failure
page, accurate public claims (L-118/L-119), unpaid-org OCR scans (SS2/L-116)."""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from conftest import real_image_bytes  # noqa: E402
from test_api import _csrf, _db, client  # noqa: F401,E402
from test_mobile_api import api  # noqa: F401,E402
from test_public_site import raw_client, stripe_on  # noqa: F401,E402

PENDING_MSG = "Add payment details on /billing to start your 14-day trial"


def _fresh_client():
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    return TestClient(app)


def _signup(c, org, email, name="Owner One", password="A-strong-password-1"):
    c.get("/register-organization")
    return c.post("/register-organization", data={
        "org_name": org, "name": name, "email": email,
        "password": password, "csrf_token": _csrf(c),
    }, follow_redirects=False)


def _norm(resp, *, email, org=None):
    body = resp.text.replace(email, "EMAIL")
    if org:
        body = body.replace(org, "ORG")
    body = re.sub(r'name="csrf_token" value="[^"]*"', 'name="csrf_token" value="X"', body)
    return body


def _cookie_names(resp):
    return sorted({h.split("=", 1)[0] for h in resp.headers.get_list("set-cookie")})


def _counts():
    c = _db()
    out = (c.execute("SELECT COUNT(*) FROM organizations").fetchone()[0],
           c.execute("SELECT COUNT(*) FROM operators").fetchone()[0])
    c.close()
    return out


@pytest.fixture()
def mails(monkeypatch):
    """Capture verification mails and existing-account notices."""
    from amlkit import mail
    log = {"verify": [], "notice": [], "outcome": mail.SENT}

    def verify(to, name, token):
        log["verify"].append((to, token))
        return log["outcome"]

    def notice(to, name):
        log["notice"].append(to)
        return log["outcome"]

    monkeypatch.setattr(mail, "send_verification_email", verify)
    monkeypatch.setattr(mail, "send_existing_account_notice", notice)
    return log


@pytest.fixture()
def seeded(raw_client, stripe_on, mails):  # noqa: F811
    """Open sign-up on, one existing account (owner@fresh.ae / Fresh Firm)."""
    r = _signup(raw_client, "Fresh Firm", "owner@fresh.ae")
    assert r.status_code == 200 and mails["verify"]
    mails["verify"].clear()
    return raw_client


class TestSignupEnumeration:
    def test_existing_and_new_email_answer_identically(self, seeded, mails):
        before = _counts()
        new = _signup(_fresh_client(), "Brand New Firm", "brandnew@other.ae")
        existing = _signup(_fresh_client(), "Another Firm", "owner@fresh.ae")
        assert new.status_code == existing.status_code == 200
        assert "Check your email" in new.text and "Check your email" in existing.text
        assert _norm(new, email="brandnew@other.ae") == _norm(existing, email="owner@fresh.ae")
        assert _cookie_names(new) == _cookie_names(existing)
        assert "already exists" not in existing.text
        # Existing email: nothing created, the owner is told instead.
        assert _counts() == (before[0] + 1, before[1] + 1)  # only the new sign-up
        assert mails["notice"] == ["owner@fresh.ae"]
        assert [t[0] for t in mails["verify"]] == ["brandnew@other.ae"]

    def test_email_match_is_case_insensitive(self, seeded, mails):
        before = _counts()
        r = _signup(_fresh_client(), "Whatever Ltd", "OWNER@Fresh.AE")
        assert r.status_code == 200 and "Check your email" in r.text
        assert _counts() == before and mails["notice"]

    def test_page_never_shows_the_verification_link_in_open_signup(self, seeded):
        from amlkit import mail
        with mock.patch.object(mail, "send_verification_email", return_value=mail.NOT_CONFIGURED):
            r = _signup(_fresh_client(), "No Mail Firm", "nomail@other.ae")
        assert "/verify-email?token=" not in r.text

    def test_existing_email_survives_a_notice_mail_failure(self, seeded, mails):
        good = _signup(_fresh_client(), "Zed Firm", "zed@other.ae")
        mails["outcome"] = "failed"
        mails["verify"].clear()
        existing = _signup(_fresh_client(), "Zed Two", "owner@fresh.ae")
        # Mail failure for an existing address is silent: same page as success.
        assert existing.status_code == 200
        assert "could not send" not in existing.text
        assert _norm(good, email="zed@other.ae") == _norm(existing, email="owner@fresh.ae")

    def test_org_name_collision_is_not_revealed_and_registers(self, seeded):
        before = _counts()
        same = _signup(_fresh_client(), "Fresh Firm", "second@other.ae")
        other = _signup(_fresh_client(), "Unique Name Ltd", "third@other.ae")
        assert same.status_code == other.status_code == 200
        assert "similar name" not in same.text
        assert _norm(same, email="second@other.ae") == _norm(other, email="third@other.ae")
        assert _counts() == (before[0] + 2, before[1] + 2)
        c = _db()
        slugs = [r["slug"] for r in c.execute("SELECT slug FROM organizations WHERE name='Fresh Firm'")]
        c.close()
        assert len(slugs) == 2 and len(set(slugs)) == 2

    def test_validation_errors_do_not_depend_on_the_email(self, seeded):
        a = _signup(_fresh_client(), "Weak Firm", "owner@fresh.ae", password="short")
        b = _signup(_fresh_client(), "Weak Firm", "unknown@other.ae", password="short")
        assert a.status_code == b.status_code
        assert _norm(a, email="owner@fresh.ae") == _norm(b, email="unknown@other.ae")

    def test_invite_gated_path_is_unchanged(self, raw_client, monkeypatch):
        monkeypatch.setenv("AMLKIT_REGISTRATION_INVITE_CODE", "test-invite")
        for k in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"):
            monkeypatch.delenv(k, raising=False)
        c = _fresh_client()
        c.get("/register-organization")
        data = {"org_name": "Inv Firm", "name": "Inv", "email": "inv@x.ae",
                "password": "A-strong-password-1", "invite_code": "test-invite"}
        assert "Check your email" in c.post("/register-organization",
                                            data={**data, "csrf_token": _csrf(c)}).text
        r = c.post("/register-organization", data={**data, "csrf_token": _csrf(c)})
        assert "already exists" in r.text


class TestEmailFailurePage:
    def test_failed_send_shows_one_honest_message_and_keeps_resend(self, raw_client, stripe_on, mails):  # noqa: F811
        mails["outcome"] = "failed"
        r = _signup(_fresh_client(), "Fail Firm", "fail@other.ae")
        assert r.status_code == 200
        assert "We could not send the verification email right now" in r.text
        assert "Use Resend in a few minutes or contact info@grovisor.ae" in r.text
        assert "We sent" not in r.text
        assert 'action="/resend-verification"' in r.text
        assert "Resend verification email" in r.text

    def test_successful_send_does_not_show_the_failure_text(self, raw_client, stripe_on, mails):  # noqa: F811
        r = _signup(_fresh_client(), "Ok Firm", "ok@other.ae")
        assert "We sent an email to" in r.text and "could not send" not in r.text

    def test_invite_mode_failed_send_is_also_honest(self, raw_client, monkeypatch, mails):  # noqa: F811
        monkeypatch.setenv("AMLKIT_REGISTRATION_INVITE_CODE", "test-invite")
        mails["outcome"] = "failed"
        c = _fresh_client()
        c.get("/register-organization")
        r = c.post("/register-organization", data={
            "org_name": "Inv Fail", "name": "I", "email": "if@x.ae",
            "password": "A-strong-password-1", "invite_code": "test-invite",
            "csrf_token": _csrf(c)})
        assert "We could not send the verification email right now" in r.text
        assert "We sent" not in r.text


class TestPublicClaims:
    @pytest.fixture()
    def pub(self, raw_client, monkeypatch):  # noqa: F811
        for k in ("UAEPASS_CLIENT_ID", "UAEPASS_CLIENT_SECRET", "UAEPASS_ENV"):
            monkeypatch.delenv(k, raising=False)
        return raw_client

    @pytest.mark.parametrize("path", ["/", "/aml-law"])
    def test_freeze_scope_wording(self, pub, path):
        t = _fresh_client().get(path).text
        assert "UN Security Council" in t and "freeze obligations" in t.lower()
        assert "Confirmed sanctions matches create freeze obligations" not in t
        assert "Freeze obligations created from confirmed matches" not in t

    def test_aml_law_says_other_lists_stay_alerts(self, pub):
        assert "Matches on other lists (OFAC, EU, UK) stay alerts" in _fresh_client().get("/aml-law").text

    @pytest.mark.parametrize("path", ["/", "/aml-law"])
    def test_no_uaepass_when_unconfigured(self, pub, path):
        assert "UAE PASS" not in _fresh_client().get(path).text

    @pytest.mark.parametrize("path", ["/", "/aml-law"])
    def test_no_uaepass_on_the_staging_sandbox(self, pub, monkeypatch, path):
        monkeypatch.setenv("UAEPASS_CLIENT_ID", "sandbox_stage")
        monkeypatch.setenv("UAEPASS_CLIENT_SECRET", "sandbox_stage")
        monkeypatch.delenv("UAEPASS_ENV", raising=False)
        assert "UAE PASS" not in _fresh_client().get(path).text
        monkeypatch.setenv("UAEPASS_ENV", "staging")
        assert "UAE PASS" not in _fresh_client().get(path).text

    @pytest.mark.parametrize("path", ["/", "/aml-law"])
    def test_uaepass_mentioned_only_when_production(self, pub, monkeypatch, path):
        monkeypatch.setenv("UAEPASS_CLIENT_ID", "real-id")
        monkeypatch.setenv("UAEPASS_CLIENT_SECRET", "real-secret")
        monkeypatch.setenv("UAEPASS_ENV", "production")
        assert "UAE PASS" in _fresh_client().get(path).text

    def test_production_env_without_credentials_stays_silent(self, pub, monkeypatch):
        monkeypatch.setenv("UAEPASS_ENV", "production")
        assert "UAE PASS" not in _fresh_client().get("/").text

    def test_landing_still_reads_well_without_uaepass(self, pub):
        assert "Capture details from Emirates ID and passport scans." in _fresh_client().get("/").text


def _make_pending(monkeypatch):
    for k, v in (("STRIPE_SECRET_KEY", "sk_test_123"), ("STRIPE_WEBHOOK_SECRET", "whsec_x"),
                 ("STRIPE_PRICE_STARTER", "price_s")):
        monkeypatch.setenv(k, v)
    c = _db()
    c.execute("UPDATE organizations SET plan='none', plan_status='pending_payment'")
    c.commit()
    c.close()


class TestUnpaidOrgScans:
    @pytest.mark.parametrize("route,field", [
        ("/customers/scan-passport", "passport_file"),
        ("/customers/scan-trade-licence", "licence_file"),
    ])
    def test_web_scans_refused_while_pending(self, client, monkeypatch, route, field):  # noqa: F811
        _make_pending(monkeypatch)
        r = client.post(route, files={field: ("a.jpg", io.BytesIO(real_image_bytes()), "image/jpeg")},
                        data={"csrf_token": _csrf(client)})
        assert r.status_code == 402 and PENDING_MSG in r.json()["detail"]

    @pytest.mark.parametrize("route,field", [
        ("/api/v1/customers/scan-passport", "passport_file"),
        ("/api/v1/customers/scan-emirates-id", "emirates_id_file"),
    ])
    def test_mobile_scans_refused_while_pending(self, api, monkeypatch, route, field):  # noqa: F811
        c, headers = api
        _make_pending(monkeypatch)
        r = c.post(route, headers=headers, files={field: ("a.jpg", real_image_bytes(), "image/jpeg")})
        assert r.status_code == 402 and PENDING_MSG in r.json()["detail"]

    def test_scans_work_for_legacy_org_with_stripe_on(self, client, monkeypatch):  # noqa: F811
        for k, v in (("STRIPE_SECRET_KEY", "sk_test_123"), ("STRIPE_WEBHOOK_SECRET", "whsec_x")):
            monkeypatch.setenv(k, v)
        r = client.post("/customers/scan-trade-licence",
                        files={"licence_file": ("a.jpg", io.BytesIO(real_image_bytes()), "image/jpeg")},
                        data={"csrf_token": _csrf(client)})
        assert r.status_code == 200

    def test_scans_work_for_subscribed_org(self, client, monkeypatch):  # noqa: F811
        _make_pending(monkeypatch)
        c = _db()
        c.execute("UPDATE organizations SET plan='starter', plan_status='active'")
        c.commit()
        c.close()
        r = client.post("/customers/scan-trade-licence",
                        files={"licence_file": ("a.jpg", io.BytesIO(real_image_bytes()), "image/jpeg")},
                        data={"csrf_token": _csrf(client)})
        assert r.status_code == 200

    def test_stripe_off_never_gates(self, client):  # noqa: F811
        r = client.post("/customers/scan-trade-licence",
                        files={"licence_file": ("a.jpg", io.BytesIO(real_image_bytes()), "image/jpeg")},
                        data={"csrf_token": _csrf(client)})
        assert r.status_code == 200

    def test_screen_and_feedback_stay_open_while_pending(self, api, monkeypatch):  # noqa: F811
        c, headers = api
        _make_pending(monkeypatch)
        r = c.post("/api/v1/screen", headers=headers, json={"name": "Jane Example"})
        assert r.status_code == 200, r.text
