"""Alert queue triage order, and the category-aware obligation note.

L-18: the queue used to be cut to a page by score (or age) in SQL and only
sorted by category inside that page, so with more than a page of
higher-scoring alerts a proliferation alert sat on page 2 and never showed.
The order is now category priority, then the sort key, then id, decided before
LIMIT/OFFSET, on the web queue, the mobile API and the dashboard alike.

L-19: a PEP (or other non-sanctions) alert must not tell the operator to freeze.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conftest import register_org, unlock_mobile_mfa  # noqa: E402

from amlkit import queries  # noqa: E402
from amlkit.db import upsert_dataset, utcnow  # noqa: E402


def _db():
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture()
def mlro(tmp_path, monkeypatch):
    """Cookie-session client for a freshly registered org's MLRO (web routes)."""
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "t.db"))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    c = TestClient(app)
    register_org(c, "Order Firm", "order_mlro", "mlro@order.ae")
    return c


@pytest.fixture()
def api(tmp_path, monkeypatch):
    """(client, bearer headers) for a freshly registered, verified org's MLRO
    over /api/v1 (same flow as test_mobile_api.api, kept local so this file
    stands alone)."""
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "t.db"))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    c = TestClient(app)
    r = c.post("/api/v1/auth/register-organization", json={
        "org_name": "Order Firm", "name": "alice", "email": "alice@order.ae",
        "password": "a-strong-password-1", "invite_code": "test-invite"})
    assert r.status_code == 200, r.text
    r2 = c.post("/api/v1/auth/verify-email", json={"token": r.json()["dev_verification_token"]})
    assert r2.status_code == 200, r2.text
    token = r2.json()["token"]
    unlock_mobile_mfa(c, token)
    return c, {"Authorization": f"Bearer {token}"}


N_SANCTION = 203  # more than one default page (200) of higher-scoring alerts


def _insert_alert(conn, ds, org_id, i, name, topics, programs, score, status="open", created="2026-01-01T00:00:00+00:00"):
    eid = conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption, countries,
           birth_date, gender, topics, programs, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, f"Q-{org_id}-{i}-{os.urandom(3).hex()}", "Person", name, '["ae"]', "1980-01-01",
         "male", json.dumps(topics), json.dumps(programs), "{}", created, created),
    ).lastrowid
    sid = conn.execute(
        """INSERT INTO screenings (org_id, query_name, trigger, algorithm, threshold, run_at)
           VALUES (?,?,?,?,?,?)""",
        (org_id, name, "adhoc", "jaro_winkler", 0.8, created),
    ).lastrowid
    return conn.execute(
        """INSERT INTO alerts (org_id, screening_id, entity_id, score, score_detail,
           matched_name, status, created_at) VALUES (?,?,?,?,?,?,?,?)""",
        (org_id, sid, eid, score, "{}", name, status, created),
    ).lastrowid


def _seed_queue():
    """Org 1: 203 high-scoring plain sanctions, then (inserted last, so the
    highest ids and the lowest scores) a proliferation, a terrorism, a PEP and
    an 'other' alert. Org 2 gets its own proliferation alert and a sanction.
    Returns (org_id, ids_by_name, other_org_ids)."""
    conn = _db()
    org_id = conn.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()["id"]
    org_b = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
        ("Other Firm", "other-firm", "active", utcnow())).lastrowid
    ds = upsert_dataset(conn, "order_list", "Order List", is_mandatory=True)
    ids: dict[str, int] = {}
    for i in range(N_SANCTION):
        _insert_alert(conn, ds, org_id, i, f"Sanction {i}", ["sanction"], [], 0.95 - i * 0.0001)
    ids["pf"] = _insert_alert(conn, ds, org_id, 900, "PF Target", ["sanction"], ["NPWMD"], 0.80)
    ids["tf"] = _insert_alert(conn, ds, org_id, 901, "TF Target", ["sanction"], ["UN-SCISIL"], 0.70)
    ids["pep"] = _insert_alert(conn, ds, org_id, 902, "PEP Person", ["role.pep.national"], [], 0.99)
    ids["other"] = _insert_alert(conn, ds, org_id, 903, "Media Person", ["crime"], [], 0.99)
    other = [
        _insert_alert(conn, ds, org_b, 950, "OrgB PF", ["sanction"], ["NPWMD"], 0.97),
        _insert_alert(conn, ds, org_b, 951, "OrgB Sanction", ["sanction"], [], 0.96),
    ]
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=? WHERE id=?",
                 (utcnow(), N_SANCTION + 6, ds))
    conn.commit()
    conn.close()
    return org_id, ids, other


