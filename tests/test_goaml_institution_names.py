"""Test for issue #261: goAML XML must source institution names from transaction data.

Before this fix, serialize_goaml_xml hardcoded "Originating Bank" and "Beneficiary Bank"
as institution_name for from_acc and to_acc in every STR/SAR filing, regardless of the
actual counterparty institutions. This test ensures real institution names from the
transaction payload are used instead.
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.reporting.goaml import GoAMLValidationError, serialize_goaml_xml  # noqa: E402


def _base_payload(**overrides) -> dict:
    payload = {
        "report_type": "STR",
        "customer_type": "natural",
        "reporting_entity_name": "Test Firm",
        "reporter_name": "Jane Officer",
        "reporter_email": "jane@grovisor.test",
        "first_name": "Ahmed",
        "last_name": "Al Mansoori",
        "nationality": "AE",
        "amount": 50000.0,
        "transaction_type": "Wire Transfer",
        "source_account": "AE070331234567890123456",
        "destination_account": "AE070339876543210987654",
        "source_institution_name": "First Abu Dhabi Bank",
        "destination_institution_name": "Emirates NBD",
    }
    payload.update(overrides)
    return payload


class TestGoAMLInstitutionNames:
    """Regression test: institution names must come from transaction data, not hardcoded."""

    def test_no_hardcoded_originating_bank_in_xml(self) -> None:
        """XML must not contain the literal string 'Originating Bank'."""
        payload = _base_payload()
        xml_content = serialize_goaml_xml(payload)

        assert "Originating Bank" not in xml_content, \
            "XML must not contain hardcoded 'Originating Bank' - should use actual institution name"

    def test_no_hardcoded_beneficiary_bank_in_xml(self) -> None:
        """XML must not contain the literal string 'Beneficiary Bank'."""
        payload = _base_payload()
        xml_content = serialize_goaml_xml(payload)

        assert "Beneficiary Bank" not in xml_content, \
            "XML must not contain hardcoded 'Beneficiary Bank' - should use actual institution name"

    def test_source_institution_name_appears_in_from_account(self) -> None:
        """from_acc/institution_name must contain the source institution from payload."""
        payload = _base_payload(source_institution_name="First Abu Dhabi Bank")
        xml_content = serialize_goaml_xml(payload)
        root = ET.fromstring(xml_content)

        from_institution = root.find("transaction/t_from/account/institution_name")
        assert from_institution is not None, "t_from/account/institution_name element missing"
        assert from_institution.text == "First Abu Dhabi Bank", \
            f"Expected 'First Abu Dhabi Bank', got '{from_institution.text}'"

    def test_destination_institution_name_appears_in_to_account(self) -> None:
        """to_acc/institution_name must contain the destination institution from payload."""
        payload = _base_payload(destination_institution_name="Emirates NBD")
        xml_content = serialize_goaml_xml(payload)
        root = ET.fromstring(xml_content)

        to_institution = root.find("transaction/t_to/account/institution_name")
        assert to_institution is not None, "t_to/account/institution_name element missing"
        assert to_institution.text == "Emirates NBD", \
            f"Expected 'Emirates NBD', got '{to_institution.text}'"

    def test_missing_source_institution_name_is_rejected(self) -> None:
        """Missing source_institution_name must raise GoAMLValidationError."""
        payload = _base_payload(source_institution_name="")

        with pytest.raises(GoAMLValidationError, match="source institution"):
            serialize_goaml_xml(payload)

    def test_missing_destination_institution_name_is_rejected(self) -> None:
        """Missing destination_institution_name must raise GoAMLValidationError."""
        payload = _base_payload(destination_institution_name="")

        with pytest.raises(GoAMLValidationError, match="destination institution"):
            serialize_goaml_xml(payload)

    def test_institution_names_not_required_when_no_transaction(self) -> None:
        """If there's no transaction (no amount), institution names are not required."""
        payload = {
            "report_type": "SAR",
            "customer_type": "natural",
            "reporting_entity_name": "Test Firm",
            "reporter_name": "Jane Officer",
            "reporter_email": "jane@test.ae",
            "first_name": "Ahmed",
            "last_name": "Al Mansoori",
            "nationality": "AE",
        }

        # Should not raise - no transaction block, so no institution names needed
        xml_content = serialize_goaml_xml(payload)
        assert xml_content
