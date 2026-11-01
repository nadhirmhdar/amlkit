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
