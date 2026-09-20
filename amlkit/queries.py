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

from .cases.manager import adverse_media_due, due_for_review
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


def dataset_health_banner(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Check dataset health and return banner info if action needed.

    Returns None when all datasets are healthy (no banner needed).
    Returns dict with 'severity' ('critical' or 'warning'), 'message', and 'link' when issues exist.

    Critical (red): mandatory dataset stale or has error
    Warning (amber): optional dataset stale or has error
    """
    # Check for errors first (higher priority)
    error_rows = conn.execute(
        "SELECT title, is_mandatory, last_error FROM datasets WHERE last_error IS NOT NULL"
    ).fetchall()

    if error_rows:
        mandatory_errors = [r for r in error_rows if r["is_mandatory"]]
        if mandatory_errors:
            count = len(mandatory_errors)
            return {
                "severity": "critical",
                "message": f"{count} mandatory sanctions source{'s' if count != 1 else ''} failing to update",
                "link": "/admin/compliance"
            }
        else:
            count = len(error_rows)
            return {
                "severity": "warning",
                "message": f"{count} optional source{'s' if count != 1 else ''} failing to update",
                "link": "/admin/compliance"
            }

    # Check for staleness
    staleness = staleness_report(conn)
    stale_mandatory = [d for d in staleness if d["breach"] and d["mandatory"]]
    # Exclude code-embedded, version-tracked datasets (e.g., FATF at its expected version)
    # from optional staleness checks, since they're not "failing to update"
    from amlkit.ingest.fatf import _FATF_DATA_AS_OF, _FATF_MAX_AGE_HOURS
    fatf_at_version = conn.execute(
        "SELECT 1 FROM datasets WHERE key='fatf_country_risk' AND last_refresh=? AND max_age_hours=?",
        (_FATF_DATA_AS_OF, _FATF_MAX_AGE_HOURS)
    ).fetchone()

    stale_optional = [d for d in staleness if d.get("hours_since_refresh") and
                      d["hours_since_refresh"] > d.get("max_age_hours", 24) and not d["mandatory"]
                      and not (d["key"] == "fatf_country_risk" and fatf_at_version)]

    if stale_mandatory:
        count = len(stale_mandatory)
        return {
            "severity": "critical",
            "message": f"{count} mandatory sanctions source{'s' if count != 1 else ''} out of date",
            "link": "/admin/compliance"
        }
    elif stale_optional:
        count = len(stale_optional)
        return {
            "severity": "warning",
            "message": f"{count} optional source{'s' if count != 1 else ''} out of date",
            "link": "/admin/compliance"
        }

    return None


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
    # Adverse media runs on its own, much shorter cadence than the CDD review
    # cycle (see risk/ruleset.yaml). Surfaced here because that is the whole
    # control: a check nobody is reminded to re-run happens once, at
    # onboarding, and then silently ages out.
    am_due = adverse_media_due(conn, org_id)

    counts = conn.execute(
        """SELECT
             (SELECT COUNT(*) FROM customers WHERE status='active' AND org_id=?) AS customers,
             (SELECT COUNT(*) FROM entities)                                     AS entities,
             (SELECT COUNT(*) FROM screenings WHERE org_id=?)                    AS screenings,
             (SELECT COUNT(*) FROM alerts WHERE org_id=?)                        AS alerts_total""",
        (org_id, org_id, org_id),
    ).fetchone()

    high_risk = conn.execute(
        """SELECT COUNT(*) c FROM customers c
           WHERE c.org_id=? AND c.status='active' AND EXISTS (
             SELECT 1 FROM risk_assessments r WHERE r.customer_id=c.id AND r.rating='high'
             AND r.id = (SELECT id FROM risk_assessments WHERE customer_id=c.id
                         ORDER BY assessed_at DESC LIMIT 1))""",
        (org_id,),
    ).fetchone()["c"]

    oldest_open = sorted(alerts, key=lambda a: a["created_at"])[:5]

    txn_alerts = transaction_alert_queue(conn, org_id, status="open")
    oldest_open_txn = sorted(txn_alerts, key=lambda a: a["created_at"])[:5]

    return {
        "staleness": staleness,
        "breaches": breaches,
        "compliant": not breaches,
        "open_alerts": alerts,
        "open_by_category": by_category,
        "oldest_open": oldest_open,
        "high_risk_customers": high_risk,
        "pending_review": [a for a in alerts if a["status"] == "pending_review"],
        "due_for_review": reviews,
        "adverse_media_due": am_due,
        "open_transaction_alerts": txn_alerts,
        "oldest_open_transaction_alerts": oldest_open_txn,
        "counts": dict(counts),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def dashboard_kpis(conn: sqlite3.Connection, org_id: int) -> dict[str, Any]:
    """Compute management KPIs for dashboard (Phase 4, Item 4).

    Returns:
        {
            "total_customers": 123,
            "total_active_customers": 98,
            "avg_alert_age_days": 4.5,
            "alerts_closed_7d": 12,
            "alerts_opened_7d": 8,
            "sla_breaches": 2,  # alerts open > 30 days
            "screening_coverage_pct": 100.0,
        }
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    seven_days_ago = (now - timedelta(days=7)).isoformat()
    thirty_days_ago = (now - timedelta(days=30)).isoformat()

    # Customer counts
    counts = conn.execute(
        """SELECT
             (SELECT COUNT(*) FROM customers WHERE org_id=?) AS total,
             (SELECT COUNT(*) FROM customers WHERE org_id=? AND status='active') AS active""",
        (org_id, org_id),
    ).fetchone()

    # Average alert age (open alerts only)
    open_alerts = conn.execute(
        "SELECT created_at FROM alerts WHERE org_id=? AND status='open'",
        (org_id,)
    ).fetchall()

    if open_alerts:
        total_age_seconds = 0
        for row in open_alerts:
            try:
                created = datetime.fromisoformat(row["created_at"])
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age_seconds = (now - created).total_seconds()
                total_age_seconds += age_seconds
            except (ValueError, TypeError):
                continue
        avg_alert_age_days = total_age_seconds / len(open_alerts) / 86400
    else:
        avg_alert_age_days = 0.0

    # SLA breaches (alerts open > 30 days)
    sla_breaches = conn.execute(
        "SELECT COUNT(*) c FROM alerts WHERE org_id=? AND status='open' AND created_at < ?",
        (org_id, thirty_days_ago)
    ).fetchone()["c"]

    # Alerts closed in last 7 days
    alerts_closed_7d = conn.execute(
        "SELECT COUNT(*) c FROM alerts WHERE org_id=? AND dispositioned_at >= ?",
        (org_id, seven_days_ago)
    ).fetchone()["c"]

    # Alerts opened in last 7 days
    alerts_opened_7d = conn.execute(
        "SELECT COUNT(*) c FROM alerts WHERE org_id=? AND created_at >= ?",
        (org_id, seven_days_ago)
    ).fetchone()["c"]

    # Screening coverage (% of active customers screened)
    active_count = counts["active"]
    if active_count > 0:
        screened_count = conn.execute(
            """SELECT COUNT(DISTINCT customer_id) c FROM screenings
               WHERE org_id=? AND customer_id IN (
                   SELECT id FROM customers WHERE org_id=? AND status='active'
               )""",
            (org_id, org_id)
        ).fetchone()["c"]
        screening_coverage_pct = (screened_count / active_count) * 100.0
    else:
        screening_coverage_pct = 100.0  # vacuous truth

    return {
        "total_customers": counts["total"],
        "total_active_customers": counts["active"],
        "avg_alert_age_days": round(avg_alert_age_days, 1),
        "alerts_closed_7d": alerts_closed_7d,
        "alerts_opened_7d": alerts_opened_7d,
        "sla_breaches": sla_breaches,
        "screening_coverage_pct": round(screening_coverage_pct, 1),
    }


def alert_queue(
    conn: sqlite3.Connection, org_id: int, status: str | None = "open", limit: int = 200,
    alert_id: int | None = None, customer_id: int | None = None, sort_by: str | None = None
) -> list[dict[str, Any]]:
    """Alerts with the entity and customer context needed to triage them,
    scoped to one organization.

    sort_by: "age_asc" for oldest-first, "age_desc" for newest-first,
             None for default (score-based) sorting.
    """
    sql = """
        SELECT a.id, a.score, a.score_detail, a.matched_name, a.status,
               a.disposition, a.reason_code, a.independent_review, a.assigned_to,
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
    if alert_id is not None:
        sql += " AND a.id = ?"
        params.append(alert_id)
    if customer_id is not None:
        sql += " AND s.customer_id = ?"
        params.append(customer_id)

    # Apply sort order
    if sort_by == "age_asc":
        sql += " ORDER BY a.created_at ASC LIMIT ?"
    elif sort_by == "age_desc":
        sql += " ORDER BY a.created_at DESC LIMIT ?"
    else:
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
    # When using age-based sorting, preserve SQL sort order; otherwise apply category/score sort
    if sort_by not in ("age_asc", "age_desc"):
        out.sort(key=lambda a: (CATEGORY_RANK.get(a["category"], 9), -a["score"]))
    return out


def alert_queue_grouped(
    conn: sqlite3.Connection, org_id: int, status: str | None = "open", limit: int = 200,
) -> list[dict[str, Any]]:
    """Alerts bucketed by customer, for the group-by-customer view."""
    flat = alert_queue(conn, org_id, status=status, limit=limit)
    buckets: dict[int | None, dict[str, Any]] = {}
    for a in flat:
        cid = a.get("customer_id")
        if cid not in buckets:
            buckets[cid] = {
                "customer_id": cid,
                "customer_name": a.get("customer_name") or a.get("query_name") or "Ad-hoc",
                "reference": a.get("reference", ""),
                "alerts": [],
            }
        buckets[cid]["alerts"].append(a)
    return sorted(buckets.values(), key=lambda g: g["customer_name"] or "")


def entity_names(conn: sqlite3.Connection, entity_id: int) -> list[dict[str, str]]:
    return [
        {"name": r["name"], "type": r["name_type"], "script": r["script"]}
        for r in conn.execute(
            "SELECT name, name_type, script FROM entity_names WHERE entity_id=? ORDER BY id",
            (entity_id,),
        )
    ]


_CUSTOMER_SELECT = """\
SELECT c.id, c.reference, c.full_name, c.name_arabic, c.customer_type,
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
"""


def _customer_rows_to_list(rows) -> list[dict[str, Any]]:
    today = datetime.now(timezone.utc).date().isoformat()
    return [
        dict(r) | {"review_overdue": bool(r["next_review"] and r["next_review"] <= today)}
        for r in rows
    ]


def customer_list(conn: sqlite3.Connection, org_id: int) -> list[dict[str, Any]]:
    """Customers of one organization, with their latest risk rating and
    screening activity."""
    rows = conn.execute(
        _CUSTOMER_SELECT + "WHERE c.org_id = ? ORDER BY c.created_at DESC",
        (org_id,),
    ).fetchall()
    return _customer_rows_to_list(rows)


def search_customers(
    conn: sqlite3.Connection, org_id: int, query: str
) -> list[dict[str, Any]]:
    """Search customers by name, reference, or Arabic name with canonicalization.

    Matches against: full_name (LIKE), name_arabic (LIKE), reference (LIKE),
    and canonical_key (prefix match on each canonical token from the query).
    """
    query = query.strip()
    if not query:
        return customer_list(conn, org_id)

    from .names.arabic import canonical_tokens, has_arabic_script, normalize_arabic

    like = f"%{query}%"
    params: list = [org_id, like, like, like]

    canon_clause = ""
    tokens = canonical_tokens(query)
    if tokens:
        canon_conditions = []
        for tok in tokens:
            canon_conditions.append("c.canonical_key LIKE ?")
            params.append(f"%{tok}%")
        canon_clause = " OR (" + " AND ".join(canon_conditions) + ")"

    arabic_canon_clause = ""
    if has_arabic_script(query):
        normalized = normalize_arabic(query)
        if normalized:
            arabic_canon_clause = " OR c.name_arabic LIKE ?"
            params.append(f"%{normalized}%")

    sql = (
        _CUSTOMER_SELECT
        + "WHERE c.org_id = ? AND ("
        + "c.full_name LIKE ? COLLATE NOCASE"
        + " OR c.reference LIKE ? COLLATE NOCASE"
        + " OR c.name_arabic LIKE ?"
        + canon_clause
        + arabic_canon_clause
        + ") ORDER BY c.created_at DESC"
    )
    rows = conn.execute(sql, params).fetchall()
    return _customer_rows_to_list(rows)


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

    alerts = alert_queue(conn, org_id, status=None, customer_id=customer_id)

    notes = case_notes(conn, customer_id, org_id)

    return {
        "customer": dict(row),
        "ubos": ubos,
        "risk": risks[0] if risks else None,
        "risk_history": risks,
        "screenings": screenings,
        "alerts": alerts,
        "notes": notes,
        "transactions": transactions_for_customer(conn, customer_id, org_id),
        "transaction_alerts": transaction_alert_queue(
            conn, org_id, status=None, customer_id=customer_id
        ),
        "signatures": signatures_for_customer(conn, customer_id, org_id),
        "adverse_media": adverse_media_for_customer(conn, customer_id, org_id),
        "adverse_media_runs": adverse_media_runs(conn, customer_id, org_id),
        "documents": documents_for_customer(conn, customer_id, org_id),
        "audit": audit_trail(conn, org_id, "customer", customer_id),
    }


def transactions_for_customer(
    conn: sqlite3.Connection, customer_id: int, org_id: int, limit: int = 200
) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM transactions WHERE customer_id=? AND org_id=?"
        " ORDER BY occurred_at DESC LIMIT ?",
        (customer_id, org_id, limit))]


def transaction_alert_queue(
    conn: sqlite3.Connection, org_id: int, status: str | None = "open", limit: int = 200,
    customer_id: int | None = None
) -> list[dict[str, Any]]:
    """Transaction-monitoring alerts with enough transaction/customer context
    to triage them, scoped to one organization. Mirrors alert_queue's shape
    (category-like `rule_key`, `detail`) so the dashboard/alerts templates
    can render both alert types with similar markup."""
    sql = """
        SELECT ta.id, ta.rule_key, ta.severity, ta.detail, ta.status,
               ta.disposition, ta.dispositioned_by, ta.dispositioned_at,
               ta.assigned_to, ta.created_at,
               t.id AS transaction_id, t.amount, t.currency, t.amount_aed,
               t.method, t.direction, t.counterparty_name, t.counterparty_country,
               t.occurred_at,
               c.id AS customer_id, c.reference, c.full_name AS customer_name
        FROM transaction_alerts ta
        JOIN transactions t ON t.id = ta.transaction_id
        JOIN customers c    ON c.id = ta.customer_id
        WHERE ta.org_id = ?
    """
    params: list[Any] = [org_id]
    if status:
        sql += " AND ta.status = ?"
        params.append(status)
    if customer_id is not None:
        sql += " AND ta.customer_id = ?"
        params.append(customer_id)
    sql += " ORDER BY ta.created_at DESC LIMIT ?"

    out: list[dict[str, Any]] = []
    for row in conn.execute(sql, (*params, limit)):
        out.append(dict(row) | {"detail": json.loads(row["detail"] or "{}")})
    return out


def signatures_for_customer(
    conn: sqlite3.Connection, customer_id: int, org_id: int
) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM signatures WHERE customer_id=? AND org_id=? ORDER BY signed_at DESC",
        (customer_id, org_id))]


def audit_trail(
    conn: sqlite3.Connection, org_id: int, object_type: str | None = None,
    object_id: int | str | None = None, limit: int = 200, offset: int = 0,
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
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.append(limit)
    params.append(offset)
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


def case_notes(conn: sqlite3.Connection, customer_id: int, org_id: int) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT id, author, body, created_at FROM case_notes"
        " WHERE customer_id=? AND org_id=? ORDER BY id DESC",
        (customer_id, org_id))]


def org_alert_threshold(conn: sqlite3.Connection, org_id: int) -> float | None:
    """The org's configured alert threshold, or None to use the engine
    default. A single global knob, not per-list-type "screening profiles" --
    see the design note in cases/review.py on deliberately avoiding that
    complexity without an evidenced need for it."""
    row = conn.execute(
        "SELECT alert_threshold FROM org_settings WHERE org_id=?", (org_id,)
    ).fetchone()
    return row["alert_threshold"] if row and row["alert_threshold"] is not None else None


def report_list(conn: sqlite3.Connection, org_id: int) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT r.id, r.report_type, r.reference, r.status, r.created_at, r.submitted_at, c.full_name AS customer_name "
        "FROM reports r LEFT JOIN customers c ON c.id = r.customer_id "
        "WHERE r.org_id=? ORDER BY r.created_at DESC", (org_id,))]


def report(conn: sqlite3.Connection, report_id: int, org_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT r.*, c.full_name AS customer_name FROM reports r "
        "LEFT JOIN customers c ON c.id = r.customer_id "
        "WHERE r.id=? AND r.org_id=?", (report_id, org_id)).fetchone()
    return dict(row) if row else None


def documents_for_customer(
    conn: sqlite3.Connection, customer_id: int, org_id: int
) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT id, doc_type, filename, sha256, uploaded_at FROM documents"
        " WHERE customer_id=? AND org_id=? ORDER BY uploaded_at DESC",
        (customer_id, org_id))]


def adverse_media_for_customer(
    conn: sqlite3.Connection, customer_id: int, org_id: int, limit: int = 200
) -> list[dict[str, Any]]:
    """Adverse-media findings for one customer, worst and least-reviewed first.

    Ordered by status before severity: an open financial-crime finding and an
    already-dismissed one are not equally urgent, and a triage list that
    buries the undecided rows under settled ones is a list nobody works
    through.
    """
    rows = conn.execute(
        """SELECT * FROM adverse_media_findings
           WHERE org_id=? AND customer_id=?
           ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'relevant' THEN 1 ELSE 2 END,
                    CASE severity
                        WHEN 'financial_crime_alleged' THEN 0
                        WHEN 'regulatory_action' THEN 1
                        WHEN 'reputational_only' THEN 2 ELSE 3 END,
                    CASE name_evidence WHEN 'title' THEN 0 ELSE 1 END,
                    published_at DESC
           LIMIT ?""",
        (org_id, customer_id, limit),
    ).fetchall()
    return [dict(r) | {"matched_terms": json.loads(r["matched_terms"] or "[]")} for r in rows]


def adverse_media_runs(
    conn: sqlite3.Connection, customer_id: int, org_id: int, limit: int = 50
) -> list[dict[str, Any]]:
    """History of adverse-media checks for one customer, including failed ones.

    Failed runs are returned deliberately. The evidence pack has to be able to
    say "checked on this date, provider unreachable" -- omitting those would
    make a file with a broken check look exactly like one with a clean result.
    """
    return [dict(r) for r in conn.execute(
        "SELECT * FROM adverse_media_screenings WHERE org_id=? AND customer_id=?"
        " ORDER BY run_at DESC LIMIT ?",
        (org_id, customer_id, limit))]


def adverse_media_queue(
    conn: sqlite3.Connection, org_id: int, status: str | None = "open", limit: int = 200
) -> list[dict[str, Any]]:
    """Org-wide adverse-media findings with customer context, for triage.

    Mirrors alert_queue/transaction_alert_queue's shape so the alerts page can
    render a third finding type without a third set of markup conventions.
    """
    sql = """
        SELECT f.*, c.reference, c.full_name AS customer_name
        FROM adverse_media_findings f
        LEFT JOIN customers c ON c.id = f.customer_id
        WHERE f.org_id = ?
    """
    params: list[Any] = [org_id]
    if status:
        sql += " AND f.status = ?"
        params.append(status)
    sql += (" ORDER BY CASE f.severity"
            "   WHEN 'financial_crime_alleged' THEN 0"
            "   WHEN 'regulatory_action' THEN 1"
            "   WHEN 'reputational_only' THEN 2 ELSE 3 END,"
            " f.created_at DESC LIMIT ?")
    return [dict(r) | {"matched_terms": json.loads(r["matched_terms"] or "[]")}
            for r in conn.execute(sql, (*params, limit))]



# ---------------------------------------------------------------------- super-admin queries
def console_overview(conn: sqlite3.Connection) -> dict[str, Any]:
    """Multi-org dashboard for super-admin users.

    Returns aggregated stats across all active organizations for the consultant
    view. This is the core Position 1 pilot feature: one login, multiple orgs.
    """
    from .ingest.loader import staleness_report

    # Get all active organizations
    orgs_rows = conn.execute(
        "SELECT id, name, slug, created_at FROM organizations WHERE status='active' ORDER BY name"
    ).fetchall()
    orgs = [dict(r) for r in orgs_rows]

    # Aggregate stats across all orgs
    for org in orgs:
        org_id = org["id"]

        # Open alerts count by category
        alerts = alert_queue(conn, org_id, status="open")
        by_category: dict[str, int] = {}
        for a in alerts:
            by_category[a["category"]] = by_category.get(a["category"], 0) + 1

        # Basic counts
        counts = conn.execute(
            """SELECT
                 (SELECT COUNT(*) FROM customers WHERE status='active' AND org_id=?) AS customers,
                 (SELECT COUNT(*) FROM alerts WHERE status='open' AND org_id=?)       AS open_alerts,
                 (SELECT COUNT(*) FROM screenings WHERE org_id=?)                     AS screenings""",
            (org_id, org_id, org_id),
        ).fetchone()

        # High-risk customers
        high_risk = conn.execute(
            """SELECT COUNT(*) c FROM customers c
               WHERE c.org_id=? AND c.status='active' AND EXISTS (
                 SELECT 1 FROM risk_assessments r WHERE r.customer_id=c.id AND r.rating='high'
                 AND r.id = (SELECT id FROM risk_assessments WHERE customer_id=c.id
                             ORDER BY assessed_at DESC LIMIT 1))""",
            (org_id,),
        ).fetchone()["c"]

        org["customers"] = counts["customers"]
        org["open_alerts"] = counts["open_alerts"]
        org["screenings"] = counts["screenings"]
        org["high_risk"] = high_risk
        org["alerts_by_category"] = by_category

    # Global staleness report (shared across all orgs)
    staleness = staleness_report(conn)
    breaches = [d for d in staleness if d["breach"]]

    # Organization-level staleness: track which orgs have been notified
    org_staleness = []
    for org in orgs:
        org_breach_count = len(breaches)
        org_staleness.append({
            "org_id": org["id"],
            "org_name": org["name"],
            "breaches": org_breach_count,
            "compliant": org_breach_count == 0,
        })

    return {
        "organizations": orgs,
        "total_orgs": len(orgs),
        "total_customers": sum(o["customers"] for o in orgs),
        "total_open_alerts": sum(o["open_alerts"] for o in orgs),
        "total_high_risk": sum(o["high_risk"] for o in orgs),
        "staleness": staleness,
        "breaches": breaches,
        "org_staleness": org_staleness,
    }


def org_alerts(conn: sqlite3.Connection, org_id: int, status: str | None = "open") -> list[dict[str, Any]]:
    """All alerts for a specific org, for super-admin drill-down."""
    return alert_queue(conn, org_id, status=status)


def org_customers(conn: sqlite3.Connection, org_id: int) -> list[dict[str, Any]]:
    """All customers for a specific org, for super-admin drill-down."""
    return customer_list(conn, org_id)


def freeze_obligations_list(conn: sqlite3.Connection, org_id: int, filter_status: str = "all") -> list[dict[str, Any]]:
    """List all freeze obligations for an org, optionally filtered by status."""
    query = """
        SELECT f.*, c.reference AS customer_reference, c.full_name,
               CAST((julianday('now') - julianday(f.identified_at)) * 24 AS INTEGER) AS hours_since_identified
        FROM freeze_obligations f
        JOIN customers c ON c.id = f.customer_id
        WHERE f.org_id = ?
    """
    params = [org_id]

    if filter_status != "all":
        query += " AND f.status = ?"
        params.append(filter_status)

    query += " ORDER BY f.identified_at DESC"

    return [dict(row) for row in conn.execute(query, params).fetchall()]


def freeze_obligations_stats(conn: sqlite3.Connection, org_id: int) -> dict[str, int]:
    """Count of freeze obligations by status for an org."""
    return dict(conn.execute("""
        SELECT status, COUNT(*) as count
        FROM freeze_obligations
        WHERE org_id = ?
        GROUP BY status
    """, (org_id,)).fetchall())


def freeze_obligation_detail(conn: sqlite3.Connection, org_id: int, freeze_id: int) -> dict[str, Any] | None:
    """Get full freeze obligation details including related customer, alert, and report."""
    row = conn.execute("""
        SELECT f.*, c.reference AS customer_reference, c.full_name,
               a.id AS alert_id, a.matched_name,
               r.id AS report_id, r.reference AS report_reference
        FROM freeze_obligations f
        JOIN customers c ON c.id = f.customer_id
        LEFT JOIN alerts a ON a.id = f.alert_id
        LEFT JOIN reports r ON r.id = f.report_id
        WHERE f.id = ? AND f.org_id = ?
    """, (freeze_id, org_id)).fetchone()

    if not row:
        return None

    obligation = dict(row)
    obligation["assets_frozen_parsed"] = json.loads(obligation["assets_frozen"] or "[]")
    return obligation



def compliance_deadlines(conn: sqlite3.Connection, org_id: int) -> list[dict[str, Any]]:
    """All compliance deadlines for an org, ordered by due date."""
    rows = conn.execute("""
        SELECT id, title, description, due_date, recurrence,
               reminder_days_before, completed_at, created_at
        FROM compliance_deadlines
        WHERE org_id = ?
        ORDER BY due_date ASC
    """, (org_id,)).fetchall()
    return [dict(row) for row in rows]


def compliance_deadline(conn: sqlite3.Connection, org_id: int, deadline_id: int) -> dict[str, Any] | None:
    """Single compliance deadline, org-isolated."""
    row = conn.execute("""
        SELECT id, title, description, due_date, recurrence,
               reminder_days_before, completed_at, created_at
        FROM compliance_deadlines
        WHERE id = ? AND org_id = ?
    """, (deadline_id, org_id)).fetchone()
    return dict(row) if row else None
