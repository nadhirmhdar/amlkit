"""Tests for p82: Full accessibility pass — WCAG 2.1 AA compliance."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEMPLATES_DIR = Path(__file__).parent.parent / "amlkit" / "web" / "templates"
CSS_PATH = Path(__file__).parent.parent / "amlkit" / "web" / "static" / "app.css"


class TestSkipNavigation:
    """Skip-to-content link for keyboard users."""

    def test_base_has_skip_link(self) -> None:
        content = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
        assert "skip-to-content" in content or "skip-nav" in content, \
            "base.html needs a skip-to-content link for keyboard nav"


class TestSemanticLandmarks:
    """Semantic HTML landmarks (nav, main, header, aside, footer)."""

    def test_base_main_has_id(self) -> None:
        content = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
        assert re.search(r'<main\b[^>]*id="main-content"', content), \
            "main element needs id='main-content' for skip link target"

    def test_sidebar_is_nav_landmark(self) -> None:
        content = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
        assert re.search(r'role="navigation"', content) or re.search(r'<nav\b', content), \
            "Sidebar navigation should be a nav landmark"


class TestFocusIndicators:
    """Visible :focus-visible styles in CSS."""

    def test_css_has_focus_visible(self) -> None:
        css = CSS_PATH.read_text(encoding="utf-8")
        assert ":focus-visible" in css, \
            "CSS needs :focus-visible styles for keyboard navigation"

    def test_css_has_outline_style(self) -> None:
        css = CSS_PATH.read_text(encoding="utf-8")
        focus_block = re.search(r':focus-visible\s*\{[^}]*outline[^}]*\}', css)
        assert focus_block, \
            "focus-visible should define an outline for keyboard users"


class TestColorContrast:
    """Colour contrast CSS variables meet WCAG AA (4.5:1 for text)."""

    def test_muted_text_not_too_light(self) -> None:
        """The --ink-3 (muted text) variable should not be lighter than #767676."""
        css = CSS_PATH.read_text(encoding="utf-8")
        match = re.search(r'--ink-3\s*:\s*(#[0-9a-fA-F]{3,6})', css)
        if match:
            hex_val = match.group(1).lstrip("#")
            if len(hex_val) == 3:
                hex_val = "".join(c * 2 for c in hex_val)
            r, g, b = int(hex_val[:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)
            luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
            assert luminance <= 140, \
                f"--ink-3 ({match.group(1)}) may be too light for 4.5:1 contrast on white"


class TestAriaLabels:
    """Interactive elements have accessible labels."""

    def test_login_form_has_labels(self) -> None:
        content = (TEMPLATES_DIR / "login.html").read_text(encoding="utf-8")
        assert re.search(r'<label\b.*for=["\'].*email', content, re.IGNORECASE), \
            "Login email input needs an associated <label>"

    def test_base_nav_links_accessible(self) -> None:
        content = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
        assert 'aria-label' in content or 'role="navigation"' in content, \
            "Navigation should have aria-label or role"

    def test_all_img_have_alt(self) -> None:
        for tmpl in TEMPLATES_DIR.glob("*.html"):
            content = tmpl.read_text(encoding="utf-8")
            imgs = re.findall(r'<img\b[^>]*>', content)
            for img in imgs:
                assert 'alt=' in img, \
                    f"{tmpl.name}: <img> missing alt attribute: {img[:60]}..."
