"""goAML report operations.

Business logic for creating and managing STR/SAR/CTR/DTR reports. Routes in
api/app.py validate session + CSRF, then delegate to these functions.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Optional

from ..db import audit, utcnow


@dataclass
class ReportResult:
    """Result of save_report operation."""
    success: bool
    report_id: Optional[int] = None
    error: Optional[str] = None


def save_report(
    db: sqlite3.Connection,
    org_id: int,
    operator_name: str,
    customer_id: int,
    report_type: str,
    reporting_entity_name: str,
    entity_reference: str,
    reporter_name: str,
    reporter_email: str,
    first_name: str,
    last_name: str = "",
    nationality: str = "AE",
    birth_date: str = "",
    gender: str = "",
    id_type: str = "",
    id_number: str = "",
    amount: str = "",
    transaction_type: str = "",
    transaction_date: str = "",
    source_account: str = "",
    destination_account: str = "",
    reason_description: str = "",
    action_taken: str = "",
    evidence_pack_attached: str = "",
    report_id: Optional[int] = None,
) -> ReportResult:
    """Save or update a goAML report draft.

    Args:
        db: Database connection
        org_id: Organization ID (tenant isolation)
        operator_name: Name of operator saving the report (for audit trail)
        customer_id: Customer this report is about
        report_type: "STR", "SAR", "CTR", or "DTR"
        reporting_entity_name: Name of the reporting entity
        entity_reference: Entity reference number
        reporter_name: Name of the reporting officer
        reporter_email: Email of the reporting officer
        first_name: Subject's first name (or entity name for legal entities)
        last_name: Subject's last name (empty for legal entities)
        nationality: Two-letter country code (default "AE")
        birth_date: ISO date string
        gender: "M", "F", or empty
        id_type: Type of identification document
        id_number: Identification document number
        amount: Transaction amount as string (will be parsed)
        transaction_type: Type of transaction
        transaction_date: ISO date string
        source_account: Source account number
        destination_account: Destination account number
        reason_description: Description of suspicious activity
        action_taken: Action taken by the entity
        evidence_pack_attached: "1" or "" (checkbox value)
        report_id: If provided, updates existing report instead of creating new

    Returns:
        ReportResult with success=True and report_id, or success=False and error message
    """
    # Look up customer type for correct goAML XML serialisation. A miss here
    # means customer_id doesn't belong to this org -- reject rather than
    # silently defaulting to "natural" and saving a report against a
    # customer_id from another tenant.
    cust_row = db.execute(
        "SELECT customer_type, full_name FROM customers WHERE id = ? AND org_id = ?",
        (customer_id, org_id)
    ).fetchone()
    if cust_row is None:
        return ReportResult(success=False, error=f"Customer {customer_id} not found.")
    cust_type = cust_row["customer_type"]

    # Parse and validate amount
    try:
        parsed_amount = float(amount) if amount.strip() else None
    except ValueError:
        return ReportResult(success=False, error=f"Amount {amount!r} is not a valid number.")

    # For CTR: fetch org's configured large_cash_threshold to use as validation threshold
    threshold = None
    if report_type == "CTR":
        from ..screening.kyt import get_rule_config
        config = get_rule_config(db, org_id)
        threshold = config["large_cash_threshold_aed"]

    # Bundle all collected parameters into a payload dict
    payload_dict = {
        "customer_id": customer_id,
        "customer_type": cust_type,
        "report_type": report_type,
        "reporting_entity_name": reporting_entity_name.strip(),
        "entity_reference": entity_reference.strip(),
        "reporter_name": reporter_name.strip(),
        "reporter_email": reporter_email.strip(),
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
        "nationality": nationality.strip().upper(),
        "birth_date": birth_date.strip(),
        "gender": gender.strip(),
        "id_type": id_type.strip(),
        "id_number": id_number.strip(),
        "amount": parsed_amount,
        "transaction_type": transaction_type.strip() if transaction_type else None,
        "transaction_date": transaction_date.strip() if transaction_date else None,
        "source_account": source_account.strip(),
        "destination_account": destination_account.strip(),
        "reason_description": reason_description.strip(),
        "action_taken": action_taken.strip(),
        "evidence_pack_attached": bool(evidence_pack_attached),
    }
    if threshold is not None:
        payload_dict["threshold"] = threshold

    payload_json = json.dumps(payload_dict)
    now = utcnow()

    if report_id:
        # A submitted report is a filed regulatory record; the UI already
        # tells the operator it is "locked and archived" once submitted, so
        # the save path must actually enforce that rather than silently
        # overwriting it. Also catches a report_id that doesn't belong to
        # this org, which the bare UPDATE below would otherwise just no-op
        # on (0 rows matched) and still report as a success.
        existing = db.execute(
            "SELECT status FROM reports WHERE id=? AND org_id=?", (report_id, org_id)
        ).fetchone()
        if existing is None:
            return ReportResult(success=False, error=f"Report {report_id} not found.")
        if existing["status"] != "draft":
            return ReportResult(
                success=False,
                error=f"Report {report_id} has been submitted and can no longer be edited.",
            )

    with db:
        if report_id:
            # Update existing report
            db.execute(
                """UPDATE reports
                   SET payload=?, reference=?
                   WHERE id=? AND org_id=?""",
                (payload_json, f"goAML-{report_type}-{report_id}", report_id, org_id)
            )
            rid = report_id
        else:
            # Create new report
            cur = db.execute(
                """INSERT INTO reports (org_id, customer_id, report_type, status, payload, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (org_id, customer_id, report_type, "draft", payload_json, now)
            )
            rid = cur.lastrowid
            db.execute(
                "UPDATE reports SET reference=? WHERE id=?",
                (f"goAML-{report_type}-{rid}", rid)
            )

        audit(db, operator_name, "report.save", "report", rid,
              {"report_type": report_type}, org_id=org_id)

    return ReportResult(success=True, report_id=rid)
