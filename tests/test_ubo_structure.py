"""UBO structure guard (U4, UBO1, #253): add_ubo refuses self-ownership, foreign
or cyclic parents, chains deeper than MAX_UBO_DEPTH and more than
MAX_UBOS_PER_CUSTOMER rows; and a pathological chain that is already in the
database (inserted straight through SQL) no longer breaks rendering or risk
reassessment (the former recursive _identified_ownership raised RecursionError
at about 1,100 levels)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases import manager  # noqa: E402
from amlkit.cases.manager import (  # noqa: E402
    MAX_UBO_DEPTH, MAX_UBOS_PER_CUSTOMER, add_ubo, ownership_state, reassess_risk,
)
from amlkit.db import connect  # noqa: E402
from tests.test_api import client, _db  # noqa: E402,F401  (fixture reuse)
from tests.test_mobile_api import api  # noqa: E402,F401


def _customer(c, name="Gulf Holdings LLC", name_arabic=None, org_id=1, ref="C1"):
    cur = c.execute(
        "INSERT INTO customers (org_id, reference, full_name, name_arabic, canonical_key, customer_type,"
        " onboarded_at, created_at, updated_at) VALUES (?,?,?,?,?,'legal','2026-01-01','2026-01-01','2026-01-01')",
        (org_id, ref, name, name_arabic, name.lower()),
    )
    c.commit()
    return cur.lastrowid


@pytest.fixture()
def conn(tmp_path):
    c = connect(tmp_path / "s.db")
    c.execute("INSERT INTO organizations (name, slug, created_at) VALUES ('O', 'o', '2026-01-01')")
    c.execute("INSERT INTO organizations (name, slug, created_at) VALUES ('P', 'p', '2026-01-01')")
    c.commit()
    yield c
    c.close()


# ---------------------------------------------------------------- (a) self
@pytest.mark.parametrize("name", [
    "Gulf Holdings LLC", "  gulf   HOLDINGS llc ", "LLC Gulf Holdings",
])
def test_customer_cannot_own_itself(conn, name):
    cid = _customer(conn)
    with pytest.raises(ValueError, match="own beneficial owner"):
        add_ubo(conn, cid, org_id=1, person_name=name, ownership_pct=30)
    assert conn.execute("SELECT COUNT(*) FROM ubo_links").fetchone()[0] == 0


def test_self_ownership_arabic_forms(conn):
    cid = _customer(conn, name="Gulf Holdings LLC", name_arabic="مجموعة الخليج القابضة")
    with pytest.raises(ValueError, match="own beneficial owner"):
        add_ubo(conn, cid, org_id=1, person_name="مجموعة الخليج القابضة", ownership_pct=30)
    with pytest.raises(ValueError, match="own beneficial owner"):
        add_ubo(conn, cid, org_id=1, person_name="Somebody", name_arabic="مجموعة  الخليج القابضة", ownership_pct=30)
    add_ubo(conn, cid, org_id=1, person_name="Ali Hassan", ownership_pct=30)  # others fine


# ------------------------------------------------------------- (b) parent
def test_parent_must_belong_to_same_customer_and_org(conn):
    c1 = _customer(conn, ref="C1")
    c2 = _customer(conn, name="Other Co", ref="C2")
    c3 = _customer(conn, name="Third Co", org_id=2, ref="C3")
    p_other = add_ubo(conn, c2, org_id=1, person_name="Corp X", ownership_pct=50)
    p_org2 = add_ubo(conn, c3, org_id=2, person_name="Corp Y", ownership_pct=50)
    for bad in (p_other, p_org2, 99999):
        with pytest.raises(ValueError, match="does not belong"):
            add_ubo(conn, c1, org_id=1, person_name="Child", ownership_pct=10, parent_ubo_id=bad)
    assert conn.execute("SELECT COUNT(*) FROM ubo_links WHERE customer_id=?", (c1,)).fetchone()[0] == 0


# -------------------------------------------------------------- (c) cycle
def test_parent_forming_cycle_refused(conn):
    cid = _customer(conn)
    ids = []
    for i in range(3):
        cur = conn.execute(
            "INSERT INTO ubo_links (org_id, customer_id, person_name, canonical_key, ownership_pct, control_type,"
            " is_ubo, is_nominee, created_at, last_verified_at) VALUES (1,?,?,?,50,'ownership',0,0,'t','t')",
            (cid, f"Corp {i}", f"corp {i}"),
        )
        ids.append(cur.lastrowid)
    # Corp0 -> Corp1 -> Corp2 -> Corp0 (cycle entered through SQL, as bad data could be)
    for child, parent in ((ids[0], ids[1]), (ids[1], ids[2]), (ids[2], ids[0])):
        conn.execute("UPDATE ubo_links SET parent_ubo_id=? WHERE id=?", (parent, child))
    conn.commit()
    with pytest.raises(ValueError, match="circular"):
        add_ubo(conn, cid, org_id=1, person_name="Child", ownership_pct=10, parent_ubo_id=ids[0])
    # and the evaluator survives the cycle
    assert ownership_state(conn, cid, 1) in {
        "ubo_undisclosed", "multi_layer_offshore", "single_layer_foreign", "fully_transparent"}


# --------------------------------------------------------------- (d) depth
def test_depth_ten_ok_eleven_refused(conn):
    cid = _customer(conn)
    parent = None
    for level in range(1, MAX_UBO_DEPTH + 1):
        parent = add_ubo(conn, cid, org_id=1, person_name=f"Holdco {level}",
                         ownership_pct=40 if parent is None else 100, parent_ubo_id=parent)
    assert MAX_UBO_DEPTH == 10
    with pytest.raises(ValueError, match="at most 10 levels"):
        add_ubo(conn, cid, org_id=1, person_name="Holdco 11", ownership_pct=100, parent_ubo_id=parent)
    assert conn.execute("SELECT COUNT(*) FROM ubo_links").fetchone()[0] == MAX_UBO_DEPTH


# ------------------------------------------------------------- (e) row cap
def test_row_cap(conn):
    cid = _customer(conn)
    conn.executemany(
        "INSERT INTO ubo_links (org_id, customer_id, person_name, canonical_key, control_type, is_ubo,"
        " is_nominee, created_at, last_verified_at) VALUES (1,?,?,?,'other',0,0,'t','t')",
        [(cid, f"Director {i}", f"director {i}") for i in range(MAX_UBOS_PER_CUSTOMER)],
    )
    conn.commit()
    assert MAX_UBOS_PER_CUSTOMER == 200
    with pytest.raises(ValueError, match="at most 200"):
        add_ubo(conn, cid, org_id=1, person_name="One Too Many")
    other = _customer(conn, name="Other Co", ref="C2")  # cap is per customer
    add_ubo(conn, other, org_id=1, person_name="Fine")


# ------------------------------------------------------------- web / mobile
def test_web_route_refuses_self_owner_with_message(client):
    c = _db()
    org = c.execute("SELECT id FROM organizations ORDER BY id DESC LIMIT 1").fetchone()[0]
    cid = _customer(c, org_id=org)
    c.close()
    csrf = client.cookies.get("amlkit_csrf") or (client.get(f"/customers/{cid}") and client.cookies.get("amlkit_csrf"))
    r = client.post(f"/customers/{cid}/ubo", data={
        "person_name": "Gulf Holdings LLC", "ownership_pct": "30", "control_type": "ownership",
        "csrf_token": csrf}, follow_redirects=False)
    # Web routes report ValueError as a flash on a 303 redirect (not a bare 400); the message is rendered on the page.
    assert r.status_code == 303
    page = client.get(f"/customers/{cid}")
    assert page.status_code == 200
    assert "cannot be recorded as its own beneficial owner" in page.text
    c = _db()
    assert c.execute("SELECT COUNT(*) FROM ubo_links WHERE customer_id=?", (cid,)).fetchone()[0] == 0
    c.close()


def test_mobile_route_refuses_self_owner_422(api):
    client, headers = api
    cid = client.post("/api/v1/customers", headers=headers, json={
        "reference": "UBO-SELF", "full_name": "Gulf Holdings LLC", "customer_type": "legal",
    }).json()["customer_id"]
    r = client.post(f"/api/v1/customers/{cid}/ubo", headers=headers, json={
        "person_name": "Gulf Holdings LLC", "ownership_pct": 30, "control_type": "ownership"})
    assert r.status_code == 422
    assert "own beneficial owner" in r.json()["detail"]


# ------------------------------------------- deep chain already in the data
def test_1100_deep_chain_renders_and_reassesses(client):
    c = _db()
    org = c.execute("SELECT id FROM organizations ORDER BY id DESC LIMIT 1").fetchone()[0]
    cid = _customer(c, org_id=org)
    prev = None
    for i in range(1100):
        cur = c.execute(
            "INSERT INTO ubo_links (org_id, customer_id, person_name, canonical_key, ownership_pct, control_type,"
            " is_ubo, is_nominee, parent_ubo_id, created_at, last_verified_at)"
            " VALUES (?,?,?,?,?,'ownership',1,0,?,'t','t')",
            (org, cid, f"Holdco {i}", f"holdco {i}", 40 if prev is None else 100, prev),
        )
        prev = cur.lastrowid
    c.commit()
    assert sys.getrecursionlimit() <= 1100 * 2  # the old recursion would have blown here
    assert ownership_state(c, cid, org, "legal") == "multi_layer_offshore"  # 40% effective
    reassess_risk(c, cid, org, actor="probe")
    c.close()
    r = client.get(f"/customers/{cid}")
    assert r.status_code == 200
