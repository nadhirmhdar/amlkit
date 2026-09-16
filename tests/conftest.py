"""Shared test fixtures and utilities."""

import pytest
from amlkit.db import connect, upsert_dataset, utcnow
from amlkit.names.arabic import blocking_keys, canonical_key


LISTED = "AHMED ABD AL-JALEEL AL-HASNAWI"


def seed_fresh_dataset(conn, key="test_list", title="Synthetic Test List"):
    """Seed a fresh mandatory dataset with one test entity.

    Required for onboard() to pass the staleness guard introduced in Phase 3.
    """
    ds = upsert_dataset(conn, key, title, is_mandatory=True)
    now = utcnow()
    # Make dataset fresh
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    cur = conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           countries, birth_date, gender, topics, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, "TEST-001", "Person", LISTED, '["ly"]', "1975-03-12", "male",
         '["sanction"]', "{}", now, now)
    )
    eid = cur.lastrowid
    conn.execute(
        "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
        " VALUES (?,?,?,?,?)",
        (eid, LISTED, "primary", canonical_key(LISTED), "latin")
    )
    for tok in blocking_keys(LISTED):
        conn.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)", (tok, eid))
    conn.commit()
    return ds


@pytest.fixture()
def conn():
    """In-memory database with fresh mandatory dataset."""
    c = connect(":memory:")
    seed_fresh_dataset(c)
    yield c
    c.close()


@pytest.fixture()
def org_id(conn) -> int:
    """Test organization."""
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
        " RETURNING id",
        ("Test Firm", "test-firm", "active", utcnow()),
    ).fetchone()
    conn.commit()
    return row["id"]
