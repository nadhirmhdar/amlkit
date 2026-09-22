"""Grovisor Minimal layout: no desktop header strip, avatar menu in the
canvas, Reports in the sidebar and as the third Home card."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conftest import register_org  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "test.db"))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    register_org(c, "Acme Corp", "Alice Mlro", "alice@acme.ae")
    return c


def _sidebar(html: str) -> str:
    m = re.search(r'<nav aria-label="Main navigation">(.*?)</nav>', html, re.S)
    assert m, "sidebar nav missing"
    return m.group(1)


def _canvas_menu(html: str) -> str:
    """The avatar menu: first element of <main>, up to its logout form."""
    main = html.split('<main id="main-content">', 1)[1]
    assert main.index('class="canvas-corner no-print"') < 400, "canvas corner is not the first element in <main>"
    return main[: main.index("</form>") + len("</form>")]


def test_no_desktop_header_strip(client):
    html = client.get("/").text
    assert "desktop-topnav" not in html


def test_avatar_menu_is_inside_main(client):
    menu = _canvas_menu(client.get("/").text)
    assert 'id="desktop-user-menu-wrap"' in menu
    assert 'aria-label="User menu"' in menu and 'aria-expanded="false"' in menu
    assert 'role="menu"' in menu
    for href in ("/audit", "/policies", "/admin", "/freeze-obligations", "/about"):
        assert f'href="{href}"' in menu, href
    assert 'action="/logout"' in menu
    # Reports moved to the sidebar, so the desktop menu no longer repeats it.
    assert 'href="/reports"' not in menu


def test_sidebar_has_reports_and_highlights_it(client):
    home = _sidebar(client.get("/").text)
    assert re.search(r'<a href="/reports"\s+class="">Reports</a>', home)

    reports = _sidebar(client.get("/reports").text)
    assert re.search(r'<a href="/reports"\s+class="on">Reports</a>', reports)


def test_home_third_card_is_reports(client):
    html = client.get("/").text
    cards = re.search(r'<div class="action-cards">(.*?)\n</div>', html, re.S).group(1)
    hrefs = re.findall(r'<a class="action-card" href="([^"]+)"', cards)
    assert hrefs == ["/screen", "/customers/new", "/reports"]
    assert "Reports &amp; Filings" in cards


def test_single_operator_chip_sits_in_the_canvas_corner(tmp_path, monkeypatch):
    """#255 put the chip in the header strip; with the strip gone it lives in
    the canvas corner beside the avatar, and only when the mode is on."""
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "solo.db"))
    monkeypatch.setenv("AMLKIT_SINGLE_OPERATOR_MODE", "1")
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    register_org(c, "Solo LLC", "Sam Solo", "sam@solo.ae")
    corner = _canvas_menu(c.get("/").text)
    assert "Single-operator mode" in corner


def test_no_chip_when_four_eyes_is_on(client):
    assert "mode-chip" not in _canvas_menu(client.get("/").text)


def test_sidebar_is_the_five_core_links(client):
    """Audit and Policies live in the avatar menus, not the sidebar."""
    nav = _sidebar(client.get("/").text)
    assert re.findall(r'<a href="([^"]+)"', nav) == ["/", "/dashboard", "/screen", "/customers", "/reports"]


def test_audit_and_policies_are_in_both_avatar_menus(client):
    html = client.get("/").text
    desktop = _canvas_menu(html)
    phone = html.split('id="user-menu-wrap"', 1)[1].split("</form>", 1)[0]
    for menu in (desktop, phone):
        assert 'href="/audit"' in menu
        assert 'href="/policies"' in menu


def test_home_cards_have_no_arrows(client):
    html = client.get("/").text
    cards = re.search(r'<div class="action-cards">(.*?)\n</div>', html, re.S).group(1)
    assert "action-card__arrow" not in cards
    assert "&rarr;" not in cards


def test_home_has_no_date_line(client):
    import datetime as _dt
    html = client.get("/").text
    head = html.split('<div class="home-head', 1)[1].split("</div>", 1)[0]
    assert "eyebrow" not in head
    assert _dt.date.today().strftime("%B") not in head


def test_greeting_is_left_to_the_browser_clock(client):
    html = client.get("/").text
    # Neutral server fallback; app.js swaps in the time-of-day greeting.
    assert "<h1><span data-greeting>Hello</span>," in html
    for server_greeting in ("Good morning", "Good afternoon", "Good evening"):
        assert server_greeting not in html
    js = client.get("/static/js/app.js").text
    assert "function greetingForHour" in js and "applyLocalGreeting()" in js
