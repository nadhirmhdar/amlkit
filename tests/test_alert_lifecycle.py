"""WP-15: alert and freeze lifecycle (L-103, L-104, L-107 / CS-21, CS-22)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_api import LISTED, client  # noqa: E402,F401
from tests.test_screening_correctness import _manager_conn, _statuses  # noqa: E402


@pytest.fixture()
def seeded(client):
    from amlkit.cases import manager
    conn, org = _manager_conn(client)
    manager.onboard(conn, org_id=org, reference="LC-1", full_name=LISTED)
    conn.commit()
    assert _statuses(conn) == [(1, "open")]
    return conn, org


def _decide(conn, org, status, at="2026-01-02T00:00:00+00:00"):
    from amlkit.match.engine import stamp_subject_hash
    conn.execute("UPDATE alerts SET status=?, dispositioned_at=? WHERE id=1", (status, at))
    stamp_subject_hash(conn, 1, org)


# ------------------------------------------------------------------ L-103
@pytest.mark.parametrize("status", ["true_positive", "escalated"])
def test_rescreen_after_decided_match_raises_no_second_alert(seeded, status):
    from amlkit.match.engine import rescreen_all
    conn, org = seeded
    _decide(conn, org, status)
    n_screenings = conn.execute("SELECT COUNT(*) FROM screenings").fetchone()[0]
    assert rescreen_all(conn, org)["alerts"] == 0
    assert rescreen_all(conn, org)["alerts"] == 0
    assert _statuses(conn) == [(1, status)]
    # the screening row is still recorded as evidence
    assert conn.execute("SELECT COUNT(*) FROM screenings").fetchone()[0] > n_screenings


def test_true_positive_then_entity_change_raises_one_flagged_alert(seeded):
    from amlkit.match.engine import rescreen_all
    conn, org = seeded
    _decide(conn, org, "true_positive")
    conn.execute("UPDATE entities SET content_changed_at='2026-01-03T00:00:00+00:00'")
    assert rescreen_all(conn, org)["alerts"] == 1
    assert _statuses(conn) == [(1, "true_positive"), (2, "open")]
    assert conn.execute("SELECT reason FROM alerts WHERE id=2").fetchone()[0] == "list_updated"
    assert conn.execute("SELECT reason FROM alerts WHERE id=1").fetchone()[0] is None
    assert rescreen_all(conn, org)["alerts"] == 0  # the new open alert dedupes


# ------------------------------------------------------------------ L-107
def test_customer_dob_change_reopens_dismissed_match(seeded):
    from amlkit.match.engine import rescreen_all
    conn, org = seeded
    _decide(conn, org, "false_positive")
    assert conn.execute("SELECT subject_hash FROM alerts WHERE id=1").fetchone()[0]
    assert rescreen_all(conn, org)["alerts"] == 0
    conn.execute("UPDATE customers SET birth_date='1970-05-05' WHERE reference='LC-1'")
    assert rescreen_all(conn, org)["alerts"] == 1
    assert conn.execute("SELECT reason FROM alerts WHERE id=2").fetchone()[0] == "subject_changed"


def test_alert_without_stored_subject_hash_adopts_as_unchanged(seeded):
    from amlkit.match.engine import rescreen_all
    conn, org = seeded
    conn.execute("UPDATE alerts SET status='false_positive',"
                 " dispositioned_at='2026-01-02T00:00:00+00:00' WHERE id=1")
    conn.execute("UPDATE customers SET birth_date='1970-05-05'")
    assert rescreen_all(conn, org)["alerts"] == 0


def test_review_disposition_stamps_subject_hash(seeded):
    from amlkit.cases import review
    conn, org = seeded
    code = next(c for c in review.REASON_CODES if c != "other")
    review.propose_disposition(
        conn, 1, org_id=org, status="false_positive", reason_code=code,
        narrative="Different date of birth and nationality on the official listing.",
        operator="alice", operator_id=None,
    )
    conn.execute("UPDATE alerts SET status='false_positive' WHERE id=1")  # skip second review
    row = conn.execute("SELECT subject_hash FROM alerts WHERE id=1").fetchone()
    assert row[0]


# ------------------------------------------------------------------ L-104
def _freeze_with_report(conn, org, report_status):
    from amlkit.db import utcnow
    now = utcnow()
    cid = conn.execute("SELECT id FROM customers WHERE org_id=? LIMIT 1", (org,)).fetchone()[0]
    rid = conn.execute(
        "INSERT INTO reports (org_id, customer_id, report_type, status, payload, created_at)"
        " VALUES (?,?,?,?,?,?)", (org, cid, "FFR", report_status, "{}", now)).lastrowid
    fid = conn.execute(
        """INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
               status, identified_at, identified_by, executed_at, executed_by, report_id)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (org, cid, "sanctions", "critical", "executed_pending_report", now, "alice",
         now, "alice", rid)).lastrowid
    conn.commit()
    return fid, rid


