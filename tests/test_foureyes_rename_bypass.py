"""Finding F1 (2026-10-04 mlro-user and red-team reports): confirm_disposition()
compared the proposer's and confirmer's *name* string, not a stable identity.
An MLRO could propose a sanctions dismissal, rename themselves on /admin
(#409), and confirm their own proposal under the new name -- defeating the
four-eyes control the self-confirm check exists to enforce.

The fix anchors the check on alert_reviews.operator_id (additive column) when
both the proposal and the confirm call carry one, falling back to the old
name comparison only for rows/callers that predate it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.review import ReviewError, confirm_disposition, propose_disposition
from tests.test_issue_167_foureyes_double_disposition import _create_test_db
from test_admin_rbac import _add_operator, _csrf, _db, client  # noqa: E402,F401


def test_rename_between_propose_and_confirm_does_not_bypass_four_eyes():
    conn, org_id, alert_id = _create_test_db()

    propose_disposition(
        conn, alert_id, org_id=org_id, status="false_positive",
        reason_code="different_dob", operator="Alice MLRO", operator_id=1,
    )

    # Same operator (id=1), renamed on /admin between propose and confirm.
    with pytest.raises(ReviewError, match="independent review requires a different operator"):
        confirm_disposition(
            conn, alert_id, org_id=org_id, operator="Alice Renamed", operator_id=1, agree=True,
        )


def test_different_operator_id_confirms_even_if_old_name_happens_to_match():
    """The id is authoritative: two different operators who happen to share a
    display name (e.g. a duplicate-name edge case, finding F4) are still
    treated as different reviewers."""
    conn, org_id, alert_id = _create_test_db()

    propose_disposition(
        conn, alert_id, org_id=org_id, status="false_positive",
        reason_code="different_dob", operator="Pat Officer", operator_id=1,
    )

    outcome = confirm_disposition(
        conn, alert_id, org_id=org_id, operator="Pat Officer", operator_id=2, agree=True,
    )
    assert outcome.status == "false_positive"


def test_legacy_rows_without_operator_id_fall_back_to_name_comparison():
    """A proposal recorded before this migration (or by a caller that still
    omits operator_id) has no id to compare -- the pre-fix name check still
    guards it rather than silently waving every such row through."""
    conn, org_id, alert_id = _create_test_db()

    propose_disposition(
        conn, alert_id, org_id=org_id, status="false_positive",
        reason_code="different_dob", operator="Legacy Operator",
    )

    with pytest.raises(ReviewError, match="independent review requires a different operator"):
        confirm_disposition(
            conn, alert_id, org_id=org_id, operator="Legacy Operator", agree=True,
        )

    # A genuinely different name still confirms, same as before this fix.
    outcome = confirm_disposition(
        conn, alert_id, org_id=org_id, operator="Someone Else", agree=True,
    )
    assert outcome.status == "false_positive"


def test_http_rename_self_then_confirm_own_proposal_is_refused(client) -> None:
    """End-to-end reproduction of F1 over the real HTTP routes: the MLRO
    (alice) proposes a dismissal, renames herself via POST
    /admin/operators/{id}/rename (#409), then tries to confirm her own
    proposal under the new name. Must still be refused."""
    conn = _db()
    org_id = conn.execute("SELECT id FROM organizations WHERE slug='test-firm'").fetchone()[0]
    alice_id = conn.execute("SELECT id FROM operators WHERE email='alice@testfirm.ae'").fetchone()[0]
    now = conn.execute("SELECT datetime('now')").fetchone()[0]

    ds = conn.execute(
        "INSERT INTO datasets (key, title, is_mandatory, last_refresh, entity_count)"
        " VALUES ('f1-ds','F1 Dataset',1,?,1) RETURNING id", (now,),
    ).fetchone()["id"]
    eid = conn.execute(
        "INSERT INTO entities (dataset_id, source_id, schema_type, caption, countries,"
        " topics, programs, raw, first_seen, last_seen)"
        " VALUES (?,'f1-e1','Person','F1 Sanctioned Subject','[]','[\"sanction\"]','[]','{}',?,?)"
        " RETURNING id", (ds, now, now),
    ).fetchone()["id"]
    screening_id = conn.execute(
        "INSERT INTO screenings (org_id, query_name, trigger, algorithm, threshold, run_at)"
        " VALUES (?,'F1 Sanctioned Subject','onboard','jaro_winkler',0.8,?) RETURNING id",
        (org_id, now),
    ).fetchone()["id"]
    alert_id = conn.execute(
        "INSERT INTO alerts (org_id, screening_id, entity_id, score, score_detail,"
        " matched_name, status, created_at)"
        " VALUES (?,?,?,0.95,'{}','F1 Sanctioned Subject','open',?) RETURNING id",
        (org_id, screening_id, eid, now),
    ).fetchone()["id"]
    conn.commit()
    conn.close()

    r = client.post(f"/alerts/{alert_id}/disposition", data={
        "status": "false_positive", "reason_code": "different_dob",
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert "independent review" in r.text.lower(), r.text[:500]

    r = client.post(f"/admin/operators/{alice_id}/rename", data={
        "name": "Alice Renamed", "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert r.status_code == 200

    r = client.post(f"/alerts/{alert_id}/confirm", data={
        "agree": "yes", "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert "independent review requires a different operator" in r.text, r.text[:800]

    conn = _db()
    status = conn.execute("SELECT status FROM alerts WHERE id=?", (alert_id,)).fetchone()["status"]
    conn.close()
    assert status == "pending_review"
