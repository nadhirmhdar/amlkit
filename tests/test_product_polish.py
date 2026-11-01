"""WP-20 product polish: first-run checklist (p51), /changelog (p52),
palette search scope (p58), /billing usage bars (p87)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_api import _csrf, _db, _register, _seed_sanctions_data  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    for k in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"):
        monkeypatch.delenv(k, raising=False)
    _seed_sanctions_data(db_file)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    c = TestClient(app)
    _register(c, "Polish Firm", "alice", "alice@polish.ae")
    return c


def _add_customer(c, ref, name):
    c.get("/customers/new")
    c.post("/customers", data={
        "reference": ref, "full_name": name, "customer_type": "natural",
        "nationality": "AE", "csrf_token": _csrf(c),
    }, follow_redirects=True)


def _row(html: str, key: str) -> str:
    i = html.index(f'data-onb="{key}"')
    return html[i:i + 80]


# ------------------------------------------------------------ p51 checklist
class TestChecklist:
    def test_shows_for_zero_customers_and_ticks_from_state(self, client):
        c = _db()
        c.execute("UPDATE datasets SET last_refresh=NULL")
        c.commit(); c.close()
        html = client.get("/dashboard").text
        assert 'id="onboarding-checklist"' in html
        for key in ("operator", "refresh", "customer", "profile"):
            assert 'data-done="no"' in _row(html, key)
        # the fixture enrols the MLRO (settle_mfa), so MFA is already ticked
        assert 'data-done="yes"' in _row(html, "mfa")

        c = _db()
        c.execute("UPDATE datasets SET last_refresh='2026-11-01T00:00:00+00:00'")
        c.execute("UPDATE organizations SET org_address='Dubai', reporting_person_name='A B',"
                  " goaml_entity_reference='REF1'")
        c.execute("INSERT INTO operators (org_id, name, email, role, is_active, created_at)"
                  " SELECT id, 'bob', 'bob@polish.ae', 'officer', 1, '2026-11-01' FROM organizations")
        c.commit(); c.close()
        html = client.get("/dashboard").text
        assert 'data-done="yes"' in _row(html, "refresh")
        assert 'data-done="yes"' in _row(html, "profile")
        assert 'data-done="yes"' in _row(html, "operator")
        assert 'data-done="no"' in _row(html, "customer")

    def test_hidden_once_org_has_customers(self, client):
        _add_customer(client, "C-1", "Some Customer")
        assert 'id="onboarding-checklist"' not in client.get("/dashboard").text

    def test_dismiss_persists_per_operator(self, client):
        r = client.post("/dashboard/onboarding/dismiss",
                        data={"csrf_token": _csrf(client)}, follow_redirects=False)
        assert r.status_code == 303
        assert 'id="onboarding-checklist"' not in client.get("/dashboard").text
        c = _db()
        assert c.execute("SELECT onboarding_dismissed_at FROM operators WHERE name='alice'"
                         ).fetchone()[0]
        c.close()

    def test_dismiss_needs_csrf(self, client):
        r = client.post("/dashboard/onboarding/dismiss", data={"csrf_token": "bad"},
                        follow_redirects=False)
        assert r.status_code != 500
        assert 'id="onboarding-checklist"' in client.get("/dashboard").text

    def test_dismissal_does_not_leak_to_other_operator(self, client):
        c = _db()
        c.execute("INSERT INTO operators (org_id, name, email, role, is_active, created_at,"
                  " onboarding_dismissed_at) SELECT id, 'bob', 'bob@polish.ae', 'officer', 1,"
                  " '2026-11-01', '2026-11-01' FROM organizations")
        c.commit(); c.close()
        from amlkit import onboarding
        c = _db()
        oid = c.execute("SELECT id FROM operators WHERE name='bob'").fetchone()[0]
        org = c.execute("SELECT id FROM organizations").fetchone()[0]
        assert onboarding.checklist(c, org, oid, "officer") is None
        aid = c.execute("SELECT id FROM operators WHERE name='alice'").fetchone()[0]
        assert onboarding.checklist(c, org, aid, "mlro") is not None
        c.close()


# ------------------------------------------------------------ p52 changelog
class TestChangelog:
    def test_requires_session(self, client):
        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        r = TestClient(app).get("/changelog", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"

    def test_renders_seeded_entries_newest_first(self, client):
        html = client.get("/changelog").text
        assert "What&#39;s new in groAML" in html or "What's new in groAML" in html
        assert html.index("1 November 2026") < html.index("31 October 2026")
        assert "amlkit" not in html.lower().split("<main")[-1]
        import re
        assert not re.search(r"\bL-\d+", html)

    def test_dot_shows_until_seen_then_clears(self, client):
        assert "whatsnew-dot" in client.get("/dashboard").text
        client.get("/changelog")
        assert "whatsnew-dot" not in client.get("/dashboard").text

    def test_new_entry_brings_dot_back(self, client, monkeypatch):
        client.get("/changelog")
        from amlkit import changelog
        monkeypatch.setattr(changelog, "latest", lambda: "2 November 2026")
        assert "whatsnew-dot" in client.get("/dashboard").text

    def test_parser_escapes_and_ignores_stray_lines(self):
        from amlkit import changelog
        out = changelog.parse("# T\nintro\n## A\n- <script>x</script>\n- two\n## B\n")
        assert out == [{"title": "A", "items": ["<script>x</script>", "two"]},
                       {"title": "B", "items": []}]

    def test_markup_in_file_is_escaped(self, client, monkeypatch):
        from amlkit import changelog
        monkeypatch.setattr(changelog, "entries",
                            lambda: [{"title": "T", "items": ["<script>alert(1)</script>"]}])
        html = client.get("/changelog").text
        assert "<script>alert(1)</script>" not in html


# ------------------------------------------------------------ p58 palette
def _add_report(ref, org_name=None, rtype="STR"):
    c = _db()
    org = c.execute("SELECT id FROM organizations WHERE name=?",
                    (org_name or "Polish Firm",)).fetchone()[0]
    cur = c.execute("INSERT INTO reports (org_id, report_type, reference, status, payload,"
                    " created_at) VALUES (?,?,?,?,?,?)",
                    (org, rtype, ref, "draft", "{}", "2026-11-01T00:00:00+00:00"))
    c.commit()
    rid = cur.lastrowid
    c.close()
    return rid


class TestPalette:
    def test_reports_found_by_reference(self, client):
        rid = _add_report("STR-2026-0042")
        data = client.get("/search?q=STR-2026").json()
        reports = [i for i in data["results"] if i["type"] == "report"]
        assert [r["url"] for r in reports] == [f"/reports/{rid}"]
        assert reports[0]["name"] == "STR-2026-0042"

    def test_only_callers_org_rows_returned(self, client):
        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        _add_report("SHARED-REF-1")
        _add_customer(client, "SHARED-C1", "Shared Name Person")
        other = TestClient(app)
        _register(other, "Other Firm", "oscar", "oscar@other.ae")
        _add_report("SHARED-REF-2", org_name="Other Firm")
        _add_customer(other, "SHARED-C2", "Shared Name Person")
        mine = client.get("/search?q=SHARED").json()["results"]
        assert {i["name"] for i in mine if i["type"] == "report"} == {"SHARED-REF-1"}
        theirs = other.get("/search?q=SHARED").json()["results"]
        assert {i["name"] for i in theirs if i["type"] == "report"} == {"SHARED-REF-2"}
        assert [i["detail"] for i in mine if i["type"] == "customer"] == ["SHARED-C1"]

    def test_report_search_is_literal_not_wildcard(self, client):
        _add_report("AAA-1")
        assert client.get("/search?q=%25").json()["results"] == []

    def test_palette_script_served_with_pages_and_shortcuts(self, client):
        js = client.get("/static/js/search-palette.js").text
        assert "/changelog" in js and "ctrlKey" in js and "Escape" in js


# ------------------------------------------------------------ p87 billing bars
class TestBillingUsage:
    @pytest.fixture()
    def billing(self, client, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
        monkeypatch.setenv("STRIPE_PRICE_STARTER", "price_s")
        return client

    def test_stays_404_when_not_configured(self, client):
        assert client.get("/billing").status_code == 404

    def test_bars_and_limits_render(self, billing):
        c = _db()
        c.execute("UPDATE organizations SET plan='starter', plan_status='active'")
        c.commit(); c.close()
        for i in range(3):
            _add_customer(billing, f"B-{i}", f"Bar Customer {i}")
        html = billing.get("/billing").text
        assert 'data-usage="customers"' in html and 'data-usage="operators"' in html
        assert html.count('role="progressbar"') == 3
        i = html.index('data-usage="customers"')
        assert "3 / 200" in " ".join(html[i:i + 1200].split())
        assert 'aria-valuemax="200"' in html[i:i + 1200]

    def test_legacy_org_has_no_bar_but_shows_unlimited(self, billing):
        html = billing.get("/billing").text
        assert "unlimited" in html and 'role="progressbar"' not in html

    def test_history_counts_from_timestamps(self, billing):
        from datetime import datetime, timezone
        from amlkit.billing import limits
        _add_customer(billing, "H-1", "History One")
        c = _db()
        org = c.execute("SELECT id FROM organizations").fetchone()[0]
        c.execute("UPDATE customers SET onboarded_at='2026-09-10T00:00:00+00:00'")
        c.execute("UPDATE operators SET created_at='2026-06-02T00:00:00+00:00'")
        c.commit()
        h = limits.monthly_history(c, org, now=datetime(2026, 11, 1, tzinfo=timezone.utc))
        c.close()
        assert [x["month"] for x in h] == ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]
        assert {x["month"]: x["customers"] for x in h}["2026-09"] == 1
        assert {x["month"]: x["operators"] for x in h}["2026-06"] == 1
        assert sum(x["customers"] for x in h) == 1

    def test_history_table_rendered_and_org_scoped(self, billing):
        html = billing.get("/billing").text
        assert 'id="usage-history"' in html and "Last 6 months" in html
        assert "AED" not in html.split('id="usage-history"')[1].split("</table>")[0]
