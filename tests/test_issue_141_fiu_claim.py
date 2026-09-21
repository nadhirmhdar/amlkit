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
    from amlkit.db import connect
    conn = connect(os.environ["AMLKIT_DB"])
    customer_id = conn.execute(
        "SELECT id FROM customers WHERE reference=?", ("C-141",)
    ).fetchone()["id"]
    conn.close()
    client.post("/reports", data={
        "customer_id": customer_id,
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


def _flash_text(resp) -> str:
    """Decode the flash cookie set on a redirect response."""
    import base64
    import json
    raw = resp.cookies.get("amlkit_flash")
    assert raw, "expected a flash cookie"
    return json.loads(base64.b64decode(raw))["text"]


def test_web_submit_does_not_claim_fiu_transmission(client) -> None:
    """Web finalize must NOT claim the report was submitted to UAE FIU."""
    report_id = _create_report(client)
    r = client.post(f"/reports/{report_id}/submit",
                    data={"csrf_token": _csrf(client)},
                    follow_redirects=False)
    assert r.status_code == 303

    flash = _flash_text(r)
    assert "<" not in flash and ">" not in flash, "flash must be plain text, no raw HTML"
    assert "goAML portal" in flash
    assert "finalized" in flash.lower()
    assert "successfully" not in flash.lower()
    assert len(r.headers.get("set-cookie", "")) < 1000  # keep flash cookie short

    page = client.get(f"/reports/{report_id}")
    assert page.status_code == 200
    assert "Report finalized" in page.text
    assert f"/reports/{report_id}/export" in page.text
    assert "officially filed" not in page.text

    from amlkit.db import connect
    conn = connect(os.environ["AMLKIT_DB"])
    row = conn.execute("SELECT status, submitted_at FROM reports WHERE id=?",
                       (report_id,)).fetchone()
    audits = conn.execute(
        "SELECT action FROM audit_log WHERE object_type='report' AND object_id=?",
        (str(report_id),)).fetchall()
    conn.close()
    assert row["status"] == "submitted"
    actions = [a["action"] for a in audits]
    assert "report.finalized" in actions
    assert "report.submit" not in actions


def test_web_double_finalize_rejected(client) -> None:
    report_id = _create_report(client)
    client.post(f"/reports/{report_id}/submit", data={"csrf_token": _csrf(client)})

    from amlkit.db import connect
    conn = connect(os.environ["AMLKIT_DB"])
    first_ts = conn.execute("SELECT submitted_at FROM reports WHERE id=?",
                            (report_id,)).fetchone()["submitted_at"]
    conn.close()

    r = client.post(f"/reports/{report_id}/submit",
                    data={"csrf_token": _csrf(client)}, follow_redirects=False)
    assert "already been finalized" in _flash_text(r)

    conn = connect(os.environ["AMLKIT_DB"])
    second_ts = conn.execute("SELECT submitted_at FROM reports WHERE id=?",
                             (report_id,)).fetchone()["submitted_at"]
    n = conn.execute(
        "SELECT COUNT(*) c FROM audit_log WHERE action='report.finalized' AND object_id=?",
        (str(report_id),)).fetchone()["c"]
    conn.close()
    assert second_ts == first_ts
    assert n == 1
