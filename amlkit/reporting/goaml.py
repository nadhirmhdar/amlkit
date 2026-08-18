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

import xml.etree.ElementTree as ET
from datetime import datetime, timezone


def serialize_goaml_xml(report_data: dict) -> str:
    """Serialize a report payload into a standard goAML XML format."""
    report_code = report_data.get("report_type", "STR").upper()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

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
    
    # Reporter Details
    reporter = ET.SubElement(root, "reporting_person")
    ET.SubElement(reporter, "first_name").text = report_data.get("reporter_name", "").split()[0] if report_data.get("reporter_name") else "MLRO"
    ET.SubElement(reporter, "last_name").text = " ".join(report_data.get("reporter_name", "").split()[1:]) if report_data.get("reporter_name") else "Officer"
    ET.SubElement(reporter, "email").text = report_data.get("reporter_email") or "mlro@grovisor.test"

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
        ET.SubElement(person, "first_name").text = report_data.get("first_name") or "Unknown"
        ET.SubElement(person, "last_name").text = report_data.get("last_name") or "Unknown"
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
        entity = ET.SubElement(subject, "entity")
        ET.SubElement(entity, "name").text = report_data.get("full_name") or "Unknown Entity"
        if report_data.get("trade_licence"):
            ET.SubElement(entity, "incorporation_number").text = report_data["trade_licence"]
        if report_data.get("nationality"):
            ET.SubElement(entity, "incorporation_legal_form").text = report_data.get("sector") or "Private Company"

    # Transaction / Activity Node
    has_txn = report_data.get("amount") or report_data.get("transaction_type")
    if has_txn:
        tx = ET.SubElement(root, "transaction")
        ET.SubElement(tx, "transactionnumber").text = f"TXN-{int(datetime.now().timestamp())}"
        ET.SubElement(tx, "internal_ref_number").text = report_data.get("reference") or "TXN-REF-001"
        ET.SubElement(tx, "date_transaction").text = report_data.get("transaction_date") or now_str[:10]
        ET.SubElement(tx, "transmode_code").text = report_data.get("transaction_type") or "Wire Transfer"
        ET.SubElement(tx, "amount_local").text = str(report_data.get("amount") or 0.0)
        
        # Source/Destination Accounts
        t_from = ET.SubElement(tx, "t_from")
        from_acc = ET.SubElement(t_from, "account")
        ET.SubElement(from_acc, "institution_name").text = "Originating Bank"
        ET.SubElement(from_acc, "account_number").text = report_data.get("source_account") or "N/A"
        
        t_to = ET.SubElement(tx, "t_to")
        to_acc = ET.SubElement(t_to, "account")
        ET.SubElement(to_acc, "institution_name").text = "Beneficiary Bank"
        ET.SubElement(to_acc, "account_number").text = report_data.get("destination_account") or "N/A"
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
