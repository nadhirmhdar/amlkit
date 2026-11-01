"""First-run checklist state for the dashboard (p51).

Everything is derived from real state; the only thing stored is the per-
operator dismissal (`operators.onboarding_dismissed_at`). Every query is
scoped by org_id.
"""

from __future__ import annotations

import sqlite3

from . import auth


def checklist(conn: sqlite3.Connection, org_id: int, operator_id: int, role: str) -> dict | None:
    """The checklist for this operator, or None when it should not be shown
    (dismissed, or the organisation already has customers)."""
    op = conn.execute(
        "SELECT onboarding_dismissed_at FROM operators WHERE id=? AND org_id=?",
        (operator_id, org_id),
    ).fetchone()
    if op is None or op["onboarding_dismissed_at"]:
        return None
    customers = conn.execute(
        "SELECT COUNT(*) FROM customers WHERE org_id=?", (org_id,)
    ).fetchone()[0]
    if customers:
        return None
    operators = conn.execute(
        "SELECT COUNT(*) FROM operators WHERE org_id=? AND is_active=1", (org_id,)
    ).fetchone()[0]
    refreshed = conn.execute(
        "SELECT 1 FROM datasets WHERE last_refresh IS NOT NULL LIMIT 1"
    ).fetchone() is not None
    org = conn.execute(
        "SELECT org_address, reporting_person_name, goaml_entity_reference"
        " FROM organizations WHERE id=?", (org_id,)
    ).fetchone()
    profile_done = bool(org and all((org[k] or "").strip() for k in
                                    ("org_address", "reporting_person_name",
                                     "goaml_entity_reference")))
    items = [
        {"key": "operator", "label": "Add a second operator",
         "hint": "Four-eyes review needs two people.", "href": "/admin",
         "done": operators >= 2},
        {"key": "refresh", "label": "Refresh the sanctions lists",
         "hint": "Screening is only as good as the lists behind it.", "href": "/admin",
         "done": refreshed},
        {"key": "customer", "label": "Onboard your first customer",
         "hint": "Screen, assess risk and open the case file.", "href": "/customers/new",
         "done": customers > 0},
    ]
    if role == "mlro":
        items.append({"key": "mfa", "label": "Enrol multi-factor sign-in",
                      "hint": "Required for MLROs.", "href": "/mfa/setup",
                      "done": auth.mfa_is_enrolled(conn, operator_id)})
        items.append({"key": "profile", "label": "Complete the goAML organisation profile",
                      "hint": "Address, reporting person and entity reference.",
                      "href": "/admin", "done": profile_done})
    return {"items": items, "done": sum(i["done"] for i in items), "total": len(items)}


# A UI preference, not a compliance event, so it is not written to the audit log.
def dismiss(conn: sqlite3.Connection, org_id: int, operator_id: int) -> None:
    from .db import utcnow
    conn.execute(
        "UPDATE operators SET onboarding_dismissed_at=COALESCE(onboarding_dismissed_at, ?)"
        " WHERE id=? AND org_id=?", (utcnow(), operator_id, org_id))
    conn.commit()
