"""WP-12 web hygiene and copy: L-88/89/90/98/99, L-79, L-81, L-84, L-85, L-61/62, L-71, L-75, L-27."""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_api import (  # noqa: E402
    LISTED, _add_operator, _csrf, _db, _flash_parse, _login, _register, _seed_sanctions_data,
)

from amlkit import auth  # noqa: E402
from amlkit.web import blog  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "hygiene.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    monkeypatch.delenv("AMLKIT_PUBLIC_BASE_URL", raising=False)
    _seed_sanctions_data(db_file)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


@pytest.fixture()
def anon(client):
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    return TestClient(app)


def _make_match(client, ref="C-W1", name="Falcon Holdings FZE"):
    client.post("/customers", data={
        "reference": ref, "full_name": name, "customer_type": "legal",
        "ubo_names": [LISTED], "ubo_pcts": ["60"], "ubo_controls": ["ownership"],
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    conn = _db()
    cid = conn.execute("SELECT id FROM customers WHERE reference=?", (ref,)).fetchone()["id"]
    conn.close()
    return cid


def _flash_texts(resp) -> str:
    out = ""
    for part in re.findall(r"amlkit_flash=\"?([A-Za-z0-9+/=]+)", resp.headers.get("set-cookie", "")):
        out += _flash_parse(part).get("text", "")
    return out


# ------------------------------------------------------------ L-88 noindex
def test_signed_in_pages_are_noindex_and_customer_title_has_no_name(client):
    cid = _make_match(client)
    for path in ("/dashboard", "/alerts", "/customers", f"/customers/{cid}", "/notifications"):
        html = client.get(path).text
        assert '<meta name="robots" content="noindex, nofollow">' in html, path
    page = client.get(f"/customers/{cid}").text
    assert "<title>Customer case file — groAML</title>" in page
    assert "Falcon Holdings" not in re.search(r"<title>.*?</title>", page, re.S).group(0)


def test_anonymous_public_pages_stay_indexable(anon):
    for path in ("/about", "/privacy", "/blog", "/apply"):
        assert 'name="robots"' not in anon.get(path).text, path


def test_robots_txt_disallows_private_paths(anon):
    body = anon.get("/robots.txt").text
    for p in ("customers", "alerts", "admin", "audit", "reports", "compliance", "billing",
              "dashboard", "screen", "freeze", "policies", "notifications", "profile"):
        assert f"Disallow: /{p}\n" in body, p
    assert "Allow: /\n" in body and "Sitemap:" in body


# ------------------------------------------------- L-89 / L-90 canonical host
def test_canonical_host_defaults_to_production(anon):
    html = anon.get("/about").text
    assert '<link rel="canonical" href="https://groaml.grovisor.ae/about">' in html
    assert 'property="og:url" content="https://groaml.grovisor.ae/about"' in html


def test_canonical_host_comes_from_setting(anon, monkeypatch):
    monkeypatch.setenv("AMLKIT_PUBLIC_BASE_URL", "https://staging.example.test/")
    for path in ("/about", "/blog", f"/blog/{blog.all_posts()[0].slug}"):
        html = anon.get(path).text
        assert "groaml.grovisor.ae" not in html, path
        assert 'rel="canonical" href="https://staging.example.test/' in html, path
        assert 'property="og:image" content="https://staging.example.test/static/img/og-card.png"' in html
    assert "https://staging.example.test/sitemap.xml" in anon.get("/robots.txt").text
    assert "<loc>https://staging.example.test/about</loc>" in anon.get("/sitemap.xml").text


def test_blog_topic_and_search_views_canonicalise_to_blog_and_are_noindex(anon):
    topic = blog.TOPICS[0].slug
    for path in (f"/blog?topic={topic}", "/blog?q=sanctions"):
        html = anon.get(path).text
        assert '<link rel="canonical" href="https://groaml.grovisor.ae/blog">' in html, path
        assert 'name="robots" content="noindex, follow"' in html, path
        assert 'property="og:url" content="https://groaml.grovisor.ae/blog"' in html, path


# ------------------------------------------------------------- L-98 headers
def test_referrer_and_permissions_policy_headers(anon, client):
    for c in (anon, client):
        for path in ("/about", "/login", "/robots.txt"):
            r = c.get(path, follow_redirects=False)
            assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin", path
            assert r.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()", path


# -------------------------------------- L-99 CS-18 / CR-21 / CR-22 (blog, gzip)
def test_anonymous_public_pages_carry_no_csrf_token_in_body(anon):
    first_post = f"/blog/{blog.all_posts()[0].slug}"
    for path in ("/about", "/blog", first_post):
        r = anon.get(path, headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200, path
        assert r.headers.get("content-encoding") == "gzip", path  # really the compressed path
        assert "csrf_token" not in r.text, path
    # Not compressed, but must not embed a token for anonymous visitors either.
    assert "csrf_token" not in anon.get("/privacy").text
    root = anon.get("/", follow_redirects=False)
    assert root.status_code == 303 and "csrf_token" not in root.text


def test_uaepass_link_is_nofollow_when_enabled_and_absent_otherwise(anon, monkeypatch):
    monkeypatch.delenv("UAEPASS_CLIENT_ID", raising=False)
    monkeypatch.delenv("UAEPASS_CLIENT_SECRET", raising=False)
    assert "uaepass/start" not in anon.get("/login").text
    monkeypatch.setenv("UAEPASS_CLIENT_ID", "x")
    monkeypatch.setenv("UAEPASS_CLIENT_SECRET", "y")
    assert 'href="/auth/uaepass/start" class="si-alt" rel="nofollow"' in anon.get("/login").text


def test_twitter_card_is_large_image(anon):
    for path in ("/about", "/blog", f"/blog/{blog.all_posts()[0].slug}"):
        html = anon.get(path).text
        assert 'name="twitter:card" content="summary_large_image"' in html, path
        assert 'name="twitter:card" content="summary"' not in html, path


# ------------------------------------------------------------ L-79 password
@pytest.mark.parametrize("path,fields", [
    ("/account/password", {"current_password": "a-strong-password-1", "confirm_password": "Another-Strong-Pass-2"}),
    ("/profile/change-password", {"old_password": "a-strong-password-1"}),
])
def test_password_change_keeps_this_session_and_signs_out_others(client, path, fields):
    conn = _db()
    op = conn.execute("SELECT id, org_id FROM operators WHERE email='alice@testfirm.ae'").fetchone()
    other = auth.create_session(conn, op["id"], op["org_id"])
    assert auth.resolve_session(conn, other) is not None
    old_cookie = client.cookies.get("amlkit_session")
    r = client.post(path, data={**fields, "new_password": "Another-Strong-Pass-2",
                                "csrf_token": _csrf(client)}, follow_redirects=False)
    assert r.status_code == 303
    assert "All other sessions have been signed out" in _flash_texts(r)
    assert client.cookies.get("amlkit_session") != old_cookie  # re-minted
    assert client.get("/dashboard", follow_redirects=False).status_code == 200  # still signed in
    conn2 = _db()
    assert auth.resolve_session(conn2, other) is None  # the other session really is gone


# ------------------------------------------------------------ L-81 eviction
def test_fourth_session_gets_one_shot_eviction_notice(client, monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT_SESSIONS", "3")
    conn = _db()
    op = conn.execute("SELECT id, org_id FROM operators WHERE email='alice@testfirm.ae'").fetchone()
    # alice's fixture login already holds one session; add one more (3 alive), then the 4th evicts.
    auth.create_session(conn, op["id"], op["org_id"])
    third = auth.create_session(conn, op["id"], op["org_id"])
    assert conn.execute("SELECT notice FROM sessions WHERE token_hash=?",
                        (auth._token_hash(third),)).fetchone()["notice"] is None
    fourth = auth.create_session(conn, op["id"], op["org_id"])
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    c = TestClient(app)
    c.cookies.set("amlkit_session", fourth)
    first = c.get("/dashboard")
    assert "the oldest session was signed out" in first.text
    assert "the oldest session was signed out" not in c.get("/dashboard").text


# ------------------------------------------------------------ L-84 / L-75
def test_officer_audit_export_redirects_with_flash_like_audit(client):
    _add_operator(client, "bob", "bob-hyg@testfirm.ae", role="officer")
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    bob = TestClient(app)
    _login(bob, "bob-hyg@testfirm.ae", "a-strong-password-2")
    r = bob.get("/audit/export", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert _flash_texts(r)
    a = bob.get("/audit", follow_redirects=False)
    assert (a.status_code, a.headers["location"]) == (r.status_code, r.headers["location"])


def test_mfa_locked_mlro_opening_admin_goes_straight_to_challenge(client):
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    c2 = TestClient(app)
    c2.get("/login")
    c2.post("/login", data={"email": "alice@testfirm.ae", "password": "a-strong-password-1",
                            "csrf_token": _csrf(c2)}, follow_redirects=False)
    r = c2.get("/admin", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/mfa/verify"


# ------------------------------------------------------------------ L-85
def test_privacy_page_lists_all_five_cookies(anon):
    html = anon.get("/privacy").text
    assert "three cookies" not in html
    for name in ("amlkit_session", "amlkit_csrf", "amlkit_flash",
                 "amlkit_trusted_device", "amlkit_uaepass_state"):
        assert name in html, name
    assert "30 days" in html and "14 days" in html


# ----------------------------------------------------------- L-61 / L-62
def test_notification_link_lands_on_the_alert_not_the_customer_tab(client):
    _make_match(client)
    conn = _db()
    link = conn.execute("SELECT link FROM notifications ORDER BY id LIMIT 1").fetchone()["link"]
    alert_id = conn.execute("SELECT MIN(id) AS i FROM alerts").fetchone()["i"]
    conn.close()
    assert link == f"/alerts?status=open#alert-{alert_id}"
    assert f'id="alert-{alert_id}"' in client.get("/alerts?status=open").text


def test_unknown_alert_filter_values_are_called_out(client):
    _make_match(client)
    ok = client.get("/alerts?status=open").text
    assert "Unknown filter ignored" not in ok
    for q in ("status=bogus", "sort=sideways", "category=nope", "group_by=weird"):
        assert "Unknown filter ignored" in client.get(f"/alerts?{q}").text, q


# ------------------------------------------------------------------ L-71
def test_case_file_shows_overdue_marker_only_when_review_is_due(client):
    cid = _make_match(client)
    conn = _db()
    assert conn.execute("SELECT COUNT(*) c FROM risk_assessments WHERE customer_id=?", (cid,)).fetchone()["c"] >= 1
    conn.execute("UPDATE risk_assessments SET next_review='2999-01-01' WHERE customer_id=?", (cid,))
    conn.commit()
    assert 'class="tag high">overdue' not in client.get(f"/customers/{cid}").text
    conn.execute("UPDATE risk_assessments SET next_review='2000-01-01' WHERE customer_id=?", (cid,))
    conn.commit()
    assert 'class="tag high">overdue' in client.get(f"/customers/{cid}").text


# ------------------------------------------------------------------ L-27
def test_legacy_name_fallback_logs_a_warning_and_script_counts_it(caplog):
    from amlkit.cases.review import confirm_disposition, propose_disposition
    from tests.test_issue_167_foureyes_double_disposition import _create_test_db
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from check_legacy_proposals import count_legacy_pending

    conn, org_id, alert_id = _create_test_db()
    propose_disposition(conn, alert_id, org_id=org_id, status="false_positive",
                        reason_code="different_dob", operator="Legacy Operator")
    assert [r["alert_id"] for r in count_legacy_pending(conn)] == [alert_id]
    with caplog.at_level(logging.WARNING, logger="amlkit.cases.review"):
        confirm_disposition(conn, alert_id, org_id=org_id, operator="Someone Else", agree=True)
    assert "legacy name comparison" in caplog.text
    assert count_legacy_pending(conn) == []  # no longer pending


def test_id_based_proposals_are_not_reported_as_legacy():
    from amlkit.cases.review import propose_disposition
    from tests.test_issue_167_foureyes_double_disposition import _create_test_db
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from check_legacy_proposals import count_legacy_pending

    conn, org_id, alert_id = _create_test_db()
    propose_disposition(conn, alert_id, org_id=org_id, status="false_positive",
                        reason_code="different_dob", operator="Pat", operator_id=1)
    assert count_legacy_pending(conn) == []
