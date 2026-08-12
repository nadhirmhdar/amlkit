"""Alert disposition and four-eyes review.

Two research findings shaped this, and both cut against the obvious design.

**Mandatory free text produces thin records.** Programmes that generate weak
disposition notes accumulate inspection findings even when their dispositions
were correct, because the regulator cannot verify decision quality without the
reasoning. But 85-95% of screening alerts are false positives, and demanding a
written sentence on every one degrades into "FP" typed a hundred times -- the
same thin record, reached more slowly. So routine closes take a structured
reason code (fast, consistent, aggregable) and narrative is required only where
the reasoning genuinely must be reconstructable: true positives and escalations.

**Universal four-eyes deadlocks small firms.** The four-eyes literature comes
from banks with compliance teams. A DNFBP with one MLRO cannot produce a second
reviewer, so a universal requirement gets disabled or worked around by sharing a
login -- worse than not having it. Independent review therefore attaches only to
the genuinely dangerous decision: *dismissing* a sanctions or PF match. A
confirmed match escalates to freeze and reporting anyway, which brings its own
scrutiny. Firms with one officer set `single_operator_mode`, which records the
absent review on the alert rather than pretending it happened.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass

from ..db import audit, utcnow
from ..screening.pf import classify_programs

# Structured closure reasons. Aggregating these is what tells you a threshold
# needs tuning -- "43% of dismissals were different_dob" is actionable in a way
# that a pile of free text is not.
REASON_CODES: dict[str, str] = {
    "different_dob": "Date of birth does not match",
    "different_nationality": "Nationality or country does not match",
    "name_coincidence": "Name coincidence - different person",
    "different_entity_type": "Different entity type (person vs organisation)",
    "insufficient_data": "Insufficient data to clear - kept open for enquiry",
    "confirmed_match": "Confirmed match to the listed party",
    "other": "Other - see narrative",
}

DISPOSITIONS = ("true_positive", "false_positive", "escalated", "open")

# Dispositions whose reasoning must be reconstructable in words.
NARRATIVE_REQUIRED = ("true_positive", "escalated")

# Reason codes that cannot stand alone whatever the disposition.
NARRATIVE_REQUIRED_CODES = ("other", "insufficient_data")

PENDING = "pending_review"


class ReviewError(RuntimeError):
    """Raised when a disposition would breach the evidence or review standard."""


@dataclass(slots=True)
class ReviewOutcome:
    alert_id: int
    status: str
    awaiting_second_review: bool
    independent_review: str
    message: str


def single_operator_mode() -> bool:
    """Whether the firm runs with one compliance officer.

    Defaults to False -- the stronger control. A firm that genuinely has one
    officer hits a clear error telling them how to enable this, which is better
    than silently weakening four-eyes for everyone.
    """
    return os.environ.get("AMLKIT_SINGLE_OPERATOR_MODE", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _alert_categories(
    conn: sqlite3.Connection, alert_id: int, org_id: int
) -> tuple[set[str], list[str]]:
    """Risk categories and topics for the entity behind an alert.

    Filters on `a.org_id=?` as part of the fetch itself, not as a separate
    check afterward -- an alert belonging to a different org is
    indistinguishable from one that does not exist, by design (see the
    equivalent "404, not filtered-empty" rule applied to every ID-in-URL
    route in api/app.py).
    """
    row = conn.execute(
        """SELECT e.topics, e.programs FROM alerts a
           JOIN entities e ON e.id = a.entity_id WHERE a.id=? AND a.org_id=?""",
        (alert_id, org_id),
    ).fetchone()
    if row is None:
        raise ReviewError(f"alert {alert_id} not found")
    programs = json.loads(row["programs"] or "[]")
    topics = json.loads(row["topics"] or "[]")
    return classify_programs(programs), topics


def needs_independent_review(
    conn: sqlite3.Connection, alert_id: int, org_id: int, status: str
) -> bool:
    """True when dismissing this alert requires a second pair of eyes.

    Only dismissal of a sanctions, PF or TF match qualifies. Confirming a match
    does not: that path leads to freezing and reporting, which is scrutinised in
    its own right.
    """
    if status != "false_positive":
        return False
    categories, topics = _alert_categories(conn, alert_id, org_id)
    return bool(categories) or "sanction" in topics


def _validate(status: str, reason_code: str, narrative: str) -> None:
    if status not in DISPOSITIONS:
        raise ReviewError(f"invalid disposition {status!r}; expected one of {DISPOSITIONS}")
    if reason_code not in REASON_CODES:
        raise ReviewError(
            f"invalid reason code {reason_code!r}; expected one of {sorted(REASON_CODES)}"
        )
    narrative = (narrative or "").strip()
    if status in NARRATIVE_REQUIRED and not narrative:
        raise ReviewError(
            f"a written narrative is required for a {status.replace('_', ' ')} - "
            "this is the record a supervisor reconstructs the decision from"
        )
    if reason_code in NARRATIVE_REQUIRED_CODES and not narrative:
        raise ReviewError(
            f"reason code {reason_code!r} requires a narrative explaining it"
        )


def propose_disposition(
    conn: sqlite3.Connection,
    alert_id: int,
    *,
    org_id: int,
    status: str,
    reason_code: str,
    operator: str,
    narrative: str = "",
) -> ReviewOutcome:
    """Record a disposition, or stage it for independent review.

    Applies immediately unless the decision is dismissing a sanctions/PF match
    and the firm is not in single-operator mode, in which case the alert moves
    to `pending_review` and awaits a different operator.
    """
    if not (operator or "").strip():
        raise ReviewError("an operator identity is required to disposition an alert")
    _validate(status, reason_code, narrative)

    # needs_independent_review() only checks alert ownership when status is
    # false_positive (it short-circuits for the others) -- so the UPDATE
    # below carries its own "AND org_id=?" and checks rowcount, which is the
    # actual ownership enforcement point for true_positive/escalated/open.
    # A cross-tenant alert_id ends up indistinguishable from a nonexistent
    # one either way, which is the property that matters.
    second_review = needs_independent_review(conn, alert_id, org_id, status)
    solo = single_operator_mode()

    if second_review and not solo:
        applied_status = PENDING
        independent = "pending"
        awaiting = True
        message = "Staged for independent review - a second operator must confirm."
    else:
        applied_status = status
        independent = (
            "single_operator" if (second_review and solo)
            else ("not_required" if not second_review else "completed")
        )
        awaiting = False
        message = (
            "Recorded. NOTE: no independent review - firm is in single-operator mode."
            if independent == "single_operator"
            else "Disposition recorded."
        )

    now = utcnow()
    with conn:
        conn.execute(
            """INSERT INTO alert_reviews
               (org_id, alert_id, action, status, reason_code, narrative, operator, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (org_id, alert_id, "propose", status, reason_code,
             narrative.strip() or None, operator, now),
        )
        cur = conn.execute(
            """UPDATE alerts SET status=?, disposition=?, reason_code=?,
               independent_review=?, dispositioned_by=?, dispositioned_at=?
               WHERE id=? AND org_id=?""",
            (applied_status, narrative.strip() or REASON_CODES[reason_code],
             reason_code, independent, operator, now, alert_id, org_id),
        )
        if cur.rowcount == 0:
            raise ReviewError(f"alert {alert_id} not found")
        audit(conn, operator, "alert.propose", "alert", alert_id,
              {"status": status, "reason_code": reason_code,
               "awaiting_second_review": awaiting, "independent_review": independent},
              org_id=org_id)

    return ReviewOutcome(alert_id, applied_status, awaiting, independent, message)


