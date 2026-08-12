"""CDD/EDD case management.

Ties screening and risk rating into a single customer record that can survive
an inspection. Three obligations drive the design:

* **Screen the whole graph.** MOET requires screening customers, potential
  clients, transaction parties, beneficial owners and related persons. Cheap
  tools commonly screen only the contracting party; onboarding here screens
  every UBO as a matter of course.
* **Identify the UBO at 25%, with fallback.** Cabinet Res. 134/2025 sets the
  threshold and requires falling back to the senior managing official where no
  one meets it. Inability to identify a UBO is scored as opacity, not ignored.
* **Retain for five years after the relationship ends.** The retention date is
  computed and stored rather than left to policy.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..db import audit, utcnow
from ..match.engine import ScreeningResult, screen
from ..names.arabic import canonical_key
from ..risk.model import CustomerProfile, RiskAssessment, assess, save as save_risk

UBO_THRESHOLD_PCT = 25.0
RETENTION_YEARS = 5


@dataclass(slots=True)
class OnboardingResult:
    customer_id: int
    reference: str
    screening: ScreeningResult
    ubo_screenings: list[tuple[str, ScreeningResult]]
    risk: RiskAssessment
    blocked: bool

    def summary(self) -> str:
        lines = [
            f"Customer {self.reference} (#{self.customer_id})",
            f"  {self.screening.summary()}",
        ]
        for name, res in self.ubo_screenings:
            lines.append(f"  UBO {name}: {res.summary()}")
        lines.append("  " + self.risk.explain().replace("\n", "\n  "))
        if self.blocked:
            lines.append(
                "  *** BLOCKED: sanctions match. Freeze without delay, do not tip off, "
                "report to supervisor and FIU. ***"
            )
        return "\n".join(lines)


def onboard(
    conn: sqlite3.Connection,
    *,
    reference: str,
    full_name: str,
    customer_type: str = "natural",
    name_arabic: str | None = None,
    nationality: str | None = None,
    country: str | None = None,
    birth_date: str | None = None,
    gender: str | None = None,
    id_number: str | None = None,
    id_type: str | None = None,
    trade_licence: str | None = None,
    sector: str = "other",
    delivery_channel: str = "face_to_face",
    cash_level: str = "non_cash",
    jurisdiction_tier: str = "standard",
    structure: str = "natural_person",
    ubos: list[dict[str, Any]] | None = None,
    actor: str = "system",
) -> OnboardingResult:
    """Create a customer, screen them and their UBOs, and assign a risk rating.

    Screening happens before the risk rating because a sanctions hit forces the
    rating to high regardless of every other factor -- the two are not
    independent inputs.
    """
    now = utcnow()
    ck = canonical_key(full_name)

    with conn:
        cur = conn.execute(
            """INSERT INTO customers
               (reference, customer_type, full_name, name_arabic, canonical_key,
                nationality, country, birth_date, gender, id_number, id_type,
                trade_licence, sector, delivery_channel, is_cash_intensive,
                onboarded_at, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                reference, customer_type, full_name, name_arabic, ck,
                nationality, country, birth_date, gender, id_number, id_type,
                trade_licence, sector, delivery_channel,
                int(cash_level == "predominantly_cash"),
                now, now, now,
            ),
        )
        customer_id = cur.lastrowid
        audit(conn, actor, "customer.onboard", "customer", customer_id,
              {"reference": reference, "name": full_name})

    # --- screen the customer, in both scripts where available --------------
    result = screen(
        conn, full_name, trigger="onboarding", country=nationality,
        birth_date=birth_date, gender=gender, customer_id=customer_id, actor=actor,
    )
    if name_arabic:
        ar = screen(
            conn, name_arabic, trigger="onboarding", country=nationality,
            birth_date=birth_date, gender=gender, customer_id=customer_id, actor=actor,
        )
        # Keep whichever script produced the stronger evidence.
        if ar.hits and (not result.hits or max(h.score for h in ar.hits) > max(h.score for h in result.hits)):
            result = ar

    # --- beneficial owners --------------------------------------------------
    ubo_results: list[tuple[str, ScreeningResult]] = []
    for ubo in ubos or []:
        ubo_id = add_ubo(conn, customer_id, actor=actor, **ubo)
        res = screen(
            conn, ubo["person_name"], trigger="onboarding",
            country=ubo.get("nationality"), birth_date=ubo.get("birth_date"),
            customer_id=customer_id, ubo_id=ubo_id, actor=actor,
        )
        ubo_results.append((ubo["person_name"], res))

    sanctions_hit = any(h.is_sanction for h in result.hits) or any(
        h.is_sanction for _, r in ubo_results for h in r.hits
    )
    pep_status = "domestic_pep" if any(h.is_pep for h in result.hits) else None

    risk = assess(
        CustomerProfile(
            pep_status=pep_status,
            jurisdiction_tier=jurisdiction_tier,
            sector=sector,
            ownership_state=ownership_state(conn, customer_id, customer_type),
            delivery_channel=delivery_channel,
            cash_level=cash_level,
            structure=structure,
            sanctions_hit=sanctions_hit,
        )
    )
    save_risk(conn, customer_id, risk, actor=actor)

    return OnboardingResult(
        customer_id=customer_id,
        reference=reference,
        screening=result,
        ubo_screenings=ubo_results,
        risk=risk,
        blocked=sanctions_hit,
    )


