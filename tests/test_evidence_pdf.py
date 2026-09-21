"""Tests for GET /customers/{id}/evidence.pdf — server-side PDF generation."""

from __future__ import annotations

import os
import re
import sqlite3

import pytest

try:
    import weasyprint  # noqa: F401
    HAS_WEASYPRINT = True
except (ImportError, OSError):
    HAS_WEASYPRINT = False

pytestmark = pytest.mark.skipif(
    not HAS_WEASYPRINT,
    reason="weasyprint not available (requires libpango/cairo system libraries)",
)


def _seed_sanctions_data(db_file):
    from amlkit.db import connect, upsert_dataset, utcnow
    from amlkit.names.arabic import blocking_keys, canonical_key

    conn = connect(db_file)
    ds = upsert_dataset(conn, "test_list", "Test List", is_mandatory=True)
    now = utcnow()
    cur = conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           countries, birth_date, gender, topics, programs, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, "T-1", "Person", "John Doe", '["ae"]', "1980-01-01", "male",
         '["sanction"]', '["TEST"]', "{}", now, now),
    )
    eid = cur.lastrowid
    conn.execute(
        "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
        " VALUES (?,?,?,?,?)",
        (eid, "John Doe", "primary", canonical_key("John Doe"), "latin"),
    )
    for tok in blocking_keys("John Doe"):
        conn.execute(
            "INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)",
            (tok, eid),
        )
    conn.execute(
        "UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?",
        (now, ds),
    )
    conn.commit()
    conn.close()


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name, name, email, password="a-strong-password-1"):
    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m, "no dev verification link"
    client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    return client


def _db():
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


def _onboard_customer(client, name="PDF Test Customer"):
    client.get("/customers/new")
    client.post("/customers", data={
        "reference": f"REF-{name[:5]}",
        "full_name": name,
        "customer_type": "natural",
        "nationality": "AE",
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    conn = _db()
    row = conn.execute(
        "SELECT id FROM customers WHERE full_name=? ORDER BY id DESC LIMIT 1",
        (name,),
    ).fetchone()
    conn.close()
    return row["id"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "PDF Firm", "pdf_user", "pdf@test.ae")
    return c


class TestEvidencePdf:
    def test_returns_pdf_for_own_org(self, client):
        cid = _onboard_customer(client)
        r = client.get(f"/customers/{cid}/evidence.pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:5] == b"%PDF-"
        assert "attachment" in r.headers.get("content-disposition", "")

    def test_404_for_cross_org_customer(self, client):
        """Org A cannot access Org B's customer evidence PDF (tenant isolation)."""
        # client is logged in as org 1 ("PDF Firm")
        # Register a second org and onboard a customer there
        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        client2 = TestClient(app)
        _register(client2, "Other Firm", "other_user", "other@test.ae")
        other_cid = _onboard_customer(client2, name="Other Org Customer")

        # Org 1's client tries to access Org 2's customer PDF
        r = client.get(f"/customers/{other_cid}/evidence.pdf")
        assert r.status_code == 404, f"Expected 404 for cross-org access, got {r.status_code}"
