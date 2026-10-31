"""Plan-limit and payment-state enforcement.

`check_limit(conn, org_id, resource)` is called just before an operator is
created or reactivated, a customer is onboarded or reactivated. It is a no-op
when billing is not configured (STRIPE_SECRET_KEY unset), so the feature is
inert exactly like UAE PASS.

Rules:
  * Legacy orgs (plan 'trial' and no trial_ends_at -- i.e. every organisation
    that existed before billing shipped, and every one registered since that
    has not subscribed) are UNLIMITED and never write-blocked. Deploying
    billing therefore cannot break an existing firm.
  * A subscribed org gets its tier's limits. An org on a dated trial
    (plan 'trial' with trial_ends_at set) gets the Starter limits.
  * past_due / unpaid / canceled: writes keep working for GRACE_DAYS after
    current_period_end, then creation is refused with a message pointing to
    /billing. A canceled org is likewise refused after the grace window.
  * Reads are NEVER refused by this module. A compliance tool must not lock an
    MLRO out of its own records; only the creation of new operators/customers
    is gated, so screening, case work, reports and exports keep working.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import stripe_client
from .plans import GRACE_DAYS, PLANS, Plan

RESOURCES = ("operators", "customers", "workspaces")
BLOCKED_STATUSES = ("past_due", "unpaid", "canceled")


class BillingLimitError(ValueError):
    """Raised when a plan limit or a lapsed subscription refuses a write.
    A ValueError so existing `except ValueError` handlers surface the message."""


@dataclass(slots=True)
class BillingState:
    plan_key: str
    status: str | None
    plan: Plan | None            # None => legacy/unlimited
    legacy: bool
    write_blocked: bool
    grace_ends_at: str | None
    usage: dict[str, int]

    def limit(self, resource: str) -> int | None:
        return None if self.plan is None else self.plan.limit(resource)


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def usage(conn: sqlite3.Connection, org_id: int) -> dict[str, int]:
    return {
        "operators": conn.execute(
            "SELECT COUNT(*) FROM operators WHERE org_id=? AND is_active=1", (org_id,)
        ).fetchone()[0],
        # Closed relationships are retained for the statutory period but are
        # not billable customers.
        "customers": conn.execute(
            "SELECT COUNT(*) FROM customers WHERE org_id=? AND status != 'closed'", (org_id,)
        ).fetchone()[0],
        # There is no client-workspace concept in the schema yet: every org is
        # one workspace. Reported for the /billing page; not enforced.
        "workspaces": 1,
    }


def org_state(conn: sqlite3.Connection, org_id: int, now: datetime | None = None) -> BillingState:
    now = now or datetime.now(timezone.utc)
    row = conn.execute(
        "SELECT plan, plan_status, trial_ends_at, current_period_end"
        " FROM organizations WHERE id=?", (org_id,)
    ).fetchone()
    use = usage(conn, org_id)
    if row is None:
        return BillingState("trial", None, None, True, False, None, use)
    plan_key = row["plan"] or "trial"
    status = row["plan_status"]
    trial_end = _parse(row["trial_ends_at"])

    if plan_key == "trial":
        if trial_end is None:
            return BillingState("trial", status, None, True, False, None, use)
        grace_end = trial_end + timedelta(days=GRACE_DAYS)
        return BillingState("trial", status or "trialing", PLANS["starter"], False,
                            now > grace_end, grace_end.isoformat(timespec="seconds"), use)

    plan = PLANS.get(plan_key)
    if plan is None:  # a plan retired from the code: do not punish the org
        return BillingState(plan_key, status, None, True, False, None, use)

    blocked, grace_iso = False, None
    if status in BLOCKED_STATUSES:
        period_end = _parse(row["current_period_end"])
        if period_end is not None:  # unknown anchor => fail open, never lock out
            grace_end = period_end + timedelta(days=GRACE_DAYS)
            grace_iso = grace_end.isoformat(timespec="seconds")
            blocked = now > grace_end
    return BillingState(plan_key, status, plan, False, blocked, grace_iso, use)


def check_limit(conn: sqlite3.Connection, org_id: int, resource: str,
                now: datetime | None = None) -> None:
    """Refuse the creation of one more `resource` if the org's plan or payment
    state forbids it. Raises BillingLimitError; returns None when allowed."""
    if resource not in RESOURCES:
        raise ValueError(f"unknown billable resource: {resource!r}")
    if stripe_client.load_config() is None:
        return
    st = org_state(conn, org_id, now)
    if st.legacy:
        return
    if st.write_blocked:
        raise BillingLimitError(
            "This workspace is read-only because the subscription is "
            f"{(st.status or 'lapsed').replace('_', ' ')} and the {GRACE_DAYS}-day grace "
            "period has ended. Your records remain fully available. "
            "Resolve billing at /billing to add operators or customers again."
        )
    cap = st.limit(resource)
    if cap is not None and st.usage[resource] >= cap:
        noun = {"operators": "operators", "customers": "customers",
                "workspaces": "client workspaces"}[resource]
        raise BillingLimitError(
            f"The {st.plan.name} plan allows up to {cap:,} {noun}, and this "
            f"organisation has reached that limit. Change plan at /billing."
        )
