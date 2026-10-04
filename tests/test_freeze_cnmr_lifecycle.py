"""A freeze is 'reported' only once its CNMR is finalised, not when drafted.

file_ffr_report() used to create a draft report and immediately mark the
freeze 'reported' (with reported_at), so a freeze dropped off the
pending-report views while nothing had been filed. Now drafting only links
the report; finalising it (web or mobile submit) moves the freeze to
'reported', in the same transaction, with a 'freeze.reported' audit row.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases import freeze, manager  # noqa: E402
from amlkit.db import utcnow  # noqa: E402
from test_api import client, _csrf, _register  # noqa: E402,F401
from test_mobile_api import api  # noqa: E402,F401


def _executed_freeze(conn, org_id: int, ref: str = "C-CNMR-1") -> int:
    now = utcnow()
    cid = conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
           onboarded_at, status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (org_id, ref, "Ahmed Saeed Al Mansoori", "natural", ref.lower(), now, "active", now, now),
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


def _draft(conn, org_id: int, fid: int) -> int:
    return freeze.file_ffr_report(
        conn, fid, org_id, reporter_name="Mary MLRO", reporter_email="mlro@firm.ae",
        operator="mlro",
    )


def _freeze_row(conn, fid: int):
    return conn.execute(
        "SELECT status, reported_at, report_id FROM freeze_obligations WHERE id=?", (fid,)
    ).fetchone()


def _audit_actions(conn, fid: int) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT action FROM audit_log WHERE object_type='freeze_obligation' AND object_id=?"
        " ORDER BY id", (str(fid),)
    )]


# ------------------------------------------------------------------ unit level

def test_draft_links_report_but_does_not_mark_reported(conn, org_id):
    fid = _executed_freeze(conn, org_id)
    report_id = _draft(conn, org_id, fid)

    row = _freeze_row(conn, fid)
    assert row["status"] == "executed_pending_report"
    assert row["reported_at"] is None
    assert row["report_id"] == report_id
    rep = conn.execute("SELECT status FROM reports WHERE id=?", (report_id,)).fetchone()
    assert rep["status"] == "draft"
    actions = _audit_actions(conn, fid)
    assert "freeze.report_drafted" in actions
    assert "freeze.reported" not in actions


def test_second_draft_attempt_returns_existing_report(conn, org_id):
    fid = _executed_freeze(conn, org_id)
    first = _draft(conn, org_id, fid)
    second = _draft(conn, org_id, fid)

    assert second == first
    assert conn.execute(
        "SELECT COUNT(*) FROM reports WHERE org_id=? AND report_type='FFR'", (org_id,)
    ).fetchone()[0] == 1
    assert _freeze_row(conn, fid)["status"] == "executed_pending_report"


def test_mark_reported_is_org_scoped(conn, org_id):
    fid = _executed_freeze(conn, org_id)
    report_id = _draft(conn, org_id, fid)
    other_org = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id",
        ("Other Firm", "other-firm", "active", utcnow()),
    ).fetchone()["id"]

    with conn:
        assert freeze.mark_freeze_reported(conn, report_id, other_org, "mallory", utcnow()) == []
    assert _freeze_row(conn, fid)["status"] == "executed_pending_report"

    now = utcnow()
    with conn:
        assert freeze.mark_freeze_reported(conn, report_id, org_id, "mlro", now) == [fid]
    row = _freeze_row(conn, fid)
    assert row["status"] == "reported"
    assert row["reported_at"] == now
    assert _audit_actions(conn, fid)[-1] == "freeze.reported"


# ------------------------------------------------------------------ web route

def _db() -> sqlite3.Connection:
    c = sqlite3.connect(os.environ["AMLKIT_DB"])
    c.row_factory = sqlite3.Row
    return c


def _seed_executed_freeze_in_test_db() -> int:
    conn = _db()
    org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
    conn.execute("UPDATE organizations SET goaml_entity_reference=? WHERE id=?",
                 ("TEST-ORG-CNMR", org_id))
    now = utcnow()
    cid = conn.execute("""
        INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
                               status, birth_date, gender, nationality, id_number, id_type,
                               onboarded_at, created_at, updated_at)
        VALUES (?, 'C-CNMR-WEB', 'Ahmad Al-Test', 'natural', 'c-cnmr-web', 'active',
                '1980-05-15', 'male', 'SY', '123456789', 'passport', ?, ?, ?)
    """, (org_id, now, now, now)).lastrowid
    fid = conn.execute("""
        INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
                                        status, identified_at, identified_by, executed_at,
                                        executed_by, assets_frozen, authority_ref)
        VALUES (?, ?, 'sanctions', 'critical', 'executed_pending_report', ?, 'alice', ?, 'alice',
                '[{"type":"cash","identifier":"USD","amount_aed":10000}]', 'UN-CNMR')
    """, (org_id, cid, now, now)).lastrowid
    conn.commit()
    conn.close()
    return fid


def _ffr_form(c) -> dict:
    return {"csrf_token": _csrf(c), "reporter_email": "alice@testfirm.ae"}


def test_web_submit_marks_freeze_reported_with_audit(client):
    fid = _seed_executed_freeze_in_test_db()
    base = f"/freeze-obligations/{fid}"

    r = client.post(f"{base}/file-ffr", data=_ffr_form(client), follow_redirects=True)
    assert r.status_code == 200 and "/reports/" in str(r.url)
    # Filing again (double-click) lands on the same draft, no duplicate.
    r2 = client.post(f"{base}/file-ffr", data=_ffr_form(client), follow_redirects=True)
    assert str(r2.url) == str(r.url)

    conn = _db()
    row = _freeze_row(conn, fid)
    assert row["status"] == "executed_pending_report" and row["reported_at"] is None
    assert conn.execute("SELECT COUNT(*) FROM reports WHERE report_type='FFR'").fetchone()[0] == 1
    # Still counted as pending report on the list page.
    assert "Executed: 1" in client.get("/freeze-obligations").text

    r = client.post(f"/reports/{row['report_id']}/submit",
                    data={"csrf_token": _csrf(client)}, follow_redirects=True)
    assert r.status_code == 200
    row = _freeze_row(conn, fid)
    assert row["status"] == "reported"
    assert row["reported_at"] is not None
    audit = conn.execute(
        "SELECT actor, detail FROM audit_log WHERE action='freeze.reported' AND object_id=?",
        (str(fid),),
    ).fetchall()
    conn.close()
    assert len(audit) == 1
    assert str(row["report_id"]) in audit[0]["detail"]


def test_other_org_cannot_submit_and_report_the_freeze(client):
    fid = _seed_executed_freeze_in_test_db()
    client.post(f"/freeze-obligations/{fid}/file-ffr", data=_ffr_form(client))
    conn = _db()
    report_id = _freeze_row(conn, fid)["report_id"]
    conn.close()
    assert report_id is not None

    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    bob = TestClient(app)
    _register(bob, "Other Firm", "bob", "bob@otherfirm.ae", "strong-pass-123")
    r = bob.post(f"/reports/{report_id}/submit", data={"csrf_token": _csrf(bob)},
                 follow_redirects=True)
    assert r.status_code == 200
    assert "not found" in r.text.lower()
    # Bob can't draft a second CNMR on it either.
    bob.post(f"/freeze-obligations/{fid}/file-ffr", data=_ffr_form(bob))

    conn = _db()
    row = _freeze_row(conn, fid)
    assert row["status"] == "executed_pending_report" and row["reported_at"] is None
    assert conn.execute("SELECT status FROM reports WHERE id=?", (report_id,)).fetchone()[0] == "draft"
    assert conn.execute("SELECT COUNT(*) FROM reports WHERE report_type='FFR'").fetchone()[0] == 1
    conn.close()


# ------------------------------------------------------------------ mobile API

def test_mobile_submit_marks_freeze_reported(api):
    client, headers = api
    from amlkit.db import connect
    conn = connect(os.environ["AMLKIT_DB"])
    org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
    conn.execute("UPDATE organizations SET goaml_entity_reference=? WHERE id=?",
                 ("TEST-ORG-MOB", org_id))
    fid = _executed_freeze(conn, org_id, "C-CNMR-MOB")
    report_id = _draft(conn, org_id, fid)
    assert _freeze_row(conn, fid)["status"] == "executed_pending_report"
    conn.close()

    r = client.post(f"/api/v1/reports/{report_id}/submit", headers=headers)
    assert r.status_code == 200, r.text

    conn = connect(os.environ["AMLKIT_DB"])
    row = _freeze_row(conn, fid)
    assert row["status"] == "reported" and row["reported_at"] is not None
    assert "freeze.reported" in _audit_actions(conn, fid)
    conn.close()


# ------------------------------------------------- legacy data fix (pre-#385)

def _legacy_reported_with_draft(conn, org_id: int, ref: str) -> tuple[int, int]:
    """Recreate the pre-#385 state: freeze 'reported' while its CNMR is a draft."""
    fid = _executed_freeze(conn, org_id, ref)
    rid = _draft(conn, org_id, fid)
    conn.execute(
        "UPDATE freeze_obligations SET status='reported', reported_at=? WHERE id=?",
        ("2026-09-30T10:00:00Z", fid),
    )
    conn.commit()
    return fid, rid


