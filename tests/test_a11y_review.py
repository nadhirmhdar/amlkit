"""Accessibility fixes from the 2026-09-21 deployed-site UX review, section 1.

Covers what is checkable server-side: rendered markup and the shipped
CSS/JS. Keyboard behaviour (combobox arrows, dialog Escape, drawer focus)
was verified in a real browser; these tests pin the hooks it depends on.

  #3  nationality combobox  -- ARIA combobox pattern in countries.js, labels bound
  #7  tablet drawer         -- real <button aria-expanded aria-controls>, closed
                               drawer visibility:hidden
  #8  feedback/disclaimer   -- native <dialog>, labelled, real Close button
  #11 phone text sizes      -- 16px body + inputs, 12px tab labels/tags
  #12 login focus ring      -- .input-underline focus-visible, no !important
  #19 reduced motion        -- prefers-reduced-motion + color-scheme meta
  #26 skip link             -- #main-content tabindex=-1
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_api import client  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent / "amlkit" / "web"
CSS = (ROOT / "static" / "app.css").read_text(encoding="utf-8")
COUNTRIES_JS = (ROOT / "static" / "js" / "countries.js").read_text(encoding="utf-8")
APP_JS = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
LOGIN = (ROOT / "templates" / "login.html").read_text(encoding="utf-8")


def _media_blocks(css: str, query: str) -> str:
    """Concatenate the bodies of every @media block whose query contains ``query``."""
    out = []
    for m in re.finditer(r"@media\s*([^{]+)\{", css):
        if query not in m.group(1):
            continue
        depth, i = 1, m.end()
        while depth and i < len(css):
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        out.append(css[m.end():i - 1])
    return "\n".join(out)


# ---------------------------------------------------------------- #26, #19
def test_main_is_focusable_skip_link_target(client) -> None:
    html = client.get("/").text
    assert 'href="#main-content"' in html
    assert re.search(r'<main id="main-content"[^>]*tabindex="-1"', html)


def test_color_scheme_meta_on_app_and_public_pages(client) -> None:
    assert '<meta name="color-scheme" content="light">' in client.get("/").text
    assert '<meta name="color-scheme" content="light">' in client.get("/about").text


def test_reduced_motion_disables_animation_and_transition() -> None:
    block = _media_blocks(CSS, "prefers-reduced-motion: reduce")
    assert re.search(r"\*\s*,\s*\*::before\s*,\s*\*::after", block)
    assert "animation-duration" in block and "transition-duration" in block


# ------------------------------------------------------------------- #8
def test_feedback_modal_is_native_dialog(client) -> None:
    html = client.get("/").text
    m = re.search(r'<dialog id="feedback-modal"[^>]*>', html)
    assert m, "feedback modal must be a native <dialog>"
    assert 'aria-labelledby="feedback-modal-title"' in m.group(0)
    assert 'id="feedback-modal-title"' in html
    assert re.search(r'<button type="button" class="feedback-modal-close"[^>]*aria-label="Close"', html)
    assert '<label class="feedback-label" for="feedback-message">' in html
    # Opened modally so focus is trapped and Escape closes it natively.
    assert "showModal()" in APP_JS
    assert "addEventListener('close', onFeedbackClosed)" in APP_JS


def test_disclaimer_modal_is_labelled_dialog(client) -> None:
    # A freshly registered operator has not acknowledged the disclaimer yet.
    html = client.get("/").text
    m = re.search(r'<dialog id="disclaimer-modal"[^>]*>', html)
    assert m, "disclaimer modal must be a native <dialog>"
    assert 'aria-labelledby="disclaimer-modal-title"' in m.group(0)
    assert 'id="disclaimer-modal-title"' in html
    # Re-opened modally by app.js; Escape must not skip the acknowledgement.
    assert "showDialogModal(disclaimer)" in APP_JS
    assert "disclaimer.addEventListener('cancel'" in APP_JS


# ------------------------------------------------------------------- #7
def test_tablet_drawer_toggle_is_a_button(client) -> None:
    html = client.get("/").text
    assert 'id="nav-toggle"' not in html
    m = re.search(r'<button[^>]*class="nav-hamburger[^"]*"[^>]*>', html)
    assert m, "drawer toggle must be a <button>"
    assert 'aria-expanded="false"' in m.group(0)
    assert 'aria-controls="sidebar"' in m.group(0)
    assert re.search(r'<aside class="sidebar[^"]*" id="sidebar"', html)
    assert 'data-action="close-nav"' in html  # scrim


def test_closed_tablet_drawer_is_out_of_tab_order() -> None:
    block = _media_blocks(CSS, "max-width: 960px")
    sidebar = re.search(r"\n\s*\.sidebar\s*\{([^}]*)\}", block)
    assert sidebar and "visibility: hidden" in sidebar.group(1)
    assert re.search(r"\.shell\.nav-open \.sidebar\s*\{[^}]*visibility: visible", block)
    assert re.search(r"\.nav-hamburger\s*\{[^}]*width: 44px; height: 44px", block)


# ------------------------------------------------------------------ #12
def test_underline_inputs_have_visible_focus_ring() -> None:
    rule = re.search(r"\.input-underline:focus-visible\s*\{([^}]*)\}", CSS)
    assert rule and "outline: 2px solid var(--accent)" in rule.group(1)
    bare = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    underline_rules = re.findall(r"[^{}]*\.input-underline[^{]*\{[^}]*\}", bare)
    assert underline_rules and not any("!important" in r for r in underline_rules)


def test_login_does_not_strip_focus_ring() -> None:
    assert re.search(r"\.si \.input-underline:focus-visible\s*\{\s*outline:\s*none", LOGIN) is None
    assert ".si .input-underline:focus-visible { outline:2px solid" in LOGIN
    assert not re.search(r"\.input-underline[^{]*\{[^}]*!important", LOGIN)
    m = re.search(r'<button[^>]*data-action="toggle-password"[^>]*>', LOGIN)
    assert m and 'aria-pressed="false"' in m.group(0)
    assert re.search(r"\.si-eye \{[^}]*width:44px; height:44px", LOGIN)


# ------------------------------------------------------------------ #11
def test_phone_text_sizes() -> None:
    phone = _media_blocks(CSS, "max-width: 680px")
    assert re.search(r"\bbody\s*\{\s*font-size:\s*16px", phone)
    assert re.search(r'select, textarea\s*\{\s*font-size:\s*16px', phone)
    assert re.search(r"\.mobile-tab__label\s*\{\s*font-size:\s*12px", phone)
    assert re.search(r"\.tag\s*\{\s*font-size:\s*12px", phone)
    assert re.search(r"\blabel\s*\{\s*font-size:\s*13px", phone)


# ------------------------------------------------------------------- #3
def test_country_combobox_aria_pattern() -> None:
    js = COUNTRIES_JS
    for needle in (
        "setAttribute('role', 'combobox')",
        "setAttribute('aria-expanded'",
        "setAttribute('aria-controls', uid + '-list')",
        "setAttribute('aria-activedescendant'",
        "setAttribute('role', 'listbox')",
        "setAttribute('role', 'option')",
        "option.id = uid + '-opt-' + i",
        "'ArrowDown'", "'ArrowUp'", "'Enter'", "'Escape'",
        "Choose a country from the list",
    ):
        assert needle in js, needle
    # Per-instance ids: no fixed listbox id shared by every dropdown.
    assert "dropdown.id = 'country-dropdown-list'" not in js
    # The original input's id moves to the visible combobox so <label for> binds.
    assert "display.id = input.id" in js


def test_country_fields_have_bound_labels(client) -> None:
    for path, ident in (("/customers/new", "cust-nationality"), ("/screen", "screen-country")):
        html = client.get(path).text
        assert f'<label for="{ident}"' in html, path
        assert re.search(rf'<input[^>]*id="{ident}"[^>]*data-country-dropdown', html), path


def test_type_scale_is_five_steps_and_buttons_have_three_sizes():
    """Body-size text uses 11/12/13/14/16px only (the old half-pixel steps are
    gone), and standard buttons are 32 (small) / 40 (default) / 48 (large)."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "amlkit" / "web"
    css = (root / "static" / "app.css").read_text()
    templates = "".join(p.read_text() for p in (root / "templates").rglob("*.html"))
    for text in (css, templates):
        sizes = {float(m) for m in re.findall(r"font-size:\s*(\d+(?:\.\d+)?)px", text)}
        small_range = {z for z in sizes if 11 <= z <= 16}
        assert small_range <= {11, 12, 13, 14, 16}, sorted(small_range)
    assert "button:not([class]), button.ghost, button.secondary, button.danger, .btn { min-height: 40px; }" in css
    assert "button.small, .btn.small, .btn.btn-sm { min-height: 32px; }" in css
    assert re.search(r"\.btn-glow \{[^}]*min-height: 48px", css)
