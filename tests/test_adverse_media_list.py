"""/adverse-media: every adverse-media finding across the firm's customers, for triage.

Read-only list (deciding happens on the customer's page); same ordering as the
dashboard's Adverse media line: most serious first, then oldest.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conftest import register_org  # noqa: E402
from tests.test_dashboard_alert_lines import _db, _seed_adverse, mlro  # noqa: E402,F401


def _add_finding(org_id, name, severity="regulatory_action", status="open", url=None):
    from amlkit.db import utcnow
    conn = _db()
    now = utcnow()
    cid = conn.execute(
        "INSERT INTO customers (org_id, reference, customer_type, full_name, canonical_key, "
        "onboarded_at, created_at, updated_at) VALUES (?, ?, 'legal', ?, ?, ?, ?, ?)",
        (org_id, f"X-{name}", name, name.lower(), now, now, now)).lastrowid
    sid = conn.execute(
        "INSERT INTO adverse_media_screenings (org_id, customer_id, query_name, trigger, window_months, "
        "status, run_at) VALUES (?, ?, ?, 'adhoc', 12, 'ok', ?)", (org_id, cid, name, now)).lastrowid
    conn.execute(
        "INSERT INTO adverse_media_findings (org_id, screening_id, customer_id, url, title, domain, "
        "severity, matched_terms, status, created_at) VALUES (?, ?, ?, ?, ?, 'example.test', ?, '[]', ?, ?)",
        (org_id, sid, cid, url or f"https://example.test/{name}", f"Headline {name}", severity, status, now))
    conn.commit()
    conn.close()
    return cid


def _org_id():
    conn = _db()
    try:
        return conn.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()["id"]
    finally:
        conn.close()


def test_requires_a_session(tmp_path, monkeypatch):
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "t.db"))
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    r = TestClient(app).get("/adverse-media", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_default_view_is_open_findings_most_serious_first(mlro):
    _seed_adverse([("Gamma Holdings", "reputational_only", "open"),
                   ("Alpha Trading", "financial_crime_alleged", "open"),
                   ("Beta Gold", "regulatory_action", "relevant")])
    html = mlro.get("/adverse-media").text
    assert html.index("Alpha Trading") < html.index("Gamma Holdings")
    assert "Beta Gold" not in html
    assert "Open <span" in html and "(2)" in html          # tab counts are exact
    assert "Relevant <span" in html and "All <span" in html


def test_status_tabs_and_unknown_status_fallback(mlro):
    _seed_adverse([("Alpha Trading", "financial_crime_alleged", "open"),
                   ("Beta Gold", "regulatory_action", "relevant"),
                   ("Gamma Holdings", "reputational_only", "not_relevant")])
    assert "Beta Gold" in mlro.get("/adverse-media?status=relevant").text
    assert "Alpha Trading" not in mlro.get("/adverse-media?status=relevant").text
    everything = mlro.get("/adverse-media?status=all").text
    assert all(n in everything for n in ("Alpha Trading", "Beta Gold", "Gamma Holdings"))
    assert "Alpha Trading" in mlro.get("/adverse-media?status=bogus").text   # falls back to open


def test_rows_link_to_the_customers_adverse_media_section(mlro):
    cid = _seed_adverse([("Alpha Trading", "financial_crime_alleged", "open")])[0]
    assert f'href="/customers/{cid}#adverse-media"' in mlro.get("/adverse-media").text


def test_another_organisations_findings_are_never_listed(mlro):
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    other = TestClient(app)
    register_org(other, "Other Firm", "other_mlro", "mlro@other.ae")
    conn = _db()
    ids = [r["id"] for r in conn.execute("SELECT id FROM organizations ORDER BY id")]
    conn.close()
    assert len(ids) == 2
    _add_finding(ids[0], "Mine Ltd")
    _add_finding(ids[1], "Theirs Ltd")
    mine = mlro.get("/adverse-media?status=all").text
    assert "Mine Ltd" in mine and "Theirs Ltd" not in mine
    assert "All <span" in mine and "(1)" in mine
    assert "Theirs Ltd" in other.get("/adverse-media?status=all").text


def test_a_non_http_article_url_is_not_made_a_link(mlro):
    _add_finding(_org_id(), "Alpha Trading", url="javascript:alert(1)")
    html = mlro.get("/adverse-media").text
    assert "javascript:" not in html and "Headline Alpha Trading" in html


def test_list_is_capped_and_says_so(mlro, monkeypatch):
    import amlkit.api.app as appmod
    monkeypatch.setattr(appmod, "ADVERSE_LIST_CAP", 2)
    for n in ("A", "B", "C"):
        _add_finding(_org_id(), f"Firm {n}")
    html = mlro.get("/adverse-media").text
    assert "Showing the first 2 of 3" in html


def test_empty_state_and_navigation_links(mlro):
    assert "Nothing to review" in mlro.get("/adverse-media").text
    assert 'href="/adverse-media"' in mlro.get("/alerts").text
    _seed_adverse([("Alpha Trading", "financial_crime_alleged", "open")])
    assert 'href="/adverse-media"' in mlro.get("/dashboard").text


def test_phone_rows_stack():
    css = (Path(__file__).resolve().parent.parent / "amlkit" / "web" / "static" / "app.css").read_text()
    assert ".adverse-list .list-row { flex-wrap: wrap;" in css
    assert ".adverse-list .list-row .side.nowrap { white-space: normal; }" in css
