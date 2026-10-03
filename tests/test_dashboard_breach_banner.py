"""Dashboard 24-hour-rule breach banner tests.

The banner previously told the operator to run `scripts/refresh.py`. That
script only touches the machine it runs on -- on the hosted Cloud Run
deployment that is a different database than the one this page reads, so
following the instruction looks like a fix and does nothing. The banner
must point to the actual in-app remedy instead (Admin -> "Refresh sanctions
lists now"), which updates this deployment's real data on every deployment
model (local or hosted) alike.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name: str, name: str, email: str, password: str = "a-strong-password-1",
              invite_code: str = "test-invite"):
    """Registers, then completes email verification via the dev-fallback
    link the response renders (no SMTP configured in tests -- see
    amlkit/mail.py), so callers still get back a signed-in client."""
    import re

    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client), "invite_code": invite_code,
    }, follow_redirects=True)
    assert "Check your email" in r.text, f"registration failed: {r.text[:300]}"
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m, f"no dev verification link in registration response: {r.text[:500]}"
    r2 = client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    from conftest import settle_mfa  # p15: MLRO sessions start locked
    settle_mfa(client)
    assert any(s in r2.text for s in ("Dashboard", "24-hour", "Two-Factor")), f"verification failed: {r2.text[:300]}"
    return client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import os

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from amlkit.db import connect, upsert_dataset

    c = TestClient(app)
    _register(c, "Test Firm", "alice", "alice@testfirm.ae")

    conn = connect(os.environ["AMLKIT_DB"])
    upsert_dataset(conn, "un_sc_sanctions", "UN Consolidated Sanctions List",
                    is_mandatory=True)
    conn.execute("UPDATE datasets SET last_refresh = '2020-01-01T00:00:00+00:00' "
                 "WHERE key = 'un_sc_sanctions'")
    conn.commit()
    conn.close()
    return c


class TestBreachBanner:
    def test_banner_points_to_admin_refresh_not_local_script(self, client) -> None:
        # The dashboard (where this banner lives) moved from "/" to
        # "/dashboard" in a later PR -- "/" is now the home/orientation
        # screen (see test_api.py::TestHomePage).
        r = client.get("/dashboard")
        assert r.status_code == 200
        assert "24-HOUR RULE BREACHED" in r.text
        assert "scripts/refresh.py" not in r.text
        assert "/admin" in r.text
        assert "Refresh sanctions lists now" in r.text

    def test_banner_message_is_one_block(self, client) -> None:
        """The banner is a flex row; its sentence and link must sit in a single
        child, or each fragment becomes its own column."""
        import re

        html = client.get("/dashboard").text
        m = re.search(r'<div class="banner err" role="alert">(.*?)\n  </div>\n', html, re.S)
        assert m, "breach banner missing"
        body = m.group(1)
        assert body.lstrip().startswith('<div class="banner__text">')
        assert body.rstrip().endswith("</div>")
        # strong, sentence and link all inside that one block
        inner = body.split('<div class="banner__text">', 1)[1].rsplit("</div>", 1)[0]
        assert "24-HOUR RULE BREACHED" in inner and 'href="/admin"' in inner


class TestDashboardCss:
    CSS = (Path(__file__).resolve().parent.parent / "amlkit" / "web" / "static" / "app.css").read_text()

    def test_phone_stat_strip_override_comes_after_base_rules(self) -> None:
        """An equal-specificity mobile rule placed before the base rule loses to it
        (the strip stayed four cramped columns on phones)."""
        base = self.CSS.index(".stat-strip { display: grid; grid-template-columns: repeat(4")
        mobile = self.CSS.rindex(".stat-strip { grid-template-columns: 1fr 1fr")
        assert mobile > base
        assert self.CSS.rindex(".stat-strip__item + .stat-strip__item { padding: 0; border-left: 0; }") > mobile

    def test_banner_clears_the_corner_chips(self) -> None:
        """Chip + bell + avatar measure about 287px; the banner must reserve at least that."""
        import re

        m = re.search(r"\.canvas-corner:has\(\.mode-chip\) \+ \.banner \{ margin-right: (\d+)px", self.CSS)
        assert m and int(m.group(1)) >= 290

    def test_phone_dashboard_rows_stack(self) -> None:
        assert ".cat-line__body .list-row { flex-wrap: wrap;" in self.CSS
        assert ".cat-line__body .list-row .side.nowrap { white-space: normal;" in self.CSS

    def test_banner_clears_the_corner_without_the_chip(self) -> None:
        """Bell + avatar alone measure about 106px (this is the normal case: the
        single-operator chip only shows in that mode)."""
        import re

        m = re.search(r"\.canvas-corner \+ \.banner \{ margin-right: (\d+)px", self.CSS)
        assert m and int(m.group(1)) >= 112
