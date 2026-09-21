"""Test that templates contain no inline scripts or event handlers (Issue #82).

CSP 'unsafe-inline' removal requires all JavaScript to be in external files.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestCSPNoInlineScripts:
    """Verify all templates are clean of inline scripts and event handlers."""

    def test_no_inline_script_blocks(self) -> None:
        """All <script> tags must have a src= attribute (no inline blocks)."""
        templates_dir = Path(__file__).parent.parent / "amlkit" / "web" / "templates"
        violations = []

        for template in templates_dir.glob("**/*.html"):
            content = template.read_text(encoding="utf-8")
            # Match <script> tags without src attribute
            inline_scripts = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>', content)
            if inline_scripts:
                violations.append(f"{template.name}: {len(inline_scripts)} inline script(s)")

        assert not violations, (
            f"Found inline <script> blocks (CSP violation):\n" +
            "\n".join(f"  - {v}" for v in violations) +
            "\n\nAll scripts must be in external .js files with <script src=...>"
        )

    def test_no_inline_event_handlers(self) -> None:
        """All event handlers must use addEventListener (no on*= attributes)."""
        templates_dir = Path(__file__).parent.parent / "amlkit" / "web" / "templates"
        violations = []

        # Pattern matches onclick=, onsubmit=, etc. but excludes data attributes
        event_handler_pattern = re.compile(r'\s(on[a-z]+)=', re.IGNORECASE)

        for template in templates_dir.glob("**/*.html"):
            content = template.read_text(encoding="utf-8")
            handlers = event_handler_pattern.findall(content)
            if handlers:
                unique = set(handlers)
                violations.append(f"{template.name}: {unique}")

        assert not violations, (
            f"Found inline event handlers (CSP violation):\n" +
            "\n".join(f"  - {v}" for v in violations) +
            "\n\nUse addEventListener in external JS files instead of on*= attributes"
        )

    def test_static_js_files_exist_and_accessible(self) -> None:
        """Verify that external JS files exist for migrated scripts."""
        static_js = Path(__file__).parent.parent / "amlkit" / "web" / "static" / "js"

        # These JS files should exist after migration
        expected_files = [
            "app.js",  # Base template: forms, theme, modals
        ]

        missing = []
        for filename in expected_files:
            filepath = static_js / filename
            if not filepath.exists():
                missing.append(filename)

        assert not missing, (
            f"Missing static JS files:\n" +
            "\n".join(f"  - {f}" for f in missing) +
            f"\n\nExpected location: {static_js}"
        )

    def test_csp_header_disallows_unsafe_inline(self) -> None:
        """Verify CSP header has script-src 'self' without 'unsafe-inline'."""
        # Import here to avoid loading app before tests run
        from amlkit.api.app import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/login")
        csp = response.headers.get("Content-Security-Policy", "")

        # Verify 'unsafe-inline' is removed from script-src
        assert "'unsafe-inline'" not in csp or "script-src 'self'" in csp, \
            "CSP script-src must not contain 'unsafe-inline' after migration"

        # Verify script-src only allows 'self'
        assert "script-src 'self'" in csp, "CSP must allow only 'self' scripts"

        # Verify no inline scripts would be allowed
        assert "script-src 'self' 'unsafe-inline'" not in csp, \
            "CSP must not contain both 'self' and 'unsafe-inline' for script-src"
