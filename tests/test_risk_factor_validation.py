"""H13 at the input boundaries: an invalid risk-factor value is rejected before
anything is written.

test_risk_scoring_fail_safe.py covers assess() itself; this covers the callers,
where the bug was that assess() raised only after onboard() had already
committed the customer and its screenings (leaving it unrated), and after the
mobile PATCH had already committed its customer UPDATE (then a 500).
"""
from __future__ import annotations

import os

import pytest

from amlkit import db
from amlkit.cases import manager
from tests.test_mobile_api import api  # noqa: F401  (fixture)

INVALID = [
    ("jurisdiction_tier", "fatf_blacklist "),  # trailing space: scored 0 before H13
    ("delivery_channel", "carrier_pigeon"),
    ("cash_level", "high_cash"),
    ("structure", "INVALID_STRUCTURE"),
]


def _count(conn, sql, *args) -> int:
    return conn.execute(sql, args).fetchone()[0]


@pytest.mark.parametrize("field, value", INVALID)
def test_onboard_rejects_invalid_factor_before_writing(conn, org_id, field, value):
    with pytest.raises(ValueError, match=field):
        manager.onboard(
            conn, org_id=org_id, reference="C-H13-1", full_name="Jane Doe",
            **{field: value},
        )
    assert _count(conn, "SELECT COUNT(*) FROM customers WHERE org_id=?", org_id) == 0
    assert _count(conn, "SELECT COUNT(*) FROM screenings WHERE org_id=?", org_id) == 0
    assert _count(
        conn, "SELECT COUNT(*) FROM audit_log WHERE org_id=? AND action='customer.onboard'", org_id
    ) == 0


def test_onboard_retry_after_rejection_succeeds(conn, org_id):
    """The same reference can be used again: nothing half-created blocks it."""
    with pytest.raises(ValueError):
        manager.onboard(conn, org_id=org_id, reference="C-H13-2", full_name="Jane Doe",
                        jurisdiction_tier="bogus")
    result = manager.onboard(conn, org_id=org_id, reference="C-H13-2", full_name="Jane Doe")
    assert result.risk is not None


@pytest.mark.parametrize("field, value", INVALID)
def test_reassess_rejects_invalid_override_without_writing(conn, org_id, field, value):
    cid = manager.onboard(conn, org_id=org_id, reference="C-H13-3", full_name="Jane Doe").customer_id
    before = _count(conn, "SELECT COUNT(*) FROM risk_assessments WHERE customer_id=?", cid)
    with pytest.raises(ValueError, match=field):
        manager.reassess_risk(conn, cid, org_id, **{field: value})
    assert _count(conn, "SELECT COUNT(*) FROM risk_assessments WHERE customer_id=?", cid) == before


def test_mobile_patch_invalid_factor_is_422_and_changes_nothing(api):  # noqa: F811
    client, headers = api
    conn = db.connect(os.environ["AMLKIT_DB"])
    try:
        org_id = conn.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()["id"]
        cid = manager.onboard(
            conn, org_id=org_id, reference="C-H13-4", full_name="Jane Doe", sector="other",
        ).customer_id
        before = conn.execute(
            "SELECT sector, updated_at FROM customers WHERE id=?", (cid,)
        ).fetchone()
        assessments = _count(conn, "SELECT COUNT(*) FROM risk_assessments WHERE customer_id=?", cid)
    finally:
        conn.close()

    r = client.patch(
        f"/api/v1/customers/{cid}/risk-factors",
        json={"sector": "real_estate", "jurisdiction_tier": "fatf_blacklist "},
        headers=headers,
    )
    assert r.status_code == 422, r.text
    assert "jurisdiction_tier" in r.json()["detail"]

    conn = db.connect(os.environ["AMLKIT_DB"])
    try:
        after = conn.execute("SELECT sector, updated_at FROM customers WHERE id=?", (cid,)).fetchone()
        assert (after["sector"], after["updated_at"]) == (before["sector"], before["updated_at"])
        assert _count(conn, "SELECT COUNT(*) FROM risk_assessments WHERE customer_id=?", cid) == assessments
    finally:
        conn.close()