def confirm_disposition(
    conn: sqlite3.Connection,
    alert_id: int,
    *,
    org_id: int,
    operator: str,
    agree: bool = True,
    reason_code: str | None = None,
    narrative: str = "",
) -> ReviewOutcome:
    """Second-operator confirmation of a staged dismissal.

    The confirming operator must differ from the proposing one -- that
    separation is the entire control, so it is enforced rather than advised.
    """
    if not (operator or "").strip():
        raise ReviewError("an operator identity is required to confirm a disposition")

    proposal = conn.execute(
        """SELECT status, reason_code, narrative, operator FROM alert_reviews
           WHERE alert_id=? AND org_id=? AND action='propose' ORDER BY id DESC LIMIT 1""",
        (alert_id, org_id),
    ).fetchone()
    if proposal is None:
        raise ReviewError(f"alert {alert_id} has no proposed disposition to confirm")

    current = conn.execute(
        "SELECT status FROM alerts WHERE id=? AND org_id=?", (alert_id, org_id)
    ).fetchone()
    if current is None:
        raise ReviewError(f"alert {alert_id} not found")
    if current["status"] != PENDING:
        raise ReviewError(f"alert {alert_id} is not awaiting review (status={current['status']})")

    if operator.strip() == (proposal["operator"] or "").strip():
        raise ReviewError(
            "independent review requires a different operator than the one who "
            "proposed the disposition. If this firm has a single compliance "
            "officer, set AMLKIT_SINGLE_OPERATOR_MODE=1 - the absence of "
            "independent review is then recorded on the alert rather than hidden."
        )

    if agree:
        status = proposal["status"]
        code = proposal["reason_code"]
        note = narrative.strip() or (proposal["narrative"] or "")
        action = "confirm"
    else:
        # An override is itself a disposition and must meet the same standard.
        status = "escalated"
        code = reason_code or "other"
        note = narrative.strip()
        action = "override"
        _validate(status, code, note)

    now = utcnow()
    with conn:
        conn.execute(
            """INSERT INTO alert_reviews
               (org_id, alert_id, action, status, reason_code, narrative, operator, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (org_id, alert_id, action, status, code, note or None, operator, now),
        )
        cur = conn.execute(
            """UPDATE alerts SET status=?, disposition=?, reason_code=?,
               independent_review='completed', dispositioned_by=?, dispositioned_at=?
               WHERE id=? AND org_id=?""",
            (status, note or REASON_CODES.get(code, code), code, operator, now, alert_id, org_id),
        )
        if cur.rowcount == 0:
            raise ReviewError(f"alert {alert_id} not found")
        audit(conn, operator, f"alert.{action}", "alert", alert_id,
              {"status": status, "reason_code": code,
               "proposed_by": proposal["operator"]}, org_id=org_id)

    return ReviewOutcome(
        alert_id, status, False, "completed",
        "Independent review completed." if agree else "Overridden and escalated.",
    )


def review_history(conn: sqlite3.Connection, alert_id: int, org_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT action, status, reason_code, narrative, operator, created_at
           FROM alert_reviews WHERE alert_id=? AND org_id=? ORDER BY id""",
        (alert_id, org_id),
    ).fetchall()
    return [dict(r) | {"reason_label": REASON_CODES.get(r["reason_code"], r["reason_code"])}
            for r in rows]
