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
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit import queries  # noqa: E402
from amlkit.db import upsert_dataset, utcnow  # noqa: E402
from tests.test_dashboard_alert_lines import _db, mlro  # noqa: E402,F401  (fixture)
from tests.test_mobile_api import api  # noqa: E402,F401  (fixture)

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
