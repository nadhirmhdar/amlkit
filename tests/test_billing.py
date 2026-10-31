"""Stripe billing tests. No network: the Stripe client's httpx transport is
replaced by an httpx.MockTransport, and webhooks are signed locally with the
same HMAC scheme Stripe uses.

Manual end-to-end check (not run by this suite): set STRIPE_SECRET_KEY to a
test-mode key, STRIPE_PRICE_STARTER/PROFESSIONAL/CONSULTANT to test Price IDs,
run `stripe listen --forward-to localhost:8000/billing/webhook`, copy the
whsec_ it prints into STRIPE_WEBHOOK_SECRET, then use /billing. See CLAUDE.md,
"Billing (Stripe)".
"""

from __future__ import annotations

import dataclasses
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_api import _csrf, _db, _register, _seed_sanctions_data  # noqa: E402

WHSEC = "whsec_test_secret"
PRICES = {"starter": "price_starter_1", "professional": "price_pro_1", "consultant": "price_cons_1"}


def _iso(delta_days: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).isoformat(timespec="seconds")


@pytest.fixture()
def stripe_env(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WHSEC)
    for tier, pid in PRICES.items():
        monkeypatch.setenv(f"STRIPE_PRICE_{tier.upper()}", pid)
    monkeypatch.setenv("STRIPE_DISPLAY_PRICE_STARTER", "AED 111 / month")
    monkeypatch.setenv("STRIPE_DISPLAY_PRICE_PROFESSIONAL", "AED 222 / month")
    monkeypatch.setenv("STRIPE_DISPLAY_PRICE_CONSULTANT", "AED 333 / month")
    monkeypatch.setenv("AMLKIT_BILLING_PUBLIC_URL", "https://groaml.example")


