"""Billing master switch: Stripe is OFF by default, even with the keys present.

`AMLKIT_BILLING_ENABLED` has to be set (1/true/yes/on) for any billing to run.
Without it the whole feature is inert exactly as if STRIPE_SECRET_KEY were
unset: the routes 404, no nav link, no limit enforcement, and public sign-up
falls back to the quote-led /apply flow. The rest of the suite switches it on
(see conftest) because it tests the Stripe-configured behaviour.
"""
from __future__ import annotations

import pytest

from conftest import register_org


def _stripe_keys(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    for t in ("STARTER", "PROFESSIONAL"):
        monkeypatch.setenv(f"STRIPE_PRICE_{t}", f"price_{t.lower()}_1")
    monkeypatch.setenv("STRIPE_DISPLAY_PRICE_STARTER", "AED 111 / year")


@pytest.fixture()
def switch_off(monkeypatch):
    """The production default: Stripe keys present, master switch not set."""
    monkeypatch.delenv("AMLKIT_BILLING_ENABLED", raising=False)
    _stripe_keys(monkeypatch)


@pytest.fixture()
def mlro(tmp_path, monkeypatch, switch_off):
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "t.db"))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    c = TestClient(app)
    register_org(c, "Switch Firm", "switch_mlro", "mlro@switch.ae")
    return c


@pytest.mark.parametrize("value", ["1", "true", "TRUE", " yes ", "on"])
def test_switch_values_that_turn_billing_on(monkeypatch, value):
    _stripe_keys(monkeypatch)
    monkeypatch.setenv("AMLKIT_BILLING_ENABLED", value)
    from amlkit.billing import self_serve_enabled, stripe_client
    assert stripe_client.load_config() is not None
    assert self_serve_enabled() is True


@pytest.mark.parametrize("value", [None, "", "0", "false", "no", "off", "enabled", "2"])
def test_anything_else_leaves_billing_off(monkeypatch, value):
    _stripe_keys(monkeypatch)
    if value is None:
        monkeypatch.delenv("AMLKIT_BILLING_ENABLED", raising=False)
    else:
        monkeypatch.setenv("AMLKIT_BILLING_ENABLED", value)
    from amlkit.billing import self_serve_enabled, stripe_client
    assert stripe_client.load_config() is None
    assert self_serve_enabled() is False


def test_switch_on_without_a_stripe_key_is_still_off(monkeypatch):
    monkeypatch.setenv("AMLKIT_BILLING_ENABLED", "1")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    from amlkit.billing import stripe_client
    assert stripe_client.load_config() is None


def test_billing_routes_404_and_no_nav_link_with_the_switch_off(mlro):
    for path in ("/billing", "/billing/success", "/billing/cancel"):
        assert mlro.get(path).status_code == 404, path
    assert mlro.post("/billing/webhook", content=b"{}").status_code == 404
    html = mlro.get("/dashboard").text
    assert 'href="/billing"' not in html


def test_public_pages_fall_back_to_the_quote_flow(mlro, switch_off):
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    anon = TestClient(app)
    landing = anon.get("/").text
    assert "Request access" in landing and 'href="/apply"' in landing
    assert "Start free trial" not in landing
    pricing = anon.get("/pricing").text
    # No payment CTA or Stripe wording. The plan prices themselves are separate display text
    # (STRIPE_DISPLAY_PRICE_*), so they still show; only the way to buy is the quote request.
    assert "Stripe" not in pricing and "Start free trial" not in pricing
    assert "Request access" in pricing and 'href="/apply"' in pricing
    # open self-serve sign-up is closed: the invite code is required again
    assert 'name="invite_code"' in anon.get("/register-organization").text


def test_limits_are_not_enforced_with_the_switch_off(mlro, switch_off):
    """A pending-payment org is not blocked or sent to a /billing that 404s."""
    import os
    import sqlite3

    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    conn.execute("UPDATE organizations SET plan='none', plan_status='pending_payment'")
    conn.commit()
    org_id = conn.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()["id"]
    from amlkit.billing import limits
    for resource in ("operators", "customers"):
        limits.check_limit(conn, org_id, resource)   # no BillingLimitError
    limits.check_scan_allowed(conn, org_id)           # no BillingLimitError
    conn.close()


def test_turning_the_switch_on_restores_billing(mlro, monkeypatch):
    monkeypatch.setenv("AMLKIT_BILLING_ENABLED", "1")
    assert mlro.get("/billing").status_code == 200


def test_deploy_workflow_passes_the_switch_through():
    """--set-env-vars replaces the whole Cloud Run list, so the switch has to be named
    in it, fed from a repo variable (unset = off)."""
    from pathlib import Path
    wf = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "source-canary.yml").read_text()
    assert "AMLKIT_BILLING_ENABLED: ${{ vars.AMLKIT_BILLING_ENABLED }}" in wf
    assert "AMLKIT_BILLING_ENABLED=${AMLKIT_BILLING_ENABLED}" in wf
