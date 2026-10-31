"""Thin Stripe REST client over httpx (deliberately not the `stripe` SDK).

Pure functions plus config loading: no database access, no FastAPI imports.
Routes in `api/billing.py` call in here; `billing/service.py` owns the DB.

Inert unless STRIPE_SECRET_KEY is set: `load_config()` returns None and the
whole billing feature (routes, pricing page, nav link) stays switched off.

Env:
  STRIPE_SECRET_KEY            API key (sk_...). Unset => billing disabled.
  STRIPE_WEBHOOK_SECRET        Signing secret (whsec_...) for /billing/webhook.
  STRIPE_PRICE_<TIER>          Stripe Price ID per tier (STARTER, PROFESSIONAL,
                               CONSULTANT). A tier without one is not offered.
  AMLKIT_BILLING_PUBLIC_URL    Base URL for success/cancel/return links.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

API_BASE = "https://api.stripe.com/v1"
SIGNATURE_TOLERANCE_SECONDS = 300
_TIMEOUT = 30

# Tests point this at an httpx.MockTransport so no request leaves the process.
_TRANSPORT: httpx.BaseTransport | None = None


class StripeError(Exception):
    """A Stripe call failed (transport error, non-2xx, or malformed reply)."""


class SignatureError(Exception):
    """A webhook's Stripe-Signature header did not verify."""


@dataclass(frozen=True, slots=True)
class StripeConfig:
    secret_key: str
    webhook_secret: str = ""
    prices: dict[str, str] = field(default_factory=dict)  # tier -> price id

    def price_for(self, tier: str) -> str | None:
        return self.prices.get(tier) or None

    def tier_for_price(self, price_id: str | None) -> str | None:
        for tier, pid in self.prices.items():
            if price_id and pid == price_id:
                return tier
        return None


def load_config() -> StripeConfig | None:
    from .plans import TIERS

    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key:
        return None
    prices = {}
    for tier in TIERS:
        pid = os.environ.get(f"STRIPE_PRICE_{tier.upper()}", "").strip()
        if pid:
            prices[tier] = pid
    return StripeConfig(
        secret_key=key,
        webhook_secret=os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip(),
        prices=prices,
    )


# ------------------------------------------------------------------ requests
def _flatten(params: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    """Stripe's form encoding: nested dicts/lists become a[b][0][c]=v."""
    out: list[tuple[str, str]] = []
    for k, v in params.items():
        name = f"{prefix}[{k}]" if prefix else str(k)
        if v is None:
            continue
        if isinstance(v, dict):
            out.extend(_flatten(v, name))
        elif isinstance(v, (list, tuple)):
            out.extend(_flatten({str(i): x for i, x in enumerate(v)}, name))
        elif isinstance(v, bool):
            out.append((name, "true" if v else "false"))
        else:
            out.append((name, str(v)))
    return out


def _request(config: StripeConfig, method: str, path: str,
             params: dict[str, Any] | None = None,
             idempotency_key: str | None = None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {config.secret_key}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        with httpx.Client(transport=_TRANSPORT, timeout=_TIMEOUT) as client:
            r = client.request(
                method, API_BASE + path, headers=headers,
                data=dict(_flatten(params)) if params and method != "GET" else None,
            )
    except httpx.HTTPError as exc:
        raise StripeError(f"Stripe request failed: {exc.__class__.__name__}") from exc
    try:
        body = r.json()
    except ValueError as exc:
        raise StripeError(f"Stripe returned non-JSON (HTTP {r.status_code})") from exc
    if r.status_code >= 400:
        msg = (body.get("error") or {}).get("message") if isinstance(body, dict) else None
        raise StripeError(f"Stripe error (HTTP {r.status_code}): {msg or 'unknown error'}")
    if not isinstance(body, dict):
        raise StripeError("Stripe returned an unexpected response")
    return body


def create_checkout_session(
    config: StripeConfig, *, price_id: str, success_url: str, cancel_url: str,
    org_id: int, tier: str, customer_id: str | None = None,
    customer_email: str | None = None, trial_days: int | None = None,
) -> dict[str, Any]:
    """Checkout Session in subscription mode. The org id travels in
    client_reference_id and in both session and subscription metadata, so the
    webhook can attribute events even if they arrive out of order."""
    meta = {"org_id": org_id, "tier": tier}
    sub_data: dict[str, Any] = {"metadata": meta}
    if trial_days:
        sub_data["trial_period_days"] = trial_days
    params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(org_id),
        "metadata": meta,
        "subscription_data": sub_data,
    }
    if customer_id:
        params["customer"] = customer_id
    elif customer_email:
        params["customer_email"] = customer_email
    session = _request(config, "POST", "/checkout/sessions", params)
    if not session.get("url"):
        raise StripeError("Stripe did not return a checkout URL")
    return session


def create_portal_session(config: StripeConfig, *, customer_id: str,
                          return_url: str) -> dict[str, Any]:
    session = _request(config, "POST", "/billing_portal/sessions",
                       {"customer": customer_id, "return_url": return_url})
    if not session.get("url"):
        raise StripeError("Stripe did not return a portal URL")
    return session


def retrieve_subscription(config: StripeConfig, subscription_id: str) -> dict[str, Any]:
    return _request(config, "GET", f"/subscriptions/{subscription_id}")


# ------------------------------------------------------------------- webhooks
def verify_webhook_signature(payload: bytes, header: str | None, secret: str, *,
                             tolerance: int = SIGNATURE_TOLERANCE_SECONDS,
                             now: float | None = None) -> None:
    """Verify a `Stripe-Signature` header: `t=<unix>,v1=<hex>[,v1=<hex>...]`
    where v1 = HMAC-SHA256(secret, f"{t}.{payload}"). Raises SignatureError.
    Any one matching v1 suffices (Stripe sends several during secret rolls)."""
    if not secret:
        raise SignatureError("webhook secret not configured")
    if not header:
        raise SignatureError("missing Stripe-Signature header")
    timestamp = ""
    candidates: list[str] = []
    for part in header.split(","):
        k, _, v = part.strip().partition("=")
        if k == "t":
            timestamp = v
        elif k == "v1":
            candidates.append(v)
    try:
        ts = int(timestamp)
    except ValueError:
        raise SignatureError("malformed Stripe-Signature header") from None
    if not candidates:
        raise SignatureError("no v1 signature in header")
    signed = f"{ts}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, c) for c in candidates):
        raise SignatureError("signature mismatch")
    current = time.time() if now is None else now
    if abs(current - ts) > tolerance:
        raise SignatureError("timestamp outside tolerance")


def construct_event(payload: bytes, header: str | None, secret: str, **kw: Any) -> dict[str, Any]:
    """Verify, then parse. The body is never parsed before it verifies."""
    verify_webhook_signature(payload, header, secret, **kw)
    try:
        event = json.loads(payload)
    except ValueError as exc:
        raise SignatureError("payload is not JSON") from exc
    if not isinstance(event, dict) or not event.get("id") or not event.get("type"):
        raise SignatureError("payload is not a Stripe event")
    return event


def sign_payload(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Build a valid Stripe-Signature header (test helper; mirrors
    `stripe trigger`/CLI signing)."""
    ts = int(time.time()) if timestamp is None else timestamp
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"
