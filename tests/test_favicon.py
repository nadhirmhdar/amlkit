"""Review finding 17: /favicon.ico must not 404."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from amlkit.api.app import app  # noqa: E402


def test_favicon_ico_is_served_without_signing_in() -> None:
    client = TestClient(app)
    r = client.get("/favicon.ico", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "/static/img/favicon.ico"
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert r.headers["content-type"] in ("image/x-icon", "image/vnd.microsoft.icon")
    assert r.content[:4] == b"\x00\x00\x01\x00"  # ICO header
    assert "no-store" not in r.headers.get("cache-control", "")


def test_pages_link_both_icons() -> None:
    html = TestClient(app).get("/login").text
    assert 'href="/static/img/favicon.ico"' in html
    assert 'href="/static/img/favicon.svg"' in html
