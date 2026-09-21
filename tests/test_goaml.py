"""goAML XML export tests.

A regulator-facing filing must never silently substitute a placeholder for
missing identifying data (reporting officer, subject identity, source/
destination account) -- it must fail loudly so the operator fixes the report
before it is filed. This also covers the transaction-number UTC/uniqueness
fix (see amlkit/reporting/goaml.py).
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
    }
    payload.update(overrides)
    return payload


class TestRequiredFields:
    def test_missing_reporter_name_is_rejected(self) -> None:
        payload = _base_payload(reporter_name="")
        with pytest.raises(GoAMLValidationError):
            serialize_goaml_xml(payload)

    def test_missing_reporter_email_is_rejected(self) -> None:
        payload = _base_payload(reporter_email="   ")
        with pytest.raises(GoAMLValidationError):
            serialize_goaml_xml(payload)

    def test_missing_natural_person_first_name_is_rejected(self) -> None:
        payload = _base_payload(first_name="")
        with pytest.raises(GoAMLValidationError):
            serialize_goaml_xml(payload)

    def test_missing_legal_entity_name_is_rejected(self) -> None:
        payload = _base_payload(customer_type="legal", first_name="")
        with pytest.raises(GoAMLValidationError):
            serialize_goaml_xml(payload)

    def test_legal_entity_name_comes_from_first_name_field(self) -> None:
        """The report form stores the entity name under "first_name" (there
        is no separate "full_name" key in a saved report payload) -- the
        serializer must read the field that is actually populated."""
        payload = _base_payload(customer_type="legal", first_name="Acme Trading LLC")
        xml_content = serialize_goaml_xml(payload)
        root = ET.fromstring(xml_content)
        assert root.find("subject/entity/name").text == "Acme Trading LLC"

    def test_missing_source_account_is_rejected_when_transaction_present(self) -> None:
        payload = _base_payload(amount=10000.0, transaction_type="Wire Transfer",
                                 source_account="", destination_account="AE1234")
        with pytest.raises(GoAMLValidationError):
            serialize_goaml_xml(payload)

    def test_missing_destination_account_is_rejected_when_transaction_present(self) -> None:
        payload = _base_payload(amount=10000.0, transaction_type="Wire Transfer",
                                 source_account="AE1234", destination_account="")
        with pytest.raises(GoAMLValidationError):
            serialize_goaml_xml(payload)

    def test_accounts_not_required_when_no_transaction(self) -> None:
        payload = _base_payload()
        xml_content = serialize_goaml_xml(payload)
        assert xml_content  # no transaction block requested, so no error


class TestTransactionNumber:
    def test_transaction_number_is_unique_across_same_second_calls(self) -> None:
        payload = _base_payload(amount=10000.0, transaction_type="Wire Transfer",
                                 source_account="AE1111", destination_account="AE2222")
        numbers = set()
        for _ in range(20):
            xml_content = serialize_goaml_xml(payload)
            root = ET.fromstring(xml_content)
            numbers.add(root.find("transaction/transactionnumber").text)
        assert len(numbers) == 20

    def test_transaction_number_uses_utc_timestamp(self) -> None:
        from datetime import datetime, timezone

        payload = _base_payload(amount=10000.0, transaction_type="Wire Transfer",
                                 source_account="AE1111", destination_account="AE2222")
        xml_content = serialize_goaml_xml(payload)
        root = ET.fromstring(xml_content)
        txn_number = root.find("transaction/transactionnumber").text
        embedded_ts = int(txn_number.split("-")[1])
        assert abs(embedded_ts - int(datetime.now(timezone.utc).timestamp())) < 5


class TestValidPayload:
    def test_full_natural_person_str_serializes(self) -> None:
        payload = _base_payload(amount=10000.0, transaction_type="Wire Transfer",
                                 source_account="AE1111", destination_account="AE2222")
        xml_content = serialize_goaml_xml(payload)
        root = ET.fromstring(xml_content)
        assert root.find("subject/person/first_name").text == "Ahmed"
        assert root.find("reporting_person/first_name").text == "Jane"
        assert root.find("transaction/t_from/account/account_number").text == "AE1111"
        assert root.find("transaction/t_to/account/account_number").text == "AE2222"

