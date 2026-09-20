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
    """Create FFR report from executed freeze obligation.

    Args:
        db: Database connection
        freeze_id: Freeze obligation ID
        org_id: Organization ID (tenant isolation)
        reporter_name: Name of person filing the report
        reporter_email: Email of person filing the report
        operator: Operator name (for audit trail)

    Returns:
        report_id: ID of created report record

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
        raise ValueError("Freeze not ready for FFR filing")

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
        "first_name": freeze["full_name"].split()[0],
        "last_name": " ".join(freeze["full_name"].split()[1:]),
        "customer_type": freeze["customer_type"],
        "reference": freeze["reference"],
        "birth_date": freeze["birth_date"],
        "gender": freeze["gender"],
        "nationality": freeze["nationality"],
        "id_number": freeze["id_number"],
        "id_type": freeze["id_type"],
    }

    from ..reporting import goaml
    xml_content = goaml.serialize_goaml_xml(report_payload)

    now = utcnow()
    cursor = db.execute("""
        INSERT INTO reports
        (org_id, customer_id, report_type, status, payload, created_at)
        VALUES (?, ?, 'FFR', 'draft', ?, ?)
    """, (org_id, freeze["customer_id"], json.dumps(report_payload), now))
    report_id = cursor.lastrowid

    db.execute("""
        UPDATE freeze_obligations
        SET report_id = ?, reported_at = ?, status = 'reported'
        WHERE id = ?
    """, (report_id, now, freeze_id))

    audit(db, operator, "freeze.reported", "freeze_obligation", freeze_id,
          {"report_id": report_id}, org_id=org_id)
    db.commit()

    return report_id
