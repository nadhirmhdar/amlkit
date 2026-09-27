"""H16: an FFR for a legal entity must carry the entity's full name, and a blank
customer name must be refused cleanly rather than crash on split()[0].

Drives the real freeze.file_ffr_report() against an executed freeze.
"""
from __future__ import annotations

import json

import pytest

from amlkit.cases import freeze, manager
from amlkit.db import utcnow


def _executed_freeze(conn, org_id: int, full_name: str, customer_type: str) -> int:
    now = utcnow()
    cid = conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
           onboarded_at, status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (org_id, f"C-H16-{customer_type}-{len(full_name)}", full_name, customer_type,
         "k", now, "active", now, now),
    ).lastrowid
    fid = manager.create_freeze_obligation(
        conn, org_id, cid, obligation_type="terrorism", risk_category="critical",
        identified_by="mlro",
    )
    manager.execute_freeze(
        conn, fid, org_id=org_id, executed_by="mlro",
        assets_frozen=[{"type": "cash", "identifier": "safe-1", "amount_aed": 60000}],
    )
    return fid


def _ffr_payload(conn, org_id: int, fid: int) -> dict:
    report_id = freeze.file_ffr_report(
        conn, fid, org_id, reporter_name="Mary MLRO", reporter_email="mlro@firm.ae",
        operator="mlro",
    )
    row = conn.execute("SELECT payload FROM reports WHERE id=?", (report_id,)).fetchone()
    return json.loads(row["payload"])


def test_legal_entity_ffr_uses_full_entity_name(conn, org_id):
    fid = _executed_freeze(conn, org_id, "Gulf Falcon Trading LLC", "legal")
    payload = _ffr_payload(conn, org_id, fid)
    assert payload["first_name"] == "Gulf Falcon Trading LLC"
    assert payload["last_name"] == ""


def test_natural_person_ffr_still_splits_name(conn, org_id):
    fid = _executed_freeze(conn, org_id, "Ahmed Saeed Al Mansoori", "natural")
    payload = _ffr_payload(conn, org_id, fid)
    assert payload["first_name"] == "Ahmed"
    assert payload["last_name"] == "Saeed Al Mansoori"


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_name_is_refused_without_a_report(conn, org_id, blank):
    fid = _executed_freeze(conn, org_id, blank, "natural")
    with pytest.raises(ValueError, match="full_name is blank"):
        freeze.file_ffr_report(
            conn, fid, org_id, reporter_name="Mary MLRO", reporter_email="mlro@firm.ae",
            operator="mlro",
        )
    assert conn.execute(
        "SELECT COUNT(*) FROM reports WHERE org_id=? AND report_type='FFR'", (org_id,)
    ).fetchone()[0] == 0
    status = conn.execute("SELECT status FROM freeze_obligations WHERE id=?", (fid,)).fetchone()[0]
    assert status == "executed_pending_report"
