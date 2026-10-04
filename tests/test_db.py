"""Connection-level configuration tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect  # noqa: E402


class TestBusyTimeout:
    def test_busy_timeout_is_configured(self) -> None:
        """Without this, two connections writing at once fail immediately
        with 'database is locked' instead of one waiting for the other --
        exactly what happened in production when a scheduled refresh
        (which now holds a connection open for the whole synchronous
        refresh) overlapped with another write."""
        conn = connect(":memory:")
        try:
            timeout_ms = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            assert timeout_ms >= 30000
        finally:
            conn.close()


class TestNameTokensEntityIndex:
    """Reloading an already-stored dataset deletes each entity's tokens by
    entity_id (ingest/loader.py). name_tokens' primary key leads with `token`,
    so without an index on entity_id every one of those deletes scans the whole
    table: reloading ~40k existing Wikidata entities took ~560s instead of
    ~11s, which pushed the scheduled /system/refresh past Cloud Run's 900s
    request limit so the rescreen after it never completed."""

    def test_delete_by_entity_id_uses_an_index_not_a_table_scan(self) -> None:
        conn = connect(":memory:")
        try:
            plan = conn.execute(
                "EXPLAIN QUERY PLAN DELETE FROM name_tokens WHERE entity_id=?", (1,)
            ).fetchall()
            detail = " ".join(row["detail"] for row in plan)
            assert "SEARCH" in detail, detail
            assert "SCAN" not in detail, detail
        finally:
            conn.close()

    def test_existing_database_gets_the_index_on_next_connect(self, tmp_path) -> None:
        """Production databases predate the index, so connect() must add it
        to an existing file -- not only to freshly created ones."""
        db_file = tmp_path / "pre_index.db"
        conn = connect(db_file)
        conn.execute("DROP INDEX ix_tokens_entity")
        conn.commit()
        conn.close()

        conn = connect(db_file)
        try:
            names = {row["name"] for row in conn.execute("PRAGMA index_list(name_tokens)")}
            assert "ix_tokens_entity" in names
        finally:
            conn.close()
