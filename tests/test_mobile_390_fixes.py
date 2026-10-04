"""Phone-width (390px) fixes: the ownership diagram scrolls inside its panel,
and the cookie notice no longer covers the last control on the sign-in page.

These are layout rules, so the tests pin the markup and CSS that carry them;
the pixel behaviour was checked in a browser at 390px.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "amlkit" / "web"
CSS = (ROOT / "static" / "app.css").read_text()
JS = (ROOT / "static" / "js" / "app.js").read_text()
BASE = (ROOT / "templates" / "base.html").read_text()
CUSTOMER = (ROOT / "templates" / "customer.html").read_text()


def test_ownership_diagram_scrolls_inside_its_panel():
    assert re.search(r"\.ubo-diagram-container \{[^}]*overflow-x: auto", CSS)
    # keyboard users can scroll it, and it is announced as a region
    panel = CUSTOMER.split("ubo-diagram-container", 1)[1].split(">", 1)[0]
    assert 'tabindex="0"' in panel and 'role="region"' in panel and "aria-label=" in panel


def test_cookie_notice_has_a_short_form_for_phones():
    notice = BASE.split('id="cookie-notice"', 1)[1].split("</div>", 1)[0]
    assert 'class="cookie-full"' in notice and 'class="cookie-short"' in notice
    short = notice.split('class="cookie-short">', 1)[1].split("</span>", 1)[0].lower()
    assert "no advertising" in short and "tracking" in short
    assert re.search(r"\.cookie-short \{ display: none; \}", CSS)
    phone = CSS.split("@media (max-width: 680px) {\n  .cookie-notice", 1)[1].split("\n}\n", 1)[0]
    assert ".cookie-full { display: none; }" in phone and ".cookie-short { display: inline; }" in phone


def test_cookie_notice_only_clears_the_tab_bar_when_there_is_one():
    phone = CSS.split("@media (max-width: 680px) {\n  .cookie-notice", 1)[1].split("\n}\n", 1)[0]
    # signed-out pages (sign-in) have no tab bar, so no 62px offset there
    assert re.search(r"\.cookie-notice \{ bottom: 12px;", "  .cookie-notice" + phone)
    assert "body:has(.mobile-tabbar) .cookie-notice" in phone


def test_cookie_notice_reserves_and_releases_page_space():
    assert "html.cookie-open body" in CSS and "--cookie-notice-h" in CSS
    assert "reserveCookieNoticeSpace" in JS
    dismiss = JS.split("function dismissCookieNotice()", 1)[1].split("}\n", 1)[0]
    assert "classList.remove('cookie-open')" in dismiss
