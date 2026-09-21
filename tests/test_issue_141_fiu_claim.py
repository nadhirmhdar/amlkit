"""Test for issue #141: stop claiming STR/SAR was submitted to UAE FIU.

The system does not transmit reports to the FIU. The flash and API responses
must clarify that the report is finalized and the goAML XML must be uploaded
manually to the FIU portal.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest_plugins = ["tests.test_api"]


def _csrf(client):
    return client.cookies.get("amlkit_csrf")


def _create_report(client):
    """Create a customer + draft STR report, return the report id."""
    client.post("/customers", data={
        "reference": "C-141",
        "full_name": "Test Subject",
        "customer_type": "natural",
        "csrf_token": _csrf(client),
    })
    client.post("/reports", data={
        "customer_id": 1,
        "report_type": "STR",
        "reporting_entity_name": "Test Firm",
        "entity_reference": "LIC-141",
        "reporter_name": "Alice MLRO",
        "reporter_email": "alice@testfirm.ae",
        "first_name": "Test",
        "last_name": "Subject",
        "nationality": "AE",
        "amount": "50000",
        "transaction_type": "Wire Transfer",
        "source_account": "AE070331234567890123456",
        "destination_account": "AE070339876543210987654",
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


def test_web_submit_does_not_claim_fiu_transmission(client) -> None:
    """Web submission must NOT claim report was submitted to UAE FIU."""
    report_id = _create_report(client)
    r = client.post(f"/reports/{report_id}/submit",
                   data={"csrf_token": _csrf(client)},
                   follow_redirects=True)
    
    assert r.status_code == 200
    assert "UAE FIU successfully" not in r.text, \
        "Must not claim successful UAE FIU submission"
    assert "goAML portal" in r.text, \
        "Must instruct user to upload to goAML portal manually"
    assert "finalized" in r.text.lower() or "manual" in r.text.lower(), \
        "Must clarify manual upload required"


# Mobile API test coverage is in tests/test_mlro_report_submit.py::test_mlro_can_submit_report
