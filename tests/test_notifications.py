"""In-app notifications for MLROs when a screening finds a new match.

Behaviour under test (all real SQLite, no DB mocks):
  * a new alert notifies every ACTIVE MLRO of the SAME organization, and nobody else
  * the inbox is per operator, org-scoped, with unread counts and mark-read
  * an open duplicate alert (the daily re-screen case) does not notify again
  * a failing email transport can never break a screening
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from amlkit import notifications, queries  # noqa: E402
from amlkit.db import connect, utcnow  # noqa: E402
from amlkit.match.engine import screen  # noqa: E402
from conftest import LISTED, seed_fresh_dataset  # noqa: E402


@pytest.fixture()
def conn(tmp_path):
    c = connect(tmp_path / "notify.db")
    seed_fresh_dataset(c)
    yield c
    c.close()


def _org(conn, name):
    return conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id",
        (name, name.lower().replace(" ", "-"), "active", utcnow()),
    ).fetchone()["id"]


def _operator(conn, org_id, name, role="mlro", active=1):
    return conn.execute(
        "INSERT INTO operators (org_id,name,email,role,is_active,email_verified_at,created_at)"
        " VALUES (?,?,?,?,?,?,?) RETURNING id",
        (org_id, name, f"{name.lower().replace(' ', '.')}@example.test", role, active, utcnow(), utcnow()),
    ).fetchone()["id"]


@pytest.fixture()
def firm(conn):
    org = _org(conn, "Alpha Firm")
    return {
        "org": org,
        "mlro_a": _operator(conn, org, "Mlro A"),
        "mlro_b": _operator(conn, org, "Mlro B"),
        "mlro_inactive": _operator(conn, org, "Mlro Off", active=0),
        "officer": _operator(conn, org, "Officer One", role="officer"),
    }


def test_new_match_notifies_every_active_mlro_of_the_firm(conn, firm):
    res = screen(conn, LISTED, org_id=firm["org"], actor="officer")
    assert res.alerts_created == 1

    for op in ("mlro_a", "mlro_b"):
        items = queries.notifications_for(conn, firm["org"], firm[op])
        assert len(items) == 1
        assert items[0]["kind"] == "screening_match"
        assert items[0]["read_at"] is None
    assert queries.notifications_for(conn, firm["org"], firm["mlro_inactive"]) == []
    assert queries.notifications_for(conn, firm["org"], firm["officer"]) == []


def test_notification_names_the_match_and_deep_links_to_alerts(conn, firm):
    screen(conn, LISTED, org_id=firm["org"], actor="officer")
    item = queries.notifications_for(conn, firm["org"], firm["mlro_a"])[0]
    assert LISTED.split()[0] in item["title"] or LISTED.split()[0] in item["body"]
    assert item["link"].startswith("/alerts")


def test_other_firms_mlro_is_never_notified(conn, firm):
    other_org = _org(conn, "Beta Firm")
    other_mlro = _operator(conn, other_org, "Beta Mlro")
    screen(conn, LISTED, org_id=firm["org"], actor="officer")
    assert queries.notifications_for(conn, other_org, other_mlro) == []
    # and a query for the wrong org can never see this firm's items
    assert queries.notifications_for(conn, other_org, firm["mlro_a"]) == []


def test_clear_screening_notifies_nobody(conn, firm):
    res = screen(conn, "Completely Unlisted Person Name", org_id=firm["org"], actor="officer")
    assert res.alerts_created == 0
    assert queries.unread_notification_count(conn, firm["org"], firm["mlro_a"]) == 0


def test_repeat_screening_with_open_alert_does_not_notify_again(conn, firm):
    screen(conn, LISTED, org_id=firm["org"], actor="officer")
    screen(conn, LISTED, org_id=firm["org"], actor="officer")  # same open alert, dedup'd
    assert queries.unread_notification_count(conn, firm["org"], firm["mlro_a"]) == 1


def test_unpersisted_screening_notifies_nobody(conn, firm):
    screen(conn, LISTED, org_id=firm["org"], persist=False)
    assert queries.unread_notification_count(conn, firm["org"], firm["mlro_a"]) == 0


def test_mark_read_and_mark_all_read_are_per_operator(conn, firm):
    screen(conn, LISTED, org_id=firm["org"], actor="officer")
    item = queries.notifications_for(conn, firm["org"], firm["mlro_a"])[0]

    assert queries.unread_notification_count(conn, firm["org"], firm["mlro_a"]) == 1
    assert notifications.mark_read(conn, firm["org"], firm["mlro_a"], item["id"]) is True
    assert queries.unread_notification_count(conn, firm["org"], firm["mlro_a"]) == 0
    # MLRO B's copy is untouched
    assert queries.unread_notification_count(conn, firm["org"], firm["mlro_b"]) == 1

    # an operator cannot mark someone else's notification read
    b_item = queries.notifications_for(conn, firm["org"], firm["mlro_b"])[0]
    assert notifications.mark_read(conn, firm["org"], firm["mlro_a"], b_item["id"]) is False
    assert queries.unread_notification_count(conn, firm["org"], firm["mlro_b"]) == 1

    assert notifications.mark_all_read(conn, firm["org"], firm["mlro_b"]) == 1
    assert queries.unread_notification_count(conn, firm["org"], firm["mlro_b"]) == 0


def test_email_failure_never_breaks_the_screening(conn, firm, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("smtp exploded")

    monkeypatch.setattr("amlkit.mail.send_screening_match_alert", boom)
    res = screen(conn, LISTED, org_id=firm["org"], actor="officer")
    assert res.alerts_created == 1  # screening and alert still recorded
    # the in-app notification is written before/independently of email
    assert queries.unread_notification_count(conn, firm["org"], firm["mlro_a"]) == 1


def test_email_is_sent_to_every_active_mlro_address(conn, firm, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "amlkit.mail.send_screening_match_alert",
        lambda to_emails, **kw: sent.append((list(to_emails), kw)) or "sent",
    )
    screen(conn, LISTED, org_id=firm["org"], actor="officer")
    assert len(sent) == 1
    assert sorted(sent[0][0]) == ["mlro.a@example.test", "mlro.b@example.test"]


def test_rescreen_sends_one_digest_not_one_notification_per_hit(conn, firm):
    from amlkit.cases.manager import onboard
    from amlkit.match.engine import rescreen_all

    # threshold above 1.0 => the customer is onboarded WITHOUT a match, as if
    # the list entry was published only after onboarding.
    onboard(conn, org_id=firm["org"], reference="C-1", full_name=LISTED, threshold=1.01, actor="officer")
    assert queries.unread_notification_count(conn, firm["org"], firm["mlro_a"]) == 0

    out = rescreen_all(conn, firm["org"])
    assert out["alerts"] == 1

    items = queries.notifications_for(conn, firm["org"], firm["mlro_a"])
    assert [i["kind"] for i in items] == ["rescreen_digest"]
    assert "1 new screening match" in items[0]["title"]


def test_rescreen_with_nothing_new_sends_no_digest(conn, firm):
    from amlkit.match.engine import rescreen_all

    rescreen_all(conn, firm["org"])
    assert queries.unread_notification_count(conn, firm["org"], firm["mlro_a"]) == 0
