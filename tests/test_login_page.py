"""Sign-in page: honest copy and accessible structure."""
from __future__ import annotations

import re

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "t.db"))
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    return TestClient(app)


def test_page_makes_no_single_sign_on_claim(client):
    # The app has email + password (+ MFA) only; there is no SSO to promise.
    html = client.get("/login").text.lower()
    assert "single sign-on" not in html and "sso" not in re.findall(r"\b\w+\b", html)


def test_sign_in_is_the_page_heading_and_the_slogan_is_not(client):
    html = client.get("/login").text
    assert len(re.findall(r"<h1[ >]", html)) == 1
    assert re.search(r"<h1[^>]*>Sign in</h1>", html)
    assert "Compliance," in html and "One decision" not in html


def test_decorative_strands_are_hidden_from_assistive_tech_and_sources_are_stated(client):
    html = client.get("/login").text
    assert re.search(r'<svg[^>]*id="si-strands"[^>]*aria-hidden="true"', html)
    assert "Screens against the UN, OFAC, EU, UK, UAE, FATF, PEP and adverse media" in html


def test_password_toggle_is_a_labelled_pressed_state_button(client):
    html = client.get("/login").text
    assert 'aria-pressed="false"' in html and 'aria-controls="password-input"' in html
    assert "\U0001F441" not in html  # no emoji glyph standing in for an icon


def test_error_message_renders_inside_the_sign_in_layout_not_the_light_banner(client):
    html = client.get("/login?err=Email+or+password+is+incorrect.").text
    assert re.search(r'role="alert">Email or password is incorrect\.</div>', html)
    assert 'class="banner err"' not in html
