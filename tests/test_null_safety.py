"""Null-safety for unchecked fetchone() calls in app.py.

Lines ~381 (setup_form) and ~1340 (admin_view) dereference the result of an
org-lookup fetchone() without checking for None. If the org row is absent
(orphaned FK, race, data corruption) these crash with a TypeError instead of
returning a user-visible error.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    from amlkit.db import connect
    connect(db_file).close()

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    return TestClient(app)


def _db():
    import sqlite3
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


class TestSetupFormOrgMissing:
    """GET /setup with a valid token whose org no longer exists."""

    def test_returns_error_page_not_500(self, client) -> None:
        from amlkit.db import utcnow

        conn = _db()
        # Create an org, then a token pointing to it
        cur = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
            ("Ghost Org", "ghost", "active", utcnow()),
        )
        org_id = cur.lastrowid
        raw_token = "test-orphan-token"
        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO setup_tokens (org_id, token_hash, created_at, expires_at) VALUES (?,?,?,?)",
            (org_id, sha256(raw_token.encode()).hexdigest(), utcnow(), expires_at),
        )
        conn.commit()

        # Delete the org with FK off so the token row survives
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("DELETE FROM organizations WHERE id=?", (org_id,))
        conn.commit()
        conn.execute("PRAGMA foreign_keys=ON")
        conn.close()

        r = client.get("/setup", params={"token": raw_token})
        assert r.status_code == 200, f"expected 200 error page, got {r.status_code}"
        assert "invalid" in r.text.lower() or "not found" in r.text.lower() or "error" in r.text.lower()


class TestAdminViewOrgMissing:
    """GET /admin when the session's org no longer exists."""

    def test_returns_redirect_not_500(self, client) -> None:
        from amlkit.db import utcnow

        # Register a user so we have a valid session
        def _csrf():
            return client.cookies.get("amlkit_csrf")

        import re
        client.get("/register-organization")
        r = client.post("/register-organization", data={
            "org_name": "Vanishing Org", "name": "admin",
            "email": "admin@vanish.test", "password": "a-strong-password-1",
            "csrf_token": _csrf(),
        }, follow_redirects=True)
        m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
        assert m, "no verification link"
        client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
        from conftest import settle_mfa  # p15: MLRO sessions start locked
        settle_mfa(client)

        # Now delete the org with FK off
        conn = _db()
        org = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()
        assert org is not None
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("DELETE FROM organizations WHERE id=?", (org["id"],))
        conn.commit()
        conn.execute("PRAGMA foreign_keys=ON")
        conn.close()

        r = client.get("/admin", follow_redirects=False)
        # Should get a redirect or error page, not a 500
        assert r.status_code != 500, "got 500 — org fetchone() returned None and was dereferenced"