def test_delisted_refused_while_cnmr_is_draft_then_allowed(seeded):
    from amlkit.cases import manager
    conn, org = seeded
    fid, rid = _freeze_with_report(conn, org, "draft")
    with pytest.raises(ValueError, match="File or discard the draft CNMR first"):
        manager.resolve_freeze_obligation(conn, fid, org_id=org, resolved_by="m",
                                          resolution_reason="delisted")
    assert conn.execute("SELECT status FROM freeze_obligations WHERE id=?", (fid,)).fetchone()[0] \
        == "executed_pending_report"
    # finalised
    conn.execute("UPDATE reports SET status='submitted' WHERE id=?", (rid,))
    manager.resolve_freeze_obligation(conn, fid, org_id=org, resolved_by="m",
                                      resolution_reason="delisted")
    assert conn.execute("SELECT status FROM freeze_obligations WHERE id=?", (fid,)).fetchone()[0] \
        == "resolved"


def test_delisted_allowed_after_draft_is_discarded(seeded):
    from amlkit.cases import manager
    conn, org = seeded
    fid, rid = _freeze_with_report(conn, org, "draft")
    conn.execute("DELETE FROM reports WHERE id=?", (rid,))  # report_id -> NULL
    manager.resolve_freeze_obligation(conn, fid, org_id=org, resolved_by="m",
                                      resolution_reason="delisted")


def test_resolve_route_shows_draft_cnmr_error(client):
    from tests.test_api import _csrf
    from tests.test_freeze_routes import _db
    conn = _db()
    org = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()[0]
    from amlkit.db import utcnow
    now = utcnow()
    cid = conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
               status, onboarded_at, created_at, updated_at)
           VALUES (?, 'C-D1', 'Draft Customer', 'natural', 'draft_customer', 'active', ?, ?, ?)""",
        (org, now, now, now)).lastrowid
    rid = conn.execute(
        "INSERT INTO reports (org_id, customer_id, report_type, status, payload, created_at)"
        " VALUES (?,?,?,?,?,?)", (org, cid, "FFR", "draft", "{}", now)).lastrowid
    fid = conn.execute(
        """INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
               status, identified_at, identified_by, executed_at, executed_by, report_id)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (org, cid, "sanctions", "critical", "executed_pending_report", now, "a", now, "a", rid)
    ).lastrowid
    conn.commit()
    conn.close()
    r = client.post(f"/freeze-obligations/{fid}/resolve",
                    data={"csrf_token": _csrf(client), "resolution_reason": "delisted"},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "File or discard the draft CNMR first" in r.text


# ------------------------------------------------------------------ CS-22
def test_freeze_email_does_not_cite_cabinet_resolution(monkeypatch):
    import smtplib
    from amlkit import mail
    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, *a): pass
        def send_message(self, msg): sent.append(msg)

    monkeypatch.setenv("AMLKIT_SMTP_HOST", "smtp.invalid")
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    mail.send_freeze_obligation_alert("mlro@example.com", 7, "C-1", "sanctions", "critical")
    assert sent, "email was not built"
    body = sent[0].get_content()
    assert "134/2025" not in body and "Cabinet Resolution" not in body
    assert "personal liability" in body