def _all_ids(org_id):
    conn = _db()
    out = [r["id"] for r in conn.execute("SELECT id FROM alerts WHERE org_id=? AND status='open'", (org_id,))]
    conn.close()
    return out


# ------------------------------------------------------------------ L-18
@pytest.mark.parametrize("sort_by", [None, "age_asc", "age_desc"])
def test_priority_categories_lead_the_first_page_for_every_sort(api, sort_by):
    org_id, ids, _ = _seed_queue()
    conn = _db()
    page = queries.alert_queue(conn, org_id, status="open", limit=200, sort_by=sort_by)
    conn.close()
    assert len(page) == 200
    assert [a["id"] for a in page[:2]] == [ids["pf"], ids["tf"]]
    assert page[0]["category"] == "proliferation" and page[1]["category"] == "terrorism"
    # PEP and other rank below every sanction, so they are what falls off the page.
    assert ids["pep"] not in {a["id"] for a in page}


def test_order_is_category_then_score_then_id_and_matches_category_rank(api):
    org_id, ids, _ = _seed_queue()
    conn = _db()
    full = queries.alert_queue(conn, org_id, status="open", limit=1000)
    conn.close()
    assert len(full) == N_SANCTION + 4
    keys = [(queries.CATEGORY_RANK[queries._category(a["topics"], a["programs"])], -a["score"], a["id"])
            for a in full]
    assert keys == sorted(keys)
    assert [a["category"] for a in full[-2:]] == ["pep", "other"]


def test_paging_is_stable_and_complete_with_no_duplicates(api):
    org_id, ids, other = _seed_queue()
    conn = _db()
    seen, offset = [], 0
    while True:
        page = queries.alert_queue(conn, org_id, status="open", limit=50, offset=offset)
        if not page:
            break
        seen += [a["id"] for a in page]
        offset += 50
    whole = [a["id"] for a in queries.alert_queue(conn, org_id, status="open", limit=1000)]
    conn.close()
    assert seen == whole                                  # same order as one big page
    assert sorted(seen) == sorted(_all_ids(org_id))       # no gaps
    assert len(set(seen)) == len(seen)                    # no duplicates
    assert not set(seen) & set(other)                     # org isolation


def test_category_filter_keeps_its_order_and_offset(api):
    org_id, ids, _ = _seed_queue()
    conn = _db()
    sanc = queries.alert_queue(conn, org_id, status="open", limit=5, category="sanction")
    sanc2 = queries.alert_queue(conn, org_id, status="open", limit=5, offset=5, category="sanction")
    pf = queries.alert_queue(conn, org_id, status="open", category="proliferation")
    conn.close()
    assert all(a["category"] == "sanction" for a in sanc + sanc2)
    assert sanc[0]["score"] > sanc[-1]["score"] > sanc2[0]["score"]
    assert [a["id"] for a in pf] == [ids["pf"]]


def test_mobile_api_puts_proliferation_first_and_pages_cleanly(api):
    client, headers = api
    org_id, ids, other = _seed_queue()
    first = client.get("/api/v1/alerts?limit=200", headers=headers).json()
    assert first["alerts"][0]["id"] == ids["pf"]
    assert first["alerts"][1]["id"] == ids["tf"]
    assert first["total"] == N_SANCTION + 4          # tenant-scoped total
    assert first["truncated"] is True

    seen, offset = [], 0
    while True:
        body = client.get(f"/api/v1/alerts?limit=60&offset={offset}", headers=headers).json()
        seen += [a["id"] for a in body["alerts"]]
        if not body["truncated"]:
            break
        offset += 60
    assert sorted(seen) == sorted(_all_ids(org_id)) and len(set(seen)) == len(seen)
    assert not set(seen) & set(other)
    assert seen[:2] == [ids["pf"], ids["tf"]]


