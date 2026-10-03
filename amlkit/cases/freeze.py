"""Freeze obligation business logic.

Extracted from api/app.py as part of Issue #73 refactor (Phase 4).
"""

import json
import sqlite3
from typing import Any

from ..db import audit, utcnow


def parse_freeze_assets_from_form(form: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse assets_frozen list from form data.

    Expects form fields: asset_type_1, asset_identifier_1, asset_amount_1, etc.
    Returns list of dicts with keys: type, identifier, amount_aed.
    """
    assets_frozen = []
    i = 1
    while f"asset_type_{i}" in form:
        asset_type = form[f"asset_type_{i}"]
        identifier = form[f"asset_identifier_{i}"]
        amount_str = form.get(f"asset_amount_{i}", "0")

        try:
            amount = float(amount_str) if amount_str else 0.0
        except ValueError:
            amount = 0.0

        if asset_type and identifier:
            assets_frozen.append({
                "type": asset_type,
                "identifier": identifier,
                "amount_aed": amount
            })
        i += 1

    return assets_frozen


def file_ffr_report(
    db: sqlite3.Connection,
    freeze_id: int,
    org_id: int,
    reporter_name: str,
    reporter_email: str,
    operator: str
) -> int:
    """Create the CNMR (internally FFR) draft for an executed freeze obligation.

    Only drafts the report and links it to the freeze (``report_id``). The
    freeze stays ``executed_pending_report`` until that report is finalised
    (see ``mark_freeze_reported``) -- a draft is not a filing, so it must not
    take the freeze off the pending-report views.

    Idempotent while a report is linked: a second call returns the existing
    report id instead of creating a duplicate draft.

    Args:
        db: Database connection
        freeze_id: Freeze obligation ID
        org_id: Organization ID (tenant isolation)
        reporter_name: Name of person filing the report
        reporter_email: Email of person filing the report
        operator: Operator name (for audit trail)

    Returns:
        report_id: ID of the created (or already-linked) report record

    Raises:
        ValueError: If freeze not found or not in correct status
    """
    freeze = db.execute("""
        SELECT f.*, c.reference, c.full_name, c.customer_type,
               c.birth_date, c.gender, c.nationality, c.id_number, c.id_type
        FROM freeze_obligations f
        JOIN customers c ON c.id = f.customer_id
        WHERE f.id = ? AND f.org_id = ?
    """, (freeze_id, org_id)).fetchone()

    if not freeze:
        raise ValueError(f"Freeze obligation {freeze_id} not found")

    if freeze["status"] != "executed_pending_report":
        raise ValueError("Freeze not ready for CNMR filing")

    # One CNMR per freeze: a linked report (draft) already exists, so hand
    # it back rather than drafting a second one (double-click, back button).
    if freeze["report_id"] is not None:
        existing = db.execute(
            "SELECT id FROM reports WHERE id = ? AND org_id = ?",
            (freeze["report_id"], org_id),
        ).fetchone()
        if existing:
            return existing["id"]

    # Guard against blank names (would raise IndexError on split()[0])
    full_name = freeze["full_name"] or ""
    if not full_name.strip():
        raise ValueError(f"Cannot file CNMR: customer full_name is blank (customer_id={freeze['customer_id']})")

    # For legal entities, use full entity name (not split())
    # goAML entity node uses first_name field for the entity's full name
    if freeze["customer_type"] == "legal":
        first_name_field = full_name
        last_name_field = ""
    else:
        # Natural person: split into first/last
        first_name_field = full_name.split()[0]
        last_name_field = " ".join(full_name.split()[1:])

    report_payload = {
        "report_type": "FFR",
        "freeze_obligation_id": freeze_id,
        "customer_id": freeze["customer_id"],
        "obligation_type": freeze["obligation_type"],
        "identified_at": freeze["identified_at"],
        "executed_at": freeze["executed_at"],
        "assets_frozen": json.loads(freeze["assets_frozen"] or "[]"),
        "authority_ref": freeze["authority_ref"],
        "reporter_name": reporter_name,
        "reporter_email": reporter_email,
        "first_name": first_name_field,
        "last_name": last_name_field,
        "customer_type": freeze["customer_type"],
        "reference": freeze["reference"],
        "birth_date": freeze["birth_date"],
        "gender": freeze["gender"],
        "nationality": freeze["nationality"],
        "id_number": freeze["id_number"],
        "id_type": freeze["id_type"],
    }

    # Inject org details into payload (follow-up to #231/#142)
    from ..reporting import goaml
    goaml.inject_reporting_entity(report_payload, db, org_id)

    xml_content = goaml.serialize_goaml_xml(report_payload)

    now = utcnow()
    cursor = db.execute("""
        INSERT INTO reports
        (org_id, customer_id, report_type, status, payload, created_at)
        VALUES (?, ?, 'FFR', 'draft', ?, ?)
    """, (org_id, freeze["customer_id"], json.dumps(report_payload), now))
    report_id = cursor.lastrowid

    # Link only: the freeze moves to 'reported' when this report is finalised.
    db.execute("""
        UPDATE freeze_obligations
        SET report_id = ?
        WHERE id = ? AND org_id = ?
    """, (report_id, freeze_id, org_id))

    audit(db, operator, "freeze.report_drafted", "freeze_obligation", freeze_id,
          {"report_id": report_id}, org_id=org_id)
    db.commit()

    return report_id


def mark_freeze_reported(
    db: sqlite3.Connection,
    report_id: int,
    org_id: int,
    operator: str,
    now: str,
) -> list[int]:
    """Move freezes linked to a just-finalised report to ``reported``.

    Called by both report-submit paths (web and mobile) inside the same
    transaction as the report's own status change, so the freeze and its
    CNMR can never disagree. Org-scoped; a no-op for reports that aren't
    linked to a freeze pending report.

    Returns:
        IDs of the freeze obligations that were marked reported.
    """
    rows = db.execute("""
        SELECT id FROM freeze_obligations
        WHERE report_id = ? AND org_id = ? AND status = 'executed_pending_report'
    """, (report_id, org_id)).fetchall()
    freeze_ids = [r["id"] for r in rows]
    for freeze_id in freeze_ids:
        db.execute("""
            UPDATE freeze_obligations
            SET reported_at = ?, status = 'reported'
            WHERE id = ? AND org_id = ?
        """, (now, freeze_id, org_id))
        audit(db, operator, "freeze.reported", "freeze_obligation", freeze_id,
              {"report_id": report_id}, org_id=org_id)
    return freeze_ids
