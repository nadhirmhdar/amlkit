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
from ..match.engine import DEFAULT_THRESHOLD, ScreeningResult, screen
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
            # State the specific obligation rather than a generic block. PF and
            # TF are distinct offences under Law 10/2025 and the operator acting
            # on the alert may not know which regime a designation falls under.
            for note in sorted(self.obligations):
                lines.append(f"  *** {note} ***")
        return "\n".join(lines)

    @property
    def all_hits(self) -> list:
        hits = list(self.screening.hits)
        for _, res in self.ubo_screenings:
            hits.extend(res.hits)
        return hits

    @property
    def obligations(self) -> set[str]:
        return {h.obligation for h in self.all_hits}

    @property
    def has_proliferation_hit(self) -> bool:
        return any(h.is_proliferation for h in self.all_hits)


def onboard(
    conn: sqlite3.Connection,
    *,
    org_id: int,
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
    threshold: float = DEFAULT_THRESHOLD,
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
               (org_id, reference, customer_type, full_name, name_arabic, canonical_key,
                nationality, country, birth_date, gender, id_number, id_type,
                trade_licence, sector, delivery_channel, is_cash_intensive,
                onboarded_at, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                org_id, reference, customer_type, full_name, name_arabic, ck,
                nationality, country, birth_date, gender, id_number, id_type,
                trade_licence, sector, delivery_channel,
                int(cash_level == "predominantly_cash"),
                now, now, now,
            ),
        )
        customer_id = cur.lastrowid
        audit(conn, actor, "customer.onboard", "customer", customer_id,
              {"reference": reference, "name": full_name}, org_id=org_id)

    # --- screen the customer, in both scripts where available --------------
    result = screen(
        conn, full_name, org_id=org_id, trigger="onboarding", country=nationality,
        birth_date=birth_date, gender=gender, customer_id=customer_id, actor=actor,
        threshold=threshold,
    )
    if name_arabic:
        ar = screen(
            conn, name_arabic, org_id=org_id, trigger="onboarding", country=nationality,
            birth_date=birth_date, gender=gender, customer_id=customer_id, actor=actor,
            threshold=threshold,
        )
        # Keep whichever script produced the stronger evidence.
        if ar.hits and (not result.hits or max(h.score for h in ar.hits) > max(h.score for h in result.hits)):
            result = ar

    # --- beneficial owners --------------------------------------------------
    ubo_results: list[tuple[str, ScreeningResult]] = []
    for ubo in ubos or []:
        ubo_id = add_ubo(conn, customer_id, org_id=org_id, actor=actor, **ubo)
        res = screen(
            conn, ubo["person_name"], org_id=org_id, trigger="onboarding",
            country=ubo.get("nationality"), birth_date=ubo.get("birth_date"),
            customer_id=customer_id, ubo_id=ubo_id, actor=actor,
            threshold=threshold,
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
    save_risk(conn, customer_id, risk, org_id=org_id, actor=actor)

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
    org_id: int,
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
               (org_id, customer_id, person_name, name_arabic, canonical_key, nationality,
                birth_date, ownership_pct, control_type, is_ubo, notes, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                org_id, customer_id, person_name, name_arabic, canonical_key(person_name),
                nationality, birth_date, ownership_pct, control_type,
                int(is_ubo), notes, utcnow(),
            ),
        )
        audit(conn, actor, "ubo.add", "customer", customer_id,
              {"person": person_name, "pct": ownership_pct, "is_ubo": is_ubo}, org_id=org_id)
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


def close_relationship(
    conn: sqlite3.Connection, customer_id: int, org_id: int, actor: str = "system"
) -> str:
    """Mark a customer inactive and set the 5-year retention date."""
    until = (date.today() + timedelta(days=365 * RETENTION_YEARS)).isoformat()
    with conn:
        conn.execute(
            "UPDATE customers SET status='closed', retention_until=?, updated_at=?"
            " WHERE id=? AND org_id=?",
            (until, utcnow(), customer_id, org_id),
        )
        audit(conn, actor, "customer.close", "customer", customer_id,
              {"retention_until": until}, org_id=org_id)
    return until


