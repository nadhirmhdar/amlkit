"""goAML filings must never carry placeholder values (Issue #268).

A statutory STR/SAR/CNMR containing a made-up bank name, "N/A", "Unknown" or a
sample reference looks like real data to the FIU. Every such value must come
from tenant data or finalisation must be refused naming the field.
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import report_finalize_error  # noqa: E402
from amlkit.db import connect  # noqa: E402
from amlkit.reporting.goaml import GoAMLValidationError, serialize_goaml_xml  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GOAML_SRC = ROOT / "amlkit" / "reporting" / "goaml.py"
BUILDER_TEMPLATE = ROOT / "amlkit" / "web" / "templates" / "str_builder.html"


def _code_strings(path: Path) -> list[str]:
    """String literals in code, excluding docstrings."""
    import ast
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    docs = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body \
                and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant):
            docs.add(id(n.body[0].value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]


PLACEHOLDER_PATTERNS = [
    re.compile(r"^[A-Z][a-z]+ Bank$"),                    # "Originating Bank", "Beneficiary Bank"
    re.compile(r"^(N/A|n/a|NA|TBD|Unknown|unknown)$"),
    re.compile(r"(?i)\bgrovisor\b|dubai hq|\bexample\b|lorem|\bTXN-REF-\d+|^AML-REF$|^ACME\b"),
    re.compile(r"^(Private Company|Passport)$"),          # guessed stand-ins for tenant data
]


def test_goaml_module_has_no_placeholder_literals():
    offenders = [s for s in _code_strings(GOAML_SRC) for p in PLACEHOLDER_PATTERNS if p.search(s)]
    assert not offenders, f"placeholder-style literals in goaml.py: {offenders}"


def test_builder_template_does_not_prefill_guessed_id_type():
    html = BUILDER_TEMPLATE.read_text(encoding="utf-8")
    assert "or 'Passport'" not in html


def _payload(**kw) -> dict:
    p = {
        "report_type": "STR", "customer_type": "natural",
        "reporting_entity_name": "Test Firm", "entity_reference": "LIC-1",
        "reporter_name": "Jane Officer", "reporter_email": "jane@firm.test",
        "first_name": "Ahmed", "last_name": "Al Mansoori", "nationality": "AE",
        "reason_description": "Structured cash deposits.",
        "amount": 75000.0, "transaction_type": "Wire Transfer",
        "source_account": "AE070331234567890123456",
        "destination_account": "AE070339876543210987654",
    }
    p.update(kw)
    return p


@pytest.fixture()
def org(tmp_path):
    conn = connect(tmp_path / "t.db")
    cur = conn.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES ('Tenant One', 'tenant-one', '2026-01-01')")
    conn.commit()
    yield conn, cur.lastrowid
    conn.close()


def _rep(payload: dict) -> dict:
    return {"status": "draft", "payload": json.dumps(payload)}


def test_complete_report_is_finalisable_and_has_no_stand_in_text(org):
    conn, org_id = org
    assert report_finalize_error(_rep(_payload()), conn, org_id) is None
    xml = serialize_goaml_xml(_payload())
    for bad in ("TXN-REF-001", "AML-REF", "Originating Bank", "Beneficiary Bank", "N/A", "Unknown"):
        assert bad not in xml
    root = ET.fromstring(xml)
    assert root.find("transaction/transmode_code").text == "Wire Transfer"
    assert root.find("transaction/internal_ref_number").text == root.find("transaction/transactionnumber").text


@pytest.mark.parametrize("field,label", [
    ("source_account", "source account number"),
    ("destination_account", "destination account number"),
    ("transaction_type", "transaction type"),
    ("reason_description", "reason for suspicion"),
])
def test_report_missing_counterparty_or_transaction_data_cannot_be_finalised(org, field, label):
    conn, org_id = org
    err = report_finalize_error(_rep(_payload(**{field: ""})), conn, org_id)
    assert err and label in err, err


def test_missing_entity_reference_is_refused_not_defaulted(org):
    conn, org_id = org
    p = _payload()
    del p["entity_reference"]
    err = report_finalize_error(_rep(p), conn, org_id)
    assert err and "entity reference" in err
    with pytest.raises(GoAMLValidationError):
        serialize_goaml_xml(p)


def test_id_number_without_type_is_refused_not_defaulted_to_passport(org):
    conn, org_id = org
    err = report_finalize_error(_rep(_payload(id_number="784-1234", id_type="")), conn, org_id)
    assert err and "ID document type" in err


def test_no_invented_issue_country_or_legal_form():
    xml = serialize_goaml_xml(_payload(id_number="X1", id_type="Passport", nationality=""))
    assert ET.fromstring(xml).find("subject/person/identification/issue_country") is None
    xml = serialize_goaml_xml(_payload(customer_type="legal", first_name="Acme LLC", nationality="AE"))
    assert ET.fromstring(xml).find("subject/entity/incorporation_legal_form") is None


def _ffr(**kw) -> dict:
    p = _payload(report_type="FFR", freeze_obligation_id=7, obligation_type="sanctions",
                 identified_at="2026-10-01T10:00:00Z", executed_at="2026-10-01T12:00:00Z",
                 assets_frozen=[{"type": "bank_account", "identifier": "AE0001", "amount_aed": 10}])
    p.update(kw)
    return p


def test_ffr_complete_has_no_placeholders():
    xml = serialize_goaml_xml(_ffr())
    assert "N/A" not in xml and "unknown" not in xml


@pytest.mark.parametrize("override", [
    {"identified_at": ""}, {"executed_at": ""},
    {"assets_frozen": [{"type": "", "identifier": "AE0001", "amount_aed": 1}]},
    {"assets_frozen": [{"type": "bank_account", "amount_aed": 1}]},
])
def test_ffr_missing_freeze_data_is_refused(override):
    with pytest.raises(GoAMLValidationError):
        serialize_goaml_xml(_ffr(**override))
