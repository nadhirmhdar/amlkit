"""goAML and PNMR XML export serialisation layer for UAE FIU filings.

Generates XML files compliant with goAML 5.x schema requirements for:
- STR (Suspicious Transaction Report)
- SAR (Suspicious Activity Report)
- PNMR (Partial Name Match Report)
- FFR (Fund Freeze Report)
- HRCT (High Risk Country Transaction Report)
- HRCA (High Risk Country Activity Report)
- DPMSR (Dealers in Precious Metals and Stones Report)
- REAR (Real Estate Activity Report)
"""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


class GoAMLValidationError(ValueError):
    """A report payload is missing data required for a regulator-facing filing.

    Raised instead of silently substituting a placeholder: a blank source
    account or reporting officer exported as "N/A" / "Unknown" looks like a
    real value to whoever reads the filed XML, and to the FIU.
    """


def _require(report_data: dict, key: str, label: str) -> str:
    value = (report_data.get(key) or "").strip()
    if not value:
        raise GoAMLValidationError(
            f"Cannot export goAML filing: {label} is required but missing."
        )
    return value


def serialize_goaml_xml(report_data: dict) -> str:
    """Serialize a report payload into a standard goAML XML format."""
    report_code = report_data.get("report_type", "STR").upper()
    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    root = ET.Element("report")
    
    # Report Header
    ET.SubElement(root, "report_code").text = report_code
    ET.SubElement(root, "entity_reference").text = report_data.get("entity_reference") or "GROVISOR-AML"
    ET.SubElement(root, "submission_code").text = "NEW"
    ET.SubElement(root, "submission_date").text = now_str
    ET.SubElement(root, "currency_code_local").text = "AED"

    # Reporting Entity Details
    rep_ent = ET.SubElement(root, "reporting_entity")
    ET.SubElement(rep_ent, "reporting_entity_name").text = report_data.get("reporting_entity_name") or "Grovisor Consultants"
    ET.SubElement(rep_ent, "reporting_entity_branch").text = report_data.get("reporting_entity_branch") or "Dubai HQ"
    
    # Reporter Details. The reporting officer is legally accountable for this
    # filing, so their name/email must be the real submitter's, never a
    # placeholder that would silently misattribute the filing.
    reporter_name = _require(report_data, "reporter_name", "reporting officer name")
    reporter_email = _require(report_data, "reporter_email", "reporting officer email")
    reporter_name_parts = reporter_name.split()
    reporter = ET.SubElement(root, "reporting_person")
    ET.SubElement(reporter, "first_name").text = reporter_name_parts[0]
    ET.SubElement(reporter, "last_name").text = " ".join(reporter_name_parts[1:]) or reporter_name_parts[0]
    ET.SubElement(reporter, "email").text = reporter_email

    # Reason / Narrative (Narrative attachment reference goes here)
    narrative = ET.SubElement(root, "reason")
    ET.SubElement(narrative, "reason_description").text = report_data.get("reason_description") or "Suspicious name match or transaction activity detected."
    if report_data.get("action_taken"):
        ET.SubElement(narrative, "action_taken").text = report_data["action_taken"]

    # Subject details (Natural or Legal person being reported)
    subject = ET.SubElement(root, "subject")
    
    cust_type = report_data.get("customer_type", "natural")
    if cust_type == "natural":
        person = ET.SubElement(subject, "person")
        ET.SubElement(person, "first_name").text = _require(report_data, "first_name", "subject first name")
        ET.SubElement(person, "last_name").text = report_data.get("last_name") or ""
        if report_data.get("gender"):
            ET.SubElement(person, "gender").text = "M" if report_data["gender"] == "male" else "F"
        if report_data.get("birth_date"):
            ET.SubElement(person, "birth_date").text = report_data["birth_date"]
        if report_data.get("nationality"):
            ET.SubElement(person, "nationality1").text = report_data["nationality"]
            
        # ID Document
        if report_data.get("id_number"):
            ident = ET.SubElement(person, "identification")
            ET.SubElement(ident, "type").text = report_data.get("id_type") or "Passport"
            ET.SubElement(ident, "number").text = report_data["id_number"]
            ET.SubElement(ident, "issue_country").text = report_data.get("nationality") or "UAE"
    else:
        # The report form (and report_save in api/app.py) collects the legal
        # entity's name in the same "first_name" field used for a natural
        # person's given name -- there is no separate "full_name" key in the
        # saved payload, so that must be the source here too.
        entity = ET.SubElement(subject, "entity")
        ET.SubElement(entity, "name").text = _require(report_data, "first_name", "subject entity name")
        if report_data.get("trade_licence"):
            ET.SubElement(entity, "incorporation_number").text = report_data["trade_licence"]
        if report_data.get("nationality"):
            ET.SubElement(entity, "incorporation_legal_form").text = report_data.get("sector") or "Private Company"

    # Transaction / Activity Node
    has_txn = report_data.get("amount") or report_data.get("transaction_type")
    if has_txn:
        tx = ET.SubElement(root, "transaction")
        # Second-granularity local time let two STRs filed within the same
        # second collide on transactionnumber. Use the same UTC instant as
        # every other timestamp in this function, plus a random suffix so
        # concurrent filings can never collide even within one second.
        ET.SubElement(tx, "transactionnumber").text = f"TXN-{int(now.timestamp())}-{uuid.uuid4().hex[:8]}"
        ET.SubElement(tx, "internal_ref_number").text = report_data.get("reference") or "TXN-REF-001"
        ET.SubElement(tx, "date_transaction").text = report_data.get("transaction_date") or now_str[:10]
        ET.SubElement(tx, "transmode_code").text = report_data.get("transaction_type") or "Wire Transfer"
        ET.SubElement(tx, "amount_local").text = str(report_data.get("amount") or 0.0)

        # Source/Destination Accounts. A blank account number here is not a
        # harmless gap -- it silently exports as "N/A" in a regulator-facing
        # filing, so require the real value instead.
        t_from = ET.SubElement(tx, "t_from")
        from_acc = ET.SubElement(t_from, "account")
        ET.SubElement(from_acc, "institution_name").text = "Originating Bank"
        ET.SubElement(from_acc, "account_number").text = _require(report_data, "source_account", "source account number")

        t_to = ET.SubElement(tx, "t_to")
        to_acc = ET.SubElement(t_to, "account")
        ET.SubElement(to_acc, "institution_name").text = "Beneficiary Bank"
        ET.SubElement(to_acc, "account_number").text = _require(report_data, "destination_account", "destination account number")
    else:
        # Non-financial reports still need an activity block
        act = ET.SubElement(root, "activity")
        ET.SubElement(act, "activity_description").text = f"Activity reported under {report_code} due to sanctions match screening."
        ET.SubElement(act, "status_code").text = "SUSPENDED" if report_code in ("PNMR", "FFR") else "MONITORED"

    # Narrative PDF Attachment (evidence pack) reference metadata
    if report_data.get("evidence_pack_attached"):
        attachments = ET.SubElement(root, "attachments")
        doc = ET.SubElement(attachments, "document")
        ET.SubElement(doc, "document_name").text = f"evidence_pack_{report_data.get('customer_id')}.pdf"
        ET.SubElement(doc, "document_type").text = "Investigation evidence pack"
        ET.SubElement(doc, "remarks").text = "Comprehensive compliance evidence pack showing screening matches and reviews."

    # Return formatted string
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8").decode("utf-8")
