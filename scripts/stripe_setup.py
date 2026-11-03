"""One-shot, idempotent Stripe set-up for groAML billing (no SDK, no database).

    STRIPE_SECRET_KEY=sk_test_... python scripts/stripe_setup.py \\
        --webhook-url https://groaml.grovisor.ae/billing/webhook [--dry-run]

Creates (or finds, by metadata.groaml_tier) the Products "groAML Starter" and
"groAML Professional" with a yearly AED Price each, and a webhook endpoint
subscribed to exactly the events amlkit.billing.service handles. Then prints the
GitHub repo secrets and variables to paste (see docs/runbooks/stripe-go-live.md).
The Consultant tier has no Price ("Contact us"). Safe to re-run.

The webhook signing secret is returned by Stripe only when the endpoint is
created. If the endpoint already exists its secret cannot be shown again; copy
it from the Stripe dashboard (Developers > Webhooks) instead.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.billing import service  # noqa: E402
from amlkit.billing.stripe_client import StripeConfig, StripeError, _request  # noqa: E402

CURRENCY = "aed"
INTERVAL = "year"
# tier -> (product name, unit amount in minor units, display text)
TIERS: dict[str, tuple[str, int, str]] = {
    "starter": ("groAML Starter", 49900, "AED 499 / year"),
    "professional": ("groAML Professional", 149900, "AED 1,499 / year"),
}
EVENTS = tuple(service.HANDLED)


def _list_all(cfg: StripeConfig, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    after = None
    for _ in range(50):  # hard stop: 5,000 objects
        q = {**params, "limit": 100}
        if after:
            q["starting_after"] = after
        page = _request(cfg, "GET", path, q)
        data = page.get("data") or []
        out.extend(data)
        if not page.get("has_more") or not data:
            break
        after = data[-1]["id"]
    return out


def find_product(cfg: StripeConfig, tier: str) -> dict[str, Any] | None:
    for p in _list_all(cfg, "/products", {"active": True}):
        if (p.get("metadata") or {}).get("groaml_tier") == tier:
            return p
    return None


def find_price(cfg: StripeConfig, product_id: str, amount: int) -> dict[str, Any] | None:
    for pr in _list_all(cfg, "/prices", {"product": product_id, "active": True}):
        rec = pr.get("recurring") or {}
        if (pr.get("currency") == CURRENCY and pr.get("unit_amount") == amount
                and rec.get("interval") == INTERVAL and rec.get("interval_count", 1) == 1):
            return pr
    return None


def find_webhook(cfg: StripeConfig, url: str) -> dict[str, Any] | None:
    for w in _list_all(cfg, "/webhook_endpoints", {}):
        if w.get("url") == url:
            return w
    return None


def run(cfg: StripeConfig, webhook_url: str, *, dry_run: bool,
        say: Callable[[str], None] = print) -> dict[str, str]:
    """Do (or, with dry_run, only describe) the set-up. Returns the values to
    paste: {NAME: value}. A value is "" when it could not be obtained."""
    values: dict[str, str] = {}
    for tier, (name, amount, display) in TIERS.items():
        var = f"STRIPE_PRICE_{tier.upper()}"
        product = find_product(cfg, tier)
        if product:
            say(f"product {name}: exists ({product['id']})")
        elif dry_run:
            say(f"product {name}: WOULD CREATE (metadata.groaml_tier={tier})")
        else:
            product = _request(cfg, "POST", "/products", {
                "name": name, "metadata": {"groaml_tier": tier}})
            say(f"product {name}: created ({product['id']})")
        price = find_price(cfg, product["id"], amount) if product else None
        if price:
            say(f"  price {display}: exists ({price['id']})")
        elif dry_run:
            say(f"  price {display}: WOULD CREATE ({amount} {CURRENCY} minor units, every 1 {INTERVAL})")
        else:
            price = _request(cfg, "POST", "/prices", {
                "product": product["id"], "currency": CURRENCY, "unit_amount": amount,
                "recurring": {"interval": INTERVAL, "interval_count": 1},
                "metadata": {"groaml_tier": tier}})
            say(f"  price {display}: created ({price['id']})")
        values[var] = price["id"] if price else ""

    hook = find_webhook(cfg, webhook_url)
    secret = ""
    if hook:
        missing = sorted(set(EVENTS) - set(hook.get("enabled_events") or []))
        extra = sorted(set(hook.get("enabled_events") or []) - set(EVENTS))
        if "*" in (hook.get("enabled_events") or []):
            missing, extra = [], []  # already receives everything we handle
        if (missing or extra) and not dry_run:
            _request(cfg, "POST", f"/webhook_endpoints/{hook['id']}", {"enabled_events": list(EVENTS)})
            say(f"webhook {webhook_url}: exists ({hook['id']}); events updated")
        elif missing or extra:
            say(f"webhook {webhook_url}: exists ({hook['id']}); WOULD UPDATE events")
        else:
            say(f"webhook {webhook_url}: exists ({hook['id']}), events already correct")
        say("  WARNING: Stripe shows the signing secret only at creation. Copy it from "
            "Dashboard > Developers > Webhooks > this endpoint > Signing secret.")
    elif dry_run:
        say(f"webhook {webhook_url}: WOULD CREATE with events: {', '.join(EVENTS)}")
    else:
        hook = _request(cfg, "POST", "/webhook_endpoints", {
            "url": webhook_url, "enabled_events": list(EVENTS),
            "description": "groAML billing"})
        secret = hook.get("secret") or ""
        say(f"webhook {webhook_url}: created ({hook['id']})")
    values["STRIPE_WEBHOOK_SECRET"] = secret
    return values


def render_block(values: dict[str, str], webhook_url: str, *, dry_run: bool) -> str:
    u = urlparse(webhook_url)
    origin = f"{u.scheme}://{u.netloc}"
    lines = ["", "=== GitHub repo settings > Secrets and variables > Actions ===",
             "SECRETS (Secrets tab):",
             "  STRIPE_SECRET_KEY            = <the sk_ key you ran this script with>"]
    for name in ("STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_STARTER", "STRIPE_PRICE_PROFESSIONAL"):
        v = values.get(name, "")
        if name == "STRIPE_WEBHOOK_SECRET" and not v:
            v = "<not available: copy from the Stripe dashboard>" if not dry_run else "<shown once, at creation>"
        elif not v:
            v = "<created on a real run>"
        lines.append(f"  {name:<28} = {v}")
    lines += ["  STRIPE_PRICE_CONSULTANT      = (leave unset: Consultant is \"Contact us\")",
              "VARIABLES (Variables tab):"]
    for tier, (_n, _a, display) in TIERS.items():
        lines.append(f"  STRIPE_DISPLAY_PRICE_{tier.upper():<13} = {display}")
    lines += ["  STRIPE_DISPLAY_PRICE_CONSULTANT = (leave unset)",
              f"  AMLKIT_BILLING_PUBLIC_URL    = {origin}", ""]
    if values.get("STRIPE_WEBHOOK_SECRET") and not dry_run:
        lines += ["WARNING: the webhook signing secret above is shown ONCE. Store it now; "
                  "it cannot be retrieved from this script again.", ""]
    lines += ["REMINDER (dashboard, cannot be set by API): Settings > Billing > Customer portal >",
              "  enable \"Customers can switch plans\" and add the two prices, so Manage billing "
              "can change plan.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--webhook-url", required=True,
                    help="e.g. https://groaml.grovisor.ae/billing/webhook")
    ap.add_argument("--dry-run", action="store_true", help="print what would be done; create nothing")
    args = ap.parse_args(argv)
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key:
        print("STRIPE_SECRET_KEY is not set in the environment.", file=sys.stderr)
        return 2
    u = urlparse(args.webhook_url)
    if u.scheme != "https" or not u.netloc or not u.path.endswith("/billing/webhook"):
        print("--webhook-url must be an https URL ending in /billing/webhook.", file=sys.stderr)
        return 2
    mode = "LIVE" if key.startswith(("sk_live_", "rk_live_")) else "TEST"
    print(f"Stripe mode: {mode}{'  (dry run)' if args.dry_run else ''}")
    try:
        values = run(StripeConfig(secret_key=key), args.webhook_url, dry_run=args.dry_run)
    except StripeError as exc:
        print(f"Stripe error: {exc}", file=sys.stderr)
        return 1
    print(render_block(values, args.webhook_url, dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
