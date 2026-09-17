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
* **Retain for eight years after the relationship ends.** The retention date is
  computed and stored rather than left to policy.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..db import audit, utcnow
from ..match.engine import DEFAULT_THRESHOLD, ScreeningResult, screen
from ..names.arabic import canonical_key
from ..risk.model import (
    CustomerProfile,
    RiskAssessment,
    assess,
    ruleset,
    save as save_risk,
)
from ..screening.adverse_media import (
    DEFAULT_WINDOW_MONTHS,
    AdverseMediaResult,
    search,
    worst_severity,
)


class StaleDatasetsError(Exception):
    """Raised when onboarding is attempted with stale or empty sanctions data."""


UBO_THRESHOLD_PCT = 25.0
RETENTION_YEARS = 8


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
    # Contact fields — optional for backward compatibility
    email: str | None = None,
    phone: str | None = None,
    address_line1: str | None = None,
    address_line2: str | None = None,
    city: str | None = None,
    postal_code: str | None = None,
    contact_person: str | None = None,
    contact_phone: str | None = None,
    contact_email: str | None = None,
) -> OnboardingResult:
    """Create a customer, screen them and their UBOs, and assign a risk rating.

    Screening happens before the risk rating because a sanctions hit forces the
    rating to high regardless of every other factor -- the two are not
    independent inputs.
    """
    from ..ingest.loader import datasets_fresh

    if not datasets_fresh(conn):
        raise StaleDatasetsError(
            "Cannot onboard: no fresh mandatory sanctions dataset available. "
            "Ask an MLRO to run Admin → Refresh sources"
        )

    # H-01: Validate UBO ownership sum cannot exceed 100%
    # All UBOs passed to onboard() are direct links (no parent_ubo_id)
    if ubos:
        total_ownership = sum(
            ubo.get("ownership_pct", 0) or 0
            for ubo in ubos
            if ubo.get("ownership_pct") is not None
        )
        if round(total_ownership, 2) > 100:
            raise ValueError(
                f"Total UBO ownership is {round(total_ownership, 2)}% (cannot exceed 100%)"
            )

    now = utcnow()
    ck = canonical_key(full_name)

    with conn:
        cur = conn.execute(
            """INSERT INTO customers
               (org_id, reference, customer_type, full_name, name_arabic, canonical_key,
                nationality, country, birth_date, gender, id_number, id_type,
                trade_licence, sector, delivery_channel, is_cash_intensive,
                email, phone, address_line1, address_line2, city, postal_code,
                contact_person, contact_phone, contact_email,
                onboarded_at, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                org_id, reference, customer_type, full_name, name_arabic, ck,
                nationality, country, birth_date, gender, id_number, id_type,
                trade_licence, sector, delivery_channel,
                int(cash_level == "predominantly_cash"),
                email, phone, address_line1, address_line2, city, postal_code,
                contact_person, contact_phone, contact_email,
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
            ownership_state=ownership_state(conn, customer_id, org_id, customer_type),
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
    is_nominee: bool = False,
    parent_ubo_id: int | None = None,
    notes: str | None = None,
    actor: str = "system",
) -> int:
    """Record a beneficial owner.

    `is_ubo` is set from the 25% threshold, except where control is recorded as
    senior managing official -- the regulation's explicit fallback when no
    natural person meets the ownership test.  Nominees are never beneficial
    owners regardless of their ownership percentage.
    """
    if ownership_pct is not None and not (0 <= ownership_pct <= 100):
        raise ValueError(
            f"ownership percentage must be between 0 and 100, got {ownership_pct}"
        )
    if is_nominee:
        is_ubo = False
    else:
        is_ubo = control_type == "senior_official" or (
            ownership_pct is not None and ownership_pct >= UBO_THRESHOLD_PCT
        )
    with conn:
        owned = conn.execute(
            "SELECT 1 FROM customers WHERE id=? AND org_id=?", (customer_id, org_id)
        ).fetchone()
        if owned is None:
            raise ValueError(f"customer {customer_id} not found")

        if parent_ubo_id is not None:
            parent = conn.execute(
                "SELECT id FROM ubo_links WHERE id=? AND customer_id=? AND org_id=?",
                (parent_ubo_id, customer_id, org_id),
            ).fetchone()
            if parent is None:
                raise ValueError(
                    f"parent_ubo_id {parent_ubo_id} not found for customer {customer_id}"
                )

        cur = conn.execute(
            """INSERT INTO ubo_links
               (org_id, customer_id, person_name, name_arabic, canonical_key, nationality,
                birth_date, ownership_pct, control_type, is_ubo, is_nominee,
                parent_ubo_id, notes, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                org_id, customer_id, person_name, name_arabic, canonical_key(person_name),
                nationality, birth_date, ownership_pct, control_type,
                int(is_ubo), int(is_nominee), parent_ubo_id, notes, utcnow(),
            ),
        )
        ubo_id = cur.lastrowid
        if parent_ubo_id == ubo_id:
            conn.execute("DELETE FROM ubo_links WHERE id=?", (ubo_id,))
            raise ValueError("a UBO link cannot be its own parent")

        audit(conn, actor, "ubo.add", "customer", customer_id,
              {"person": person_name, "pct": ownership_pct, "is_ubo": is_ubo,
               "is_nominee": is_nominee}, org_id=org_id)
        return ubo_id


