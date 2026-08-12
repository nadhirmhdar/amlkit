"""Read helpers for the interface.

Kept separate from the engine modules, which are concerned with deciding things
rather than displaying them. Nothing here mutates state.

Every function that touches a tenant-owned table (customers, ubo_links,
screenings, alerts, alert_reviews, risk_assessments, documents, reports,
audit_log) takes `org_id` as a required argument, with no default. This is
deliberate and structural: per-route discipline ("remember to filter by
org") is exactly the kind of rule a future route can forget, so instead there
is no code path through this module that can query tenant data without an
org_id -- the function signature itself is the enforcement. `entities` and
its supporting tables (datasets, entity_names, name_tokens,
entity_identifiers) are shared sanctions/PEP reference data and are the only
exception.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .cases.manager import due_for_review
from .ingest.loader import staleness_report
from .screening.pf import classify_programs, obligation_note

# Triage order. Proliferation first: it is a standalone offence under Law
# 10/2025 and the least familiar to an operator, so it should never be buried
# under a longer list of ordinary sanctions hits.
CATEGORY_RANK = {"proliferation": 0, "terrorism": 1, "sanction": 2, "pep": 3, "other": 4}


def _category(topics: list[str], programs: list[str]) -> str:
    cats = classify_programs(programs)
    if "proliferation" in cats:
        return "proliferation"
    if "terrorism" in cats:
        return "terrorism"
    if "sanction" in topics:
        return "sanction"
    if any(t.startswith("role.pep") for t in topics):
        return "pep"
    return "other"


def dashboard(conn: sqlite3.Connection, org_id: int) -> dict[str, Any]:
    """Everything the 'am I compliant right now' view needs, for one org.

    `entities` (the shared sanctions/PEP corpus) is the one count here that is
    NOT org-scoped -- deliberately: every firm screens against the same
    underlying data, so its size is informative to all of them, not a
    property of any one org's book.
    """
    staleness = staleness_report(conn)
    breaches = [d for d in staleness if d["breach"]]

    alerts = (alert_queue(conn, org_id, status="open")
              + alert_queue(conn, org_id, status="pending_review"))
    by_category: dict[str, int] = {}
    for a in alerts:
        by_category[a["category"]] = by_category.get(a["category"], 0) + 1

    reviews = due_for_review(conn, org_id)

    counts = conn.execute(
        """SELECT
             (SELECT COUNT(*) FROM customers WHERE status='active' AND org_id=?) AS customers,
             (SELECT COUNT(*) FROM entities)                                     AS entities,
             (SELECT COUNT(*) FROM screenings WHERE org_id=?)                    AS screenings,
             (SELECT COUNT(*) FROM alerts WHERE org_id=?)                        AS alerts_total""",
        (org_id, org_id, org_id),
    ).fetchone()

    return {
        "staleness": staleness,
        "breaches": breaches,
        "compliant": not breaches,
        "open_alerts": alerts,
        "open_by_category": by_category,
        "pending_review": [a for a in alerts if a["status"] == "pending_review"],
        "due_for_review": reviews,
        "counts": dict(counts),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def alert_queue(
    conn: sqlite3.Connection, org_id: int, status: str | None = "open", limit: int = 200
) -> list[dict[str, Any]]:
    """Alerts with the entity and customer context needed to triage them,
    scoped to one organization."""
    sql = """
        SELECT a.id, a.score, a.score_detail, a.matched_name, a.status,
               a.disposition, a.reason_code, a.independent_review,
               a.dispositioned_by, a.dispositioned_at, a.created_at,
               e.id AS entity_id, e.caption, e.schema_type, e.topics, e.programs,
               e.countries, e.birth_date,
               d.key AS dataset, d.title AS dataset_title,
               s.id AS screening_id, s.query_name, s.trigger,
               c.id AS customer_id, c.reference, c.full_name AS customer_name,
               u.person_name AS ubo_name
        FROM alerts a
        JOIN entities e   ON e.id = a.entity_id
        JOIN datasets d   ON d.id = e.dataset_id
        JOIN screenings s ON s.id = a.screening_id
        LEFT JOIN customers c ON c.id = s.customer_id
        LEFT JOIN ubo_links u ON u.id = s.ubo_id
        WHERE a.org_id = ?
    """
    params: list[Any] = [org_id]
    if status:
        sql += " AND a.status = ?"
        params.append(status)
    sql += " ORDER BY a.score DESC LIMIT ?"

    out: list[dict[str, Any]] = []
    for row in conn.execute(sql, (*params, limit)):
        topics = json.loads(row["topics"] or "[]")
        programs = json.loads(row["programs"] or "[]")
        cat = _category(topics, programs)
        out.append(
            dict(row)
            | {
                "topics": topics,
                "programs": programs,
                "countries": json.loads(row["countries"] or "[]"),
                "category": cat,
                "obligation": obligation_note(classify_programs(programs)),
                "detail": json.loads(row["score_detail"] or "{}"),
                "aliases": entity_names(conn, row["entity_id"]),
                # Whose name actually matched -- the customer, or one of their
                # beneficial owners. A listed UBO behind a clean company is the
                # case operators most need pointed out to them.
                "matched_party": row["ubo_name"] or row["customer_name"] or row["query_name"],
                "via_ubo": bool(row["ubo_name"]),
            }
        )
    out.sort(key=lambda a: (CATEGORY_RANK.get(a["category"], 9), -a["score"]))
    return out


def entity_names(conn: sqlite3.Connection, entity_id: int) -> list[dict[str, str]]:
    return [
        {"name": r["name"], "type": r["name_type"], "script": r["script"]}
        for r in conn.execute(
            "SELECT name, name_type, script FROM entity_names WHERE entity_id=? ORDER BY id",
            (entity_id,),
        )
    ]


def customer_list(conn: sqlite3.Connection, org_id: int) -> list[dict[str, Any]]:
    """Customers of one organization, with their latest risk rating and
    screening activity."""
    rows = conn.execute(
        """SELECT c.id, c.reference, c.full_name, c.name_arabic, c.customer_type,
                  c.nationality, c.sector, c.status, c.onboarded_at,
                  r.rating, r.score AS risk_score, r.requires_edd, r.next_review,
                  (SELECT MAX(run_at) FROM screenings WHERE customer_id=c.id) AS last_screened,
                  (SELECT COUNT(*) FROM alerts al
                     JOIN screenings s2 ON s2.id = al.screening_id
                    WHERE s2.customer_id = c.id AND al.status IN ('open','pending_review'))
                    AS open_alerts
           FROM customers c
           LEFT JOIN risk_assessments r ON r.id = (
                SELECT id FROM risk_assessments WHERE customer_id=c.id
                ORDER BY assessed_at DESC LIMIT 1)
           WHERE c.org_id = ?
           ORDER BY c.created_at DESC""",
        (org_id,),
    ).fetchall()
    today = datetime.now(timezone.utc).date().isoformat()
    return [
        dict(r) | {"review_overdue": bool(r["next_review"] and r["next_review"] <= today)}
        for r in rows
    ]


def customer(conn: sqlite3.Connection, customer_id: int, org_id: int) -> dict[str, Any] | None:
    """Full case file for one customer, or None if it does not exist OR
    belongs to a different organization -- the two cases are deliberately
    indistinguishable to the caller, so a cross-tenant customer_id in a URL
    produces the same 404 a nonexistent one would."""
    row = conn.execute(
        "SELECT * FROM customers WHERE id=? AND org_id=?", (customer_id, org_id)
    ).fetchone()
    if row is None:
        return None

    ubos = [dict(r) for r in conn.execute(
        "SELECT * FROM ubo_links WHERE customer_id=? AND org_id=?"
        " ORDER BY is_ubo DESC, ownership_pct DESC",
        (customer_id, org_id))]

    risk_rows = conn.execute(
        "SELECT * FROM risk_assessments WHERE customer_id=? AND org_id=? ORDER BY assessed_at DESC",
        (customer_id, org_id)).fetchall()
    risks = [dict(r) | {"factors": json.loads(r["factors"] or "{}")} for r in risk_rows]

    screenings = [dict(r) | {"datasets_used": json.loads(r["datasets_used"] or "[]")}
                  for r in conn.execute(
        "SELECT * FROM screenings WHERE customer_id=? AND org_id=? ORDER BY run_at DESC",
        (customer_id, org_id))]

    alerts = [a for a in alert_queue(conn, org_id, status=None, limit=500)
              if a["customer_id"] == customer_id]

    return {
        "customer": dict(row),
        "ubos": ubos,
        "risk": risks[0] if risks else None,
        "risk_history": risks,
        "screenings": screenings,
        "alerts": alerts,
        "audit": audit_trail(conn, org_id, "customer", customer_id),
    }


def audit_trail(
    conn: sqlite3.Connection, org_id: int, object_type: str | None = None,
    object_id: int | str | None = None, limit: int = 200,
) -> list[dict[str, Any]]:
    """Audit entries for one organization, plus shared/system entries.

    `org_id IS NULL` rows are shared reference-data actions (sanctions-list
    refreshes) with no PII -- visible alongside this org's own history rather
    than hidden, since every firm's compliance posture depends on knowing
    when the lists it screens against last updated.
    """
    sql = "SELECT ts, actor, action, object_type, object_id, detail FROM audit_log WHERE (org_id=? OR org_id IS NULL)"
    params: list[Any] = [org_id]
    if object_type:
        sql += " AND object_type=?"
        params.append(object_type)
        if object_id is not None:
            sql += " AND object_id=?"
            params.append(str(object_id))
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return [
        dict(r) | {"detail": json.loads(r["detail"]) if r["detail"] else None}
        for r in conn.execute(sql, params)
    ]


def operators(conn: sqlite3.Connection, org_id: int) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT id, name, email, role, is_active FROM operators WHERE org_id=? ORDER BY name",
        (org_id,))]


def datasets(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    # Not org-scoped: sanctions/PEP datasets are shared reference data,
    # identical for every firm using this deployment.
    return [dict(r) for r in conn.execute(
        "SELECT key, title, publisher, licence, is_mandatory, last_refresh, entity_count"
        " FROM datasets ORDER BY is_mandatory DESC, key")]
