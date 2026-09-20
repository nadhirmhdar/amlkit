"""Issue #167: Four-eyes review double-disposition bug.

A second reviewer should not be able to approve/reject an alert that already
has a final disposition, preventing double-disposition and audit log confusion.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.review import (
    ReviewError,
    confirm_disposition,
    propose_disposition,
)
from amlkit.db import connect, utcnow, upsert_dataset
from amlkit.names.arabic import blocking_keys, canonical_key


def _create_test_db():
    """Create in-memory DB with alert data."""
    conn = connect(":memory:")

    # Create org
    org_row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id",
        ("Test Firm", "test-firm", "active", utcnow()),
    ).fetchone()
    org_id = org_row["id"]

    # Create dataset and entity (sanctions)
    ds = upsert_dataset(conn, "test_list", "Test List", is_mandatory=True)
    now = utcnow()
    listed = "AHMED TEST SUBJECT"
    cur = conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption, countries,
           birth_date, gender, topics, programs, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, "T-1", "Person", listed, '["ly"]', "1975-03-12", "male",
         '["sanction"]', '["AE-UNSC1373"]', "{}", now, now),
    )
    eid = cur.lastrowid
    conn.execute(
        "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
        " VALUES (?,?,?,?,?)",
        (eid, listed, "primary", canonical_key(listed), "latin"))
    for tok in blocking_keys(listed):
        conn.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)", (tok, eid))
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))

    # Create screening and alert
    conn.execute(
        """INSERT INTO screenings (org_id, query_name, trigger, algorithm, threshold, run_at)
           VALUES (?,?,?,?,?,?)""",
        (org_id, listed, "onboard", "jaro_winkler", 0.8, now)
    )
    screening_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        """INSERT INTO alerts (org_id, screening_id, entity_id, score, score_detail, matched_name, status, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (org_id, screening_id, eid, 0.95, '{}', listed, "open", now)
    )
    alert_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.commit()
    return conn, org_id, alert_id


def test_cannot_confirm_already_dispositioned_alert():
    """Second reviewer cannot confirm an alert that already has final disposition."""
    conn, org_id, alert_id = _create_test_db()

    # Reviewer 1 proposes dismissal
    outcome1 = propose_disposition(
        conn, alert_id,
        org_id=org_id,
        status="false_positive",
        reason_code="different_dob",
        operator="alice",
        narrative=""
    )
    assert outcome1.status == "pending_review"
    assert outcome1.awaiting_second_review is True

    # Reviewer 2 confirms the dismissal
    outcome2 = confirm_disposition(
        conn, alert_id,
        org_id=org_id,
        operator="bob",
        agree=True
    )
    assert outcome2.status == "false_positive"

    # Alert should now have final disposition
    current = conn.execute(
        "SELECT status FROM alerts WHERE id=? AND org_id=?", (alert_id, org_id)
    ).fetchone()
    assert current["status"] == "false_positive"

    # Reviewer 3 (or Reviewer 2 again) tries to confirm again
    # This MUST fail - cannot re-disposition an already-dispositioned alert
    with pytest.raises(ReviewError, match="not awaiting review"):
        confirm_disposition(
            conn, alert_id,
            org_id=org_id,
            operator="charlie",
            agree=True
        )


def test_cannot_propose_disposition_on_already_dispositioned_alert():
    """Cannot re-propose disposition on an alert that already has final status."""
    conn, org_id, alert_id = _create_test_db()

    # Reviewer 1 proposes dismissal
    propose_disposition(
        conn, alert_id,
        org_id=org_id,
        status="false_positive",
        reason_code="different_dob",
        operator="alice"
    )

    # Reviewer 2 confirms
    confirm_disposition(
        conn, alert_id,
        org_id=org_id,
        operator="bob",
        agree=True
    )

    # Alert is now false_positive
    # Trying to propose a NEW disposition should fail
    with pytest.raises(ReviewError, match="already"):
        propose_disposition(
            conn, alert_id,
            org_id=org_id,
            status="escalated",
            reason_code="confirmed_match",
            operator="charlie",
            narrative="Actually this is a match"
        )
