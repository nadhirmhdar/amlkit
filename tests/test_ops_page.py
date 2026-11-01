"""WP-19: /admin/ops page and the structured log lines behind the monitoring metrics."""

from __future__ import annotations

import logging
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_api import client, _db, _login, _register, _csrf  # noqa: E402,F401


def _iso(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")


def _org_id(conn: sqlite3.Connection, name: str) -> int:
    return conn.execute("SELECT id FROM organizations WHERE name=?", (name,)).fetchone()["id"]


def _seed(conn, org_id, *, freezes, drafts, alerts, tag):
    """freezes: ages (hours) of pending obligations; drafts/alerts: ages of CNMR drafts / open alerts."""
    now = _iso(0)
    cid = conn.execute(
        """INSERT INTO customers (org_id, reference, full_name, customer_type, canonical_key,
                                  status, onboarded_at, created_at, updated_at)
           VALUES (?, ?, ?, 'natural', ?, 'active', ?, ?, ?)""",
        (org_id, f"C-{tag}", f"Customer {tag}", f"c-{tag}", now, now, now),
    ).lastrowid
    for h in freezes:
        conn.execute(
            """INSERT INTO freeze_obligations (org_id, customer_id, obligation_type, risk_category,
                                               status, identified_at, identified_by)
               VALUES (?, ?, 'sanctions', 'critical', 'pending_execution', ?, 'seed')""",
            (org_id, cid, _iso(h)),
        )
    for h in drafts:
        conn.execute(
            "INSERT INTO reports (org_id, customer_id, report_type, status, payload, created_at) "
            "VALUES (?, ?, 'FFR', 'draft', '{}', ?)", (org_id, cid, _iso(h)))
    for h in alerts:
        conn.execute(
            """INSERT INTO alerts (org_id, screening_id, entity_id, score, score_detail,
                                   matched_name, status, created_at)
               VALUES (?, 1, 1, 0.9, '{}', 'X', 'open', ?)""", (org_id, _iso(h)))
    conn.commit()


def _field(html: str, element_id: str) -> str:
    m = re.search(rf'id="{element_id}"[^>]*>\s*([^<]*?)\s*<', html)
    assert m, f"{element_id} not on page"
    return m.group(1)


@pytest.fixture()
def seeded(client):
    from amlkit.db import audit, upsert_dataset

    conn = _db()
    a = _org_id(conn, "Test Firm")
    ds = upsert_dataset(conn, "stale_src", "Stale Source Test", is_mandatory=True)
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=42, max_age_hours=24 WHERE id=?",
                 (_iso(100), ds))
    audit(conn, "system:scheduled-refresh", "dataset.refresh", "dataset", "stale_src",
          {"entities": 42}, org_id=None)
    audit(conn, "alice", "dataset.refresh_requested", "organization", a, {}, org_id=a)
    audit(conn, "alice", "screening.run", "screening", 1, {}, org_id=a)
    _seed(conn, a, freezes=[48, 2], drafts=[30], alerts=[5, 10, 72], tag="A")

    # Another organisation with clearly different (and larger) figures.
    other = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES ('Other Firm', 'other-firm', 'active', ?)",
        (_iso(0),)).lastrowid
    conn.commit()
    _seed(conn, other, freezes=[900] * 5, drafts=[800] * 7, alerts=[700] * 9, tag="B")
    audit(conn, "mallory", "screening.run", "screening", 2, {}, org_id=other)
    audit(conn, "mallory", "dataset.refresh_requested", "organization", other, {}, org_id=other)
    conn.commit()
    conn.close()
    return client


