"""Record retention: firm policy vs statutory minimum (#313), and extending
retention_until dates stored under the older, shorter rule (#79).

Cabinet Resolution 134/2025 Art. 25(2) sets a five-year minimum; groAML's ten
years is internal policy above that floor, so neither code nor UI may present
ten years as a requirement of the Resolution.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amlkit import db as dbmod  # noqa: E402
from amlkit.cases.manager import (  # noqa: E402
    RETENTION_YEARS,
    STATUTORY_MIN_RETENTION_YEARS,
    close_relationship,
    onboard,
    reactivate_customer,
    retention_from,
)
from amlkit.db import connect, utcnow  # noqa: E402
from conftest import register_org, seed_fresh_dataset  # noqa: E402

# "requires/mandates ... ten years" or "extended ... five to ten years".
_FALSE_CLAIM = re.compile(
    r"(134[^.]{0,120}(requir|mandat|extend)[^.]{0,80}(ten|10)[ -]year)"
    r"|((requir|mandat)[^.]{0,40}(ten|10)[ -]year[^.]{0,80}134)"
    r"|(five to ten years)",
    re.IGNORECASE | re.DOTALL,
)


# ------------------------------------------------------------------ constants

def test_policy_is_above_statutory_minimum() -> None:
    assert STATUTORY_MIN_RETENTION_YEARS == 5
    assert RETENTION_YEARS == 10
    assert RETENTION_YEARS >= STATUTORY_MIN_RETENTION_YEARS


def test_no_source_claims_cr_134_requires_ten_years() -> None:
    files = [ROOT / "amlkit" / "cases" / "manager.py", ROOT / "amlkit" / "db.py",
             ROOT / "README.md", *(ROOT / "amlkit" / "web" / "templates").rglob("*.html")]
    for f in files:
        text = f.read_text(encoding="utf-8")
        m = _FALSE_CLAIM.search(text)
        assert m is None, f"{f.relative_to(ROOT)}: {m.group(0)!r}"
    db_src = (ROOT / "amlkit" / "db.py").read_text(encoding="utf-8")
    assert "8 years" not in db_src and "10-year rule" not in db_src


# ----------------------------------------------------------------- rendering

@pytest.fixture()
def web(tmp_path, monkeypatch):
    db_file = tmp_path / "t.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    c = connect(db_file)
    seed_fresh_dataset(c)
    c.close()
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    client = TestClient(app)
    register_org(client, "Retention Firm", "alice", "alice@retention.ae")
    return client, db_file


def test_customer_page_states_policy_not_legal_requirement(web) -> None:
    client, db_file = web
    c = connect(db_file)
    org_id = c.execute("SELECT id FROM organizations").fetchone()["id"]
    res = onboard(c, org_id=org_id, reference="C-1", full_name="Jane Example", actor="t")
    c.close()
    html = client.get(f"/customers/{res.customer_id}").text
    assert "Records retained until" in html
    flat = " ".join(html.split())
    assert f"Retained for {RETENTION_YEARS} years (firm policy; statutory minimum is " \
           f"{STATUTORY_MIN_RETENTION_YEARS} years under Cabinet Resolution 134/2025 " \
           "Art. 25(2))" in flat
    assert not _FALSE_CLAIM.search(flat)


def test_privacy_page_states_policy_and_statutory_minimum(web) -> None:
    client, _ = web
    flat = " ".join(client.get("/privacy").text.split())
    assert f"{RETENTION_YEARS} years under groAML's retention policy" in flat
    assert "requires at least five years" in flat
    assert "the period required by UAE AML law" not in flat


# ----------------------------------------------------------------- migration

@pytest.fixture()
def conn():
    c = connect(":memory:")
    seed_fresh_dataset(c)
    yield c
    c.close()


def _org(conn, slug: str) -> int:
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
        " RETURNING id", (slug, slug, "active", utcnow())).fetchone()
    conn.commit()
    return row["id"]


def _closed(conn, org_id: int, ref: str, exit_date: str, retention_until: str) -> int:
    cid = onboard(conn, org_id=org_id, reference=ref, full_name=f"Person {ref}",
                  actor="t").customer_id
    conn.execute("UPDATE customers SET status='closed', exit_date=?, exit_reason='other',"
                 " retention_until=? WHERE id=?", (exit_date, retention_until, cid))
    conn.commit()
    return cid


def _until(conn, cid: int) -> str:
    return conn.execute("SELECT retention_until FROM customers WHERE id=?",
                        (cid,)).fetchone()["retention_until"]


def _ext_audits(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT org_id, detail FROM audit_log"
                        " WHERE action='retention.extended' ORDER BY id").fetchall()


def test_extends_five_year_row_and_leaves_correct_and_longer_rows(conn) -> None:
    org = _org(conn, "a")
    old = _closed(conn, org, "OLD", "2021-08-11", "2026-08-11")       # 5-year rule
    eight = _closed(conn, org, "EIGHT", "2022-01-05", "2030-01-05")   # 8-year rule
    ok = _closed(conn, org, "OK", "2023-03-01", retention_from(date(2023, 3, 1)))
    longer = _closed(conn, org, "LONG", "2020-01-01", "2040-01-01")
    active = onboard(conn, org_id=org, reference="ACT", full_name="Active One",
                     actor="t").customer_id
    onboarded = conn.execute("SELECT onboarded_at FROM customers WHERE id=?",
                             (active,)).fetchone()["onboarded_at"][:10]
    conn.execute("UPDATE customers SET retention_until=? WHERE id=?",
                 (date.fromisoformat(onboarded).replace(year=int(onboarded[:4]) + 5).isoformat(),
                  active))
    conn.commit()
    before_ok = _until(conn, ok)

    dbmod._extend_retention_until(conn)
    conn.commit()

    assert _until(conn, old) == "2031-08-11"
    assert _until(conn, eight) == "2032-01-05"
    assert _until(conn, ok) == before_ok
    assert _until(conn, longer) == "2040-01-01"  # never shortened
    assert _until(conn, active) == retention_from(date.fromisoformat(onboarded))
    audits = _ext_audits(conn)
    assert len(audits) == 1 and audits[0]["org_id"] == org
    detail = json.loads(audits[0]["detail"])
    assert detail["count"] == 3 and detail["retention_years"] == RETENTION_YEARS
    assert {c["id"] for c in detail["customers"]} == {old, eight, active}


def test_idempotent_second_run_changes_nothing(conn) -> None:
    org = _org(conn, "a")
    cid = _closed(conn, org, "OLD", "2021-08-11", "2026-08-11")
    dbmod._extend_retention_until(conn)
    conn.commit()
    assert dbmod._extend_retention_until(conn) == {}
    conn.commit()
    assert _until(conn, cid) == "2031-08-11"
    assert len(_ext_audits(conn)) == 1


def test_dry_run_writes_nothing(conn) -> None:
    org = _org(conn, "a")
    cid = _closed(conn, org, "OLD", "2021-08-11", "2026-08-11")
    plan = dbmod._extend_retention_until(conn, dry_run=True)
    assert plan == {org: [{"id": cid, "from": "2026-08-11", "to": "2031-08-11"}]}
    assert _until(conn, cid) == "2026-08-11"
    assert _ext_audits(conn) == []


def test_reactivation_date_is_the_base_for_active_rows(conn) -> None:
    org = _org(conn, "a")
    cid = _closed(conn, org, "R", "2021-08-11", "2026-08-11")
    reactivate_customer(conn, cid, org_id=org, reason="back", actor="t")
    # Simulate the old rule: reactivation stored today + 5 years.
    today = date.today()
    short = retention_from(today).replace(str(today.year + RETENTION_YEARS),
                                          str(today.year + 5), 1)
    conn.execute("UPDATE customers SET retention_until=? WHERE id=?", (short, cid))
    conn.commit()
    dbmod._extend_retention_until(conn)
    assert _until(conn, cid) == retention_from(today)


def test_orgs_audited_separately_and_not_crossed(conn) -> None:
    a, b = _org(conn, "a"), _org(conn, "b")
    ca = _closed(conn, a, "X", "2021-08-11", "2026-08-11")
    cb = _closed(conn, b, "X", "2019-02-02", "2024-02-02")
    # Org b's reactivation audit for an id equal to org a's customer must not
    # be read as org a's reactivation.
    dbmod.audit(conn, "t", "customer.reactivated", "customer", ca, {}, org_id=b)
    conn.commit()
    dbmod._extend_retention_until(conn)
    conn.commit()
    assert _until(conn, ca) == "2031-08-11"
    assert _until(conn, cb) == "2029-02-02"
    by_org = {r["org_id"]: json.loads(r["detail"]) for r in _ext_audits(conn)}
    assert set(by_org) == {a, b}
    assert [c["id"] for c in by_org[a]["customers"]] == [ca]
    assert [c["id"] for c in by_org[b]["customers"]] == [cb]


def test_connect_runs_the_fix_once(tmp_path) -> None:
    db_file = tmp_path / "upgrade.db"
    c = connect(db_file)
    seed_fresh_dataset(c)
    org = _org(c, "a")
    cid = _closed(c, org, "OLD", "2021-08-11", "2026-08-11")
    # Simulate a database from before this fix.
    c.execute("DELETE FROM data_migrations")
    c.commit()
    c.close()

    c = connect(db_file)
    assert _until(c, cid) == "2031-08-11"
    assert len(_ext_audits(c)) == 1
    # Later deliberate edits (e.g. purge tests) are not rewritten on reconnect.
    c.execute("UPDATE customers SET retention_until='2020-01-01' WHERE id=?", (cid,))
    c.commit()
    c.close()
    c = connect(db_file)
    assert _until(c, cid) == "2020-01-01"
    assert len(_ext_audits(c)) == 1
    c.close()


def test_close_relationship_uses_policy(conn) -> None:
    org = _org(conn, "a")
    cid = onboard(conn, org_id=org, reference="C", full_name="Close Me", actor="t").customer_id
    assert close_relationship(conn, cid, org_id=org, reason="other") == retention_from(date.today())
