"""WP-26: public marketing front door (/, /aml-law, /pricing), the two sign-up
modes (Stripe = open sign-up with a pending-payment org; no Stripe = invite
code / request access) and the pending_payment billing state."""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_api import _csrf, _db, _register, _seed_sanctions_data  # noqa: E402
from test_billing import (  # noqa: E402
    WHSEC, _post_webhook, _set_org, _sub_event,
)


@pytest.fixture()
def raw_client(tmp_path, monkeypatch):
    """Anonymous client on a fresh DB (no org registered)."""
    db_file = tmp_path / "public.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    monkeypatch.delenv("AMLKIT_PUBLIC_BASE_URL", raising=False)
    for k in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"):
        monkeypatch.delenv(k, raising=False)
    _seed_sanctions_data(db_file)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    return TestClient(app)


@pytest.fixture()
def client(raw_client):
    _register(raw_client, "Test Firm", "alice", "alice@testfirm.ae")
    return raw_client


@pytest.fixture()
def anon(client):
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    return TestClient(app)


@pytest.fixture()
def stripe_on(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WHSEC)
    for t in ("STARTER", "PROFESSIONAL", "CONSULTANT"):
        monkeypatch.setenv(f"STRIPE_PRICE_{t}", f"price_{t.lower()}_1")
    monkeypatch.setenv("STRIPE_DISPLAY_PRICE_STARTER", "AED 111 / year")


def _self_serve_signup(c, org="Fresh Firm", email="owner@fresh.ae"):
    """Register without an invite code and follow the dev verification link."""
    c.get("/register-organization")
    r = c.post("/register-organization", data={
        "org_name": org, "name": "Owner One", "email": email,
        "password": "A-strong-password-1", "csrf_token": _csrf(c),
    }, follow_redirects=True)
    assert "Check your email" in r.text, r.text[:400]
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    return c.get(f"/verify-email?token={m.group(1)}", follow_redirects=False)


def _org_by_name(name):
    c = _db()
    row = c.execute("SELECT * FROM organizations WHERE name=?", (name,)).fetchone()
    c.close()
    return row