@pytest.fixture()
def stripe_calls(monkeypatch):
    """Mock Stripe's API; returns the list of recorded requests."""
    from amlkit.billing import stripe_client

    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = parse_qs(request.content.decode()) if request.content else {}
        calls.append({"method": request.method, "path": request.url.path, "form": body,
                      "auth": request.headers.get("Authorization")})
        if request.url.path == "/v1/checkout/sessions":
            return httpx.Response(200, json={"id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1"})
        if request.url.path == "/v1/billing_portal/sessions":
            return httpx.Response(200, json={"id": "bps_1", "url": "https://billing.stripe.com/p/session/x"})
        if request.url.path.startswith("/v1/subscriptions/"):
            return httpx.Response(200, json={"id": request.url.path.rsplit("/", 1)[1], "status": "active"})
        return httpx.Response(404, json={"error": {"message": "nope"}})

    monkeypatch.setattr(stripe_client, "_TRANSPORT", httpx.MockTransport(handler))
    return calls


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    for k in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"):
        monkeypatch.delenv(k, raising=False)
    _seed_sanctions_data(db_file)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    c = TestClient(app)
    _register(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


def _org_id() -> int:
    c = _db()
    oid = c.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()["id"]
    c.close()
    return oid


def _org() -> dict:
    c = _db()
    row = dict(c.execute("SELECT * FROM organizations ORDER BY id LIMIT 1").fetchone())
    c.close()
    return row


def _set_org(**cols) -> None:
    c = _db()
    sets = ", ".join(f"{k}=?" for k in cols)
    c.execute(f"UPDATE organizations SET {sets} WHERE id=?", (*cols.values(), _org_id()))
    c.commit()
    c.close()


def _post_webhook(client, event: dict, *, secret: str = WHSEC, ts: int | None = None, sig: str | None = None):
    from amlkit.billing import stripe_client
    payload = json.dumps(event).encode()
    header = sig if sig is not None else stripe_client.sign_payload(payload, secret, ts)
    return client.post("/billing/webhook", content=payload,
                       headers={"Stripe-Signature": header, "Content-Type": "application/json"})


def _sub_event(eid, etype="customer.subscription.updated", *, status="active", price="price_pro_1",
               sub="sub_1", customer="cus_1", org_id=None, period_end=None, trial_end=None):
    return {
        "id": eid, "type": etype, "created": int(time.time()),
        "data": {"object": {
            "id": sub, "customer": customer, "status": status,
            "metadata": {"org_id": str(org_id)} if org_id else {},
            "current_period_end": period_end or int(time.time()) + 86400 * 30,
            "trial_end": trial_end,
            "items": {"data": [{"price": {"id": price}}]},
        }},
    }


def _billing_events() -> list[dict]:
    c = _db()
    rows = [dict(r) for r in c.execute("SELECT * FROM billing_events ORDER BY id")]
    c.close()
    return rows


def _audit_actions(prefix="billing.") -> list[str]:
    c = _db()
    rows = [r["action"] for r in c.execute("SELECT action FROM audit_log WHERE action LIKE ?", (prefix + "%",))]
    c.close()
    return rows


# ====================================================================== inert
class TestInertWhenUnconfigured:
    @pytest.mark.parametrize("path", ["/pricing", "/billing", "/billing/success", "/billing/cancel"])
    def test_get_routes_404(self, client, path):
        assert client.get(path).status_code == 404

    @pytest.mark.parametrize("path", ["/billing/checkout", "/billing/portal", "/billing/webhook"])
    def test_post_routes_404(self, client, path):
        r = client.post(path, data={"csrf_token": _csrf(client), "tier": "starter"})
        assert r.status_code == 404

    def test_no_nav_link_or_sitemap_entry(self, client):
        assert 'href="/billing"' not in client.get("/dashboard").text
        assert "/pricing" not in client.get("/sitemap.xml").text

    def test_check_limit_is_a_noop(self, client):
        from amlkit.billing.limits import check_limit
        _set_org(plan="starter", plan_status="canceled", current_period_end=_iso(-60))
        c = _db()
        check_limit(c, _org_id(), "operators")  # would raise if billing were on
        c.close()

    def test_apply_still_works(self, client):
        assert client.get("/apply").status_code == 200


class TestSchema:
    def test_columns_and_table(self, client):
        c = _db()
        cols = {r["name"] for r in c.execute("PRAGMA table_info(organizations)")}
        assert {"billing_customer_id", "billing_subscription_id", "plan", "plan_status",
                "trial_ends_at", "current_period_end"} <= cols
        ev = {r["name"] for r in c.execute("PRAGMA table_info(billing_events)")}
        assert {"id", "org_id", "stripe_event_id", "type", "payload", "received_at", "processed_at"} <= ev
        c.close()
        org = _org()
        assert org["plan"] == "trial" and org["trial_ends_at"] is None

    def test_migration_adds_columns_to_an_old_database(self, tmp_path):
        import sqlite3
        from amlkit.db import connect, _reset_init_cache
        path = tmp_path / "old.db"
        raw = sqlite3.connect(path)
        raw.execute("CREATE TABLE organizations (id INTEGER PRIMARY KEY, name TEXT NOT NULL,"
                    " slug TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL)")
        raw.execute("INSERT INTO organizations (name, slug, created_at) VALUES ('Old','old','2025-01-01')")
        raw.commit()
        raw.close()
        _reset_init_cache()
        conn = connect(path)
        row = conn.execute("SELECT plan, plan_status, trial_ends_at FROM organizations").fetchone()
        assert (row["plan"], row["plan_status"], row["trial_ends_at"]) == ("trial", None, None)
        conn.close()


# =================================================================== pricing
class TestPricing:
    def test_renders_three_tiers_with_env_prices_for_anonymous(self, client, stripe_env):
        client.cookies.clear()
        r = client.get("/pricing")
        assert r.status_code == 200
        for name in ("Starter", "Professional", "Consultant"):
            assert name in r.text
        assert "AED 111 / month" in r.text and "AED 333 / month" in r.text
        assert "/register-organization" in r.text and "/apply" in r.text
        assert "Grovisor Business Consultants FZE" not in r.text or "groAML" in r.text
        assert "/pricing" in client.get("/sitemap.xml").text

    def test_no_price_in_env_means_contact_us_not_a_made_up_figure(self, client, stripe_env, monkeypatch):
        monkeypatch.delenv("STRIPE_DISPLAY_PRICE_STARTER")
        r = client.get("/pricing")
        assert "Contact us" in r.text

    def test_plan_limits_are_data(self):
        from amlkit.billing.plans import PLANS
        assert (PLANS["starter"].max_workspaces, PLANS["starter"].max_operators, PLANS["starter"].max_customers) == (1, 3, 200)
        assert (PLANS["professional"].max_operators, PLANS["professional"].max_customers) == (10, 2000)
        assert (PLANS["consultant"].max_workspaces, PLANS["consultant"].max_operators, PLANS["consultant"].max_customers) == (20, 25, 10000)


# ================================================================ billing page
class TestBillingPage:
    def test_requires_session(self, client, stripe_env):
        client.cookies.clear()
        r = client.get("/billing", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"

    def test_mlro_sees_plan_usage_and_buttons(self, client, stripe_env):
        r = client.get("/billing")
        assert r.status_code == 200
        assert "Founding access" in r.text  # legacy org
        assert "unlimited" in r.text
        assert 'action="/billing/checkout"' in r.text
        assert 'href="/billing"' in client.get("/dashboard").text  # nav link when configured

    def test_subscribed_org_sees_limits_and_portal(self, client, stripe_env):
        _set_org(plan="starter", plan_status="active", billing_customer_id="cus_1",
                 billing_subscription_id="sub_1", current_period_end=_iso(20))
        r = client.get("/billing")
        assert "Starter" in r.text and "/ 3" in r.text and "/ 200" in r.text
        assert 'action="/billing/portal"' in r.text
        assert 'action="/billing/checkout"' not in r.text

    def test_officer_is_refused(self, client, stripe_env):
        from test_api import _add_operator, _login
        _add_operator(client, "bob", "bob@testfirm.ae", role="officer")
        client.post("/logout", data={"csrf_token": _csrf(client)})
        _login(client, "bob@testfirm.ae", "a-strong-password-2")
        r = client.get("/billing", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/dashboard"


# ==================================================================== checkout
class TestCheckout:
    def test_creates_session_and_redirects(self, client, stripe_env, stripe_calls):
        r = client.post("/billing/checkout", data={"tier": "professional", "csrf_token": _csrf(client)},
                        follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "https://checkout.stripe.com/c/pay/cs_test_1"
        (call,) = stripe_calls
        assert call["path"] == "/v1/checkout/sessions" and call["auth"] == "Bearer sk_test_123"
        f = call["form"]
        assert f["mode"] == ["subscription"]
        assert f["line_items[0][price]"] == ["price_pro_1"] and f["line_items[0][quantity]"] == ["1"]
        assert f["subscription_data[trial_period_days]"] == ["14"]
        assert f["client_reference_id"] == [str(_org_id())]
        assert f["subscription_data[metadata][org_id]"] == [str(_org_id())]
        assert f["customer_email"] == ["alice@testfirm.ae"]
        assert f["success_url"] == ["https://groaml.example/billing/success"]
        assert f["cancel_url"] == ["https://groaml.example/billing/cancel"]
        assert "billing.checkout_started" in _audit_actions()

    def test_returning_customer_gets_no_second_trial(self, client, stripe_env, stripe_calls):
        _set_org(billing_customer_id="cus_9", plan="starter", plan_status="canceled")
        client.post("/billing/checkout", data={"tier": "starter", "csrf_token": _csrf(client)})
        f = stripe_calls[0]["form"]
        assert f["customer"] == ["cus_9"] and "subscription_data[trial_period_days]" not in f
        assert "customer_email" not in f

    def test_csrf_required(self, client, stripe_env, stripe_calls):
        r = client.post("/billing/checkout", data={"tier": "starter", "csrf_token": "wrong"},
                        follow_redirects=False)
        assert r.status_code == 303 and "stripe.com" not in r.headers["location"]
        assert stripe_calls == []

    def test_unknown_or_unpriced_tier_refused(self, client, stripe_env, stripe_calls, monkeypatch):
        monkeypatch.delenv("STRIPE_PRICE_CONSULTANT")
        for tier in ("gold", "consultant", ""):
            r = client.post("/billing/checkout", data={"tier": tier, "csrf_token": _csrf(client)},
                            follow_redirects=False)
            assert r.headers["location"] == "/billing"
        assert stripe_calls == []

    def test_live_subscription_cannot_start_a_second_one(self, client, stripe_env, stripe_calls):
        _set_org(plan="starter", plan_status="active", billing_subscription_id="sub_1", billing_customer_id="cus_1")
        r = client.post("/billing/checkout", data={"tier": "professional", "csrf_token": _csrf(client)},
                        follow_redirects=False)
        assert r.headers["location"] == "/billing" and stripe_calls == []

    def test_stripe_failure_is_a_friendly_error(self, client, stripe_env, monkeypatch):
        from amlkit.billing import stripe_client
        monkeypatch.setattr(stripe_client, "_TRANSPORT", httpx.MockTransport(
            lambda req: httpx.Response(500, json={"error": {"message": "boom"}})))
        r = client.post("/billing/checkout", data={"tier": "starter", "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert r.status_code == 200 and "Could not start checkout" in r.text

    def test_success_and_cancel_pages(self, client, stripe_env):
        assert "being activated" in client.get("/billing/success", follow_redirects=True).text
        assert "cancelled" in client.get("/billing/cancel", follow_redirects=True).text


class TestPortal:
    def test_no_customer_yet(self, client, stripe_env, stripe_calls):
        r = client.post("/billing/portal", data={"csrf_token": _csrf(client)}, follow_redirects=True)
        assert "no billing account" in r.text and stripe_calls == []

    def test_redirects_to_portal(self, client, stripe_env, stripe_calls):
        _set_org(billing_customer_id="cus_1")
        r = client.post("/billing/portal", data={"csrf_token": _csrf(client)}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("https://billing.stripe.com/")
        f = stripe_calls[0]["form"]
        assert f["customer"] == ["cus_1"] and f["return_url"] == ["https://groaml.example/billing"]

    def test_csrf_required(self, client, stripe_env, stripe_calls):
        _set_org(billing_customer_id="cus_1")
        client.post("/billing/portal", data={"csrf_token": "bad"})
        assert stripe_calls == []


# ============================================================ signature (unit)
class TestSignature:
    def test_valid_tampered_stale_and_rotated(self):
        from amlkit.billing.stripe_client import SignatureError, sign_payload, verify_webhook_signature as v
        body = b'{"id":"evt_1","type":"x"}'
        now = 1_700_000_000
        good = sign_payload(body, WHSEC, now)
        v(body, good, WHSEC, now=now + 10)
        with pytest.raises(SignatureError):
            v(body + b" ", good, WHSEC, now=now)
        with pytest.raises(SignatureError):
            v(body, good, "whsec_other", now=now)
        with pytest.raises(SignatureError, match="tolerance"):
            v(body, good, WHSEC, now=now + 301)
        v(body, good, WHSEC, now=now + 300)
        # two v1 entries (secret roll): any match suffices
        rotated = good + ",v1=" + "0" * 64
        v(body, rotated, WHSEC, now=now)
        for bad in (None, "", "garbage", "t=abc,v1=ff", f"t={now}"):
            with pytest.raises(SignatureError):
                v(body, bad, WHSEC, now=now)


# ==================================================================== webhook
class TestWebhook:
    def test_bad_signature_400(self, client, stripe_env):
        ev = _sub_event("evt_bad", org_id=_org_id())
        assert _post_webhook(client, ev, sig="t=1,v1=deadbeef").status_code == 400
        assert _post_webhook(client, ev, secret="whsec_wrong").status_code == 400
        assert _post_webhook(client, ev, ts=int(time.time()) - 3600).status_code == 400
        assert client.post("/billing/webhook", content=b"{}").status_code == 400
        assert _billing_events() == [] and _org()["plan"] == "trial"

    def test_no_session_or_csrf_needed(self, client, stripe_env):
        client.cookies.clear()
        assert _post_webhook(client, {"id": "evt_x", "type": "ping", "data": {"object": {}}}).status_code == 200

    def test_missing_webhook_secret_is_503(self, client, stripe_env, monkeypatch):
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET")
        assert _post_webhook(client, {"id": "e", "type": "t"}).status_code == 503

    def test_checkout_completed_links_org(self, client, stripe_env):
        ev = {"id": "evt_co", "type": "checkout.session.completed", "created": int(time.time()),
              "data": {"object": {"id": "cs_1", "customer": "cus_77", "subscription": "sub_77",
                                  "client_reference_id": str(_org_id()), "metadata": {}}}}
        r = _post_webhook(client, ev)
        assert r.status_code == 200 and r.json() == {"status": "processed"}
        org = _org()
        assert (org["billing_customer_id"], org["billing_subscription_id"]) == ("cus_77", "sub_77")
        (row,) = _billing_events()
        assert row["org_id"] == org["id"] and row["processed_at"]
        assert "billing.checkout_completed" in _audit_actions()

    def test_subscription_maps_price_to_plan_and_status(self, client, stripe_env):
        trial_end = int(time.time()) + 14 * 86400
        ev = _sub_event("evt_s1", "customer.subscription.created", status="trialing",
                        price="price_cons_1", org_id=_org_id(), trial_end=trial_end)
        assert _post_webhook(client, ev).status_code == 200
        org = _org()
        assert org["plan"] == "consultant" and org["plan_status"] == "trialing"
        assert org["billing_subscription_id"] == "sub_1" and org["billing_customer_id"] == "cus_1"
        assert org["trial_ends_at"] and org["current_period_end"]
        # later update found by stored customer id, no metadata needed
        assert _post_webhook(client, _sub_event("evt_s2", status="active", price="price_starter_1")).status_code == 200
        org = _org()
        assert org["plan"] == "starter" and org["plan_status"] == "active"
        assert _audit_actions().count("billing.subscription_sync") == 2

    def test_status_mapping(self, client, stripe_env):
        for i, (stripe_status, expected) in enumerate([
            ("past_due", "past_due"), ("unpaid", "unpaid"), ("incomplete", "past_due"),
            ("incomplete_expired", "canceled"), ("paused", "unpaid"), ("trialing", "trialing")]):
            _post_webhook(client, _sub_event(f"evt_m{i}", status=stripe_status, org_id=_org_id()))
            assert _org()["plan_status"] == expected, stripe_status

    def test_unknown_price_keeps_existing_plan(self, client, stripe_env):
        _set_org(plan="professional", plan_status="active")
        _post_webhook(client, _sub_event("evt_u", price="price_mystery", org_id=_org_id()))
        assert _org()["plan"] == "professional"

    def test_period_end_on_items_new_api_shape(self, client, stripe_env):
        ev = _sub_event("evt_n", org_id=_org_id())
        obj = ev["data"]["object"]
        obj["items"]["data"][0]["current_period_end"] = 1_900_000_000
        del obj["current_period_end"]
        _post_webhook(client, ev)
        assert _org()["current_period_end"].startswith("2030-")

    def test_replay_is_acked_but_not_reprocessed(self, client, stripe_env):
        ev = _sub_event("evt_dup", status="active", org_id=_org_id())
        assert _post_webhook(client, ev).json() == {"status": "processed"}
        _set_org(plan_status="past_due")  # something else changed it since
        r = _post_webhook(client, ev)
        assert r.status_code == 200 and r.json() == {"status": "duplicate"}
        assert _org()["plan_status"] == "past_due"  # the replay did not overwrite it
        assert len(_billing_events()) == 1
        assert _audit_actions().count("billing.subscription_sync") == 1

    def test_failed_processing_is_retried_on_redelivery(self, client, stripe_env, monkeypatch):
        from amlkit.billing import service
        ev = _sub_event("evt_retry", org_id=_org_id())
        real = service._process
        monkeypatch.setattr(service, "_process", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db")))
        assert _post_webhook(client, ev).status_code == 500
        monkeypatch.setattr(service, "_process", real)
        assert _post_webhook(client, ev).json() == {"status": "processed"}
        assert _org()["plan_status"] == "active"

    def test_unknown_event_type_stored_and_acked(self, client, stripe_env):
        ev = {"id": "evt_odd", "type": "charge.dispute.created", "data": {"object": {"id": "dp_1"}}}
        r = _post_webhook(client, ev)
        assert r.status_code == 200 and r.json() == {"status": "stored"}
        (row,) = _billing_events()
        assert row["type"] == "charge.dispute.created" and row["org_id"] is None
        assert json.loads(row["payload"])["id"] == "evt_odd"

    def test_event_for_unknown_org_stored_and_acked(self, client, stripe_env):
        r = _post_webhook(client, _sub_event("evt_ghost", org_id=99999, customer="cus_nobody", sub="sub_nobody"))
        assert r.status_code == 200 and r.json() == {"status": "stored"}
        assert _org()["plan"] == "trial"

    def test_payment_failed_then_paid(self, client, stripe_env):
        _set_org(plan="starter", plan_status="active", billing_customer_id="cus_1", billing_subscription_id="sub_1")
        failed = {"id": "evt_f", "type": "invoice.payment_failed", "created": int(time.time()),
                  "data": {"object": {"id": "in_1", "customer": "cus_1", "subscription": "sub_1"}}}
        _post_webhook(client, failed)
        org = _org()
        assert org["plan_status"] == "past_due" and org["current_period_end"]
        paid = {**failed, "id": "evt_p", "type": "invoice.paid"}
        _post_webhook(client, paid)
        assert _org()["plan_status"] == "active"
        assert {"billing.payment_failed", "billing.payment_recovered"} <= set(_audit_actions())

    def test_zero_dollar_trial_invoice_does_not_activate_a_trial(self, client, stripe_env):
        _set_org(plan="starter", plan_status="trialing", billing_customer_id="cus_1")
        _post_webhook(client, {"id": "evt_t", "type": "invoice.paid", "created": 1,
                               "data": {"object": {"id": "in_0", "customer": "cus_1"}}})
        assert _org()["plan_status"] == "trialing"

    def test_deleted_cancels_and_stale_subscription_ignored(self, client, stripe_env):
        _set_org(plan="professional", plan_status="active", billing_customer_id="cus_1",
                 billing_subscription_id="sub_new")
        # an OLD subscription ending must not cancel the live one
        _post_webhook(client, _sub_event("evt_old", "customer.subscription.deleted", sub="sub_old"))
        assert _org()["plan_status"] == "active"
        _post_webhook(client, _sub_event("evt_del", "customer.subscription.deleted", sub="sub_new",
                                         status="active"))
        org = _org()
        assert org["plan_status"] == "canceled" and org["plan"] == "professional"

    def test_every_write_is_audited_with_org_id(self, client, stripe_env):
        _post_webhook(client, _sub_event("evt_a", org_id=_org_id()))
        c = _db()
        rows = c.execute("SELECT org_id FROM audit_log WHERE action LIKE 'billing.%'").fetchall()
        c.close()
        assert rows and all(r["org_id"] == _org_id() for r in rows)


# ============================================================= enforcement
class TestOperatorLimit:
    def _create(self, client, n):
        return client.post("/admin/operators", data={
            "name": f"op{n}", "email": f"op{n}@testfirm.ae", "password": "a-strong-password-2",
            "role": "officer", "csrf_token": _csrf(client)}, follow_redirects=True)

    def _operators(self):
        c = _db()
        n = c.execute("SELECT COUNT(*) FROM operators WHERE is_active=1").fetchone()[0]
        c.close()
        return n

    def test_refused_at_cap_with_pointer_to_billing(self, client, stripe_env):
        _set_org(plan="starter", plan_status="active", current_period_end=_iso(20))
        assert "created" in self._create(client, 1).text   # alice + op1 = 2
        assert "created" in self._create(client, 2).text   # = 3 (cap)
        r = self._create(client, 3)
        assert "allows up to 3 operators" in r.text and "/billing" in r.text
        assert self._operators() == 3

    def test_higher_tier_allows_more(self, client, stripe_env):
        _set_org(plan="professional", plan_status="active", current_period_end=_iso(20))
        for n in range(1, 5):
            assert "created" in self._create(client, n).text
        assert self._operators() == 5

    def test_legacy_org_is_unlimited_even_with_billing_on(self, client, stripe_env):
        for n in range(1, 6):
            assert "created" in self._create(client, n).text
        assert self._operators() == 6

    def test_reactivation_cannot_bypass_the_cap(self, client, stripe_env):
        self._create(client, 1)
        c = _db()
        op = c.execute("SELECT id FROM operators WHERE name='op1'").fetchone()["id"]
        c.close()
        client.post(f"/admin/operators/{op}/deactivate", data={"csrf_token": _csrf(client)})
        self._create(client, 2)
        self._create(client, 3)  # alice + op2 + op3
        _set_org(plan="starter", plan_status="active", current_period_end=_iso(20))
        r = client.post(f"/admin/operators/{op}/reactivate", data={"csrf_token": _csrf(client)}, follow_redirects=True)
        assert "allows up to 3 operators" in r.text

    def test_mobile_api_returns_402(self, client, stripe_env):
        _set_org(plan="starter", plan_status="active", current_period_end=_iso(20))
        self._create(client, 1)
        self._create(client, 2)
        login = client.post("/api/v1/auth/login", json={"email": "alice@testfirm.ae", "password": "a-strong-password-1"})
        assert login.status_code == 200, login.text
        token = login.json()["token"]
        from conftest import unlock_mobile_mfa  # p15: an MLRO's token starts MFA-locked
        unlock_mobile_mfa(client, token)
        h = {"Authorization": f"Bearer {token}"}
        r = client.post("/api/v1/admin/operators", headers=h, json={
            "name": "x", "email": "x@testfirm.ae", "password": "a-strong-password-2"})
        assert r.status_code == 402 and "/billing" in r.json()["detail"]


class TestCustomerLimit:
    def _onboard(self, ref):
        from amlkit.cases.manager import onboard
        c = _db()  # the client fixture already seeded a fresh sanctions dataset
        try:
            return onboard(c, org_id=_org_id(), reference=ref, full_name=f"Customer {ref}")
        finally:
            c.close()

    def test_refused_at_cap_before_anything_is_written(self, client, stripe_env, monkeypatch):
        from amlkit.billing import limits, plans
        from amlkit.billing.limits import BillingLimitError
        tiny = dataclasses.replace(plans.PLANS["starter"], max_customers=2)
        monkeypatch.setitem(plans.PLANS, "starter", tiny)
        monkeypatch.setitem(limits.PLANS, "starter", tiny)
        _set_org(plan="starter", plan_status="active", current_period_end=_iso(20))
        self._onboard("C1")
        self._onboard("C2")
        with pytest.raises(BillingLimitError, match="2 customers"):
            self._onboard("C3")
        c = _db()
        assert c.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 2
        c.close()

    def test_closed_customers_do_not_count(self, client, stripe_env, monkeypatch):
        from amlkit.billing import limits
        _set_org(plan="starter", plan_status="active")
        self._onboard("C1")
        c = _db()
        assert limits.usage(c, _org_id())["customers"] == 1
        c.execute("UPDATE customers SET status='closed'")
        c.commit()
        assert limits.usage(c, _org_id())["customers"] == 0
        c.close()

    def test_web_form_shows_the_message(self, client, stripe_env, monkeypatch):
        from amlkit.billing import limits, plans
        tiny = dataclasses.replace(plans.PLANS["starter"], max_customers=0)
        monkeypatch.setitem(plans.PLANS, "starter", tiny)
        monkeypatch.setitem(limits.PLANS, "starter", tiny)
        _set_org(plan="starter", plan_status="active")
        r = client.post("/customers", data={
            "reference": "W1", "full_name": "Web Customer", "customer_type": "natural",
            "csrf_token": _csrf(client)}, follow_redirects=True)
        assert "allows up to 0 customers" in r.text and "/billing" in r.text


class TestGraceAndReadOnly:
    @pytest.mark.parametrize("status", ["past_due", "unpaid", "canceled"])
    def test_writes_allowed_inside_grace_refused_after(self, client, stripe_env, status):
        from amlkit.billing.limits import BillingLimitError, check_limit
        c = _db()
        _set_org(plan="professional", plan_status=status, current_period_end=_iso(-3))
        check_limit(c, _org_id(), "operators")  # day 3 of 7: still allowed
        _set_org(plan="professional", plan_status=status, current_period_end=_iso(-8))
        with pytest.raises(BillingLimitError, match="read-only.*grace"):
            check_limit(c, _org_id(), "operators")
        with pytest.raises(BillingLimitError, match="/billing"):
            check_limit(c, _org_id(), "customers")
        c.close()

    def test_active_and_trialing_never_blocked(self, client, stripe_env):
        from amlkit.billing.limits import check_limit
        c = _db()
        for st in ("active", "trialing"):
            _set_org(plan="starter", plan_status=st, current_period_end=_iso(-90))
            check_limit(c, _org_id(), "operators")
        c.close()

    def test_unknown_period_end_fails_open(self, client, stripe_env):
        from amlkit.billing.limits import check_limit
        _set_org(plan="starter", plan_status="past_due", current_period_end=None)
        c = _db()
        check_limit(c, _org_id(), "operators")
        c.close()

    def test_reads_always_work_when_blocked(self, client, stripe_env):
        _set_org(plan="starter", plan_status="canceled", current_period_end=_iso(-60))
        for path in ("/dashboard", "/customers", "/screen", "/reports", "/audit", "/admin", "/billing"):
            assert client.get(path).status_code == 200, path
        # and new operators are refused with the clear message
        r = client.post("/admin/operators", data={
            "name": "late", "email": "late@testfirm.ae", "password": "a-strong-password-2",
            "role": "officer", "csrf_token": _csrf(client)}, follow_redirects=True)
        assert "read-only" in r.text and "/billing" in r.text

    def test_billing_page_explains_read_only(self, client, stripe_env):
        _set_org(plan="starter", plan_status="past_due", current_period_end=_iso(-30))
        assert "read-only" in client.get("/billing").text

    def test_expired_dated_trial_uses_starter_limits_then_blocks(self, client, stripe_env):
        from amlkit.billing.limits import org_state
        _set_org(plan="trial", trial_ends_at=_iso(5))
        c = _db()
        st = org_state(c, _org_id())
        assert st.plan.key == "starter" and not st.write_blocked
        _set_org(plan="trial", trial_ends_at=_iso(-8))
        assert org_state(c, _org_id()).write_blocked
        c.close()

    def test_workspaces_reported_but_single(self, client, stripe_env):
        from amlkit.billing.limits import check_limit, usage
        c = _db()
        assert usage(c, _org_id())["workspaces"] == 1
        _set_org(plan="starter", plan_status="active")
        with pytest.raises(Exception):  # Starter allows 1 workspace and 1 is used
            check_limit(c, _org_id(), "workspaces")
        c.close()
