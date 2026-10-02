"""Connection-level configuration tests."""

from __future__ import annotations

import sqlite3
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


class TestLegalNameBackfill:
    def test_pre_existing_org_gets_legal_name_backfilled_from_name(self, tmp_path) -> None:
        """An org that existed before the legal_name column was introduced
        must not have its STR builder's required reporting-entity-name
        field silently go blank with no explanation (see
        web/templates/str_builder.html, which no longer falls back to
        org.name) -- connect() must backfill legal_name=name for it, once,
        the same way it backfills email_verified_at for pre-existing
        operators."""
        db_file = tmp_path / "pre_existing.db"
        raw = sqlite3.connect(db_file)
        raw.execute(
            """CREATE TABLE organizations (
                 id INTEGER PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
                 status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL
               )"""
        )
        raw.execute(
            "INSERT INTO organizations (name, slug, status, created_at)"
            " VALUES ('Grovisor Business Consultants', 'grovisor', 'active', '2025-01-01T00:00:00Z')"
        )
        raw.commit()
        raw.close()

        conn = connect(db_file)
        try:
            row = conn.execute("SELECT legal_name FROM organizations WHERE slug='grovisor'").fetchone()
            assert row["legal_name"] == "Grovisor Business Consultants"
        finally:
            conn.close()

    def test_org_created_after_the_migration_is_not_backfilled(self, tmp_path) -> None:
        """A NEW org, created once legal_name already exists, must keep
        starting with legal_name unset -- backfilling it from `name` on
        every connect() would silently satisfy the required-field guard
        the same way the removed org.name template fallback used to,
        defeating the fix it's paired with."""
        db_file = tmp_path / "fresh.db"
        conn = connect(db_file)
        try:
            conn.execute(
                "INSERT INTO organizations (name, slug, status, created_at)"
                " VALUES ('New Co', 'new-co', 'active', '2026-01-01T00:00:00Z')"
            )
            conn.commit()
        finally:
            conn.close()

        # Re-open (a second connect() call, exercising the migration path
        # again) and confirm the new org's legal_name is still unset.
        conn = connect(db_file)
        try:
            row = conn.execute("SELECT legal_name FROM organizations WHERE slug='new-co'").fetchone()
            assert row["legal_name"] is None
        finally:
            conn.close()
