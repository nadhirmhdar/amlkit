"""The MLRO's in-app notification inbox: bell count, inbox page, mark-read.

Real app + real SQLite via TestClient, same wiring as test_api.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_api import (  # noqa: E402
    LISTED,
    _add_operator,
    _csrf,
    _db,
    _login,
    _register,
    _seed_sanctions_data,
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "notif.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


def _make_match(client, ref="C-N1"):
    """Onboard a company whose owner is on the list => a new alert."""
    client.post("/customers", data={
        "reference": ref, "full_name": "Falcon Holdings FZE", "customer_type": "legal",
        "ubo_names": [LISTED], "ubo_pcts": ["60"], "ubo_controls": ["ownership"],
        "csrf_token": _csrf(client),
    }, follow_redirects=True)


def _count(client) -> int:
    r = client.get("/notifications/unread-count")
    assert r.status_code == 200
    return r.json()["count"]


def _first_notification_id() -> int:
    conn = _db()
    row = conn.execute("SELECT id FROM notifications ORDER BY id LIMIT 1").fetchone()
    conn.close()
    assert row is not None, "expected a notification to exist"
    return row["id"]


def test_inbox_requires_login(tmp_path, monkeypatch):
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "anon.db"))
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    r = c.get("/notifications", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert c.get("/notifications/unread-count").status_code == 401


def test_new_match_raises_the_mlro_unread_count(client):
    assert _count(client) == 0
    _make_match(client)
    assert _count(client) == 1


def test_inbox_lists_the_notification_with_a_deep_link(client):
    _make_match(client)
    r = client.get("/notifications")
    assert r.status_code == 200
    assert "New screening match" in r.text
    # the deep link is asserted directly against the stored row rather than
    # by loading the customer page, which renders a UBO diagram via Graphviz
    # (an external `dot` binary this environment doesn't have on PATH) --
    # unrelated to what this test is about.
    conn = _db()
    link = conn.execute("SELECT link FROM notifications ORDER BY id LIMIT 1").fetchone()["link"]
    conn.close()
    assert link.startswith("/customers/") and link.endswith("#alerts")


def test_layout_has_a_bell_linking_to_the_inbox(client):
    r = client.get("/")
    assert 'href="/notifications"' in r.text
    assert "data-notif-badge" in r.text


def test_opening_a_notification_marks_it_read_and_goes_to_the_alert(client):
    _make_match(client)
    nid = _first_notification_id()
    r = client.post(f"/notifications/{nid}/read", data={"csrf_token": _csrf(client)}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/customers/")
    assert _count(client) == 0


def test_mark_read_needs_a_csrf_token(client):
    _make_match(client)
    nid = _first_notification_id()
    client.post(f"/notifications/{nid}/read", data={"csrf_token": "forged"}, follow_redirects=False)
    assert _count(client) == 1


def test_mark_all_read(client):
    _make_match(client, "C-N1")
    _make_match(client, "C-N2")
    assert _count(client) >= 1
    client.post("/notifications/read-all", data={"csrf_token": _csrf(client)}, follow_redirects=True)
    assert _count(client) == 0


def test_officers_have_an_empty_inbox(client):
    _make_match(client)
    _add_operator(client, "olive", "olive@testfirm.ae")
    client.post("/logout", data={"csrf_token": _csrf(client)})
    _login(client, "olive@testfirm.ae", "a-strong-password-2")
    assert _count(client) == 0
    assert "No notifications" in client.get("/notifications").text


def test_another_firm_cannot_read_or_clear_my_notifications(client, tmp_path):
    _make_match(client)
    nid = _first_notification_id()

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    other = TestClient(app)
    _register(other, "Other Firm", "bob", "bob@other.ae")
    assert _count(other) == 0
    other.post(f"/notifications/{nid}/read", data={"csrf_token": _csrf(other)}, follow_redirects=False)
    assert _count(client) == 1  # alice's notification is untouched
