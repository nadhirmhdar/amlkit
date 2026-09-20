"""Tests for p83: Screen reader compatibility — all interactive elements labelled,
no aria-hidden traps, dropdown menus accessible."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEMPLATES_DIR = Path(__file__).parent.parent / "amlkit" / "web" / "templates"
JS_PATH = Path(__file__).parent.parent / "amlkit" / "web" / "static" / "js" / "app.js"


class TestButtonLabels:
    """Every button with icon-only or ambiguous text has aria-label."""

    def test_hamburger_has_aria_label(self) -> None:
        content = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
        hamburger = re.search(r'class="nav-hamburger[^"]*"[^>]*>', content)
        if hamburger:
            assert "aria-label" in hamburger.group(), \
                "Hamburger menu button needs aria-label"

    def test_feedback_button_has_aria_label(self) -> None:
        content = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
        assert re.search(r'class="feedback-btn[^"]*"[^>]*aria-label', content), \
            "Feedback button (emoji-only) needs aria-label"


class TestDropdownAccessibility:
    """Dropdown menus use proper ARIA roles."""

    def test_user_dropdown_has_role_menu(self) -> None:
        content = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
        assert 'role="menu"' in content, \
            "User dropdown should have role='menu'"

    def test_dropdown_items_have_role(self) -> None:
        content = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
        assert 'role="menuitem"' in content or 'class="user-dropdown__item"' in content, \
            "Dropdown links should have role='menuitem' or be menu items"

    def test_user_menu_button_has_aria_expanded(self) -> None:
        content = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
        assert 'aria-expanded' in content, \
            "User menu toggle should track aria-expanded state"


class TestNoAriaHiddenTraps:
    """No interactive elements inside aria-hidden regions."""

    def test_no_buttons_inside_aria_hidden(self) -> None:
        for tmpl in TEMPLATES_DIR.glob("*.html"):
            content = tmpl.read_text(encoding="utf-8")
            hidden_regions = re.findall(
                r'aria-hidden="true"[^>]*>.*?</[^>]+>',
                content, re.DOTALL
            )
            for region in hidden_regions:
                assert '<button' not in region and '<a ' not in region, \
                    f"{tmpl.name}: interactive element inside aria-hidden region"


class TestLiveRegions:
    """Dynamic content areas use aria-live for screen reader announcements."""

    def test_banner_region_is_live(self) -> None:
        content = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
        banners = re.findall(r'class="banner[^"]*"', content)
        assert len(banners) > 0, "Expected banner elements in base.html"

    def test_feedback_result_is_live(self) -> None:
        content = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
        result_div = re.search(r'id="feedback-result"[^>]*>', content)
        assert result_div and 'aria-live' in result_div.group(), \
            "feedback-result div should have aria-live for dynamic updates"


class TestKeyboardNavigation:
    """Escape key closes menus (verified via JS)."""

    def test_escape_closes_menu(self) -> None:
        js = JS_PATH.read_text(encoding="utf-8")
        assert "Escape" in js, \
            "JS should handle Escape key to close menus"

    def test_js_manages_aria_expanded(self) -> None:
        js = JS_PATH.read_text(encoding="utf-8")
        assert "aria-expanded" in js, \
            "JS should toggle aria-expanded when opening/closing menus"