def ownership_state(
    conn: sqlite3.Connection, customer_id: int, org_id: int, customer_type: str = "legal"
) -> str:
    """Derive an ownership-opacity band from recorded UBO data.

    A legal person with no identified UBO scores as `ubo_undisclosed` rather
    than as transparent-by-default. Absence of evidence is a risk indicator
    here, and defaulting the other way would understate risk exactly where the
    regulation is most concerned.

    Scoped to `org_id` -- without it a UBO row injected under another org's
    session (e.g. via a customer_id that isn't theirs) would still be counted
    here, corrupting this org's own customer's risk band with another
    tenant's data.
    """
    if customer_type == "natural":
        return "fully_transparent"

    rows = conn.execute(
        "SELECT ownership_pct, control_type, is_ubo, is_nominee FROM ubo_links WHERE customer_id=? AND org_id=?",
        (customer_id, org_id),
    ).fetchall()
    if not rows:
        return "ubo_undisclosed"

    non_nominee = [r for r in rows if not r["is_nominee"]]

    if any(r["control_type"] == "nominee" for r in non_nominee):
        return "nominee_or_bearer"
    if not non_nominee or not any(r["is_ubo"] for r in non_nominee):
        return "ubo_undisclosed"

    identified = sum(r["ownership_pct"] or 0 for r in non_nominee if r["is_ubo"])
    if identified < 50:
        return "multi_layer_offshore"
    if identified < 75:
        return "single_layer_foreign"
    return "fully_transparent"


def resolve_ubo_chain(
    conn: sqlite3.Connection,
    customer_id: int,
    org_id: int,
    *,
    max_depth: int = 10,
) -> list[dict[str, Any]]:
    """Walk the UBO ownership tree and return all nodes with effective ownership.

    For each leaf (a UBO with no children), effective_pct is the product of
    ownership_pct along the path from root to leaf.  Nominees are included in
    the result (so the caller can display them) but marked; their children are
    still traversed.
    """
    all_rows = [dict(r) for r in conn.execute(
        "SELECT id, person_name, ownership_pct, control_type, is_ubo, is_nominee, parent_ubo_id"
        " FROM ubo_links WHERE customer_id=? AND org_id=?",
        (customer_id, org_id),
    ).fetchall()]

    by_parent: dict[int | None, list[dict]] = {}
    for row in all_rows:
        by_parent.setdefault(row["parent_ubo_id"], []).append(row)

    child_ids = {r["parent_ubo_id"] for r in all_rows if r["parent_ubo_id"] is not None}
    result: list[dict[str, Any]] = []
    visited: set[int] = set()

    def _walk(node: dict, effective_pct: float, depth: int) -> None:
        if node["id"] in visited or depth > max_depth:
            return
        visited.add(node["id"])

        own_pct = node["ownership_pct"] if node["ownership_pct"] is not None else 0.0
        node_effective = effective_pct * (own_pct / 100.0) if effective_pct is not None else own_pct

        children = by_parent.get(node["id"], [])
        is_leaf = len(children) == 0

        result.append({
            "id": node["id"],
            "person_name": node["person_name"],
            "ownership_pct": node["ownership_pct"],
            "effective_pct": node_effective,
            "control_type": node["control_type"],
            "is_ubo": node["is_ubo"],
            "is_nominee": bool(node["is_nominee"]),
            "is_leaf": is_leaf,
            "depth": depth,
            "parent_ubo_id": node["parent_ubo_id"],
        })

        for child in children:
            _walk(child, node_effective, depth + 1)

    for root in by_parent.get(None, []):
        _walk(root, 100.0, 0)

    return result


def close_relationship(
    conn: sqlite3.Connection, customer_id: int, org_id: int, actor: str = "system"
) -> str:
    """Mark a customer inactive and set the 8-year retention date."""
    today = date.today()
    try:
        until = today.replace(year=today.year + RETENTION_YEARS).isoformat()
    except ValueError:
        # Feb 29 → Feb 28 in the target year (non-leap)
        until = (today + timedelta(days=365 * RETENTION_YEARS + 1)).isoformat()
    with conn:
        conn.execute(
            "UPDATE customers SET status='closed', retention_until=?, updated_at=?"
            " WHERE id=? AND org_id=?",
            (until, utcnow(), customer_id, org_id),
        )
        audit(conn, actor, "customer.close", "customer", customer_id,
              {"retention_until": until}, org_id=org_id)
    return until


