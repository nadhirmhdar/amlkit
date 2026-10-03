"""Every data export out of the app writes exactly one audit row.

Covers the web CSV exports (alerts, customers, feedback, audit log), the
evidence-pack PDF, the goAML XML download, and their mobile-API equivalents.
Each row must carry the exporting session's org_id and an `export.*` action,
and must not contain the exported data itself.

Also covers super-admin cross-org console views
(docs/reviews/2026-09-21-deployed-site-review/proposed_tests/
test_proposed_gaps.py :: TestConsoleCrossOrgAccessIsAudited).
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_api import _csrf, _register, _seed_sanctions_data  # noqa: E402


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


def _org_id(name: str) -> int:
    conn = _db()
    row = conn.execute("SELECT id FROM organizations WHERE name=?", (name,)).fetchone()
    conn.close()
    return row["id"]


def _export_rows(action: str) -> list[sqlite3.Row]:
    conn = _db()
    rows = conn.execute(
        "SELECT org_id, actor, action, object_type, object_id, detail FROM audit_log"
        " WHERE action=?", (action,)).fetchall()
    conn.close()
    return rows


def _seed_report(org_id: int) -> int:
    """A draft STR for `org_id` that serialises to goAML XML."""
    from amlkit.db import utcnow
    now = utcnow()
    conn = _db()
    conn.execute("UPDATE organizations SET goaml_entity_reference=? WHERE id=?",
                 ("AUDIT-EXPORT-1", org_id))
    cur = conn.execute(
        "INSERT INTO customers (org_id, reference, customer_type, full_name, canonical_key,"
        " status, onboarded_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (org_id, "C-EXP", "natural", "John Doe", "john|doe", "active", now, now, now))
    payload = {"report_type": "STR", "reporter_name": "Test Reporter",
               "reporter_email": "reporter@example.ae",
               "first_name": "John", "last_name": "Doe"}
    cur = conn.execute(
        "INSERT INTO reports (org_id, customer_id, report_type, status, payload, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (org_id, cur.lastrowid, "STR", "draft", json.dumps(payload), now))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


@pytest.fixture()
def api(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    r = c.post("/api/v1/auth/register-organization", json={
        "org_name": "Mobile Firm", "name": "alice", "email": "alice@mobilefirm.ae",
        "password": "a-strong-password-1", "invite_code": "test-invite",
    })
    assert r.status_code == 200, r.text
    r2 = c.post("/api/v1/auth/verify-email",
                json={"token": r.json()["dev_verification_token"]})
    token = r2.json()["token"]
    from conftest import unlock_mobile_mfa
    unlock_mobile_mfa(c, token)
    return c, {"Authorization": f"Bearer {token}"}


class TestWebExportsAreAudited:
    @pytest.mark.parametrize("path, action", [
        ("/alerts.csv?status=open", "export.alerts_csv"),
        ("/customers.csv", "export.customers_csv"),
        ("/admin/feedback/export", "export.feedback_csv"),
        ("/audit/export", "export.audit_csv"),
    ])
    def test_csv_export_writes_one_audit_row(self, client, path, action):
        r = client.get(path)
        assert r.status_code == 200, r.text[:200]
        assert r.headers["content-type"].startswith("text/csv")
        rows = _export_rows(action)
        assert len(rows) == 1, [dict(x) for x in rows]
        assert rows[0]["org_id"] == _org_id("Test Firm")
        assert rows[0]["actor"] == "alice"
        assert "rows" in json.loads(rows[0]["detail"])

    def test_alerts_csv_records_filter(self, client):
        client.get("/alerts.csv?status=open&category=sanctions")
        detail = json.loads(_export_rows("export.alerts_csv")[0]["detail"])
        assert detail["status"] == "open"

    def test_evidence_pdf_writes_audit_row(self, client, monkeypatch):
        import amlkit.reporting.evidence_pdf as evidence_pdf
        monkeypatch.setattr(evidence_pdf, "render_pdf", lambda html: b"%PDF-fake")
        org = _org_id("Test Firm")
        rid = _seed_report(org)  # also seeds a customer
        conn = _db()
        cid = conn.execute("SELECT customer_id FROM reports WHERE id=?", (rid,)).fetchone()[0]
        conn.close()

        r = client.get(f"/customers/{cid}/evidence.pdf")
        assert r.status_code == 200, r.text[:200]
        rows = _export_rows("export.evidence_pdf")
        assert len(rows) == 1
        assert rows[0]["org_id"] == org
        assert (rows[0]["object_type"], rows[0]["object_id"]) == ("customer", str(cid))

    def test_evidence_pdf_not_found_is_not_audited(self, client):
        r = client.get("/customers/99999/evidence.pdf")
        assert r.status_code == 404
        assert _export_rows("export.evidence_pdf") == []

    def test_goaml_xml_export_writes_audit_row(self, client):
        org = _org_id("Test Firm")
        rid = _seed_report(org)
        r = client.get(f"/reports/{rid}/export")
        assert r.status_code == 200, r.text[:300]
        rows = _export_rows("export.goaml_xml")
        assert len(rows) == 1
        assert rows[0]["org_id"] == org
        assert (rows[0]["object_type"], rows[0]["object_id"]) == ("report", str(rid))
        # The exported XML itself is never copied into the audit trail.
        assert "John" not in (rows[0]["detail"] or "")


class TestMobileExportsAreAudited:
    @pytest.mark.parametrize("path, action", [
        ("/api/v1/alerts.csv", "export.alerts_csv"),
        ("/api/v1/customers.csv", "export.customers_csv"),
        ("/api/v1/audit/export", "export.audit_csv"),
    ])
    def test_csv_export_writes_one_audit_row(self, api, path, action):
        c, headers = api
        r = c.get(path, headers=headers)
        assert r.status_code == 200, r.text[:200]
        rows = _export_rows(action)
        assert len(rows) == 1, [dict(x) for x in rows]
        assert rows[0]["org_id"] == _org_id("Mobile Firm")
        assert json.loads(rows[0]["detail"])["via"] == "mobile"

    def test_goaml_xml_export_writes_audit_row(self, api):
        c, headers = api
        org = _org_id("Mobile Firm")
        rid = _seed_report(org)
        r = c.get(f"/api/v1/reports/{rid}/export", headers=headers)
        assert r.status_code == 200, r.text[:300]
        rows = _export_rows("export.goaml_xml")
        assert len(rows) == 1
        assert rows[0]["org_id"] == org
        assert rows[0]["object_id"] == str(rid)


class TestConsoleCrossOrgAccessIsAudited:
    """Adapted from the 2026-09-21 review's proposed test."""

    @pytest.fixture()
    def super_admin(self, client):
        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        other = TestClient(app)
        _register(other, "Other Firm", "bob", "bob@otherfirm.ae")

        conn = _db()
        conn.execute("UPDATE operators SET super_admin=1 WHERE email='alice@testfirm.ae'")
        conn.commit()
        conn.close()
        client.post("/logout", data={"csrf_token": _csrf(client)})
        client.get("/login")
        client.post("/login", data={"email": "alice@testfirm.ae",
                                    "password": "a-strong-password-1",
                                    "csrf_token": _csrf(client)}, follow_redirects=True)
        from conftest import settle_mfa
        settle_mfa(client)
        return _org_id("Other Firm")

    @pytest.mark.parametrize("view", ["customers", "alerts"])
    def test_viewing_another_orgs_data_writes_an_audit_row(self, client, super_admin, view):
        r = client.get(f"/console/org/{super_admin}/{view}", follow_redirects=False)
        # The review's original fixture skipped settle_mfa() after re-login, so
        # its request was 303'd to /mfa/verify and never reached the route.
        assert r.status_code == 200, r.text[:200]

        conn = _db()
        rows = conn.execute(
            "SELECT action, org_id, actor FROM audit_log WHERE action LIKE 'console.%'"
        ).fetchall()
        conn.close()
        assert rows, f"super-admin viewed another org's {view} and no audit row was written"
        assert any(row["org_id"] == super_admin for row in rows), (
            f"audit row does not name the viewed org: {[dict(x) for x in rows]}"
        )
        # Attributed to the super-admin (email, as in test_a02_5_superadmin_audit).
        assert all(row["actor"] == "alice@testfirm.ae" for row in rows)
