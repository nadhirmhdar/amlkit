"""First-run guided onboarding for empty orgs (p51)."""
import os
import re
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from test_api import _register, _seed_sanctions_data, _csrf  # noqa: E402

GUIDE = "Get started with amlkit"


def _conn():
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "test.db"))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(tmp_path / "test.db")
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    c = TestClient(app)
    _register(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


def _org_id():
    with closing(_conn()) as c:
        return c.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()["id"]


def _flags(html):
    return re.findall(r'data-step="(\d)" data-complete="(true|false)"', html)


def _add_customer(org_id, status="active"):
    from amlkit.db import connect
    from amlkit.cases.manager import onboard
    with closing(connect(os.environ["AMLKIT_DB"])) as c:
        onboard(c, org_id=org_id, reference="C-001", full_name="Test Customer")
        if status != "active":
            c.execute("UPDATE customers SET status=? WHERE org_id=?", (status, org_id))
        c.commit()


def _screen(org_id):
    from amlkit.db import connect, utcnow
    with closing(connect(os.environ["AMLKIT_DB"])) as c:
        c.execute("INSERT INTO screenings (org_id, query_name, trigger, algorithm, threshold, run_at)"
                  " VALUES (?,?,?,?,?,?)", (org_id, "X", "adhoc", "weighted", 0.75, utcnow()))
        c.commit()


def test_empty_org_shows_guide_all_incomplete(client):
    html = client.get("/").text
    assert GUIDE in html
    assert _flags(html) == [("1", "false"), ("2", "false"), ("3", "false")]
    assert "(completed)" not in html


def test_screening_marks_step1_complete(client):
    _screen(_org_id())
    html = client.get("/").text
    assert GUIDE in html
    assert ("1", "true") in _flags(html)
    assert html.count("(completed)") == 1


def test_customer_marks_step2_and_guide_persists_until_all_done(client):
    _add_customer(_org_id())
    html = client.get("/").text
    assert GUIDE in html
    assert ("2", "true") in _flags(html)
    assert ("3", "false") in _flags(html)


def test_guide_hides_when_all_steps_done(client):
    oid = _org_id()
    _screen(oid)
    _add_customer(oid)
    r = client.post("/onboarding/review-dashboard",
                    data={"csrf_token": _csrf(client)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/dashboard"
    assert GUIDE not in client.get("/").text


def test_archived_only_org_counts_as_having_customers(client):
    _add_customer(_org_id(), status="archived")
    html = client.get("/").text
    assert ("2", "true") in _flags(html)


def test_get_pages_do_not_set_dashboard_visited(client):
    client.get("/")
    client.get("/dashboard")
    from amlkit import queries
    with closing(_conn()) as c:
        assert queries.dashboard_visited(c, _org_id()) is False
    assert ("3", "false") in _flags(client.get("/").text)


def test_review_dashboard_post_marks_step3(client):
    client.post("/onboarding/review-dashboard", data={"csrf_token": _csrf(client)})
    from amlkit import queries
    with closing(_conn()) as c:
        assert queries.dashboard_visited(c, _org_id()) is True
    assert ("3", "true") in _flags(client.get("/").text)


def test_review_dashboard_post_requires_csrf(client):
    r = client.post("/onboarding/review-dashboard", data={"csrf_token": "bogus"},
                    follow_redirects=False)
    assert r.headers["location"] == "/"
    from amlkit import queries
    with closing(_conn()) as c:
        assert queries.dashboard_visited(c, _org_id()) is False


def test_tenant_isolation_of_onboarding_queries(client):
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit import queries
    from amlkit.cases.manager import mark_dashboard_reviewed

    _register(TestClient(app), "Other Firm", "bob", "bob@other.ae")
    with closing(_conn()) as c:
        ids = [r["id"] for r in c.execute("SELECT id FROM organizations ORDER BY id")]
    a, b = ids[0], ids[1]

    _screen(a)
    _add_customer(a)
    with closing(_conn()) as c:
        mark_dashboard_reviewed(c, a)
    with closing(_conn()) as c:
        assert queries.has_screening_history(c, a) is True
        assert queries.has_screening_history(c, b) is False
        assert queries.dashboard_visited(c, a) is True
        assert queries.dashboard_visited(c, b) is False
        assert queries.total_customer_count(c, a) == 1
        assert queries.total_customer_count(c, b) == 0