def test_legacy_drafts_behind_reported_freezes_are_finalised(conn, org_id):
    from amlkit.db import _finalise_legacy_cnmr_drafts

    fid, rid = _legacy_reported_with_draft(conn, org_id, "C-LEGACY-1")
    # A freeze drafted under the new rule (still pending) must be left alone.
    pending_fid = _executed_freeze(conn, org_id, "C-PENDING-1")
    pending_rid = _draft(conn, org_id, pending_fid)

    done = _finalise_legacy_cnmr_drafts(conn)
    conn.commit()

    assert done == [{"report_id": rid, "freeze_id": fid, "org_id": org_id}]
    rep = conn.execute("SELECT status, submitted_at FROM reports WHERE id=?", (rid,)).fetchone()
    assert rep["status"] == "submitted"
    assert rep["submitted_at"] == "2026-09-30T10:00:00Z"  # the freeze's reported_at
    audit_row = conn.execute(
        "SELECT actor, detail, org_id FROM audit_log WHERE action='report.finalized'"
        " AND object_type='report' AND object_id=?", (str(rid),)
    ).fetchone()
    assert audit_row["actor"] == "system" and audit_row["org_id"] == org_id
    assert '"via": "data_fix"' in audit_row["detail"]

    assert conn.execute("SELECT status FROM reports WHERE id=?",
                        (pending_rid,)).fetchone()["status"] == "draft"
    assert _freeze_row(conn, pending_fid)["status"] == "executed_pending_report"

    # Nothing left to do on a second pass.
    assert _finalise_legacy_cnmr_drafts(conn) == []


def test_legacy_draft_fix_runs_once_per_database(tmp_path):
    from amlkit.db import _reset_init_cache, connect
    from conftest import seed_fresh_dataset

    db_file = tmp_path / "legacy.db"
    c = connect(db_file)
    seed_fresh_dataset(c)
    org = c.execute(
        "INSERT INTO organizations (name, slug, status, created_at, goaml_entity_reference)"
        " VALUES ('L','l','active',?, 'L-1') RETURNING id", (utcnow(),)
    ).fetchone()["id"]
    c.commit()
    _, rid = _legacy_reported_with_draft(c, org, "C-LEGACY-2")
    c.execute("DELETE FROM data_migrations WHERE name='finalise_legacy_cnmr_drafts'")
    c.commit()
    c.close()

    _reset_init_cache()  # a new process (deploy) runs the one-shot fix
    c = connect(db_file)
    assert c.execute("SELECT status FROM reports WHERE id=?", (rid,)).fetchone()["status"] == "submitted"
    c.close()
