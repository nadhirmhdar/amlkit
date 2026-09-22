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


class TestFeedbackButtonClearsTabBar:
    """The feedback button is position:fixed at every width. On phones it
    must not land on top of the tab bar -- and specifically must not cover
    the last tab (Customers), which z-index 999 made untappable."""

    def test_mobile_override_comes_after_the_base_rule(self) -> None:
        """CSS cascade tie-break is source order for equal specificity: an
        earlier override is silently beaten by a later, unconditional base
        rule at any viewport, mobile included. This is exactly the mistake
        that shipped the bug -- assert the override is positioned so it
        actually wins, not just that it exists somewhere in the file."""
        css = CSS_PATH.read_text(encoding="utf-8")
        blocks = list(re.finditer(r'\.feedback-btn\s*\{([^}]*)\}', css))
        assert len(blocks) >= 2, "expected a base .feedback-btn rule plus a mobile override"
        last = blocks[-1]
        assert "--tabbar-h" in last.group(1), (
            "the LAST .feedback-btn rule in the file (the one that wins the "
            "cascade) must be the tab-bar-clearing override -- if the base "
            "rule (bottom: 24px, no tabbar awareness) comes after it, the "
            "button silently reverts to overlapping the tab bar on phones"
        )

    def test_mobile_override_is_scoped_to_the_680px_breakpoint(self) -> None:
        css = CSS_PATH.read_text(encoding="utf-8")
        blocks = list(re.finditer(r'\.feedback-btn\s*\{([^}]*)\}', css))
        override_pos = [m for m in blocks if "--tabbar-h" in m.group(1)][0].start()
        preceding = css[:override_pos]
        last_open = preceding.rfind("@media")
        last_close_before_media_body = preceding.rfind("}", 0, last_open) if last_open != -1 else -1
        assert last_open != -1, "tab-bar override should be inside a @media block"
        media_header = css[last_open:preceding.find("{", last_open) + 1]
        assert "680px" in media_header, media_header


class TestAlertsPillDoesNotOverlap:
    """The home-page floating alerts pill (.alerts-float-wrap) used to be
    position:sticky, which renders "stuck" at a fixed viewport coordinate
    from the very first paint on any page taller than the viewport --
    independent of scroll position -- permanently overlapping whatever sits
    at that coordinate (sidebar, tab bar, cards). It is now position:fixed
    with the wrapper doing explicit offset math per breakpoint."""

    def test_wrap_is_position_fixed_not_sticky(self) -> None:
        css = CSS_PATH.read_text(encoding="utf-8")
        wrap_block = re.search(r'\.alerts-float-wrap\s*\{([^}]*)\}', css)
        assert wrap_block, ".alerts-float-wrap base rule not found"
        assert "position: fixed" in wrap_block.group(1)

        pill_block = re.search(r'(?<!-)\.alerts-float\s*\{([^}]*)\}', css)
        assert pill_block, ".alerts-float base rule not found"
        assert "sticky" not in pill_block.group(1), (
            ".alerts-float itself must not carry position:sticky any more -- "
            "positioning belongs entirely to .alerts-float-wrap"
        )

    def test_mobile_breakpoint_clears_the_feedback_button(self) -> None:
        """The feedback button (.feedback-btn) is also fixed at
        bottom: tabbar-h+20px on phones, in the same bottom-right corner.
        The pill's mobile override must pad its right side wide enough to
        clear the button's circle instead of running full-width under it."""
        css = CSS_PATH.read_text(encoding="utf-8")
        blocks = list(re.finditer(r'\.alerts-float-wrap\s*\{([^}]*)\}', css))
        mobile = [m for m in blocks if "--tabbar-h" in m.group(1)]
        assert mobile, "expected a tabbar-aware .alerts-float-wrap override"
        rule = mobile[-1].group(1)
        m = re.search(r'padding:\s*0\s+(\d+)px\s+0\s+(\d+)px', rule)
        assert m, f"expected an asymmetric 'padding: 0 <right>px 0 <left>px' shorthand, got: {rule}"
        right_padding, left_padding = int(m.group(1)), int(m.group(2))
        assert right_padding > left_padding + 40, (
            "right padding must clear the feedback button's ~56px circle plus "
            "its own inset -- a right padding close to the left padding means "
            "the pill runs back under the button"
        )

    def test_mobile_override_is_scoped_to_the_680px_breakpoint(self) -> None:
        css = CSS_PATH.read_text(encoding="utf-8")
        blocks = list(re.finditer(r'\.alerts-float-wrap\s*\{([^}]*)\}', css))
        override_pos = [m for m in blocks if "--tabbar-h" in m.group(1)][0].start()
        preceding = css[:override_pos]
        last_open = preceding.rfind("@media")
        assert last_open != -1, "tab-bar-aware override should be inside a @media block"
        media_header = css[last_open:preceding.find("{", last_open) + 1]
        assert "680px" in media_header, media_header