def due_for_review(conn: sqlite3.Connection, org_id: int) -> list[dict[str, Any]]:
    """Customers of one organization whose periodic review date has passed.

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
           WHERE c.status='active' AND c.org_id=?
             AND r.next_review IS NOT NULL AND r.next_review <= ?
           ORDER BY r.next_review""",
        (org_id, today),
    ).fetchall()
    return [dict(r) for r in rows]


def record_transaction(
    conn: sqlite3.Connection,
    customer_id: int,
    org_id: int,
    *,
    direction: str,
    method: str,
    amount: float,
    currency: str = "AED",
    amount_aed: float | None = None,
    counterparty_name: str | None = None,
    counterparty_country: str | None = None,
    occurred_at: str | None = None,
    actor: str = "system",
) -> tuple[int, list]:
    """Record a transaction and evaluate it against the KYT rule set.

    `amount_aed` is required when `currency` is not AED: no FX conversion is
    performed here, so silently treating a foreign-currency amount as its AED
    face value would misprice every threshold check against it. The caller
    (the route) is expected to collect the AED-equivalent from the operator
    rather than this function guessing an exchange rate.

    Same tenant-ownership check as add_case_note above, for the same reason:
    transactions.customer_id is a bare foreign key.
    """
    from ..screening.kyt import evaluate_transaction

    if amount <= 0:
        raise ValueError("transaction amount must be positive")
    currency = (currency or "AED").strip().upper()
    if amount_aed is None:
        if currency != "AED":
            raise ValueError("amount_aed is required when currency is not AED")
        amount_aed = amount
    occurred_at = occurred_at or utcnow()
    now = utcnow()

    with conn:
        owned = conn.execute(
            "SELECT 1 FROM customers WHERE id=? AND org_id=?", (customer_id, org_id)
        ).fetchone()
        if owned is None:
            raise ValueError(f"customer {customer_id} not found")

        cur = conn.execute(
            """INSERT INTO transactions
               (org_id, customer_id, reference, direction, method, amount, currency,
                amount_aed, counterparty_name, counterparty_country, occurred_at,
                recorded_by, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                org_id, customer_id, None, direction, method, amount, currency,
                amount_aed, counterparty_name,
                (counterparty_country or "").strip().upper() or None,
                occurred_at, actor, now,
            ),
        )
        transaction_id = cur.lastrowid
        audit(conn, actor, "transaction.record", "customer", customer_id,
              {"transaction_id": transaction_id, "amount_aed": amount_aed, "method": method},
              org_id=org_id)

        triggered = evaluate_transaction(
            conn, org_id=org_id, customer_id=customer_id, transaction_id=transaction_id,
            method=method, amount_aed=amount_aed, counterparty_country=counterparty_country,
            occurred_at=occurred_at,
        )
        for rule in triggered:
            acur = conn.execute(
                """INSERT INTO transaction_alerts
                   (org_id, transaction_id, customer_id, rule_key, severity, detail, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (org_id, transaction_id, customer_id, rule.rule_key, rule.severity,
                 rule.to_detail_json(), now),
            )
            audit(conn, actor, "transaction_alert.raise", "customer", customer_id,
                  {"transaction_id": transaction_id, "alert_id": acur.lastrowid,
                   "rule": rule.rule_key, "severity": rule.severity},
                  org_id=org_id)

    return transaction_id, triggered


def disposition_transaction_alert(
    conn: sqlite3.Connection, alert_id: int, org_id: int, *,
    status: str, note: str = "", actor: str = "system",
) -> None:
    """Close out a transaction alert. No four-eyes here -- see kyt.py's
    module docstring for why that's a deliberate, narrower scope than the
    sanctions/PF disposition workflow."""
    if status not in ("true_positive", "false_positive"):
        raise ValueError(f"invalid disposition status: {status!r}")
    with conn:
        owned = conn.execute(
            "SELECT 1 FROM transaction_alerts WHERE id=? AND org_id=?", (alert_id, org_id)
        ).fetchone()
        if owned is None:
            raise ValueError(f"transaction alert {alert_id} not found")
        now = utcnow()
        conn.execute(
            """UPDATE transaction_alerts
               SET status=?, disposition=?, dispositioned_by=?, dispositioned_at=?
               WHERE id=? AND org_id=?""",
            (status, note.strip() or None, actor, now, alert_id, org_id),
        )
        audit(conn, actor, "transaction_alert.disposition", "transaction_alert", alert_id,
              {"status": status, "note": note}, org_id=org_id)


def record_signature(
    conn: sqlite3.Connection,
    customer_id: int,
    org_id: int,
    *,
    purpose: str,
    statement: str,
    signer_name: str,
    signer_role: str = "customer",
    ip_address: str | None = None,
    user_agent: str | None = None,
    actor: str = "system",
) -> int:
    """Capture a typed-signature acknowledgment with a tamper-evident hash.

    The hash covers `purpose`, `statement` and `signer_name` exactly as shown
    to the signer -- not the row's own id or timestamp, which are metadata
    about the act of signing rather than part of what was agreed to. A later
    edit to a standard acknowledgment template is then immediately visible as
    a hash mismatch against records signed under the old wording, rather than
    silently being read as "the same thing was agreed to."

    This is a basic audit-trail acknowledgment, not a legally-binding UAE
    e-signature under Federal Decree-Law No. 46 of 2021 on Electronic
    Transactions and Trust Services -- that requires a licensed trust service
    provider. Stated here rather than left to be assumed.
    """
    import hashlib

    purpose = (purpose or "").strip()
    statement = (statement or "").strip()
    signer_name = (signer_name or "").strip()
    if not purpose or not statement or not signer_name:
        raise ValueError("purpose, statement and signer_name are all required")

    content_hash = hashlib.sha256(
        "\x1f".join([purpose, statement, signer_name]).encode("utf-8")
    ).hexdigest()
    now = utcnow()

    with conn:
        owned = conn.execute(
            "SELECT 1 FROM customers WHERE id=? AND org_id=?", (customer_id, org_id)
        ).fetchone()
        if owned is None:
            raise ValueError(f"customer {customer_id} not found")
        cur = conn.execute(
            """INSERT INTO signatures
               (org_id, customer_id, purpose, statement, signer_name, signer_role,
                content_hash, ip_address, user_agent, signed_by, signed_at, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                org_id, customer_id, purpose, statement, signer_name, signer_role,
                content_hash, ip_address, user_agent, actor, now, now,
            ),
        )
        signature_id = cur.lastrowid
        audit(conn, actor, "signature.record", "customer", customer_id,
              {"signature_id": signature_id, "purpose": purpose, "signer_name": signer_name,
               "content_hash": content_hash},
              org_id=org_id)
        return signature_id


def add_case_note(
    conn: sqlite3.Connection, customer_id: int, org_id: int, *, author: str, body: str,
) -> int:
    """Record investigative narrative not tied to any one alert -- periodic
    review commentary, source-of-wealth notes, anything that belongs in the
    case file but isn't a disposition decision.

    Verifies the customer belongs to org_id before writing: case_notes.
    customer_id is a bare foreign key, so an insert with a mismatched org_id
    would otherwise succeed as long as the customer row exists at all
    (anywhere), silently creating a note that claims one org's ownership over
    another org's customer. This is the same "404, not a filtered-empty
    result" property applied everywhere else in this module -- a cross-tenant
    customer_id is treated as not found, not merely skipped.
    """
    body = (body or "").strip()
    if not body:
        raise ValueError("a case note cannot be empty")
    with conn:
        owned = conn.execute(
            "SELECT 1 FROM customers WHERE id=? AND org_id=?", (customer_id, org_id)
        ).fetchone()
        if owned is None:
            raise ValueError(f"customer {customer_id} not found")
        cur = conn.execute(
            "INSERT INTO case_notes (org_id, customer_id, author, body, created_at)"
            " VALUES (?,?,?,?,?)",
            (org_id, customer_id, author, body, utcnow()),
        )
        audit(conn, author, "case_note.add", "customer", customer_id,
              {"note_id": cur.lastrowid}, org_id=org_id)
        return cur.lastrowid