@pytest.mark.parametrize("alerts_sort_by", [None, "age_asc"])
def test_dashboard_lists_proliferation_first_past_the_cap(api, alerts_sort_by):
    org_id, ids, _ = _seed_queue()
    conn = _db()
    d = queries.dashboard(conn, org_id, alerts_sort_by=alerts_sort_by)
    conn.close()
    assert d["alerts_truncated"] is True
    assert [a["id"] for a in d["open_alerts"][:2]] == [ids["pf"], ids["tf"]]


def test_mobile_dashboard_includes_the_proliferation_alert(api):
    client, headers = api
    org_id, ids, _ = _seed_queue()
    d = client.get("/api/v1/dashboard", headers=headers).json()
    assert d["open_alerts"][0]["id"] == ids["pf"]


def test_web_alerts_page_shows_proliferation_before_the_sanctions(mlro):
    org_id, ids, _ = _seed_queue()
    html = mlro.get("/alerts").text
    assert "PF Target" in html and "OrgB PF" not in html
    assert html.index("PF Target") < html.index("Sanction 0")
    assert html.index("TF Target") < html.index("Sanction 0")


# ------------------------------------------------------------------ L-19
def test_pep_alert_never_carries_the_freeze_note(api):
    org_id, ids, _ = _seed_queue()
    conn = _db()
    rows = {a["id"]: a for a in queries.alert_queue(conn, org_id, status=None, limit=1000)}
    conn.close()
    pep = rows[ids["pep"]]["obligation"]
    assert "freeze" not in pep.lower() and "tip off" not in pep.lower()
    assert "enhanced due diligence" in pep and "senior-management" in pep
    other = rows[ids["other"]]["obligation"]
    assert "freeze" not in other.lower() and "tip off" not in other.lower()


def test_sanctions_terrorism_and_proliferation_keep_the_freeze_note(api):
    org_id, ids, _ = _seed_queue()
    conn = _db()
    rows = {a["id"]: a for a in queries.alert_queue(conn, org_id, status=None, limit=1000)}
    conn.close()
    sanction = next(a for a in rows.values() if a["category"] == "sanction")
    assert "Freeze without delay" in sanction["obligation"] and "Do not tip off" in sanction["obligation"]
    assert "TERRORISM FINANCING" in rows[ids["tf"]]["obligation"]
    assert "Freeze without delay" in rows[ids["tf"]]["obligation"]
    assert "PROLIFERATION FINANCING" in rows[ids["pf"]]["obligation"]
    assert "Freeze without delay" in rows[ids["pf"]]["obligation"]


def test_screening_hit_obligation_is_category_aware():
    from amlkit.match.engine import Hit
    base = dict(entity_id=1, dataset="d", caption="c", schema_type="Person", score=0.9,
                matched_name="n", detail={})
    pep = Hit(topics=["role.pep"], programs=[], **base)
    sanction = Hit(topics=["sanction"], programs=[], **base)
    assert "freeze" not in pep.obligation.lower()
    assert "Freeze without delay" in sanction.obligation


# ------------------------------------------------------------ review follow-ups
def _small_org():
    """An empty org with one dataset, for tests that need only a few alerts."""
    conn = _db()
    org_id = conn.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()["id"]
    ds = upsert_dataset(conn, "small_list", "Small List", is_mandatory=True)
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=? WHERE id=?", (utcnow(), 10, ds))
    conn.commit()
    return conn, org_id, ds


class _ClosingConn:
    """Delegates to a real connection but, just before the page-load statement
    (the `a.id IN (...)` read), runs `before_page_load()` -- i.e. the data
    changes between the ordering read and the row fetch."""

    def __init__(self, conn, before_page_load):
        self._conn, self._hook, self._fired = conn, before_page_load, False

    def execute(self, sql, *args, **kw):
        if not self._fired and "a.id IN (" in sql:
            self._fired = True
            self._hook()
        return self._conn.execute(sql, *args, **kw)

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.mark.parametrize("sort_by", [None, "age_asc", "age_desc"])
def test_alert_closed_between_ordering_read_and_page_load_is_skipped(api, sort_by):
    conn, org_id, ds = _small_org()
    ids = [
        _insert_alert(conn, ds, org_id, 1, "A", ["sanction"], [], 0.90, created="2026-01-01T00:00:00+00:00"),
        _insert_alert(conn, ds, org_id, 2, "B", ["sanction"], [], 0.80, created="2026-01-02T00:00:00+00:00"),
        _insert_alert(conn, ds, org_id, 3, "C", ["sanction"], [], 0.70, created="2026-01-03T00:00:00+00:00"),
    ]
    conn.commit()
    order = ids[::-1] if sort_by == "age_desc" else ids
    before = queries.alert_queue(conn, org_id, status="open", limit=10, sort_by=sort_by)
    assert [a["id"] for a in before] == order
    victim = ids[1]

    def close_victim():
        other = _db()
        other.execute("UPDATE alerts SET status='closed' WHERE id=?", (victim,))
        other.commit()
        other.close()

    page = queries.alert_queue(_ClosingConn(conn, close_victim), org_id, status="open",
                               limit=10, sort_by=sort_by)   # must not raise KeyError
    assert [a["id"] for a in page] == [i for i in order if i != victim]
    conn.close()