def purge_expired(
    conn: sqlite3.Connection,
    org_id: int,
    *,
    actor: str = "system",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Delete customers whose retention_until has passed.

    Only purges customers with status='closed' AND retention_until < now.
    Audit entry is written BEFORE each deletion so the record of purging
    survives the customer row being gone.
    """
    from pathlib import Path

    now = date.today().isoformat()
    rows = conn.execute(
        "SELECT id, reference FROM customers"
        " WHERE org_id=? AND status='closed'"
        " AND retention_until IS NOT NULL AND retention_until < ?",
        (org_id, now),
    ).fetchall()

    details = [{"customer_id": r["id"], "reference": r["reference"]} for r in rows]
    if dry_run:
        return {"purged": len(details), "details": details, "dry_run": True}

    purged_count = 0
    for row in rows:
        cid = row["id"]
        ref = row["reference"]

        # Try to delete documents first. If any fail, skip this customer
        # entirely so it retries on the next purge run. An orphaned GCS object
        # past retention with no DB pointer is worse than a deferred purge.
        doc_paths = conn.execute(
            "SELECT stored_path FROM documents WHERE customer_id=? AND org_id=?",
            (cid, org_id),
        ).fetchall()

        delete_failed = False
        for doc in doc_paths:
            p = doc["stored_path"]
            if p:
                try:
                    from .. import storage
                    storage.delete(p)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(
                        "purge_expired: could not delete document %s for customer %s: %s (%s)",
                        p, ref, e, type(e).__name__
                    )
                    delete_failed = True
                    break

        if delete_failed:
            # Skip this customer; leave the row for retry. Log the failure.
            with conn:
                audit(conn, actor, "retention.purge_failed", "customer", cid,
                      {"reference": ref, "reason": "document_delete_failed"}, org_id=org_id)
            continue

        # All documents deleted successfully; now purge the customer
        with conn:
            audit(conn, actor, "customer.purge", "customer", cid,
                  {"reference": ref}, org_id=org_id)

            conn.execute("DELETE FROM adverse_media_findings WHERE customer_id=? AND org_id=?", (cid, org_id))
            conn.execute("DELETE FROM adverse_media_screenings WHERE customer_id=? AND org_id=?", (cid, org_id))
            conn.execute("DELETE FROM alert_reviews WHERE org_id=? AND alert_id IN (SELECT a.id FROM alerts a JOIN screenings s ON s.id=a.screening_id WHERE s.customer_id=? AND a.org_id=?)", (org_id, cid, org_id))
            conn.execute("DELETE FROM alerts WHERE screening_id IN (SELECT id FROM screenings WHERE customer_id=?) AND org_id=?", (cid, org_id))
            conn.execute("DELETE FROM screenings WHERE customer_id=? AND org_id=?", (cid, org_id))
            conn.execute("DELETE FROM transaction_alerts WHERE customer_id=? AND org_id=?", (cid, org_id))
            conn.execute("DELETE FROM transactions WHERE customer_id=? AND org_id=?", (cid, org_id))
            conn.execute("DELETE FROM ubo_links WHERE customer_id=? AND org_id=?", (cid, org_id))
            conn.execute("DELETE FROM risk_assessments WHERE customer_id=? AND org_id=?", (cid, org_id))
            conn.execute("DELETE FROM documents WHERE customer_id=? AND org_id=?", (cid, org_id))
            conn.execute("DELETE FROM case_notes WHERE customer_id=? AND org_id=?", (cid, org_id))
            conn.execute("DELETE FROM signatures WHERE customer_id=? AND org_id=?", (cid, org_id))
            conn.execute("DELETE FROM reports WHERE customer_id=? AND org_id=?", (cid, org_id))
            conn.execute("DELETE FROM customers WHERE id=? AND org_id=?", (cid, org_id))

        purged_count += 1

    return {"purged": purged_count, "details": details}


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

    if triggered:
        reassess_transaction_risk(conn, customer_id, org_id, actor=actor)

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


# ---------------------------------------------------------------- adverse media
def run_adverse_media(
    conn: sqlite3.Connection,
    *,
    org_id: int,
    name: str,
    name_arabic: str | None = None,
    customer_id: int | None = None,
    ubo_id: int | None = None,
    trigger: str = "adhoc",
    client: Any | None = None,
    window_months: int = DEFAULT_WINDOW_MONTHS,
    actor: str = "system",
) -> tuple[int, AdverseMediaResult, int]:
    """Search adverse coverage for one name and record the run.

    Returns `(screening_id, result, new_findings)`. `new_findings` counts rows
    actually written, which is lower than `len(result.findings)` whenever an
    article has been seen for this customer before -- see the dedup note below.

    The run row is written whether or not the provider answered. A record
    saying "adverse media was checked on this date and the provider was
    unreachable" is evidence of an attempted control; silently writing nothing
    leaves a file that looks identical to one where nobody ever ran the check.
    """
    result = search(
        name,
        name_arabic=name_arabic,
        client=client,
        window_months=window_months,
    )

    now = utcnow()
    new_findings = 0
    with conn:
        cur = conn.execute(
            """INSERT INTO adverse_media_screenings
               (org_id, customer_id, ubo_id, query_name, query_arabic, trigger,
                provider, window_months, status, error, articles_considered,
                findings, severity, run_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                org_id, customer_id, ubo_id, result.query, result.query_arabic,
                trigger, result.provider, result.window_months, result.status,
                result.error, result.articles_considered, len(result.findings),
                result.severity, now,
            ),
        )
        screening_id = cur.lastrowid

        for f in result.findings:
            # An article is immutable: the same URL is the same article, and
            # re-surfacing one an operator has already ruled on turns a
            # periodic re-run into a queue of decisions they have already
            # made. Deduped across the whole customer, not just this run, and
            # regardless of prior disposition. Ad-hoc searches (no customer)
            # have nothing to dedup against and record every finding.
            if customer_id is not None:
                seen = conn.execute(
                    "SELECT 1 FROM adverse_media_findings"
                    " WHERE org_id=? AND customer_id=? AND url=? LIMIT 1",
                    (org_id, customer_id, f.article.url),
                ).fetchone()
                if seen:
                    continue
            conn.execute(
                """INSERT INTO adverse_media_findings
                   (org_id, screening_id, customer_id, url, title, domain, language,
                    source_country, published_at, severity, matched_terms,
                    name_evidence, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    org_id, screening_id, customer_id, f.article.url, f.article.title,
                    f.article.domain, f.article.language, f.article.source_country,
                    f.article.published_at, f.severity,
                    json.dumps(f.matched_terms, ensure_ascii=False),
                    f.name_evidence, now,
                ),
            )
            new_findings += 1

        audit(
            conn, actor, "adverse_media.screen",
            "customer" if customer_id else "adverse_media_screening",
            customer_id or screening_id,
            {
                "screening_id": screening_id,
                "query": result.query,
                "trigger": trigger,
                "provider": result.provider,
                "status": result.status,
                "articles_considered": result.articles_considered,
                "findings": len(result.findings),
                "new_findings": new_findings,
                "severity": result.severity,
                "error": result.error,
            },
            org_id=org_id,
        )
    return screening_id, result, new_findings


def disposition_adverse_media_finding(
    conn: sqlite3.Connection,
    finding_id: int,
    org_id: int,
    *,
    status: str,
    note: str = "",
    actor: str = "system",
) -> str | None:
    """Rule on one adverse-media finding, then re-rate the customer.

    Returns the customer's new risk rating, or None for an ad-hoc finding with
    no customer attached.

    No four-eyes requirement, for the same reason `disposition_transaction_alert`
    has none (see kyt.py): the sanctions/PF review machinery exists because UAE
    law places personal liability on a freeze-and-report decision. Judging
    whether a news article is about your customer is a risk-rating input, not a
    designation, and requiring two operators for every one of them at news
    volume would degrade into rubber-stamping.

    Marking a finding relevant is the ONLY path by which adverse media reaches
    a risk rating. The provider cannot make that call: GDELT indexes coverage,
    it does not decide that "Ahmed Al Mansoori" in a Reuters headline is *this*
    Ahmed Al Mansoori. A human decides, and the rating follows.
    """
    if status not in ("relevant", "not_relevant"):
        raise ValueError(f"invalid adverse media disposition: {status!r}")
    with conn:
        row = conn.execute(
            "SELECT customer_id FROM adverse_media_findings WHERE id=? AND org_id=?",
            (finding_id, org_id),
        ).fetchone()
        if row is None:
            raise ValueError(f"adverse media finding {finding_id} not found")
        now = utcnow()
        conn.execute(
            """UPDATE adverse_media_findings
               SET status=?, disposition=?, dispositioned_by=?, dispositioned_at=?
               WHERE id=? AND org_id=?""",
            (status, note.strip() or None, actor, now, finding_id, org_id),
        )
        audit(conn, actor, "adverse_media.disposition", "adverse_media_finding",
              finding_id, {"status": status, "note": note}, org_id=org_id)
        customer_id = row["customer_id"]

    if customer_id is None:
        return None
    return reassess_adverse_media(conn, customer_id, org_id, actor=actor)


def adverse_media_severity(
    conn: sqlite3.Connection, customer_id: int, org_id: int
) -> str:
    """Worst severity among findings an operator has marked relevant.

    Open and not_relevant findings score nothing. An unreviewed lead is not a
    finding about a customer, and rating someone high risk on an article
    nobody has read is exactly the false-positive behaviour this codebase
    rejects everywhere else.
    """
    rows = conn.execute(
        "SELECT DISTINCT severity FROM adverse_media_findings"
        " WHERE org_id=? AND customer_id=? AND status='relevant'",
        (org_id, customer_id),
    ).fetchall()
    return worst_severity(r["severity"] for r in rows)


def _prior_value(factors: dict, key: str, default: Any) -> Any:
    entry = factors.get(key)
    if isinstance(entry, dict) and entry.get("value") is not None:
        return entry["value"]
    return default


def reassess_transaction_risk(
    conn: sqlite3.Connection, customer_id: int, org_id: int, *, actor: str = "system"
) -> str | None:
    """Re-rate a customer based on their current open transaction-alert count.

    Maps open alert count to a cash_intensity level and re-runs the risk model
    with that single factor changed, carrying all other factors forward from the
    prior assessment. A supervisor comparing two dated assessments will see one
    factor change -- which is what actually happened.

    Returns the new rating, or None when there is no prior assessment to build on.
    """
    prior = conn.execute(
        "SELECT factors FROM risk_assessments WHERE customer_id=? AND org_id=?"
        " ORDER BY id DESC LIMIT 1",
        (customer_id, org_id),
    ).fetchone()
    if prior is None:
        return None

    try:
        factors = json.loads(prior["factors"]) or {}
    except (TypeError, ValueError):
        factors = {}

    open_alerts = conn.execute(
        "SELECT COUNT(*) c FROM transaction_alerts"
        " WHERE customer_id=? AND org_id=? AND status='open'",
        (customer_id, org_id),
    ).fetchone()["c"]

    if open_alerts >= 3:
        cash_level = "predominantly_cash"
    elif open_alerts >= 1:
        cash_level = "mixed"
    else:
        cash_level = "non_cash"

    customer_row = conn.execute(
        "SELECT customer_type FROM customers WHERE id=? AND org_id=?",
        (customer_id, org_id),
    ).fetchone()
    customer_type = (customer_row["customer_type"] if customer_row else None) or "natural"

    profile = CustomerProfile(
        pep_status=_prior_value(factors, "pep", None),
        jurisdiction_tier=_prior_value(factors, "jurisdiction", "standard"),
        sector=_prior_value(factors, "sector", "other"),
        ownership_state=ownership_state(conn, customer_id, org_id, customer_type),
        delivery_channel=_prior_value(factors, "delivery_channel", "face_to_face"),
        cash_level=cash_level,
        adverse_media=_prior_value(factors, "adverse_media", "none"),
        structure=_prior_value(factors, "structure", "natural_person"),
        sanctions_hit=bool(_prior_value(factors, "sanctions_hit", False)),
    )
    assessment = assess(profile)
    save_risk(conn, customer_id, assessment, org_id=org_id, actor=actor)
    audit(conn, actor, "risk.reassessed_transaction", "customer", customer_id,
          {"open_transaction_alerts": open_alerts, "cash_level": cash_level,
           "new_rating": assessment.rating},
          org_id=org_id)
    return assessment.rating


def reassess_adverse_media(
    conn: sqlite3.Connection, customer_id: int, org_id: int, *, actor: str = "system"
) -> str | None:
    """Re-rate a customer with their current adverse-media severity applied.

    The other risk factors are read back from the customer's most recent
    assessment's stored `factors` rather than recomputed from the customer
    row. Two reasons, and the second is the important one:

    * `jurisdiction_tier` and `structure` are onboarding inputs that have no
      column on `customers` -- recomputing from the row alone would silently
      drop them and could lower a rating.
    * The stored factors ARE the previous assessment's reasoning. Carrying
      them forward means the new assessment differs from the old one in
      exactly one factor, so a supervisor comparing two dated assessments
      sees adverse media as the single thing that changed -- which is what
      actually happened.

    Returns the new rating, or None when the customer has no prior assessment
    to build on (nothing to re-rate, and inventing a profile would be worse).
    """
    prior = conn.execute(
        "SELECT factors FROM risk_assessments WHERE customer_id=? AND org_id=?"
        " ORDER BY id DESC LIMIT 1",
        (customer_id, org_id),
    ).fetchone()
    if prior is None:
        return None

    try:
        factors = json.loads(prior["factors"]) or {}
    except (TypeError, ValueError):
        factors = {}

    severity = adverse_media_severity(conn, customer_id, org_id)
    profile = CustomerProfile(
        pep_status=_prior_value(factors, "pep", None),
        jurisdiction_tier=_prior_value(factors, "jurisdiction", "standard"),
        sector=_prior_value(factors, "sector", "other"),
        ownership_state=ownership_state(
            conn, customer_id, org_id,
            (conn.execute(
                "SELECT customer_type FROM customers WHERE id=? AND org_id=?",
                (customer_id, org_id),
            ).fetchone() or {"customer_type": "natural"})["customer_type"],
        ),
        delivery_channel=_prior_value(factors, "delivery_channel", "face_to_face"),
        cash_level=_prior_value(factors, "cash_intensity", "non_cash"),
        adverse_media=severity,
        structure=_prior_value(factors, "structure", "natural_person"),
        sanctions_hit=bool(_prior_value(factors, "sanctions_hit", False)),
    )
    assessment = assess(profile)
    save_risk(conn, customer_id, assessment, org_id=org_id, actor=actor)
    return assessment.rating


def reassess_risk(
    conn: sqlite3.Connection,
    customer_id: int,
    org_id: int,
    *,
    actor: str = "system",
    jurisdiction_tier: str | None = None,
    sector: str | None = None,
    delivery_channel: str | None = None,
    cash_level: str | None = None,
    structure: str | None = None,
) -> RiskAssessment | None:
    """Re-rate a customer from current state.

    Derives `sanctions_hit` from currently-open (unresolved) screening alerts.
    All other factors are carried forward from the prior assessment unless an
    explicit override is provided -- so the new record differs from the old one
    in exactly the dimensions that actually changed, which is what a supervisor
    comparing two dated assessments needs to see.

    Optional overrides (`jurisdiction_tier`, `sector`, etc.) are used by the
    profile-update API endpoint when a compliance officer corrects a risk
    factor. All other callers (post-rescreen, manual re-assess) omit them.

    Returns None when there is no prior assessment to build on.
    """
    prior = conn.execute(
        "SELECT factors FROM risk_assessments WHERE customer_id=? AND org_id=?"
        " ORDER BY id DESC LIMIT 1",
        (customer_id, org_id),
    ).fetchone()
    if prior is None:
        return None

    try:
        factors = json.loads(prior["factors"]) or {}
    except (TypeError, ValueError):
        factors = {}

    # Derive sanctions and PEP status from screening alerts that are NOT
    # confirmed false positives. true_positive (confirmed match) and
    # escalated (second reviewer disagreed with dismissal) both mean the
    # concern is unresolved and must keep the rating high. Only false_positive
    # means a human reviewed it and it was the wrong person.
    alert_rows = conn.execute(
        """SELECT e.topics
           FROM alerts a
           JOIN screenings s ON s.id = a.screening_id
           JOIN entities e   ON e.id = a.entity_id
           WHERE s.customer_id = ? AND a.org_id = ?
             AND a.status != 'false_positive'""",
        (customer_id, org_id),
    ).fetchall()

    sanctions_hit = False
    pep_hit = False
    for row in alert_rows:
        topics = json.loads(row["topics"] or "[]")
        if "sanction" in topics:
            sanctions_hit = True
        if any(t.startswith("role.pep") for t in topics):
            pep_hit = True

    # PEP status is a characteristic of the person -- once identified, carry
    # it forward even after the alert is closed (EDD completed ≠ no longer PEP).
    prior_pep = _prior_value(factors, "pep", None)
    pep_status: str | None = prior_pep or ("domestic_pep" if pep_hit else None)

    customer_row = conn.execute(
        "SELECT customer_type FROM customers WHERE id=? AND org_id=?",
        (customer_id, org_id),
    ).fetchone()
    customer_type = (customer_row["customer_type"] if customer_row else None) or "natural"

    severity = adverse_media_severity(conn, customer_id, org_id)

    profile = CustomerProfile(
        pep_status=pep_status,
        jurisdiction_tier=jurisdiction_tier or _prior_value(factors, "jurisdiction", "standard"),
        sector=sector or _prior_value(factors, "sector", "other"),
        ownership_state=ownership_state(conn, customer_id, org_id, customer_type),
        delivery_channel=delivery_channel or _prior_value(factors, "delivery_channel", "face_to_face"),
        cash_level=cash_level or _prior_value(factors, "cash_intensity", "non_cash"),
        adverse_media=severity,
        structure=structure or _prior_value(factors, "structure", "natural_person"),
        sanctions_hit=sanctions_hit,
    )
    assessment = assess(profile)
    save_risk(conn, customer_id, assessment, org_id=org_id, actor=actor)
    return assessment


# ------------------------------------------------- adverse media, periodic
# The cadence lives in risk/ruleset.yaml (`adverse_media_months`) rather than
# here, next to review_months, because both are review intervals keyed by risk
# rating and splitting them across two files would make neither findable. It
# is deliberately shorter than the CDD review cycle -- see the note there.
ADVERSE_MEDIA_DEFAULT_MONTHS = 12

# How many customers one batch run will check. Small on purpose: the provider
# is rate-limited to roughly one request every five seconds and a customer
# with an Arabic name costs two, so a batch of 5 is already ~30-60 seconds of
# wall clock. Raising this does not make the work faster, it just makes one
# request block for longer -- the throttle is the floor, not the batch size.
ADVERSE_MEDIA_BATCH_LIMIT = 5


def _adverse_media_interval_months(rating: str | None) -> int:
    rs = ruleset()
    table = rs.get("adverse_media_months") or {}
    return int(table.get(rating or "", ADVERSE_MEDIA_DEFAULT_MONTHS))


def adverse_media_due(
    conn: sqlite3.Connection, org_id: int, *, as_of: datetime | None = None
) -> list[dict[str, Any]]:
    """Active customers whose adverse-media check is missing or stale.

    This is the control that closes the "prompted, not remembered" gap. A
    check nobody is reminded to re-run is a check that happens once, at
    onboarding, and then silently ages out -- which is indistinguishable, in a
    file, from never having run it at all.

    Two rules worth being explicit about:

    * **Only a successful run counts.** A run recorded with
      `status='unavailable'` leaves the customer due. The provider being down
      is not evidence about a customer, and letting a failed attempt reset the
      clock would turn an outage into a clean bill of health.
    * **Never-checked sorts first.** A customer with no check at all is a
      bigger gap than one whose check is a month past due, so the queue an
      operator works down leads with the ones carrying no evidence at all.

    Returns one row per due customer with `reason` ('never' | 'stale'),
    `last_checked` (None when never), `interval_months`, and the rating that
    set that interval.
    """
    now = as_of or datetime.now(timezone.utc)
    rows = conn.execute(
        """SELECT c.id, c.reference, c.full_name, c.name_arabic,
                  r.rating,
                  (SELECT MAX(run_at) FROM adverse_media_screenings s
                    WHERE s.customer_id = c.id AND s.org_id = c.org_id
                      AND s.status = 'ok') AS last_ok
           FROM customers c
           LEFT JOIN risk_assessments r ON r.id = (
               SELECT id FROM risk_assessments WHERE customer_id = c.id
               ORDER BY assessed_at DESC LIMIT 1)
           WHERE c.status = 'active' AND c.org_id = ?
           ORDER BY c.id""",
        (org_id,),
    ).fetchall()

    out: list[dict[str, Any]] = []
    for row in rows:
        months = _adverse_media_interval_months(row["rating"])
        last = row["last_ok"]
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                # An unparseable timestamp is treated as no check at all
                # rather than as a recent one -- fail toward doing the work.
                last_dt = None
            if last_dt is not None:
                age_days = (now - last_dt).days
                if age_days < months * 30:
                    continue
                reason = "stale"
            else:
                reason = "never"
        else:
            reason = "never"

        out.append({
            "id": row["id"],
            "reference": row["reference"],
            "full_name": row["full_name"],
            "name_arabic": row["name_arabic"],
            "rating": row["rating"],
            "reason": reason,
            "last_checked": last if reason == "stale" else None,
            "interval_months": months,
        })

    out.sort(key=lambda c: (c["reason"] != "never", c["last_checked"] or ""))
    return out


def run_due_adverse_media(
    conn: sqlite3.Connection,
    org_id: int,
    *,
    limit: int = ADVERSE_MEDIA_BATCH_LIMIT,
    client: Any | None = None,
    actor: str = "system",
) -> dict[str, Any]:
    """Re-check the next `limit` customers whose adverse media is due.

    Bounded on purpose. This is NOT the automatic sweep that
    screening/adverse_media.py rules out -- it is an operator saying "work
    through the next few", with the throttle still applying between each one.
    Nothing here is scheduled, and nothing runs without someone asking.

    A provider outage does not abort the batch: `run_adverse_media` records
    the failed attempt and returns, so one unreachable moment does not lose
    the customers behind it in the queue. The counts returned distinguish the
    two outcomes, because "checked 5, all clear" and "attempted 5, provider
    down" are different facts.
    """
    due = adverse_media_due(conn, org_id)[: max(0, int(limit))]
    checked = failed = new_findings = 0
    for cust in due:
        _, result, added = run_adverse_media(
            conn,
            org_id=org_id,
            customer_id=cust["id"],
            name=cust["full_name"],
            name_arabic=cust["name_arabic"],
            trigger="periodic",
            client=client,
            actor=actor,
        )
        if result.status == "ok":
            checked += 1
            new_findings += added
        else:
            failed += 1

    return {
        "attempted": len(due),
        "checked": checked,
        "failed": failed,
        "new_findings": new_findings,
        "still_due": max(0, len(adverse_media_due(conn, org_id))),
    }


# ---------------------------------------------------------- TFS freeze tracking
# Targeted Financial Sanctions freeze obligations. Cabinet Resolution 134/2025
# places personal liability on senior management for TFS compliance failures.


def create_freeze_obligation(
    conn: sqlite3.Connection,
    org_id: int,
    customer_id: int,
    *,
    alert_id: int | None = None,
    obligation_type: str,
    risk_category: str,
    identified_by: str,
    notes: str = "",
) -> int:
    """Create a new TFS freeze obligation.

    Returns the freeze_obligation_id.

    Automatically:
    - Sets status='pending_execution'
    - Sets identified_at=now()
    - Logs audit entry (freeze.identified)

    Raises:
        ValueError: invalid obligation_type or risk_category
    """
    # Validate inputs
    valid_types = {"sanctions", "proliferation", "terrorism"}
    if obligation_type not in valid_types:
        raise ValueError(
            f"Invalid obligation_type: {obligation_type!r}. "
            f"Must be one of: {', '.join(sorted(valid_types))}"
        )

    valid_categories = {"high", "critical"}
    if risk_category not in valid_categories:
        raise ValueError(
            f"Invalid risk_category: {risk_category!r}. "
            f"Must be one of: {', '.join(sorted(valid_categories))}"
        )

    now = utcnow()

    # Insert freeze obligation and log audit atomically
    with conn:
        cursor = conn.execute(
            """INSERT INTO freeze_obligations
               (org_id, customer_id, alert_id, obligation_type, risk_category,
                identified_at, identified_by, notes, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (org_id, customer_id, alert_id, obligation_type, risk_category,
             now, identified_by, notes, "pending_execution")
        )
        freeze_id = cursor.lastrowid

        # Log audit entry
        audit(
            conn,
            identified_by,
            "freeze.identified",
            "freeze_obligation",
            freeze_id,
            {
                "customer_id": customer_id,
                "alert_id": alert_id,
                "obligation_type": obligation_type,
                "risk_category": risk_category,
            },
            org_id=org_id,
        )

    return freeze_id


def execute_freeze(
    conn: sqlite3.Connection,
    freeze_obligation_id: int,
    *,
    org_id: int,
    executed_by: str,
    assets_frozen: list[dict[str, Any]],
    notes: str = "",
) -> None:
    """Mark a freeze obligation as executed.

    Updates:
    - status='executed_pending_report'
    - executed_at=now()
    - executed_by
    - assets_frozen (JSON)

    Logs audit entry (freeze.executed).

    Raises:
        ValueError: obligation already executed, resolved, or not found in this org
    """
    # Check current status (tenant-scoped)
    row = conn.execute(
        "SELECT status, executed_at FROM freeze_obligations WHERE id = ? AND org_id = ?",
        (freeze_obligation_id, org_id)
    ).fetchone()

    if not row:
        raise ValueError(f"Freeze obligation {freeze_obligation_id} not found in org {org_id}")

    status = row["status"]
    if row["executed_at"] is not None:
        raise ValueError(
            f"Freeze obligation {freeze_obligation_id} already executed at {row['executed_at']}"
        )

    if status == "resolved":
        raise ValueError(
            f"Cannot execute freeze obligation {freeze_obligation_id}: already resolved"
        )

    now = utcnow()

    # Update freeze obligation and log audit atomically
    with conn:
        conn.execute(
            """UPDATE freeze_obligations
               SET status = 'executed_pending_report',
                   executed_at = ?,
                   executed_by = ?,
                   assets_frozen = ?,
                   notes = ?
               WHERE id = ? AND org_id = ?""",
            (now, executed_by, json.dumps(assets_frozen), notes, freeze_obligation_id, org_id)
        )

        # Log audit entry
        audit(
            conn,
            executed_by,
            "freeze.executed",
            "freeze_obligation",
            freeze_obligation_id,
            {
                "asset_count": len(assets_frozen),
                "total_amount_aed": sum(a.get("amount_aed", 0) for a in assets_frozen),
            },
            org_id=org_id,
        )


def resolve_freeze_obligation(
    conn: sqlite3.Connection,
    freeze_obligation_id: int,
    *,
    org_id: int,
    resolved_by: str,
    resolution_reason: str,
    authority_ref: str = "",
    notes: str = "",
) -> None:
    """Close a freeze obligation (lift freeze or confirm false positive).

    Updates:
    - status='resolved'
    - resolved_at=now()
    - resolved_by
    - resolution_reason
    - authority_ref

    Logs audit entry (freeze.resolved).

    Raises:
        ValueError: invalid resolution_reason, obligation not executed, or not found in this org
    """
    # Validate resolution reason
    valid_reasons = {"delisted", "false_positive", "authority_clearance"}
    if resolution_reason not in valid_reasons:
        raise ValueError(
            f"Invalid resolution_reason: {resolution_reason!r}. "
            f"Must be one of: {', '.join(sorted(valid_reasons))}"
        )

    # Check current status (tenant-scoped)
    row = conn.execute(
        "SELECT status, executed_at FROM freeze_obligations WHERE id = ? AND org_id = ?",
        (freeze_obligation_id, org_id)
    ).fetchone()

    if not row:
        raise ValueError(f"Freeze obligation {freeze_obligation_id} not found in org {org_id}")

    status = row["status"]

    # Allow resolving as false_positive without execution
    if resolution_reason != "false_positive" and row["executed_at"] is None:
        raise ValueError(
            f"Cannot resolve freeze obligation {freeze_obligation_id} with "
            f"reason '{resolution_reason}': obligation not executed. "
            f"Use 'false_positive' to resolve without execution."
        )

    if status == "resolved":
        raise ValueError(
            f"Freeze obligation {freeze_obligation_id} already resolved"
        )

    now = utcnow()

    # Update freeze obligation and log audit atomically
    with conn:
        conn.execute(
            """UPDATE freeze_obligations
               SET status = 'resolved',
                   resolved_at = ?,
                   resolved_by = ?,
                   resolution_reason = ?,
                   authority_ref = ?,
                   notes = ?
               WHERE id = ? AND org_id = ?""",
            (now, resolved_by, resolution_reason, authority_ref, notes, freeze_obligation_id, org_id)
        )

        # Log audit entry
        audit(
            conn,
            resolved_by,
            "freeze.resolved",
            "freeze_obligation",
            freeze_obligation_id,
            {
                "resolution_reason": resolution_reason,
                "authority_ref": authority_ref,
            },
            org_id=org_id,
        )


def check_unexecuted_freeze_obligations(
    conn: sqlite3.Connection,
    org_id: int,
) -> list[dict[str, Any]]:
    """Find freeze obligations pending execution for > 24 hours.

    Returns:
        [
            {
                "id": 1,
                "customer_reference": "C-2026-001",
                "obligation_type": "proliferation",
                "risk_category": "critical",
                "identified_at": "2026-09-10T14:23:00Z",
                "hours_pending": 36,
            },
        ]

    Sends MLRO email alert if any obligations are overdue.

    Cabinet Resolution 134/2025 requires immediate freeze execution. This check
    identifies freeze obligations that have been pending for over 24 hours,
    which indicates a compliance gap requiring urgent attention.
    """
    # Query for pending obligations > 24 hours old
    cursor = conn.execute(
        """SELECT
               f.id,
               f.customer_id,
               c.reference AS customer_reference,
               f.obligation_type,
               f.risk_category,
               f.identified_at,
               f.identified_by,
               CAST((julianday('now') - julianday(f.identified_at)) * 24 AS INTEGER) AS hours_pending
           FROM freeze_obligations f
           JOIN customers c ON c.id = f.customer_id
           WHERE f.org_id = ?
             AND f.status = 'pending_execution'
             AND julianday('now') - julianday(f.identified_at) > 1.0
           ORDER BY f.identified_at ASC""",
        (org_id,)
    )

    overdue = [dict(row) for row in cursor.fetchall()]

    # Send email alert if any overdue obligations found
    if overdue:
        # Get MLRO email for this org
        mlro_row = conn.execute(
            "SELECT email FROM operators WHERE org_id = ? AND role = 'mlro' LIMIT 1",
            (org_id,)
        ).fetchone()
        mlro_email = mlro_row["email"] if mlro_row else None

        # Send alert for each overdue obligation
        from .. import mail
        for ob in overdue:
            if mlro_email:
                mail.send_freeze_obligation_alert(
                    to_email=mlro_email,
                    freeze_obligation_id=ob["id"],
                    customer_reference=ob["customer_reference"],
                    obligation_type=ob["obligation_type"],
                    risk_category=ob["risk_category"]
                )

        # Log to audit that overdue obligations were detected
        audit(
            conn,
            "system",
            "freeze.overdue_check",
            "freeze_obligation",
            None,
            {"overdue_count": len(overdue), "org_id": org_id},
            org_id=org_id
        )

    return overdue