# ------------------------------------------------------------------ landing
class TestLanding:
    def test_anonymous_root_is_the_landing_page_not_a_redirect(self, raw_client):
        r = raw_client.get("/", follow_redirects=False)
        assert r.status_code == 200
        assert "<h1" in r.text and "UAE" in r.text
        for block in ("Sanctions and PEP screening", "CDD and KYC", "goAML reporting",
                      "How it works", "Append-only audit trail", "MFA for MLROs"):
            assert block in r.text
        assert "amlkit" not in r.text.lower().replace("/static", "")

    def test_signed_in_root_keeps_the_orientation_page(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "alice" in r.text and "Onboard a customer" in r.text
        assert "How it works" not in r.text

    def test_landing_has_seo_and_no_tenant_or_csrf_leak(self, raw_client):
        r = raw_client.get("/")
        assert '<link rel="canonical" href="https://groaml.grovisor.ae/">' in r.text
        assert 'property="og:title" content="groAML by Grovisor: AML/CFT' in r.text
        assert "noindex" not in r.text
        assert r.text.count("<h1") == 1
        assert 'name="csrf_token"' not in r.text

    def test_no_other_trial_length_is_ever_quoted(self, raw_client, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
        for path in ("/", "/pricing", "/aml-law"):
            text = raw_client.get(path).text
            for n in re.findall(r"(\d+)-day", text):
                assert n == "14", (path, n)


# ---------------------------------------------------------------- CTA modes
class TestCtaModes:
    @pytest.mark.parametrize("path", ["/", "/pricing", "/aml-law", "/about", "/privacy", "/blog"])
    def test_without_stripe_cta_is_request_access(self, raw_client, path):
        t = raw_client.get(path).text
        assert "Request access" in t and 'href="/apply"' in t
        assert "Start free trial" not in t

    @pytest.mark.parametrize("path", ["/", "/pricing", "/aml-law", "/about", "/privacy", "/blog"])
    def test_with_stripe_cta_is_start_free_trial(self, raw_client, stripe_on, path):
        t = raw_client.get(path).text
        assert "Start free trial" in t and 'href="/register-organization"' in t
        assert "Request access" not in t

    def test_apply_page_gets_the_shared_nav(self, raw_client):
        t = raw_client.get("/apply").text
        assert 'class="pub-nav' in t and 'href="/aml-law"' in t and "info@grovisor.ae" in t

    def test_shared_nav_and_footer_links(self, raw_client):
        t = raw_client.get("/").text
        for href in ("/#product", "/aml-law", "/pricing", "/blog", "/about", "/login",
                     "/privacy", "mailto:info@grovisor.ae"):
            assert f'href="{href}"' in t, href

    def test_signed_in_nav_is_untouched(self, client):
        assert 'class="pub-nav' not in client.get("/dashboard").text

    def test_self_serve_helper_follows_stripe_config(self, monkeypatch):
        from amlkit.billing import self_serve_enabled
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        assert self_serve_enabled() is False
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_1")
        assert self_serve_enabled() is True


# ----------------------------------------------------------------- aml-law
class TestAmlLaw:
    def test_renders_and_names_instruments_without_article_numbers(self, raw_client):
        r = raw_client.get("/aml-law")
        assert r.status_code == 200
        for s in ("Federal Decree-Law No. 10 of 2025", "Cabinet Resolution No. 134 of 2025",
                  "Cabinet Decision No. 109 of 2023", "Cabinet Resolution No. 74 of 2020",
                  "general information, not legal advice"):
            assert s in r.text
        body = re.sub(r"<[^>]+>", " ", r.text)
        assert not re.search(r"\bArticle\s*\d|\bArt\.\s*\d|AED\s*\d|\b\d+\s*(business |working )?days\b", body)
        assert "Customer due diligence" in r.text and "Targeted financial sanctions" in r.text


# ------------------------------------------------------------------ pricing
class TestPricingAlwaysPublic:
    def test_without_stripe_renders_three_tiers_and_contact_us(self, raw_client):
        r = raw_client.get("/pricing")
        assert r.status_code == 200
        for n in ("Starter", "Professional", "Consultant"):
            assert n in r.text
        assert r.text.count("Contact us") == 3
        assert "Up to 3 operators" in r.text and "Up to 2,000 customers" in r.text

    def test_with_stripe_shows_prices_and_trial_wording(self, raw_client, stripe_on):
        r = raw_client.get("/pricing")
        assert r.status_code == 200
        assert "AED 111 / year" in r.text and r.text.count("Contact us") == 2
        assert "14-day free trial" in r.text and "starts when you add payment details" in r.text

    def test_sitemap_lists_the_public_pages_in_both_modes(self, raw_client, monkeypatch):
        for _ in range(2):
            t = raw_client.get("/sitemap.xml").text
            for p in ("/", "/aml-law", "/pricing", "/about", "/blog"):
                assert f"<loc>https://groaml.grovisor.ae{p}</loc>" in t, p
            monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_1")

    def test_other_billing_routes_still_404_without_stripe(self, raw_client):
        assert raw_client.get("/billing").status_code == 404

    def test_private_pages_stay_noindex(self, client):
        assert "noindex" in client.get("/dashboard").text


# --------------------------------------------------------------- registration
class TestRegistrationModes:
    def test_without_stripe_invite_code_is_required_and_org_is_legacy(self, raw_client):
        assert "reg-invite-code" in raw_client.get("/register-organization").text
        raw_client.get("/register-organization")
        r = raw_client.post("/register-organization", data={
            "org_name": "No Code", "name": "Nora", "email": "n@x.ae",
            "password": "A-strong-password-1", "csrf_token": _csrf(raw_client),
        })
        assert "Invalid invite code" in r.text
        _register(raw_client, "Invited Firm", "ivy", "ivy@invited.ae")
        org = _org_by_name("Invited Firm")
        assert (org["plan"], org["plan_status"]) == ("trial", None)

    def test_with_stripe_no_invite_code_needed_and_org_is_pending(self, raw_client, stripe_on, monkeypatch):
        monkeypatch.setenv("AMLKIT_REGISTRATION_INVITE_CODE", "some-code")
        assert "reg-invite-code" not in raw_client.get("/register-organization").text
        resp = _self_serve_signup(raw_client)
        org = _org_by_name("Fresh Firm")
        assert (org["plan"], org["plan_status"]) == ("none", "pending_payment")
        assert org["trial_ends_at"] is None
        # Email verification lands MLRO on MFA enrolment first, otherwise /billing.
        assert resp.status_code == 303
        assert resp.headers["location"].startswith(("/billing", "/mfa/setup"))

    def test_with_stripe_registration_open_even_without_invite_secret(self, raw_client, stripe_on, monkeypatch):
        monkeypatch.delenv("AMLKIT_REGISTRATION_INVITE_CODE", raising=False)
        t = raw_client.get("/register-organization").text
        assert "Registration not available" not in t and "Start your free trial" in t


# -------------------------------------------------------- pending payment state
@pytest.fixture()
def pending(raw_client, stripe_on, monkeypatch):
    """A signed-in MLRO of a self-serve org that has not paid yet."""
    resp = _self_serve_signup(raw_client)
    from conftest import settle_mfa
    settle_mfa(raw_client)
    return raw_client


class TestPendingPayment:
    def test_billing_page_shows_pending_banner_and_checkout(self, pending):
        r = pending.get("/billing")
        assert r.status_code == 200
        assert "Add payment details to start your 14-day trial" in r.text
        assert "/billing/checkout" in r.text and "Start 14-day free trial" in r.text
        assert "No plan yet" in r.text

    def test_other_signed_in_pages_carry_the_banner(self, pending):
        assert "Add payment details to start your 14-day trial" in pending.get("/dashboard").text

    def test_check_limit_refuses_operator_and_customer_creation(self, pending):
        from amlkit.billing.limits import BillingLimitError, check_limit
        c = _db()
        oid = _org_by_name("Fresh Firm")["id"]
        for res in ("operators", "customers"):
            with pytest.raises(BillingLimitError, match="Add payment details on /billing to start your 14-day trial"):
                check_limit(c, oid, res)
        c.close()

    def test_customer_onboard_and_operator_create_are_refused_via_the_app(self, pending):
        oid = _org_by_name("Fresh Firm")["id"]
        r = pending.post("/customers", data={
            "reference": "P1", "full_name": "Pending Customer", "customer_type": "natural",
            "csrf_token": _csrf(pending)}, follow_redirects=True)
        assert "Add payment details on /billing to start your 14-day trial" in r.text
        r = pending.post("/admin/operators", data={
            "name": "Bob", "email": "bob@fresh.ae", "role": "officer",
            "password": "A-strong-password-2", "csrf_token": _csrf(pending)},
            follow_redirects=True)
        assert "Add payment details on /billing to start your 14-day trial" in r.text
        c = _db()
        assert c.execute("SELECT COUNT(*) FROM operators WHERE org_id=?", (oid,)).fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM customers WHERE org_id=?", (oid,)).fetchone()[0] == 0
        c.close()

    def test_reads_still_work(self, pending):
        for path in ("/dashboard", "/customers", "/screen", "/audit", "/reports", "/billing"):
            assert pending.get(path).status_code == 200, path

    def test_checkout_completed_webhook_clears_pending(self, pending):
        oid = _org_by_name("Fresh Firm")["id"]
        ev = {"id": "evt_co_1", "type": "checkout.session.completed", "created": int(time.time()),
              "data": {"object": {"id": "cs_1", "customer": "cus_9", "subscription": "sub_9",
                                  "client_reference_id": str(oid),
                                  "metadata": {"org_id": str(oid), "tier": "professional"}}}}
        assert _post_webhook(pending, ev).status_code == 200
        org = _org_by_name("Fresh Firm")
        assert (org["plan"], org["plan_status"]) == ("professional", "trialing")
        from amlkit.billing.limits import check_limit
        c = _db()
        check_limit(c, oid, "operators")  # allowed again
        c.close()

    def test_subscription_created_webhook_clears_pending(self, pending):
        oid = _org_by_name("Fresh Firm")["id"]
        ev = _sub_event("evt_sub_1", "customer.subscription.created", status="trialing",
                        price="price_starter_1", org_id=oid, trial_end=int(time.time()) + 14 * 86400)
        from amlkit.billing.stripe_client import load_config
        assert _post_webhook(pending, ev).status_code == 200
        org = _org_by_name("Fresh Firm")
        assert org["plan_status"] == "trialing" and org["plan"] in ("starter",)

    def test_legacy_org_is_unaffected_when_stripe_is_on(self, client, stripe_on):
        from amlkit.billing.limits import check_limit, org_state
        c = _db()
        oid = _org_by_name("Test Firm")["id"]
        st = org_state(c, oid)
        assert st.legacy and not st.pending_payment
        check_limit(c, oid, "operators")
        check_limit(c, oid, "customers")
        c.close()

    def test_non_stripe_org_created_in_stripe_mode_off_is_unlimited(self, client, stripe_on):
        # Registered by the fixture with an invite code while Stripe was off.
        org = _org_by_name("Test Firm")
        assert (org["plan"], org["plan_status"]) == ("trial", None)
