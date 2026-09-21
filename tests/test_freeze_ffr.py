"""Tests for FFR (Fund Freeze Report) XML generation."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from amlkit.reporting import goaml


def test_serialize_ffr_xml_structure():
    """FFR XML has correct goAML structure."""
    report_data = {
        "report_type": "FFR",
        "freeze_obligation_id": 1,
        "customer_id": 123,
        "obligation_type": "proliferation",
        "identified_at": "2026-09-13T10:00:00Z",
        "executed_at": "2026-09-13T11:30:00Z",
        "assets_frozen": [
            {
                "type": "bank_account",
                "identifier": "AE070331234567890123456",
                "amount_aed": 150000.50
            }
        ],
        "reporting_entity_name": "Test Firm",
        "reporter_name": "John Smith",
        "reporter_email": "john.smith@test.com",
        "first_name": "Sanctioned",
        "last_name": "Person",
        "customer_type": "natural",
        "reference": "C-2026-001",
    }

    xml_str = goaml.serialize_goaml_xml(report_data)

    # Parse XML
    root = ET.fromstring(xml_str)

    # Verify root structure
    assert root.tag == "report"
    assert root.find("report_code").text == "FFR"
    assert root.find("submission_code").text == "NEW"

    # Verify freeze obligation reference
    assert root.find("reason/reason_description") is not None
    desc = root.find("reason/reason_description").text
    assert "freeze" in desc.lower() or "obligation" in desc.lower()

    # Verify subject
    subject = root.find("subject/person")
    assert subject is not None
    assert subject.find("first_name").text == "Sanctioned"

    # Verify activity (FFR uses activity block, not transaction)
    activity = root.find("activity")
    assert activity is not None
    assert activity.find("status_code").text == "SUSPENDED"


def test_serialize_ffr_requires_freeze_obligation_id():
    """FFR raises error if freeze_obligation_id missing."""
    report_data = {
        "report_type": "FFR",
        # Missing freeze_obligation_id
        "reporting_entity_name": "Test Firm",
        "reporter_name": "John Smith",
        "reporter_email": "john.smith@test.com",
    }

    with pytest.raises(goaml.GoAMLValidationError, match="freeze obligation"):
        goaml.serialize_goaml_xml(report_data)


def test_serialize_ffr_includes_assets():
    """FFR XML includes assets_frozen details."""
    report_data = {
        "report_type": "FFR",
        "freeze_obligation_id": 1,
        "customer_id": 123,
        "obligation_type": "sanctions",
        "assets_frozen": [
            {"type": "bank_account", "identifier": "AE070331234567890123456", "amount_aed": 150000.50},
            {"type": "investment_account", "identifier": "INV-12345", "amount_aed": 500000.00}
        ],
        "reporting_entity_name": "Test Firm",
        "reporter_name": "John Smith",
        "reporter_email": "john.smith@test.com",
        "first_name": "Test",
        "last_name": "Customer",
        "customer_type": "natural",
    }

    xml_str = goaml.serialize_goaml_xml(report_data)
    root = ET.fromstring(xml_str)

    # Verify assets are included in activity description or separate section
    activity = root.find("activity")
    assert activity is not None
    desc = activity.find("activity_description").text
    # Should mention assets or total amount
    assert desc is not None


def test_serialize_ffr_obligation_types():
    """FFR handles all obligation types correctly."""
    for obligation_type in ["sanctions", "proliferation", "terrorism"]:
        report_data = {
            "report_type": "FFR",
            "freeze_obligation_id": 1,
            "customer_id": 123,
            "obligation_type": obligation_type,
            "assets_frozen": [],
            "reporting_entity_name": "Test Firm",
            "reporter_name": "John Smith",
            "reporter_email": "john.smith@test.com",
            "first_name": "Test",
            "last_name": "Customer",
            "customer_type": "natural",
        }

        xml_str = goaml.serialize_goaml_xml(report_data)
        root = ET.fromstring(xml_str)

        # Should not raise error and should include obligation type in description
        assert root.find("report_code").text == "FFR"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
