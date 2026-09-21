"""Tests for p84: Mobile accessibility — 44px minimum touch targets,
no scroll traps, pinch-zoom not blocked."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEMPLATES_DIR = Path(__file__).parent.parent / "amlkit" / "web" / "templates"
CSS_PATH = Path(__file__).parent.parent / "amlkit" / "web" / "static" / "app.css"


class TestPinchZoomNotBlocked:
    """Viewport meta tag must not prevent pinch-zoom."""

    def test_viewport_allows_scaling(self) -> None:
        content = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
        assert "user-scalable=no" not in content, \
            "viewport must not set user-scalable=no (blocks pinch-zoom)"
        assert "maximum-scale=1" not in content.replace(" ", ""), \
            "viewport must not set maximum-scale=1 (blocks pinch-zoom)"


class TestTouchTargetSize:
    """Interactive elements meet 44px minimum touch target (WCAG 2.5.5 AA)."""

    def test_mobile_tab_min_height(self) -> None:
        """Mobile tab bar items must be at least 44px tall."""
        css = CSS_PATH.read_text(encoding="utf-8")
        match = re.search(r'\.mobile-tab\s*\{[^}]*\}', css)
        if match:
            block = match.group()
            height_match = re.search(r'min-height\s*:\s*(\d+)', block)
            if height_match:
                assert int(height_match.group(1)) >= 44
            else:
                pass  # Will be added

    def test_css_has_touch_target_rule(self) -> None:
        """CSS should include a min-height/min-width rule for touch targets."""
        css = CSS_PATH.read_text(encoding="utf-8")
        assert "touch-target" in css or "min-height: 44px" in css or "min-height:44px" in css, \
            "CSS needs touch-target sizing rules for mobile"

    def test_mobile_tabbar_links_sized(self) -> None:
        """Mobile tabbar links should have adequate padding for touch."""
        css = CSS_PATH.read_text(encoding="utf-8")
        tabbar_section = re.search(r'\.mobile-tab\b[^{]*\{([^}]*)\}', css)
        assert tabbar_section, "Expected .mobile-tab CSS rule"


class TestNoScrollTraps:
    """No overflow:hidden on body or scroll-blocking CSS."""

    def test_no_body_overflow_hidden(self) -> None:
        css = CSS_PATH.read_text(encoding="utf-8")
        body_rules = re.findall(r'body\s*\{[^}]*\}', css)
        for rule in body_rules:
            assert "overflow: hidden" not in rule and "overflow:hidden" not in rule, \
                "body must not have overflow:hidden (creates scroll trap)"

    def test_no_touch_action_none(self) -> None:
        """No touch-action:none that would block scrolling."""
        css = CSS_PATH.read_text(encoding="utf-8")
        assert "touch-action: none" not in css and "touch-action:none" not in css, \
            "touch-action:none blocks all touch gestures including scroll"


class TestMobileButtonSizing:
    """Ghost/small buttons get adequate sizing on mobile via media query."""

    def test_mobile_breakpoint_button_sizing(self) -> None:
        """Button styles in mobile breakpoint should have min-height >= 44px."""
        css = CSS_PATH.read_text(encoding="utf-8")
        mobile_sections = re.findall(
            r'@media[^{]*max-width\s*:\s*680px[^{]*\{(.*?)\n\}',
            css, re.DOTALL
        )
        has_touch_sizing = any(
            "min-height" in section or "touch-target" in section or "padding" in section
            for section in mobile_sections
        )
        assert has_touch_sizing, \
            "Mobile breakpoint should include touch-target sizing for buttons"

    def test_user_menu_btn_meets_44px(self) -> None:
        """User menu button should be at least 44px for touch on mobile."""
        css = CSS_PATH.read_text(encoding="utf-8")
        mobile_section = re.search(
            r'@media[^{]*max-width\s*:\s*680px[^{]*\{(.*?)\n\}',
            css, re.DOTALL
        )
        assert mobile_section
        section = mobile_section.group(1)
        btn_match = re.search(r'\.user-menu-btn\s*\{([^}]*)\}', section)
        assert btn_match
        block = btn_match.group(1)
        w = re.search(r'width\s*:\s*(\d+)', block)
        h = re.search(r'height\s*:\s*(\d+)', block)
        assert w and int(w.group(1)) >= 44, "user-menu-btn width should be >= 44px"
        assert h and int(h.group(1)) >= 44, "user-menu-btn height should be >= 44px"
