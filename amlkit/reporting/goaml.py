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
- DTR (Dealer Transaction Report)
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


# Report types with UI creation routes
SUPPORTED_REPORT_TYPES = {"STR", "SAR", "FFR"}


def inject_reporting_entity(payload: dict, db, org_id: int) -> None:
    """Inject reporting entity details into a goAML payload from the organization record.

    Fills reporting_entity_name, reporting_entity_branch, and entity_reference when absent.
    Raises GoAMLValidationError if the payload has no entity_reference and the org's
    goaml_entity_reference is not set either.

    This consolidates the org lookup logic previously copy-pasted across three call sites
    (web export, mobile export, freeze report filing).
    """
    # Fetch org details
    row = db.execute(
        "SELECT name, org_address, goaml_entity_reference FROM organizations WHERE id = ?",
        (org_id,)
    ).fetchone()

    if not row:
        raise GoAMLValidationError(f"Organization {org_id} not found")

    # Fill in missing fields
    if not payload.get("reporting_entity_name"):
        payload["reporting_entity_name"] = row["name"]

    if not payload.get("reporting_entity_branch"):
        payload["reporting_entity_branch"] = row["org_address"] or ""

    # entity_reference is mandatory. A value already on the payload (the STR/SAR
    # builder and the mobile API both collect one per report) wins; otherwise
    # fall back to the org's configured reference. Only raise when neither
    # source provides one -- never silently emit the old "AML-REF" placeholder.
    if not (payload.get("entity_reference") or "").strip():
        if not row["goaml_entity_reference"]:
            raise GoAMLValidationError(
                "goAML entity reference not configured for this organization. "
                "Set it in the admin organization profile."
            )
        payload["entity_reference"] = row["goaml_entity_reference"]


def serialize_goaml_xml(report_data: dict) -> str:
    """Serialize a report payload into a standard goAML XML format.

    Only report types with UI creation routes are supported:
    - STR (Suspicious Transaction Report) - via /reports/build
    - SAR (Suspicious Activity Report) - via /reports/build
    - FFR (Fund Freeze Report) - via /freeze-obligations/{id}/file-ffr

    FFR (Fund Freeze Report) specific requirements:
    - freeze_obligation_id (required)
    - obligation_type ('sanctions' | 'proliferation' | 'terrorism')
    - assets_frozen (list of asset dicts with type/identifier/amount_aed)
    - identified_at, executed_at (ISO timestamps)
    """
    report_code = report_data.get("report_type", "STR").upper()

    # Gate unsupported report types (no creation routes)
    if report_code not in SUPPORTED_REPORT_TYPES:
        raise ValueError(
            f"Report type '{report_code}' is not supported. "
            f"Supported types: {', '.join(sorted(SUPPORTED_REPORT_TYPES))}"
        )
    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # FFR-specific validation
    if report_code == "FFR":
        freeze_id = report_data.get("freeze_obligation_id")
        if not freeze_id:
            raise GoAMLValidationError(
                "Cannot export FFR: freeze obligation ID is required."
            )

    root = ET.Element("report")

    # Report Header
    ET.SubElement(root, "report_code").text = report_code
    ET.SubElement(root, "entity_reference").text = report_data.get("entity_reference") or "AML-REF"
    ET.SubElement(root, "submission_code").text = "NEW"
    ET.SubElement(root, "submission_date").text = now_str
    ET.SubElement(root, "currency_code_local").text = "AED"

    # Reporting Entity Details
    rep_ent = ET.SubElement(root, "reporting_entity")
    entity_name = _require(report_data, "reporting_entity_name", "reporting entity name")
    ET.SubElement(rep_ent, "reporting_entity_name").text = entity_name
    branch = report_data.get("reporting_entity_branch") or report_data.get("org_address") or ""
    if branch:
        ET.SubElement(rep_ent, "reporting_entity_branch").text = branch

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

    # Reason / Narrative - FFR-specific for freeze obligations
    narrative = ET.SubElement(root, "reason")
    if report_code == "FFR":
        obligation_type = report_data.get("obligation_type", "sanctions")
        type_labels = {
            "proliferation": "Proliferation Financing (Federal Decree-Law No. 10 of 2025)",
            "terrorism": "Terrorism Financing",
            "sanctions": "Targeted Financial Sanctions"
        }
        type_label = type_labels.get(obligation_type, "Sanctions")

        assets_frozen = report_data.get("assets_frozen") or []
        total_aed = sum(a.get("amount_aed", 0) for a in assets_frozen)

        freeze_desc = (
            f"{type_label} freeze obligation executed. "
            f"Assets frozen: {len(assets_frozen)} item(s), "
            f"total value AED {total_aed:,.2f}. "
            f"Freeze obligation reference: #{report_data.get('freeze_obligation_id')}. "
            f"Identified: {report_data.get('identified_at', 'N/A')}, "
            f"Executed: {report_data.get('executed_at', 'N/A')}."
        )
        if report_data.get("authority_ref"):
            freeze_desc += f" Authority reference: {report_data['authority_ref']}."

        ET.SubElement(narrative, "reason_description").text = freeze_desc
        ET.SubElement(narrative, "action_taken").text = "Asset freeze executed per UAE TFS obligations"
    else:
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
    # FFR always uses activity block (not transaction), even if it has amounts
    if report_code == "FFR":
        act = ET.SubElement(root, "activity")
        assets_frozen = report_data.get("assets_frozen") or []
        if assets_frozen:
            # Build detailed asset freeze description
            asset_details = []
            for i, asset in enumerate(assets_frozen, 1):
                asset_type = asset.get("type", "unknown")
                identifier = asset.get("identifier", "N/A")
                amount = asset.get("amount_aed", 0)
                asset_details.append(f"{i}. {asset_type}: {identifier} (AED {amount:,.2f})")
            asset_list = "; ".join(asset_details)
            desc = f"Asset freeze executed for {report_data.get('obligation_type', 'sanctions')} obligation. Frozen assets: {asset_list}"
        else:
            desc = f"Asset freeze executed for {report_data.get('obligation_type', 'sanctions')} obligation. No liquid assets identified at time of freeze."

        ET.SubElement(act, "activity_description").text = desc
        ET.SubElement(act, "status_code").text = "SUSPENDED"
    elif has_txn:
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
        ET.SubElement(act, "status_code").text = "SUSPENDED" if report_code in ("PNMR",) else "MONITORED"

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
