"""Billing persistence: applying Stripe webhook events to organizations.

Every write is audited with the org id. The raw verified event is stored in
billing_events first, keyed by stripe_event_id, so a replay is recognised and
not processed twice; an event whose processing failed (processed_at NULL) is
retried when Stripe redelivers it.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from ..db import audit, utcnow
from .stripe_client import StripeConfig

ACTOR = "stripe"

# Stripe subscription.status -> organizations.plan_status
_STATUS_MAP = {
    "trialing": "trialing",
    "active": "active",
    "past_due": "past_due",
    "unpaid": "unpaid",
    "canceled": "canceled",
    "incomplete": "past_due",
    "incomplete_expired": "canceled",
    "paused": "unpaid",
}
HANDLED = (
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_failed",
    "invoice.paid",
)


def _iso(unix: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(unix), tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _find_org(conn: sqlite3.Connection, *, org_hint: Any = None,
              customer: str | None = None, subscription: str | None = None) -> int | None:
    # Metadata/client_reference_id is only trusted if the org exists; a
    # customer or subscription id that we have stored is the stronger key.
    if customer:
        r = conn.execute("SELECT id FROM organizations WHERE billing_customer_id=?", (customer,)).fetchone()
        if r:
            return r["id"]
    if subscription:
        r = conn.execute("SELECT id FROM organizations WHERE billing_subscription_id=?", (subscription,)).fetchone()
        if r:
            return r["id"]
    try:
        oid = int(org_hint)
    except (TypeError, ValueError):
        return None
    r = conn.execute("SELECT id FROM organizations WHERE id=?", (oid,)).fetchone()
    return r["id"] if r else None


def _period_end(sub: dict[str, Any]) -> str | None:
    # Newer API versions moved current_period_end onto the subscription items.
    val = sub.get("current_period_end")
    if val is None:
        items = ((sub.get("items") or {}).get("data")) or []
        if items:
            val = items[0].get("current_period_end")
    return _iso(val)


def _sub_price_id(sub: dict[str, Any]) -> str | None:
    items = ((sub.get("items") or {}).get("data")) or []
    if items:
        return (items[0].get("price") or {}).get("id")
    return None


def _invoice_subscription(inv: dict[str, Any]) -> str | None:
    sub = inv.get("subscription")
    if not sub:
        sub = (((inv.get("parent") or {}).get("subscription_details")) or {}).get("subscription")
    return sub if isinstance(sub, str) else None


def apply_subscription(conn: sqlite3.Connection, org_id: int, sub: dict[str, Any],
                       config: StripeConfig, *, event_type: str, event_created: Any = None) -> None:
    status = _STATUS_MAP.get(sub.get("status") or "")
    if status is None:
        return
    tier = config.tier_for_price(_sub_price_id(sub)) or (sub.get("metadata") or {}).get("tier")
    cur = conn.execute("SELECT plan, plan_status FROM organizations WHERE id=?", (org_id,)).fetchone()
    plan = tier if tier else cur["plan"]  # unknown price: keep what we had
    period_end = _period_end(sub)
    if status in ("canceled",) and period_end is None:
        period_end = _iso(sub.get("ended_at") or sub.get("canceled_at") or event_created)
    conn.execute(
        "UPDATE organizations SET billing_subscription_id=?, plan=?, plan_status=?,"
        " trial_ends_at=?, current_period_end=COALESCE(?, current_period_end),"
        " billing_customer_id=COALESCE(?, billing_customer_id) WHERE id=?",
        (sub.get("id"), plan, status, _iso(sub.get("trial_end")), period_end,
         sub.get("customer") if isinstance(sub.get("customer"), str) else None, org_id),
    )
    audit(conn, ACTOR, "billing.subscription_sync", "organization", org_id,
          {"event": event_type, "subscription": sub.get("id"), "from_plan": cur["plan"],
           "to_plan": plan, "from_status": cur["plan_status"], "to_status": status},
          org_id=org_id)


def _process(conn: sqlite3.Connection, event: dict[str, Any], config: StripeConfig) -> int | None:
    """Apply one event; returns the org id it was attributed to (or None)."""
    etype = event["type"]
    obj = ((event.get("data") or {}).get("object")) or {}
    if etype == "checkout.session.completed":
        meta = obj.get("metadata") or {}
        org_id = _find_org(conn, org_hint=obj.get("client_reference_id") or meta.get("org_id"),
                           customer=obj.get("customer"))
        if org_id is None:
            return None
        conn.execute(
            "UPDATE organizations SET billing_customer_id=COALESCE(?, billing_customer_id),"
            " billing_subscription_id=COALESCE(?, billing_subscription_id) WHERE id=?",
            (obj.get("customer"), obj.get("subscription"), org_id),
        )
        audit(conn, ACTOR, "billing.checkout_completed", "organization", org_id,
              {"customer": obj.get("customer"), "subscription": obj.get("subscription")},
              org_id=org_id)
        return org_id

    if etype in ("customer.subscription.created", "customer.subscription.updated",
                 "customer.subscription.deleted"):
        org_id = _find_org(conn, org_hint=(obj.get("metadata") or {}).get("org_id"),
                           customer=obj.get("customer"), subscription=obj.get("id"))
        if org_id is None:
            return None
        org_row = conn.execute(
            "SELECT billing_subscription_id, billing_last_event_created FROM organizations"
            " WHERE id=?", (org_id,)).fetchone()
        held = org_row["billing_subscription_id"]
        # L-106: Stripe does not guarantee delivery order. A subscription event
        # older than the newest one already applied is stored but not applied.
        created = event.get("created")
        created = created if isinstance(created, int) and not isinstance(created, bool) else None
        last = org_row["billing_last_event_created"]
        if created is not None and last is not None and created < last:
            return org_id
        if etype != "customer.subscription.created" and held and obj.get("id") != held:
            return org_id  # a superseded subscription: must not overwrite the live one
        if etype.endswith("deleted"):
            obj = {**obj, "status": "canceled"}
        apply_subscription(conn, org_id, obj, config, event_type=etype,
                           event_created=event.get("created"))
        if created is not None:
            conn.execute("UPDATE organizations SET billing_last_event_created=? WHERE id=?",
                         (created, org_id))
        return org_id

    if etype in ("invoice.payment_failed", "invoice.paid"):
        org_id = _find_org(conn, customer=obj.get("customer"),
                           subscription=_invoice_subscription(obj))
        if org_id is None:
            return None
        cur = conn.execute("SELECT plan_status FROM organizations WHERE id=?", (org_id,)).fetchone()
        if etype == "invoice.payment_failed":
            conn.execute(
                "UPDATE organizations SET plan_status='past_due',"
                " current_period_end=COALESCE(current_period_end, ?) WHERE id=?",
                (_iso(event.get("created")), org_id),
            )
            audit(conn, ACTOR, "billing.payment_failed", "organization", org_id,
                  {"invoice": obj.get("id"), "from_status": cur["plan_status"]}, org_id=org_id)
        elif cur["plan_status"] in ("past_due", "unpaid"):
            # Only a lapsed org is revived by a paid invoice; a $0 trial
            # invoice must not turn 'trialing' into 'active'.
            conn.execute("UPDATE organizations SET plan_status='active' WHERE id=?", (org_id,))
            audit(conn, ACTOR, "billing.payment_recovered", "organization", org_id,
                  {"invoice": obj.get("id")}, org_id=org_id)
        return org_id
    return None


def handle_event(conn: sqlite3.Connection, event: dict[str, Any], config: StripeConfig) -> str:
    """Store and apply a verified event. Returns 'processed', 'duplicate' or
    'stored' (unhandled/unattributable type, kept for the record)."""
    eid = event["id"]
    row = conn.execute("SELECT id, processed_at FROM billing_events WHERE stripe_event_id=?",
                       (eid,)).fetchone()
    if row is not None and row["processed_at"]:
        return "duplicate"
    if row is None:
        try:
            conn.execute(
                "INSERT INTO billing_events (stripe_event_id, type, payload, received_at)"
                " VALUES (?,?,?,?)",
                (eid, event["type"], json.dumps(event, ensure_ascii=False), utcnow()),
            )
        except sqlite3.IntegrityError:  # concurrent delivery of the same event
            conn.rollback()
            return "duplicate"
    try:
        org_id = _process(conn, event, config) if event["type"] in HANDLED else None
    except Exception:
        conn.rollback()  # drops the inbox row too, so Stripe's retry starts clean
        raise
    conn.execute("UPDATE billing_events SET org_id=?, processed_at=? WHERE stripe_event_id=?",
                 (org_id, utcnow(), eid))
    conn.commit()
    return "processed" if org_id is not None else "stored"
