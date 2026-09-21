"""Tests for GET /customers/{id}/evidence.pdf — server-side PDF generation."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

# Import shared test helpers
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_api import _csrf, _register, _seed_sanctions_data  # noqa: E402

try:
    import weasyprint  # noqa: F401
    HAS_WEASYPRINT = True
except (ImportError, OSError):
    HAS_WEASYPRINT = False

pytestmark = pytest.mark.skipif(
    not HAS_WEASYPRINT,
    reason="weasyprint not available (requires libpango/cairo system libraries)",
)


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