class TestAccess:
    def test_officer_is_redirected(self, client):
        client.post("/admin/operators", data={
            "name": "bob", "email": "bob@testfirm.ae", "password": "A-strong-password-2",
            "role": "officer", "csrf_token": _csrf(client)})
        client.cookies.delete("amlkit_session")
        _login(client, "bob@testfirm.ae", "A-strong-password-2")
        r = client.get("/admin/ops", follow_redirects=False)
        assert r.status_code in (302, 303)
        assert r.headers["location"] == "/"

    def test_anonymous_goes_to_login(self, client):
        client.cookies.clear()
        r = client.get("/admin/ops", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"

    def test_menu_links_to_page(self, client):
        assert 'href="/admin/ops"' in client.get("/").text


class TestPage:
    def test_sections_present(self, client):
        r = client.get("/admin/ops")
        assert r.status_code == 200
        for marker in ("ops-version", "ops-datasets", "ops-replica", "ops-queues", "ops-activity"):
            assert marker in r.text
        assert "Ops status" in r.text

    def test_version_defaults_to_dev_and_reads_env(self, client, monkeypatch):
        monkeypatch.delenv("AMLKIT_GIT_SHA", raising=False)
        assert _field(client.get("/admin/ops").text, "ops-version") == "dev"
        monkeypatch.setenv("AMLKIT_GIT_SHA", "abc1234")
        assert _field(client.get("/admin/ops").text, "ops-version") == "abc1234"

    def test_values_reflect_seeded_state(self, seeded):
        html = seeded.get("/admin/ops").text
        # stale mandatory dataset
        assert "Stale Source Test" in html
        assert "BREACH" in html
        # freeze: 2 pending, 1 of them past 24h
        assert _field(html, "ops-freeze-pending") == "2"
        assert re.search(r'id="ops-freeze-overdue"[^>]*>\s*1 overdue', html)
        # CNMR draft + open alerts with oldest ages
        assert _field(html, "ops-cnmr-drafts") == "1"
        assert _field(html, "ops-open-alerts") == "3"
        assert "oldest 3.0 days" in html  # 72h alert
        assert "oldest 2.0 days" in html  # 48h freeze
        assert "oldest 30" in html  # 30h CNMR draft
        # activity + shared refresh actor
        assert "by alice" in html
        assert "system:scheduled-refresh" in html

    def test_other_orgs_figures_do_not_appear(self, seeded):
        html = seeded.get("/admin/ops").text
        assert _field(html, "ops-freeze-pending") != "5"
        assert _field(html, "ops-cnmr-drafts") != "7"
        assert _field(html, "ops-open-alerts") != "9"
        assert "mallory" not in html
        assert "Other Firm" not in html

    def test_replica_status_unknown_without_litestream(self, client):
        html = client.get("/admin/ops").text
        assert "unknown" in html
        assert "none since this instance started" in html

    def test_replica_last_sync_recorded_in_process(self, client, monkeypatch):
        from amlkit import replication

        monkeypatch.setattr(replication, "_last_ok",
                            {"at": _iso(1), "reason": "unit test"})
        html = client.get("/admin/ops").text
        assert "unit test" in html


class TestLogLines:
    @pytest.fixture()
    def scheduler(self, seeded, monkeypatch):
        monkeypatch.setenv("SCHEDULER_SECRET", "s3cret-scheduler")
        return {"Authorization": "Bearer s3cret-scheduler"}

    def test_freeze_check_logs_one_structured_line(self, seeded, scheduler, caplog):
        with caplog.at_level(logging.INFO, logger="amlkit.ops"):
            r = seeded.post("/system/check-freeze-obligations", headers=scheduler)
        assert r.status_code == 200
        body = r.json()
        recs = [x for x in caplog.records if x.getMessage().startswith("freeze_obligation_check")]
        assert len(recs) == 1
        fields = recs[0].extra_fields
        assert fields["overdue_count"] == body["overdue"] >= 1
        assert fields["org_count"] == body["orgs_checked"] >= 2

    def test_refresh_logs_counts_and_duration(self, seeded, scheduler, caplog, monkeypatch):
        import amlkit.api.app as appmod

        monkeypatch.setattr(appmod, "run_sanctions_refresh", lambda conn, actor, org_id=None: {
            "loaded": ["x"], "failures": [], "mandatory_failures": [],
            "rescreen_failures": [], "orgs_screened": 2, "new_alerts": 3})
        monkeypatch.setattr(appmod, "check_and_notify_staleness", lambda conn: {})
        with caplog.at_level(logging.INFO, logger="amlkit.ops"):
            r = seeded.post("/system/refresh", headers=scheduler)
        assert r.status_code == 200
        recs = [x for x in caplog.records if x.getMessage().startswith("sanctions_refresh")]
        assert len(recs) == 1
        f = recs[0].extra_fields
        assert f["dataset_counts"]["stale_src"] == 42
        assert f["duration_seconds"] >= 0
        assert f["new_alerts"] == 3 and f["failure_count"] == 0

    def test_json_formatter_exposes_fields_for_log_metrics(self, seeded, scheduler):
        """The monitoring filters read jsonPayload.overdue_count / .message."""
        import json
        from amlkit.logging_config import StructuredFormatter
        from amlkit import ops

        rec = logging.LogRecord("amlkit.ops", logging.INFO, __file__, 1,
                                "freeze_obligation_check overdue_count=1 org_count=2", None, None)
        rec.extra_fields = {"overdue_count": 1, "org_count": 2}
        out = json.loads(StructuredFormatter().format(rec))
        assert out["overdue_count"] == 1 and out["org_count"] == 2
        assert out["message"].startswith(ops.FREEZE_CHECK_MESSAGE)
