"""Setup-token expiry.

setup_tokens (the one-time link that claims the first admin login after a
fresh-from-v1 tenancy migration) previously had no expires_at column at all:
_valid_setup_token only checked used_at IS NULL, so a setup email forwarded,
archived, or leaked months ago stayed a live path to create an admin account
indefinitely. This exercises the expiry enforcement directly against
_valid_setup_token and the /setup HTTP routes, rather than reconstructing the
legacy-migration trigger that normally creates these rows -- that mechanism
is unchanged and untouched by this fix.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.api.app import _valid_setup_token, app  # noqa: E402
from amlkit.db import connect, utcnow  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    conn = connect(str(tmp_path / "test.db"))
    yield conn
    conn.close()


@pytest.fixture()
def org_id(db) -> int:
    row = db.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
        " RETURNING id",
        ("Test Firm", "test-firm", "active", utcnow()),
    ).fetchone()
    db.commit()
    return row["id"]


def _insert_token(db, org_id: int, raw_token: str, expires_at: str | None) -> None:
    db.execute(
        "INSERT INTO setup_tokens (org_id, token_hash, created_at, expires_at) VALUES (?,?,?,?)",
        (org_id, sha256(raw_token.encode()).hexdigest(), utcnow(), expires_at),
    )
    db.commit()


class TestSetupTokenExpiry:
    def test_fresh_token_is_valid(self, db, org_id) -> None:
        future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="seconds")
        _insert_token(db, org_id, "tok-fresh", future)
        assert _valid_setup_token(db, "tok-fresh") is not None

    def test_expired_token_is_rejected(self, db, org_id) -> None:
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds")
        _insert_token(db, org_id, "tok-expired", past)
        assert _valid_setup_token(db, "tok-expired") is None

    def test_null_expires_at_is_rejected(self, db, org_id) -> None:
        """A row from before this migration (no expires_at ever set) must
        fail closed, not be granted an unbounded lifetime."""
        _insert_token(db, org_id, "tok-legacy", None)
        assert _valid_setup_token(db, "tok-legacy") is None

    def test_expired_token_rejected_over_http(self, db, org_id) -> None:
        from fastapi.testclient import TestClient

        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
        _insert_token(db, org_id, "tok-http-expired", past)

        os.environ["AMLKIT_DB"] = str(Path(db.execute("PRAGMA database_list").fetchone()[2]))
        client = TestClient(app)
        r = client.get("/setup", params={"token": "tok-http-expired"})
        assert r.status_code == 200
        assert "invalid, expired, or already used" in r.text
