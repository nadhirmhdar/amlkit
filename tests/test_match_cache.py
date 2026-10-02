"""Tests for the name-token blocking cache (amlkit/match/cache.py).

Covers get_entities_for_tokens() directly: cache misses populate from SQLite,
cache hits avoid re-querying, empty/negative results are remembered, and
invalidate() forces a re-read. These were previously exercised only
indirectly; cache_size/invalidate had a unit test but the core lookup did
not.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect, upsert_dataset  # noqa: E402
from amlkit.match import cache  # noqa: E402


def _add_entity(conn: sqlite3.Connection, dataset_id: int, caption: str,
                tokens: list[str]) -> int:
    cur = conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           countries, topics, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (dataset_id, caption, "natural", caption, '["AE"]', '["sanction"]',
         "{}", "2025-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    )
    eid = cur.lastrowid
    for tok in tokens:
        conn.execute(
            "INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)",
            (tok, eid),
        )
    return eid


@pytest.fixture()
def conn():
    c = connect(":memory:")
    ds = upsert_dataset(c, "test_list", "Synthetic Test List", is_mandatory=True)
    c.commit()
    yield c, ds
    c.close()


@pytest.fixture(autouse=True)
def _clear_cache():
    # The cache is process-global; isolate every test from the others.
    cache.invalidate()
    yield
    cache.invalidate()


def test_empty_tokens_returns_empty_and_does_not_touch_db(conn):
    c, _ = conn
    assert cache.get_entities_for_tokens(c, []) == []
    assert cache.cache_size() == 0


def test_miss_populates_from_db(conn):
    c, ds = conn
    eid = _add_entity(c, ds, "FOAD SALEHI", ["foad", "salehi"])
    c.commit()

    results = cache.get_entities_for_tokens(c, ["foad"])
    assert results == [("foad", eid)]
    assert cache.cache_size() == 1


def test_hit_does_not_requery_db(conn):
    c, ds = conn
    eid = _add_entity(c, ds, "FOAD SALEHI", ["foad"])
    c.commit()

    # Prime the cache.
    assert cache.get_entities_for_tokens(c, ["foad"]) == [("foad", eid)]

    # Delete the row underneath the cache; a cache hit must ignore the DB.
    c.execute("DELETE FROM name_tokens WHERE token='foad'")
    c.commit()

    assert cache.get_entities_for_tokens(c, ["foad"]) == [("foad", eid)]


def test_negative_result_is_cached(conn):
    c, _ = conn
    assert cache.get_entities_for_tokens(c, ["nonesuch"]) == []
    # The miss is remembered so a token with no matches is still cached.
    assert cache.cache_size() == 1
    assert cache.get_entities_for_tokens(c, ["nonesuch"]) == []


def test_multiple_entities_per_token(conn):
    c, ds = conn
    e1 = _add_entity(c, ds, "FOAD SALEHI", ["salehi"])
    e2 = _add_entity(c, ds, "MARYAM SALEHI", ["salehi"])
    c.commit()

    results = cache.get_entities_for_tokens(c, ["salehi"])
    assert sorted(eid for _, eid in results) == sorted([e1, e2])


def test_mixed_hit_and_miss(conn):
    c, ds = conn
    eid = _add_entity(c, ds, "FOAD SALEHI", ["foad"])
    c.commit()

    # Prime "foad" only.
    cache.get_entities_for_tokens(c, ["foad"])
    e2 = _add_entity(c, ds, "MARYAM SALEHI", ["maryam"])
    c.commit()

    results = cache.get_entities_for_tokens(c, ["foad", "maryam"])
    assert ("foad", eid) in results
    assert ("maryam", e2) in results


def test_invalidate_forces_requery(conn):
    c, ds = conn
    eid = _add_entity(c, ds, "FOAD SALEHI", ["foad"])
    c.commit()
    cache.get_entities_for_tokens(c, ["foad"])

    # New entity added after the cache was primed.
    e2 = _add_entity(c, ds, "FOAD ZAND", ["foad"])
    c.commit()

    # Stale cache still returns only the first entity...
    assert cache.get_entities_for_tokens(c, ["foad"]) == [("foad", eid)]

    # ...until invalidation, which picks up both.
    cache.invalidate()
    assert cache.cache_size() == 0
    results = cache.get_entities_for_tokens(c, ["foad"])
    assert sorted(eid for _, eid in results) == sorted([eid, e2])
