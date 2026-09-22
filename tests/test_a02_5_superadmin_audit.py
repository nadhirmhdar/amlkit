"""A-02-5: Super-admin cross-tenant console access must be audited.

super-admin GET routes console_org_alerts and console_org_customers correctly
gate via require_super_admin but write NO audit_log entry. Cross-tenant
customer and alert access by a super-admin leaves no trace.

Test: super-admin hits both console routes for a different org, assert
audit_log row exists with acting operator identity and target org_id.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _csrf(client) -> str:
    """Extract CSRF token from client cookies."""
    return client.cookies.get("amlkit_csrf")


def _register_mlro(client, org_name: str, email: str, password: str = "strong-pass-1"):
    """Register MLRO and complete verification."""
    import re
    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name,
        "name": "MLRO",
        "email": email,
        "password": password,
        "csrf_token": _csrf(client),
        "invite_code": "test-invite",
    }, follow_redirects=True)
    assert "Check your email" in r.text, f"registration failed: {r.text[:300]}"
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m, f"no verification link: {r.text[:500]}"
    client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    from conftest import settle_mfa
    settle_mfa(client)
    return client


@pytest.fixture()
def super_admin_client(tmp_path, monkeypatch):
    """Super-admin session."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    client = TestClient(app)

    # Register super-admin org
    _register_mlro(client, "Super Admin Org", "super@admin.local")

    # Promote to super-admin
    import sqlite3
    import os
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    conn.execute("UPDATE operators SET super_admin=1 WHERE email='super@admin.local'")
    conn.commit()
    conn.close()

    return client


@pytest.fixture()
def other_org_id(tmp_path):
    """Create another org with customers and alerts."""
    import sqlite3
    import os
    from amlkit.db import connect, utcnow, upsert_dataset
    from amlkit.names.arabic import blocking_keys, canonical_key

    conn = connect(os.environ["AMLKIT_DB"])

    # Create another org
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id",
        ("Other Firm", "other-firm", "active", utcnow())
    ).fetchone()
    org_id = row["id"]

    # Seed a mandatory dataset so onboard() passes staleness guard
    ds = upsert_dataset(conn, "test_list", "Test List", is_mandatory=True)
    now = utcnow()
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    cur = conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           countries, birth_date, gender, topics, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, "TEST-001", "Person", "AHMED TEST", '["ly"]', "1975-03-12", "male",
         '["sanction"]', "{}", now, now)
    )
    eid = cur.lastrowid
    conn.execute(
        "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
        " VALUES (?,?,?,?,?)",
        (eid, "AHMED TEST", "primary", canonical_key("AHMED TEST"), "latin")
    )
    for tok in blocking_keys("AHMED TEST"):
        conn.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)", (tok, eid))

    # Create a customer with an alert
    from amlkit.cases.manager import onboard
    result = onboard(conn, org_id=org_id, reference="C-OTHER-001",
                    full_name="Ahmed Al Mansoori", customer_type="natural",
                    birth_date="1980-01-01")

    conn.commit()
    conn.close()
    return org_id


class TestSuperAdminAuditTrail:
    """Super-admin cross-tenant console access must be audited."""

    def test_console_org_alerts_creates_audit_entry(self, super_admin_client, other_org_id) -> None:
        """Super-admin viewing another org's alerts must be audited."""
        import os
        import sqlite3

        # Before: no audit entries for console.org_alerts.view
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        conn.row_factory = sqlite3.Row
        before_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM audit_log WHERE action='console.org_alerts.view'"
        ).fetchone()["cnt"]
        assert before_count == 0, "Precondition: no audit entries yet"
        conn.close()

        # Super-admin views other org's alerts
        r = super_admin_client.get(f"/console/org/{other_org_id}/alerts")
        assert r.status_code == 200, f"Expected success, got {r.status_code}"

        # After: audit entry exists
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        conn.row_factory = sqlite3.Row
        audit_entry = conn.execute(
            """SELECT actor, action, object_type, object_id, detail, org_id
               FROM audit_log
               WHERE action='console.org_alerts.view' AND org_id=?
               ORDER BY id DESC LIMIT 1""",
            (other_org_id,)
        ).fetchone()
        conn.close()

        assert audit_entry is not None, "Audit entry must exist after super-admin views alerts"
        assert audit_entry["org_id"] == other_org_id, "Audit must be under viewed org_id"
        assert audit_entry["actor"] == "super@admin.local", "Actor must be super-admin email"

        detail = json.loads(audit_entry["detail"])
        assert "super_admin_org_id" in detail, "Detail must contain super-admin's org_id"

    def test_console_org_customers_creates_audit_entry(self, super_admin_client, other_org_id) -> None:
        """Super-admin viewing another org's customers must be audited."""
        import os
        import sqlite3

        # Before: no audit entries for console.org_customers.view
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        conn.row_factory = sqlite3.Row
        before_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM audit_log WHERE action='console.org_customers.view'"
        ).fetchone()["cnt"]
        assert before_count == 0, "Precondition: no audit entries yet"
        conn.close()

        # Super-admin views other org's customers
        r = super_admin_client.get(f"/console/org/{other_org_id}/customers")
        assert r.status_code == 200, f"Expected success, got {r.status_code}"

        # After: audit entry exists
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        conn.row_factory = sqlite3.Row
        audit_entry = conn.execute(
            """SELECT actor, action, object_type, object_id, detail, org_id
               FROM audit_log
               WHERE action='console.org_customers.view' AND org_id=?
               ORDER BY id DESC LIMIT 1""",
            (other_org_id,)
        ).fetchone()
        conn.close()

        assert audit_entry is not None, "Audit entry must exist after super-admin views customers"
        assert audit_entry["org_id"] == other_org_id, "Audit must be under viewed org_id"
        assert audit_entry["actor"] == "super@admin.local", "Actor must be super-admin email"

        detail = json.loads(audit_entry["detail"])
        assert "super_admin_org_id" in detail, "Detail must contain super-admin's org_id"
