"""Test for issue #142: goAML XML must use org profile, not hardcoded names.

goAML XML exports were hardcoding "Grovisor Consultants" and "Dubai HQ" for
the reporting entity, regardless of which org was logged in. The fix injects
the session org's actual name/address into the XML serialization.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest_plugins = ["tests.test_api"]


def _csrf(client):
    return client.cookies.get("amlkit_csrf")


def _create_customer_and_report(client):
    """Create a customer + STR report, return the report id."""
    # Set goaml_entity_reference (required for XML export)
    from amlkit.db import connect
    conn = connect(os.environ["AMLKIT_DB"])
    conn.execute("UPDATE organizations SET goaml_entity_reference = ? WHERE id = (SELECT org_id FROM sessions LIMIT 1)", ("TEST-ORG-142",))
    conn.commit()
    conn.close()

    client.post("/customers", data={
        "reference": "C-142",
        "full_name": "Test Subject",
        "customer_type": "natural",
        "csrf_token": _csrf(client),
    })
    r = client.post("/reports", data={
        "customer_id": 1,
        "report_type": "STR",
        "reporting_entity_name": "Test Firm",
        "entity_reference": "LIC-1",
        "reporter_name": "Alice MLRO",
        "reporter_email": "alice@testfirm.ae",
        "first_name": "Test",
        "last_name": "Subject",
        "nationality": "AE",
        "amount": "50000",
        "transaction_type": "Wire Transfer",
        "source_account": "AE070331234567890123456",
        "destination_account": "AE070339876543210987654",
        "source_institution_name": "First Abu Dhabi Bank",
        "destination_institution_name": "Emirates NBD",
        "reason_description": "Suspicious wire.",
        "csrf_token": _csrf(client),
    })

    from amlkit.db import connect
    conn = connect(os.environ["AMLKIT_DB"])
    row = conn.execute(
        "SELECT id FROM reports ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row["id"]


class TestGoAMLOrgName:
    def test_export_xml_contains_org_name_not_hardcoded(self, client) -> None:
        report_id = _create_customer_and_report(client)
        r = client.get(f"/reports/{report_id}/export")
        assert r.status_code == 200

        root = ET.fromstring(r.text)
        entity_name = root.find("reporting_entity/reporting_entity_name").text

        assert entity_name == "Test Firm", \
            f"Expected org name 'Test Firm', got '{entity_name}'"
        assert "Grovisor" not in r.text, \
            "XML must not contain hardcoded 'Grovisor' anywhere"

    def test_export_injects_org_name_when_payload_lacks_it(self, client) -> None:
        """Even if the stored report payload has no reporting_entity_name,
        the export route must inject the org's name from the database."""
        # Set goaml_entity_reference (required for XML export)
        from amlkit.db import connect
        conn = connect(os.environ["AMLKIT_DB"])
        conn.execute("UPDATE organizations SET goaml_entity_reference = ? WHERE id = (SELECT org_id FROM sessions LIMIT 1)", ("TEST-ORG-142b",))
        conn.commit()
        conn.close()

        client.post("/customers", data={
            "reference": "C-142b",
            "full_name": "Another Subject",
            "customer_type": "natural",
            "csrf_token": _csrf(client),
        })
        client.post("/reports", data={
            "customer_id": 1,
            "report_type": "STR",
            "reporting_entity_name": "Test Firm",
            "entity_reference": "LIC-1",
            "reporter_name": "Alice MLRO",
            "reporter_email": "alice@testfirm.ae",
            "first_name": "Another",
            "last_name": "Subject",
            "nationality": "AE",
            "amount": "30000",
            "transaction_type": "Wire Transfer",
            "source_account": "AE070331234567890123456",
            "destination_account": "AE070339876543210987654",
            "source_institution_name": "First Abu Dhabi Bank",
            "destination_institution_name": "Emirates NBD",
            "reason_description": "Suspicious.",
            "csrf_token": _csrf(client),
        })

        from amlkit.db import connect
        conn = connect(os.environ["AMLKIT_DB"])
        row = conn.execute(
            "SELECT id, payload FROM reports ORDER BY id DESC LIMIT 1"
        ).fetchone()
        import json
        payload = json.loads(row["payload"])
        payload.pop("reporting_entity_name", None)
        conn.execute("UPDATE reports SET payload=? WHERE id=?",
                      (json.dumps(payload), row["id"]))
        conn.commit()
        conn.close()

        r = client.get(f"/reports/{row['id']}/export")
        assert r.status_code == 200
        root = ET.fromstring(r.text)
        entity_name = root.find("reporting_entity/reporting_entity_name").text
        assert entity_name == "Test Firm", \
            f"Export must inject org name from DB when payload lacks it, got '{entity_name}'"

    def test_export_xml_does_not_contain_hardcoded_dubai_hq(self, client) -> None:
        report_id = _create_customer_and_report(client)
        r = client.get(f"/reports/{report_id}/export")
        assert r.status_code == 200
        assert "Dubai HQ" not in r.text, \
            "XML must not contain hardcoded 'Dubai HQ'"

    def test_serializer_requires_reporting_entity_name(self) -> None:
        from amlkit.reporting.goaml import GoAMLValidationError, serialize_goaml_xml
        payload = {
            "report_type": "STR",
            "customer_type": "natural",
            "reporter_name": "Jane Officer",
            "reporter_email": "jane@test.ae",
            "first_name": "Ahmed",
            "last_name": "Al Mansoori",
            "nationality": "AE",
        }
        with pytest.raises(GoAMLValidationError, match="reporting entity name"):
            serialize_goaml_xml(payload)
