"""EXPLAIN QUERY PLAN audit for amlkit hot query paths.

Read-only, additive. Opens a throwaway SQLite database built by
db.connect() so it sees the real production schema (every migration and
CREATE INDEX), seeds a few rows, then runs EXPLAIN QUERY PLAN on each hot
query and flags any full-table SCAN of a large table.

Changes no application code and no production data.

    .venv/Scripts/python.exe scripts/db_index_audit.py

Exit code 0 when no large table is scanned on a hot path, 1 otherwise
(so it can gate CI).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit import db

LARGE_TABLES = {
    "entities",
    "entity_names",
    "name_tokens",
    "entity_identifiers",
    "alerts",
    "screenings",
    "customers",
    "ubo_links",
    "transactions",
    "transaction_alerts",
    "adverse_media_findings",
    "audit_log",
}

HOT_QUERIES = [
    (
        "candidates: name_tokens by token (engine._candidates -> cache)",
        "SELECT token, entity_id FROM name_tokens WHERE token IN (?, ?, ?)",
        ("smith", "john", "ali"),
    ),
    (
        "candidates: entities by id set (engine._candidates)",
        "SELECT e.id, e.caption, e.schema_type, e.countries, e.birth_date, "
        "e.gender, e.topics, e.programs, d.key AS dataset "
        "FROM entities e JOIN datasets d ON d.id = e.dataset_id "
        "WHERE e.id IN (?, ?, ?)",
        (1, 2, 3),
    ),
    (
        "screen: names for entity (engine._names_for)",
        "SELECT name FROM entity_names WHERE entity_id=?",
        (1,),
    ),
    (
        "screen: identifiers for entity (engine._identifiers_for)",
        "SELECT id_type, id_value FROM entity_identifiers WHERE entity_id=?",
        (1,),
    ),
    (
        "persist: existing open alert dedup (engine._persist)",
        "SELECT 1 FROM alerts a JOIN screenings s ON s.id = a.screening_id "
        "WHERE a.org_id = ? AND a.entity_id = ? AND a.status = 'open' "
        "AND s.customer_id IS ? AND s.ubo_id IS ? LIMIT 1",
        (1, 1, 1, None),
    ),
    (
        "rescreen_all: active customers by org (engine.rescreen_all)",
        "SELECT id, full_name, name_arabic, nationality, birth_date, gender "
        "FROM customers WHERE status='active' AND org_id=?",
        (1,),
    ),
    (
        "rescreen_all: active UBOs by org (engine.rescreen_all)",
        "SELECT id, customer_id, person_name, name_arabic, nationality, birth_date "
        "FROM ubo_links WHERE is_ubo=1 AND is_nominee=0 AND org_id=?",
        (1,),
    ),
    (
        "alert_queue: alerts by org (queries.alert_queue)",
        "SELECT a.id, a.score, a.status FROM alerts a "
        "JOIN entities e ON e.id = a.entity_id "
        "JOIN datasets d ON d.id = e.dataset_id "
        "JOIN screenings s ON s.id = a.screening_id "
        "LEFT JOIN customers c ON c.id = s.customer_id "
        "LEFT JOIN ubo_links u ON u.id = s.ubo_id "
        "WHERE a.org_id = ? AND a.status = ? ORDER BY a.score DESC LIMIT ?",
        (1, "open", 200),
    ),
    (
        "customer_list: customers by org (queries.customer_list)",
        "SELECT c.id, c.reference, c.full_name FROM customers c WHERE c.org_id = ?",
        (1,),
    ),
    (
        "transaction_alert_queue: txn alerts by org (queries.transaction_alert_queue)",
        "SELECT ta.id, ta.rule_key, ta.status FROM transaction_alerts ta "
        "JOIN transactions t ON t.id = ta.transaction_id "
        "JOIN customers c ON c.id = ta.customer_id "
        "WHERE ta.org_id = ?",
        (1,),
    ),
]


def _seed(conn):
    conn.execute(
        "INSERT INTO datasets (key, title, publisher, licence, is_mandatory) "
        "VALUES ('un', 'UN List', 'UN', 'open', 1)"
    )
    ds = conn.execute("SELECT id FROM datasets WHERE key='un'").fetchone()["id"]
    conn.execute(
        "INSERT INTO entities (id, dataset_id, source_id, schema_type, caption, "
        "first_seen, last_seen) VALUES (1, ?, 's1', 'Person', 'John Smith', "
        "'2024-01-01', '2024-01-01')",
        (ds,),
    )
    conn.execute(
        "INSERT INTO entity_names (entity_id, name, canonical_key) "
        "VALUES (1, 'John Smith', 'john smith')"
    )
    conn.execute(
        "INSERT INTO name_tokens (token, entity_id) VALUES ('john', 1), ('smith', 1)"
    )
    conn.execute(
        "INSERT INTO entity_identifiers (entity_id, id_type, id_value) "
        "VALUES (1, 'passport', 'X1234567')"
    )
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) "
        "VALUES ('Test Org', 'test', 'active', '2024-01-01')"
    )
    conn.commit()


def audit(conn):
    findings = []
    for label, sql, params in HOT_QUERIES:
        rows = conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
        plan_lines = [r["detail"] for r in rows]
        scans = [
            line
            for line in plan_lines
            for tbl in LARGE_TABLES
            if line.startswith("SCAN " + tbl) and "USING" not in line
        ]
        # H20: Also flag TEMP B-TREE (missing composite index for ORDER BY)
        temp_btree = [line for line in plan_lines if "TEMP B-TREE" in line]
        findings.append({"label": label, "plan": plan_lines, "full_scans": scans, "temp_btree": temp_btree})
    return findings


def main():
    with tempfile.TemporaryDirectory() as tmp:
        conn = db.connect(Path(tmp) / "audit.db")
        try:
            _seed(conn)
            findings = audit(conn)
        finally:
            conn.close()

    problems = 0
    print("=" * 72)
    print("amlkit DB index audit -- EXPLAIN QUERY PLAN of hot query paths")
    print("=" * 72)
    for f in findings:
        flagged = bool(f["full_scans"]) or bool(f.get("temp_btree", []))
        problems += len(f["full_scans"]) + len(f.get("temp_btree", []))
        marker = "!! FULL SCAN/TEMP" if flagged else "ok"
        print("\n[" + marker + "] " + f["label"])
        for line in f["plan"]:
            print("    " + line)
        for scan in f["full_scans"]:
            print("    ^^ flagged: full scan of a large table -> " + scan)

    print("\n" + "=" * 72)
    if problems:
        print("RESULT: " + str(problems) + " hot query path(s) fall back to a full scan.")
        print("Add a covering index as an additive CREATE INDEX IF NOT EXISTS.")
    else:
        print("RESULT: no hot query path scans a large table. All covered.")
    print("=" * 72)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
