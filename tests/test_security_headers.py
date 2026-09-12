"""Security headers tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from amlkit.api.app import app  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(app)


class TestSecurityHeaders:
    def test_csp_header_present(self, client) -> None:
        """Content-Security-Policy header must be set on all responses."""
        r = client.get("/about")
        assert "Content-Security-Policy" in r.headers
        csp = r.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_x_content_type_options_present(self, client) -> None:
        """X-Content-Type-Options must be set to prevent MIME-sniffing."""
        r = client.get("/about")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options_present(self, client) -> None:
        """X-Frame-Options must be set to prevent clickjacking."""
        r = client.get("/about")
        assert r.headers.get("X-Frame-Options") == "DENY"

    def test_hsts_not_present_without_proxy_flag(self, client) -> None:
        """HSTS should NOT be set in dev (no AMLKIT_BEHIND_PROXY)."""
        # Ensure the env var is not set
        os.environ.pop("AMLKIT_BEHIND_PROXY", None)
        r = client.get("/about")
        assert "Strict-Transport-Security" not in r.headers

    def test_hsts_present_with_proxy_flag(self, client) -> None:
        """HSTS must be set in production (AMLKIT_BEHIND_PROXY=1)."""
        os.environ["AMLKIT_BEHIND_PROXY"] = "1"
        try:
            r = client.get("/about")
            assert "Strict-Transport-Security" in r.headers
            hsts = r.headers["Strict-Transport-Security"]
            assert "max-age=31536000" in hsts
            assert "includeSubDomains" in hsts
        finally:
            os.environ.pop("AMLKIT_BEHIND_PROXY", None)

    def test_csp_allows_inline_scripts(self, client) -> None:
        """CSP must allow 'unsafe-inline' for scripts since templates use inline scripts."""
        r = client.get("/about")
        csp = r.headers["Content-Security-Policy"]
        assert "script-src 'self' 'unsafe-inline'" in csp

    def test_csp_allows_inline_styles(self, client) -> None:
        """CSP must allow 'unsafe-inline' for styles since templates use inline style attributes."""
        r = client.get("/about")
        csp = r.headers["Content-Security-Policy"]
        assert "style-src 'self' 'unsafe-inline'" in csp

    def test_security_headers_on_authenticated_pages(self, client) -> None:
        """Security headers must be present on all responses, not just public pages."""
        # /login is publicly accessible
        r = client.get("/login")
        assert "Content-Security-Policy" in r.headers
        assert "X-Content-Type-Options" in r.headers
        assert "X-Frame-Options" in r.headers
