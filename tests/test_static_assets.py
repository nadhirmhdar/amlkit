"""Smoke tests for static assets after CSP migration.

After migrating to external JS files (removing 'unsafe-inline' from CSP),
verify that all static assets are served correctly with proper content types.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from amlkit.api.app import app  # noqa: E402


class TestStaticAssets:
    """Smoke tests for static file serving."""

    def test_css_file_returns_200(self) -> None:
        """app.css should be served with 200 OK."""
        client = TestClient(app)
        r = client.get("/static/app.css")

        assert r.status_code == 200, "CSS file should be served successfully"
        assert "text/css" in r.headers.get("content-type", ""), \
            "CSS should have correct content-type"

    def test_image_files_return_200(self) -> None:
        """Image assets should be served with 200 OK."""
        client = TestClient(app)

        images = [
            "/static/img/grovisor-logo.png",
            "/static/img/grovisor-icon.png",
        ]

        for img_path in images:
            r = client.get(img_path)
            assert r.status_code == 200, f"{img_path} should be served successfully"
            assert "image/" in r.headers.get("content-type", ""), \
                f"{img_path} should have image content-type"

    def test_self_hosted_manrope_is_served(self) -> None:
        """Manrope is self-hosted because the CSP's font-src 'self' blocks Google Fonts."""
        client = TestClient(app)
        for font_path in (
            "/static/fonts/manrope-latin.woff2",
            "/static/fonts/manrope-latin-ext.woff2",
        ):
            r = client.get(font_path)
            assert r.status_code == 200, f"{font_path} should be served successfully"
            assert r.content[:4] == b"wOF2", f"{font_path} should be a WOFF2 file"

        css = client.get("/static/app.css").text
        assert "@font-face" in css and "/static/fonts/manrope-latin.woff2" in css
        assert "fonts.googleapis.com" not in css, "app.css must not import Google Fonts"

    def test_nonexistent_static_file_returns_404(self) -> None:
        """Requesting a non-existent static file should return 404."""
        client = TestClient(app)
        r = client.get("/static/nonexistent.js")

        assert r.status_code == 404, "Non-existent file should return 404"

    # NOTE: When JS files are added to static/js/ after CSP migration,
    # add tests here to verify they return 200 with application/javascript content-type