def test_several_alerts_closed_between_reads_keep_the_survivor(api):
    conn, org_id, ds = _small_org()
    ids = [_insert_alert(conn, ds, org_id, i, f"P{i}", ["sanction"], [], 0.9 - i * 0.1) for i in range(3)]
    conn.commit()

    def close_first_two():
        other = _db()
        other.execute("UPDATE alerts SET status='closed' WHERE id IN (?,?)", ids[:2])
        other.commit()
        other.close()

    page = queries.alert_queue(_ClosingConn(conn, close_first_two), org_id, status="open", limit=10)
    assert [a["id"] for a in page] == [ids[2]]
    conn.close()


def test_age_order_uses_created_at_within_each_category(api):
    conn, org_id, ds = _small_org()

    def mk(i, name, topics, progs, day, score=0.9):
        return _insert_alert(conn, ds, org_id, i, name, topics, progs, score,
                             created=f"2026-01-{day:02d}T00:00:00+00:00")

    # Ids are NOT in date order, so id order and date order disagree.
    s_mid = mk(1, "S mid", ["sanction"], [], 10)
    s_old = mk(2, "S old", ["sanction"], [], 5)
    s_new = mk(3, "S new", ["sanction"], [], 20)
    s_tie = mk(4, "S tie", ["sanction"], [], 10)               # same date as s_mid
    pf_new = mk(5, "PF new", ["sanction"], ["NPWMD"], 28, 0.1)  # newest overall, still first
    pep_old = mk(6, "PEP old", ["role.pep"], [], 1)             # oldest overall, still last
    conn.commit()
    asc = [a["id"] for a in queries.alert_queue(conn, org_id, status="open", limit=50, sort_by="age_asc")]
    desc = [a["id"] for a in queries.alert_queue(conn, org_id, status="open", limit=50, sort_by="age_desc")]
    assert asc == [pf_new, s_old, s_mid, s_tie, s_new, pep_old]
    assert desc == [pf_new, s_new, s_tie, s_mid, s_old, pep_old]   # date ties: id DESC
    conn.close()


def test_offset_beyond_total_and_limit_zero_return_empty(api):
    conn, org_id, ds = _small_org()
    for i in range(3):
        _insert_alert(conn, ds, org_id, i, f"X{i}", ["sanction"], [], 0.9 - i * 0.1)
    conn.commit()
    assert len(queries.alert_queue(conn, org_id, status="open", limit=10)) == 3
    assert queries.alert_queue(conn, org_id, status="open", limit=10, offset=3) == []
    assert queries.alert_queue(conn, org_id, status="open", limit=10, offset=500) == []
    assert queries.alert_queue(conn, org_id, status="open", limit=0) == []
    assert queries.alert_queue(conn, org_id, status="open", limit=2, offset=2)[0]["matched_name"] == "X2"
    assert queries.alert_queue(conn, org_id, status="open", limit=10, category="pep") == []
    conn.close()


def _hit(topics, programs, entity_id=1):
    from amlkit.match.engine import Hit
    return Hit(entity_id=entity_id, dataset="d", caption="c", schema_type="Person",
               score=0.9, matched_name="n", topics=topics, detail={}, programs=programs)


