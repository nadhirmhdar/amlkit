"""Mobile API: the alert queue pages past the 200-row cap, and the dashboard
payload is explicit about its cap and keeps its highest-score order.

The web dashboard lists oldest alerts first (so its dots show what has waited
longest); the mobile payload keeps the original highest-score order.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_mobile_api import api  # noqa: E402,F401  (fixture)
from tests.test_dashboard_alert_lines import _db, _seed_alerts  # noqa: E402

N = 205


@pytest.fixture()
def long_queue(api):
    """205 open alerts where the newest alert has the highest score, so score
    order (mobile) and age order (web) are opposites."""
    client, headers = api
    _seed_alerts([(["sanction"], "open", f"Person {i}") for i in range(N)])
    conn = _db()
    conn.execute("UPDATE alerts SET score = 0.5 + id * 0.001, "
                 "created_at = '2026-01-01T' || printf('%02d:%02d:00+00:00', (id / 60) % 24, id % 60)")
    conn.commit()
    ids = [r["id"] for r in conn.execute("SELECT id FROM alerts ORDER BY id")]
    conn.close()
    return client, headers, ids


def test_alert_queue_default_page_is_unchanged_and_reports_the_total(long_queue):
    client, headers, ids = long_queue
    body = client.get("/api/v1/alerts", headers=headers).json()
    assert len(body["alerts"]) == 200
    assert body["total"] == N and body["limit"] == 200 and body["offset"] == 0
    assert body["truncated"] is True


def test_alert_queue_pages_cover_every_alert_exactly_once(long_queue):
    client, headers, ids = long_queue
    first = client.get("/api/v1/alerts?limit=120", headers=headers).json()
    second = client.get("/api/v1/alerts?limit=120&offset=120", headers=headers).json()
    assert len(first["alerts"]) == 120 and first["truncated"] is True
    assert len(second["alerts"]) == N - 120 and second["truncated"] is False
    seen = [a["id"] for a in first["alerts"]] + [a["id"] for a in second["alerts"]]
    assert sorted(seen) == ids and len(set(seen)) == N


def test_alert_queue_limit_and_offset_are_clamped(long_queue):
    client, headers, _ = long_queue
    assert len(client.get("/api/v1/alerts?limit=9999", headers=headers).json()["alerts"]) == 200
    assert len(client.get("/api/v1/alerts?limit=0", headers=headers).json()["alerts"]) == 1
    assert client.get("/api/v1/alerts?offset=-5", headers=headers).json()["offset"] == 0
    past = client.get("/api/v1/alerts?offset=500", headers=headers).json()
    assert past["alerts"] == [] and past["total"] == N and past["truncated"] is False


def test_alert_queue_total_respects_the_status_filter(long_queue):
    client, headers, _ = long_queue
    assert client.get("/api/v1/alerts?status=pending_review", headers=headers).json()["total"] == 0
    assert client.get("/api/v1/alerts?status=all", headers=headers).json()["total"] == N


def test_mobile_dashboard_states_its_cap_and_keeps_exact_counts(long_queue):
    client, headers, ids = long_queue
    d = client.get("/api/v1/dashboard", headers=headers).json()
    assert d["alerts_cap"] == 200 and d["alerts_truncated"] is True
    assert len(d["open_alerts"]) == 200
    assert d["alert_open_total"] == N and d["alert_total"] == N


def test_mobile_dashboard_keeps_highest_score_first_but_web_stays_oldest_first(long_queue):
    client, headers, ids = long_queue
    mobile = client.get("/api/v1/dashboard", headers=headers).json()["open_alerts"]
    # highest score = newest alert; the five lowest-scored (oldest) fall off the cap
    assert mobile[0]["id"] == max(ids)
    assert not ({a["id"] for a in mobile} & set(ids[:5]))

    from amlkit import queries
    conn = _db()
    org_id = conn.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()["id"]
    web = queries.dashboard(conn, org_id)["open_alerts"]
    conn.close()
    # web: oldest first, so the five newest are the ones past the cap
    assert web[0]["id"] == min(ids)
    assert not ({a["id"] for a in web} & set(ids[-5:]))
