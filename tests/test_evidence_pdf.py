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

from amlkit.reporting.evidence_pdf import (  # noqa: E402
    PDF_BASE_URL,
    STATIC_ROOT,
    mime_type_for,
    resolve_static_asset,
)

needs_weasyprint = pytest.mark.skipif(
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


@needs_weasyprint
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

    def test_arabic_customer_name_download(self, client):
        """Non-latin-1 names must not break the Content-Disposition header."""
        cid = _onboard_customer(client, name="محمد بن راشد")
        r = client.get(f"/customers/{cid}/evidence.pdf")
        assert r.status_code == 200
        cd = r.headers["content-disposition"]
        assert f'filename="evidence-{cid}-customer.pdf"' in cd
        assert "filename*=UTF-8''" in cd


class TestStaticAssetResolution:
    """The PDF fetcher's allow-list: runs without WeasyPrint installed."""

    def test_static_css_allowed(self):
        path = resolve_static_asset(PDF_BASE_URL + "static/app.css")
        assert path == STATIC_ROOT / "app.css"
        assert mime_type_for(path) == "text/css"

    def test_root_relative_href_resolves_to_allowed_url(self):
        from urllib.parse import urljoin
        assert resolve_static_asset(urljoin(PDF_BASE_URL, "/static/app.css")) is not None

    @pytest.mark.parametrize("url", [
        "http://169.254.169.254/latest/meta-data/",
        "https://example.com/static/app.css",
        "http://localhost:8000/static/app.css",
        "file:///etc/passwd",
        (STATIC_ROOT / "app.css").as_uri(),
        "ftp://example.com/x",
        "data:text/css,body{}",
        PDF_BASE_URL + "templates/base.html",
        PDF_BASE_URL + "static/../templates/base.html",
        PDF_BASE_URL + "static/%2e%2e/templates/base.html",
        PDF_BASE_URL + "static/..%2f..%2fdb.py",
        PDF_BASE_URL + "static/does-not-exist.css",
        PDF_BASE_URL + "static/",
    ])
    def test_everything_else_blocked(self, url):
        assert resolve_static_asset(url) is None


@needs_weasyprint
class TestStaticOnlyFetcher:
    """The real WeasyPrint fetcher object (pinned WeasyPrint API)."""

    def test_is_weasyprint_url_fetcher(self):
        from weasyprint.urls import URLFetcher
        from amlkit.reporting.evidence_pdf import make_url_fetcher
        assert isinstance(make_url_fetcher(), URLFetcher)

    def test_serves_local_static_css(self):
        from amlkit.reporting.evidence_pdf import make_url_fetcher
        resp = make_url_fetcher().fetch(PDF_BASE_URL + "static/app.css")
        try:
            assert resp.content_type == "text/css"
            assert resp.read() == (STATIC_ROOT / "app.css").read_bytes()
        finally:
            resp.close()

    @pytest.mark.parametrize("url", [
        "http://169.254.169.254/latest/meta-data/",
        "https://example.com/logo.png",
        "file:///etc/passwd",
    ])
    def test_external_urls_refused(self, url, monkeypatch):
        import urllib.request
        from amlkit.reporting.evidence_pdf import make_url_fetcher

        def _no_network(*a, **kw):
            raise AssertionError(f"network/file open attempted for {url}")
        monkeypatch.setattr(urllib.request.OpenerDirector, "open", _no_network)
        with pytest.raises(ValueError, match="blocked"):
            make_url_fetcher().fetch(url)

    def test_render_does_not_fetch_external_resources(self, monkeypatch):
        """End to end: an external <img>/<link> in the HTML is never fetched."""
        import urllib.request
        from amlkit.reporting.evidence_pdf import render_pdf

        opened = []

        def _record_open(self, *a, **kw):
            opened.append(a)
            raise AssertionError("network/file fetch attempted")
        monkeypatch.setattr(urllib.request.OpenerDirector, "open", _record_open)
        pdf = render_pdf(
            '<html><head><link rel="stylesheet" href="http://127.0.0.1:9/x.css">'
            '<link rel="stylesheet" href="/static/app.css"></head>'
            '<body><img src="http://169.254.169.254/x.png">'
            '<img src="file:///etc/passwd"><p>hi</p></body></html>'
        )
        assert pdf[:5] == b"%PDF-"
        assert opened == []