@pytest.mark.parametrize("topics,programs,expected", [
    (["sanction", "role.pep.national"], [], "sanction"),         # sanction beats PEP
    (["role.pep"], ["NPWMD"], "proliferation"),                  # PF program beats PEP topic
    (["role.pep.national"], ["UN-SCISIL"], "terrorism"),
    (["sanction", "role.pep"], ["NPWMD"], "proliferation"),
    (["role.pep.national"], [], "pep"),
    (["role.pep"], [], "pep"),
    (["crime"], [], "other"),
    ([], [], "other"),
    (None, None, "other"),
    (None, ["NPWMD"], "proliferation"),
    (["sanction"], None, "sanction"),
])
def test_triage_category_precedence_and_none_inputs(topics, programs, expected):
    from amlkit.screening.pf import triage_category
    assert triage_category(topics, programs) == expected
    assert _hit(topics or [], programs or []).obligation  # never raises, never empty


@pytest.mark.parametrize("topics,programs", [
    (["sanction", "role.pep.national"], []),
    (["role.pep"], ["NPWMD"]),
    (["role.pep"], ["UN-SCISIL"]),
])
def test_pep_combined_with_a_designation_still_gets_the_freeze_text(topics, programs):
    ob = _hit(topics, programs).obligation
    assert "Freeze without delay" in ob and "Do not tip off" in ob
    assert "PEP match" not in ob


def test_plain_pep_gets_the_pep_text():
    from amlkit.screening.pf import PEP_OBLIGATION
    ob = _hit(["role.pep.national"], []).obligation
    assert ob == PEP_OBLIGATION and "freeze" not in ob.lower() and "tip off" not in ob.lower()


def test_hit_obligation_for_terrorism_and_other():
    from amlkit.screening.pf import OTHER_OBLIGATION
    tf = _hit(["sanction"], ["UN-SCISIL"]).obligation
    assert "TERRORISM FINANCING" in tf and "Freeze without delay" in tf
    other = _hit(["crime"], []).obligation
    assert other == OTHER_OBLIGATION
    assert "freeze" not in other.lower() and "tip off" not in other.lower()
    assert _hit([], []).obligation == OTHER_OBLIGATION


def test_multi_topic_entities_rank_and_word_by_the_stronger_category(api):
    """sanction+PEP ranks as sanction; PEP + a PF programme ranks as
    proliferation; both get freeze text. A plain PEP ranks below them."""
    conn, org_id, ds = _small_org()
    pep = _insert_alert(conn, ds, org_id, 1, "Plain PEP", ["role.pep.national"], [], 0.99)
    sanc_pep = _insert_alert(conn, ds, org_id, 2, "Sanction+PEP", ["role.pep", "sanction"], [], 0.50)
    pf_pep = _insert_alert(conn, ds, org_id, 3, "PF+PEP", ["role.pep"], ["NPWMD"], 0.40)
    conn.commit()
    page = queries.alert_queue(conn, org_id, status="open", limit=10)
    assert [a["id"] for a in page] == [pf_pep, sanc_pep, pep]
    assert [a["category"] for a in page] == ["proliferation", "sanction", "pep"]
    assert all("Freeze without delay" in a["obligation"] for a in page[:2])
    assert "freeze" not in page[2]["obligation"].lower()
    conn.close()


@pytest.mark.parametrize("topics,programs,expected", [
    (["role.pep.national"], [], "pep"),
    (["sanction", "role.pep"], [], "sanction"),
    (["role.pep"], ["NPWMD"], "proliferation"),
    (["sanction"], ["UN-SCISIL"], "terrorism"),
    (["crime"], [], "other"),
])
def test_screen_hit_json_category_agrees_with_obligation_and_queue(api, topics, programs, expected):
    """The mobile /screen hit tag comes from the same triage_category as the
    queue's and as the obligation text, so a PEP is no longer tagged 'other'."""
    from amlkit.api.mobile import _hit_json
    from amlkit.screening.pf import PEP_OBLIGATION
    conn, org_id, ds = _small_org()
    aid = _insert_alert(conn, ds, org_id, 1, "Q", topics, programs, 0.9)
    conn.commit()
    row = queries.alert_queue(conn, org_id, status="open", alert_id=aid)[0]
    eid = conn.execute("SELECT entity_id FROM alerts WHERE id=?", (aid,)).fetchone()["entity_id"]
    hj = _hit_json(conn, _hit(topics, programs, entity_id=eid))
    assert hj["category"] == row["category"] == expected
    assert hj["obligation"] == row["obligation"]
    assert (hj["obligation"] == PEP_OBLIGATION) == (expected == "pep")
    conn.close()
