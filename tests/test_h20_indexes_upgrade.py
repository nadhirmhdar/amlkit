"""H20 composite indexes must not break opening a pre-tenancy database.

alerts.org_id and audit_log.org_id arrive via _MIGRATIONS on upgraded
databases, so any index on them has to be created after migration
(_create_org_indexes), not in the SCHEMA executescript that runs first.
"""
from __future__ import annotations

import re
import sqlite3

from amlkit import db


def _pre_tenancy_table(table: str) -> str:
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", db.SCHEMA, re.S)
    assert m, table
    cols = [
        line for line in m.group(1).splitlines()
        if not re.match(r"\s*org_id\s", line)
    ]
    return f"CREATE TABLE {table} (" + "\n".join(cols) + "\n);"


def test_connect_upgrades_pre_tenancy_alerts_and_audit_log(tmp_path):
    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.executescript(_pre_tenancy_table("alerts") + _pre_tenancy_table("audit_log"))
    raw.close()

    conn = db.connect(path)
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(alerts)")}
        assert "org_id" in cols
        indexes = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert {
            "ix_alert_org_status_score",
            "ix_alert_org_status_created",
            "ix_audit_org_action_ts",
        } <= indexes
    finally:
        conn.close()


def test_alert_queue_uses_composite_index(tmp_path):
    conn = db.connect(tmp_path / "fresh.db")
    try:
        plan = " ".join(
            r[3] for r in conn.execute(
                "EXPLAIN QUERY PLAN SELECT id FROM alerts WHERE org_id=? AND status=? ORDER BY score DESC",
                (1, "open"),
            )
        )
        assert "ix_alert_org_status_score" in plan
        assert "TEMP B-TREE" not in plan
    finally:
        conn.close()
