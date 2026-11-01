"""Billing routes (Stripe). Every route 404s unless STRIPE_SECRET_KEY is set.

Session-gated and CSRF-protected, except /billing/webhook (authenticated by
Stripe's signature instead) and the public /pricing page.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import mail
from ..billing import limits, plans, service, stripe_client
from ..db import audit
from .deps import (
    client_ip, current_session, get_db, require_csrf, require_role, require_session,
)
from .limits import limiter

log = logging.getLogger("amlkit.billing")
router = APIRouter()
DB = Annotated[sqlite3.Connection, Depends(get_db)]

LIVE_STATUSES = ("trialing", "active", "past_due")


def _not_found() -> HTMLResponse:
    return HTMLResponse("Not found", status_code=404)


def _app():
    # Imported lazily: app.py includes this router, so a top-level import
    # would be circular.
    from . import app as app_module
    return app_module


def _public_base(request: Request) -> str:
    configured = os.environ.get("AMLKIT_BILLING_PUBLIC_URL", "").strip()
    return (configured or str(request.base_url)).rstrip("/")


def _is_stripe_url(url: str) -> bool:
    u = urlparse(url)
    return u.scheme == "https" and (u.hostname or "").endswith(".stripe.com")


async def _raw_body(request: Request) -> bytes:
    return await request.body()


def _mlro(request: Request, db: sqlite3.Connection, csrf_token: str | None = None):
    """(session, None) or (None, response). MLRO only; CSRF when a token is given."""
    try:
        session = require_session(request, db)
        if csrf_token is not None:
            require_csrf(request, csrf_token)
        require_role(session, "mlro")
    except PermissionError as exc:
        if current_session(request, db) is None:
            return None, RedirectResponse("/login", status_code=303)
        return None, _app().back("/dashboard", err=str(exc))
    return session, None


def _org(db: sqlite3.Connection, org_id: int) -> sqlite3.Row:
    return db.execute("SELECT * FROM organizations WHERE id=?", (org_id,)).fetchone()


def _plan_cards(config: stripe_client.StripeConfig) -> list[dict]:
    return [
        {"plan": plans.PLANS[t], "price": plans.display_price(t),
         "offered": config.price_for(t) is not None}
        for t in plans.TIERS
    ]


# ------------------------------------------------------------------- public
@router.get("/pricing", response_class=HTMLResponse)
def pricing(request: Request, db: DB):
    config = stripe_client.load_config()
    if config is None:
        return _not_found()
    return _app().render(request, "pricing.html", {
        "cards": _plan_cards(config), "trial_days": plans.TRIAL_DAYS,
    }, db)


# ------------------------------------------------------------------ account
@router.get("/billing", response_class=HTMLResponse)
def billing_page(request: Request, db: DB):
    config = stripe_client.load_config()
    if config is None:
        return _not_found()
    session, resp = _mlro(request, db)
    if resp:
        return resp
    org = _org(db, session.org_id)
    state = limits.org_state(db, session.org_id)
    has_live = bool(org["billing_subscription_id"]) and org["plan_status"] in LIVE_STATUSES
    return _app().render(request, "billing.html", {
        "session": session, "org": org, "state": state, "cards": _plan_cards(config),
        "has_live_subscription": has_live, "has_customer": bool(org["billing_customer_id"]),
        "trial_days": plans.TRIAL_DAYS, "grace_days": plans.GRACE_DAYS,
        "current_plan": plans.get_plan(org["plan"]),
        "resources": [("Operators", "operators"), ("Customers", "customers"),
                      ("Client workspaces", "workspaces")],
        "history": limits.monthly_history(db, session.org_id),
    }, db)


@router.post("/billing/checkout")
@limiter.limit("10/minute")
def billing_checkout(request: Request, db: DB, tier: Annotated[str, Form()] = "",
                     csrf_token: Annotated[str, Form()] = ""):
    config = stripe_client.load_config()
    if config is None:
        return _not_found()
    session, resp = _mlro(request, db, csrf_token)
    if resp:
        return resp
    back = _app().back
    price_id = config.price_for(tier) if tier in plans.PLANS else None
    if price_id is None:
        return back("/billing", err="That plan is not available.")
    org = _org(db, session.org_id)
    if org["billing_subscription_id"] and org["plan_status"] in LIVE_STATUSES:
        # A second Checkout would create a second, parallel subscription.
        return back("/billing", err="This organisation already has a subscription. "
                    "Use Manage billing to change plan.")
    first_time = not (org["billing_subscription_id"] or org["billing_customer_id"])
    base = _public_base(request)
    try:
        cs = stripe_client.create_checkout_session(
            config, price_id=price_id, org_id=session.org_id, tier=tier,
            success_url=f"{base}/billing/success", cancel_url=f"{base}/billing/cancel",
            customer_id=org["billing_customer_id"],
            customer_email=None if org["billing_customer_id"] else session.email,
            trial_days=plans.TRIAL_DAYS if first_time else None,
        )
    except stripe_client.StripeError as exc:
        log.warning("checkout failed for org %s: %s", session.org_id, exc)
        return back("/billing", err="Could not start checkout. Please try again shortly.")
    if not _is_stripe_url(cs["url"]):
        log.error("unexpected checkout url host for org %s", session.org_id)
        return back("/billing", err="Could not start checkout. Please try again shortly.")
    audit(db, session.operator_name, "billing.checkout_started", "organization",
          session.org_id, {"tier": tier, "stripe_session": cs.get("id")}, org_id=session.org_id)
    db.commit()
    return RedirectResponse(cs["url"], status_code=303)


@router.get("/billing/success")
def billing_success(request: Request, db: DB):
    if stripe_client.load_config() is None:
        return _not_found()
    session, resp = _mlro(request, db)
    if resp:
        return resp
    return _app().back("/billing", msg="Thank you. Your subscription is being activated; "
                       "this page updates as soon as Stripe confirms it.")


@router.get("/billing/cancel")
def billing_cancel(request: Request, db: DB):
    if stripe_client.load_config() is None:
        return _not_found()
    session, resp = _mlro(request, db)
    if resp:
        return resp
    return _app().back("/billing", msg="Checkout was cancelled. Nothing was charged.")


@router.post("/billing/portal")
@limiter.limit("10/minute")
def billing_portal(request: Request, db: DB, csrf_token: Annotated[str, Form()] = ""):
    config = stripe_client.load_config()
    if config is None:
        return _not_found()
    session, resp = _mlro(request, db, csrf_token)
    if resp:
        return resp
    back = _app().back
    org = _org(db, session.org_id)
    if not org["billing_customer_id"]:
        return back("/billing", err="There is no billing account yet. Choose a plan first.")
    try:
        ps = stripe_client.create_portal_session(
            config, customer_id=org["billing_customer_id"],
            return_url=f"{_public_base(request)}/billing")
    except stripe_client.StripeError as exc:
        log.warning("portal failed for org %s: %s", session.org_id, exc)
        return back("/billing", err="Could not open the billing portal. Please try again shortly.")
    if not _is_stripe_url(ps["url"]):
        return back("/billing", err="Could not open the billing portal. Please try again shortly.")
    audit(db, session.operator_name, "billing.portal_opened", "organization",
          session.org_id, None, org_id=session.org_id)
    db.commit()
    return RedirectResponse(ps["url"], status_code=303)


# ------------------------------------------------------------------ webhook
@router.post("/billing/webhook")
@limiter.limit("120/minute")
def billing_webhook(request: Request, db: DB, payload: Annotated[bytes, Depends(_raw_body)]):
    config = stripe_client.load_config()
    if config is None:
        return _not_found()
    if not config.webhook_secret:
        return JSONResponse({"error": "webhook secret not configured"}, status_code=503)
    try:
        event = stripe_client.construct_event(
            payload, request.headers.get("Stripe-Signature"), config.webhook_secret)
    except stripe_client.SignatureError as exc:
        log.warning("rejected billing webhook from %s: %s", client_ip(request), exc)
        return JSONResponse({"error": "invalid signature"}, status_code=400)
    try:
        outcome = service.handle_event(db, event, config)
    except Exception:
        log.exception("billing event %s failed", event.get("id"))
        return JSONResponse({"error": "processing failed"}, status_code=500)  # Stripe retries
    return JSONResponse({"status": outcome})
