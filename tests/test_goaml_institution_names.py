"""goAML export: institution names must come from transaction data.

Kanban #261 / GitHub #261. The original bug (fixed in goaml.py) hardcoded the
literal strings "Originating Bank" / "Beneficiary Bank" as the from/to account
institution_name, so every filed STR/SAR carried placeholder counterparties
regardless of the real banks involved.

test_goaml.py already pins the required-field and blank-fallback behaviour of
the serialiser; test_goaml_tenant_data.py pins the save->export path carries a
tenant's own figures. The gap this file closes is a focused *regression guard*
for #261 specifically: the serialiser must (a) echo whatever institution names
the report payload provides, and (b) never emit the old hardcoded literals --
not even when the institution fields are blank or absent.

Pure unit tests against serialize_goaml_xml (no DB), matching test_goaml.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.reporting.goaml import serialize_goaml_xml  # noqa: E402


_HARDCODED_LITERALS = ("Originating Bank", "Beneficiary Bank")


def _txn_payload(**overrides) -> dict:
    payload = {
        "report_type": "STR",
        "customer_type": "natural",
        "reporting_entity_name": "Test Firm Consultants",
        "entity_reference": "TF-LIC-0001",
        "reporter_name": "Jane Officer",
        "reporter_email": "jane@grovisor.test",
        "first_name": "Ahmed",
        "last_name": "Al Mansoori",
        "nationality": "AE",
        "amount": "250000",
        "transaction_type": "Wire Transfer",
        "source_account": "AE1111",
        "destination_account": "AE2222",
    }
    payload.update(overrides)
    return payload


class TestInstitutionNamesComeFromData:
    def test_from_institution_name_echoes_the_payload(self) -> None:
        payload = _txn_payload(
            source_institution_name="Mashreq Bank",
            destination_institution_name="First Abu Dhabi Bank",
        )
        root = ET.fromstring(serialize_goaml_xml(payload))
        assert root.find("transaction/t_from/account/institution_name").text == "Mashreq Bank"

    def test_to_institution_name_echoes_the_payload(self) -> None:
        payload = _txn_payload(
            source_institution_name="Mashreq Bank",
            destination_institution_name="First Abu Dhabi Bank",
        )
        root = ET.fromstring(serialize_goaml_xml(payload))
        assert root.find("transaction/t_to/account/institution_name").text == "First Abu Dhabi Bank"

    def test_distinct_counterparties_are_not_collapsed(self) -> None:
        payload = _txn_payload(
            source_institution_name="Emirates NBD",
            destination_institution_name="Abu Dhabi Commercial Bank",
        )
        root = ET.fromstring(serialize_goaml_xml(payload))
        src = root.find("transaction/t_from/account/institution_name").text
        dst = root.find("transaction/t_to/account/institution_name").text
        assert src == "Emirates NBD"
        assert dst == "Abu Dhabi Commercial Bank"
        assert src != dst


class TestHardcodedLiteralsNeverReappear:
    def test_no_hardcoded_literal_when_names_provided(self) -> None:
        payload = _txn_payload(
            source_institution_name="Mashreq Bank",
            destination_institution_name="First Abu Dhabi Bank",
        )
        xml = serialize_goaml_xml(payload)
        for literal in _HARDCODED_LITERALS:
            assert literal not in xml

    def test_no_hardcoded_literal_when_names_blank(self) -> None:
        payload = _txn_payload(
            source_institution_name="",
            destination_institution_name="",
        )
        xml = serialize_goaml_xml(payload)
        for literal in _HARDCODED_LITERALS:
            assert literal not in xml

    def test_no_hardcoded_literal_when_names_absent(self) -> None:
        payload = _txn_payload()
        assert "source_institution_name" not in payload
        assert "destination_institution_name" not in payload
        xml = serialize_goaml_xml(payload)
        for literal in _HARDCODED_LITERALS:
            assert literal not in xml

    def test_blank_institution_exports_empty_element_not_literal(self) -> None:
        payload = _txn_payload(
            source_institution_name="",
            destination_institution_name="Noor Bank",
        )
        root = ET.fromstring(serialize_goaml_xml(payload))
        # blank source exports as an empty element (text None), real dest echoes
        assert root.find("transaction/t_from/account/institution_name").text is None
        assert root.find("transaction/t_to/account/institution_name").text == "Noor Bank"


class TestWhitespaceOnlyNameIsTreatedAsBlank:
    def test_whitespace_only_institution_name_does_not_leak_whitespace(self) -> None:
        payload = _txn_payload(
            source_institution_name="   ",
            destination_institution_name="\t",
        )
        root = ET.fromstring(serialize_goaml_xml(payload))
        assert root.find("transaction/t_from/account/institution_name").text is None
        assert root.find("transaction/t_to/account/institution_name").text is None
