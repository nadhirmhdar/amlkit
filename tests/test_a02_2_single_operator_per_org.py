"""Test A-02-2 / Issue #258: single_operator_mode must be per-org, not process-wide.

Bug: AMLKIT_SINGLE_OPERATOR_MODE env var is process-wide. Setting it for one
solo-officer tenant disables four-eyes review for all tenants on the instance,
including multi-operator orgs that should require independent review.

Fix: Store per-org config in DB (org_settings.single_operator_mode), resolved
from org_id at the call site. The env var is only a default for single-org
installs: it is ignored once the database holds more than one organization,
and never overrides an explicit per-org setting.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.review import propose_disposition, single_operator_mode
from amlkit.db import connect, set_org_single_operator_mode
from test_p43_alerts_group_dismiss import _seed

NOW = "2026-01-01T00:00:00+00:00"


def _org(conn, slug):
    conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
                 (slug.title(), slug, "active", NOW))
    conn.commit()
    return conn.execute("SELECT id FROM organizations WHERE slug=?", (slug,)).fetchone()[0]


def test_env_var_applies_on_single_org_install(tmp_path, monkeypatch):
    """Back-compat: a single-tenant deployment keeps the env var as its switch."""
    monkeypatch.setenv("AMLKIT_SINGLE_OPERATOR_MODE", "1")
    conn = connect(tmp_path / "t.db")
    org = _org(conn, "solo")
    assert single_operator_mode(conn, org) is True
    conn.close()


def test_defaults_to_false_without_env_or_db(tmp_path, monkeypatch):
    """Without env var or DB config, default to False (stricter control)."""
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    conn = connect(tmp_path / "t.db")
    org = _org(conn, "test")
    assert single_operator_mode(conn, org) is False
    conn.close()


def test_env_var_ignored_once_instance_is_multi_tenant(tmp_path, monkeypatch):
    """The core regression for #258: an org that never opted in must not
    inherit single-operator mode from a process-wide env var on a shared
    instance."""
    monkeypatch.setenv("AMLKIT_SINGLE_OPERATOR_MODE", "1")
    conn = connect(tmp_path / "t.db")
    solo = _org(conn, "solo")
    multi = _org(conn, "multi")
    assert single_operator_mode(conn, solo) is False
    assert single_operator_mode(conn, multi) is False

    # The solo firm opts in explicitly; the other org is unaffected.
    set_org_single_operator_mode(conn, solo, True)
    conn.commit()
    assert single_operator_mode(conn, solo) is True
    assert single_operator_mode(conn, multi) is False
    conn.close()


def test_explicit_setting_overrides_env_var_both_ways(tmp_path, monkeypatch):
    monkeypatch.setenv("AMLKIT_SINGLE_OPERATOR_MODE", "1")
    conn = connect(tmp_path / "t.db")
    org = _org(conn, "one")
    set_org_single_operator_mode(conn, org, False)
    assert single_operator_mode(conn, org) is False  # explicit off beats env on

    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE")
    set_org_single_operator_mode(conn, org, True)
    assert single_operator_mode(conn, org) is True   # explicit on without env

    set_org_single_operator_mode(conn, org, None)
    assert single_operator_mode(conn, org) is False  # cleared -> default
    conn.close()


def test_setting_one_org_does_not_bypass_four_eyes_for_another(monkeypatch):
    """Issue #258's suggested test: single-operator mode for org 1 only, and a
    dismissal on org 2 still stages for a second operator."""
    monkeypatch.setenv("AMLKIT_SINGLE_OPERATOR_MODE", "1")
    conn = connect(":memory:")
    solo = _org(conn, "solo")
    set_org_single_operator_mode(conn, solo, True)
    conn.commit()
    seed = _seed(conn)  # org 2: multi-operator firm with open sanctions alerts

    outcome = propose_disposition(
        conn, seed["alert_ids"][0], org_id=seed["org_id"],
        status="false_positive", reason_code="different_dob", operator="Operator",
    )
    assert outcome.awaiting_second_review is True
    assert outcome.status == "pending_review"
    conn.close()


def test_admin_route_sets_and_clears_per_org_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "admin.db"))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    from conftest import register_org

    c = TestClient(app)
    register_org(c, "Solo LLC", "Sam Solo", "sam@solo.ae")
    assert "Single-operator mode is <strong>on</strong>" not in c.get("/").text

    r = c.post("/admin/single-operator",
               data={"mode": "on", "csrf_token": c.cookies.get("amlkit_csrf")},
               follow_redirects=True)
    assert r.status_code == 200
    assert "Single-operator mode is <strong>on</strong>" in c.get("/").text

    conn = connect(tmp_path / "admin.db")
    assert conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE action='org.single_operator_set'"
    ).fetchone()[0] == 1
    conn.close()

    c.post("/admin/single-operator",
           data={"mode": "default", "csrf_token": c.cookies.get("amlkit_csrf")},
           follow_redirects=True)
    assert "Single-operator mode is <strong>on</strong>" not in c.get("/").text

    r = c.post("/admin/single-operator",
               data={"mode": "bogus", "csrf_token": c.cookies.get("amlkit_csrf")},
               follow_redirects=True)
    assert "Choose on, off, or default" in r.text
