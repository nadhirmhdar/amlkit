"""connect() runs schema creation + migrations once per database file per process.

get_db() opens a connection per HTTP request; re-running the schema pass on
each one meant DDL, backfills and a fatf_countries rewrite on every GET.
"""

from __future__ import annotations

import sqlite3

import pytest

from amlkit import db


@pytest.fixture
def init_spy(monkeypatch):
    calls: list[int] = []
    real = db._migrate

    def spy(conn):
        calls.append(1)
        return real(conn)

    monkeypatch.setattr(db, "_migrate", spy)
    return calls


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_fresh_path_gets_full_schema(tmp_path, init_spy):
    conn = db.connect(tmp_path / "fresh.db")
    try:
        assert {"customers", "operators", "audit_log", "fatf_countries"} <= _tables(conn)
        assert conn.execute("SELECT COUNT(*) FROM fatf_countries").fetchone()[0] > 0
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()
    assert len(init_spy) == 1


def test_second_connect_skips_schema_and_migrations(tmp_path, init_spy):
    path = tmp_path / "once.db"
    db.connect(path).close()
    assert len(init_spy) == 1

    conn = db.connect(path)
    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    try:
        assert len(init_spy) == 1, "second connect re-ran migrations"
        assert conn.total_changes == 0
        # Per-connection PRAGMAs are still applied on the cached path.
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        conn.close()
    assert not [s for s in statements if not s.upper().startswith("PRAGMA")]


def test_replacing_file_reinitialises(tmp_path, init_spy):
    path = tmp_path / "replaced.db"
    db.connect(path).close()
    for suffix in ("", "-wal", "-shm"):
        p = path.with_name(path.name + suffix)
        if p.exists():
            p.unlink()
    sqlite3.connect(path).close()  # a different, empty file at the same path

    conn = db.connect(path)
    try:
        assert len(init_spy) == 2
        assert "customers" in _tables(conn)
    finally:
        conn.close()


def test_memory_db_always_initialises(init_spy):
    for expected in (1, 2):
        conn = db.connect(":memory:")
        try:
            assert "customers" in _tables(conn)
        finally:
            conn.close()
        assert len(init_spy) == expected


def test_reset_init_cache_forces_reinit(tmp_path, init_spy):
    path = tmp_path / "reset.db"
    db.connect(path).close()
    db._reset_init_cache()
    db.connect(path).close()
    assert len(init_spy) == 2
