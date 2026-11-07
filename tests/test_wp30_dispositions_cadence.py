"""WP-30: reason codes must fit the disposition (L-120 BD1), a bulk dismiss that
dismissed nothing is a warning (L-121), and the sanctions refresh runs every
4 hours (L-123 CS-5)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.review import (  # noqa: E402
    ALLOWED_REASON_CODES, DISPOSITIONS, REASON_CODES, ReviewError, _validate,
)
from test_api import _alert, _csrf, _first_alert_id, client, LISTED  # noqa: E402,F401
from test_mobile_api import api  # noqa: E402,F401

REFUSED = [
    ("false_positive", "confirmed_match"),
    ("false_positive", "insufficient_data"),
    ("true_positive", "different_dob"),
    ("true_positive", "different_nationality"),
    ("true_positive", "name_coincidence"),
    ("true_positive", "different_entity_type"),
    ("true_positive", "insufficient_data"),
    ("escalated", "different_dob"),
    ("escalated", "name_coincidence"),
    ("open", "confirmed_match"),
    ("open", "different_dob"),
]
ALLOWED = [
    ("false_positive", "different_dob"),
    ("true_positive", "confirmed_match"),
    ("escalated", "insufficient_data"),
    ("open", "insufficient_data"),
]


def test_table_covers_every_disposition_and_only_known_codes():
    assert set(ALLOWED_REASON_CODES) == set(DISPOSITIONS)
    for codes in ALLOWED_REASON_CODES.values():
        assert set(codes) <= set(REASON_CODES)
    assert "insufficient_data" not in ALLOWED_REASON_CODES["false_positive"]


@pytest.mark.parametrize("status,code", REFUSED)
def test_validate_refuses_mismatch(status, code):
    with pytest.raises(ReviewError, match="does not fit the disposition"):
        _validate(status, code, "narrative given")


@pytest.mark.parametrize("status,code", ALLOWED)
def test_validate_accepts_fitting_pair(status, code):
    _validate(status, code, "narrative given")


@pytest.fixture()
def web_alert(client):
    client.post("/customers", data={
        "reference": "C-WP30", "full_name": "Falcon WP30 FZE", "customer_type": "legal",
        "ubo_names": [LISTED], "ubo_pcts": ["60"], "ubo_controls": ["ownership"],
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    return _first_alert_id()


@pytest.mark.parametrize("status,code", REFUSED)
def test_web_refuses_mismatch(client, web_alert, status, code):
    r = client.post(f"/alerts/{web_alert}/disposition", data={
        "status": status, "reason_code": code, "narrative": "Reasoned narrative.",
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert "does not fit the disposition" in r.text
    assert _alert("status") == "open"


@pytest.mark.parametrize("status,code", ALLOWED)
def test_web_accepts_fitting_pair(client, web_alert, status, code):
    r = client.post(f"/alerts/{web_alert}/disposition", data={
        "status": status, "reason_code": code, "narrative": "Reasoned narrative.",
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert "does not fit the disposition" not in r.text
    assert _alert("reason_code") == code


def test_web_bulk_dismiss_of_nothing_is_a_warning(client):
    client.post("/customers", data={
        "reference": "C-EMPTY", "full_name": "Quiet Trading LLC", "customer_type": "legal",
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    from test_api import _db
    conn = _db()
    cid = conn.execute("SELECT id FROM customers WHERE reference='C-EMPTY'").fetchone()["id"]
    conn.close()
    r = client.post("/alerts/bulk-dismiss", data={
        "customer_id": cid, "reason_code": "name_coincidence",
        "back_to": "/alerts?group_by=customer", "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert "No open alerts to dismiss" in r.text
    assert "Dismissed 0" not in r.text


def _mobile_alert(client, headers):
    client.post("/api/v1/customers", headers=headers, json={
        "reference": "CUST-WP30", "full_name": LISTED,
    })
    return client.get("/api/v1/alerts", headers=headers).json()["alerts"][0]["id"]


@pytest.mark.parametrize("status,code", REFUSED)
def test_mobile_refuses_mismatch(api, status, code):
    client, headers = api
    aid = _mobile_alert(client, headers)
    r = client.post(f"/api/v1/alerts/{aid}/disposition", headers=headers, json={
        "status": status, "reason_code": code, "narrative": "Reasoned narrative.",
    })
    assert r.status_code == 400, r.text
    assert "does not fit the disposition" in r.json()["detail"]


@pytest.mark.parametrize("status,code", ALLOWED)
def test_mobile_accepts_fitting_pair(api, status, code):
    client, headers = api
    aid = _mobile_alert(client, headers)
    r = client.post(f"/api/v1/alerts/{aid}/disposition", headers=headers, json={
        "status": status, "reason_code": code, "narrative": "Reasoned narrative.",
    })
    assert r.status_code == 200, r.text


# ----------------------------------------------------------------- L-123 CS-5
WF = Path(__file__).resolve().parent.parent / ".github/workflows/source-canary.yml"


def test_sanctions_refresh_schedule_is_every_four_hours_in_create_and_update():
    text = WF.read_text()
    schedules = re.findall(r'--schedule "([^"]+)"', text)
    refresh = [s for s in schedules if s.startswith("0 */")]
    assert refresh == ["0 */4 * * *", "0 */4 * * *"], schedules
    assert "*/20" not in text
    assert "Every 20 hours" not in text