def add_ubo(
    conn: sqlite3.Connection,
    customer_id: int,
    *,
    person_name: str,
    name_arabic: str | None = None,
    nationality: str | None = None,
    birth_date: str | None = None,
    ownership_pct: float | None = None,
    control_type: str = "ownership",
    notes: str | None = None,
    actor: str = "system",
) -> int:
    """Record a beneficial owner.

    `is_ubo` is set from the 25% threshold, except where control is recorded as
    senior managing official -- the regulation's explicit fallback when no
    natural person meets the ownership test.
    """
    is_ubo = control_type == "senior_official" or (
        ownership_pct is not None and ownership_pct >= UBO_THRESHOLD_PCT
    )
    with conn:
        cur = conn.execute(
            """INSERT INTO ubo_links
               (customer_id, person_name, name_arabic, canonical_key, nationality,
                birth_date, ownership_pct, control_type, is_ubo, notes, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                customer_id, person_name, name_arabic, canonical_key(person_name),
                nationality, birth_date, ownership_pct, control_type,
                int(is_ubo), notes, utcnow(),
            ),
        )
        audit(conn, actor, "ubo.add", "customer", customer_id,
              {"person": person_name, "pct": ownership_pct, "is_ubo": is_ubo})
        return cur.lastrowid


def ownership_state(
    conn: sqlite3.Connection, customer_id: int, customer_type: str = "legal"
) -> str:
    """Derive an ownership-opacity band from recorded UBO data.

    A legal person with no identified UBO scores as `ubo_undisclosed` rather
    than as transparent-by-default. Absence of evidence is a risk indicator
    here, and defaulting the other way would understate risk exactly where the
    regulation is most concerned.
    """
    if customer_type == "natural":
        return "fully_transparent"

    rows = conn.execute(
        "SELECT ownership_pct, control_type, is_ubo FROM ubo_links WHERE customer_id=?",
        (customer_id,),
    ).fetchall()
    if not rows:
        return "ubo_undisclosed"

    if any(r["control_type"] == "nominee" for r in rows):
        return "nominee_or_bearer"
    if not any(r["is_ubo"] for r in rows):
        return "ubo_undisclosed"

    identified = sum(r["ownership_pct"] or 0 for r in rows if r["is_ubo"])
    if identified < 50:
        return "multi_layer_offshore"
    if identified < 75:
        return "single_layer_foreign"
    return "fully_transparent"


def disposition_alert(
    conn: sqlite3.Connection,
    alert_id: int,
    status: str,
    *,
    by: str,
    notes: str = "",
) -> None:
    """Record a human decision on an alert.

    Dispositions are the record that a person -- not a threshold -- decided the
    outcome. The original score and its breakdown are never overwritten.
    """
    valid = {"true_positive", "false_positive", "escalated", "open"}
    if status not in valid:
        raise ValueError(f"invalid disposition {status!r}; expected one of {sorted(valid)}")

    with conn:
        conn.execute(
            """UPDATE alerts SET status=?, disposition=?, dispositioned_by=?,
               dispositioned_at=? WHERE id=?""",
            (status, notes, by, utcnow(), alert_id),
        )
        audit(conn, by, "alert.disposition", "alert", alert_id,
              {"status": status, "notes": notes})


def close_relationship(conn: sqlite3.Connection, customer_id: int, actor: str = "system") -> str:
    """Mark a customer inactive and set the 5-year retention date."""
    until = (date.today() + timedelta(days=365 * RETENTION_YEARS)).isoformat()
    with conn:
        conn.execute(
            "UPDATE customers SET status='closed', retention_until=?, updated_at=? WHERE id=?",
            (until, utcnow(), customer_id),
        )
        audit(conn, actor, "customer.close", "customer", customer_id, {"retention_until": until})
    return until


def due_for_review(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Customers whose periodic review date has passed.

    Periodic review is an obligation, not a nicety: EOCN requires re-screening
    at periodic KYC review as well as on list updates.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    rows = conn.execute(
        """SELECT c.id, c.reference, c.full_name, r.rating, r.next_review
           FROM customers c
           JOIN risk_assessments r ON r.id = (
               SELECT id FROM risk_assessments WHERE customer_id=c.id
               ORDER BY assessed_at DESC LIMIT 1)
           WHERE c.status='active' AND r.next_review IS NOT NULL AND r.next_review <= ?
           ORDER BY r.next_review""",
        (today,),
    ).fetchall()
    return [dict(r) for r in rows]
