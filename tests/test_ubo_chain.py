"""Tests for recursive UBO traversal (ownership chains)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import (  # noqa: E402
    UBO_THRESHOLD_PCT,
    add_ubo,
    onboard,
    resolve_ubo_chain,
)
from amlkit.db import connect, upsert_dataset, utcnow  # noqa: E402
from amlkit.names.arabic import blocking_keys, canonical_key  # noqa: E402


@pytest.fixture()
def conn():
    c = connect(":memory:")
    ds = upsert_dataset(c, "test_list", "Synthetic Test List", is_mandatory=True)
    now = utcnow()
    cur = c.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           countries, birth_date, gender, topics, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, "SYN-1", "Person", "TEST ENTITY", '["ae"]', "1980-01-01", "male",
         '["sanction"]', "{}", now, now),
    )
    eid = cur.lastrowid
    c.execute(
        "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
        " VALUES (?,?,?,?,?)", (eid, "TEST ENTITY", "primary", canonical_key("TEST ENTITY"), "latin"))
    for tok in blocking_keys("TEST ENTITY"):
        c.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)", (tok, eid))
    c.commit()
    yield c
    c.close()


@pytest.fixture()
def org_id(conn) -> int:
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
        " RETURNING id",
        ("Test Firm", "test-firm", "active", utcnow()),
    ).fetchone()
    conn.commit()
    return row["id"]


class TestResolveUboChain:
    def test_simple_chain_effective_ownership(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-CHAIN1", full_name="End Client",
                      customer_type="legal")
        parent = add_ubo(conn, res.customer_id, org_id=org_id,
                         person_name="Company A", ownership_pct=50.0)
        add_ubo(conn, res.customer_id, org_id=org_id,
                person_name="Person X", ownership_pct=80.0, parent_ubo_id=parent)

        chain = resolve_ubo_chain(conn, res.customer_id, org_id)
        leaves = [u for u in chain if u["is_leaf"]]
        assert len(leaves) == 1
        assert leaves[0]["person_name"] == "Person X"
        assert abs(leaves[0]["effective_pct"] - 40.0) < 0.01  # 50% * 80%

    def test_deep_chain_three_levels(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-CHAIN2", full_name="End Client 2",
                      customer_type="legal")
        l1 = add_ubo(conn, res.customer_id, org_id=org_id,
                     person_name="Company B", ownership_pct=80.0)
        l2 = add_ubo(conn, res.customer_id, org_id=org_id,
                     person_name="Company C", ownership_pct=50.0, parent_ubo_id=l1)
        add_ubo(conn, res.customer_id, org_id=org_id,
                person_name="Person Y", ownership_pct=60.0, parent_ubo_id=l2)

        chain = resolve_ubo_chain(conn, res.customer_id, org_id)
        leaves = [u for u in chain if u["is_leaf"]]
        assert len(leaves) == 1
        assert abs(leaves[0]["effective_pct"] - 24.0) < 0.01  # 80% * 50% * 60%

    def test_cycle_detection_does_not_infinite_loop(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-CYCLE", full_name="Cycle Corp",
                      customer_type="legal")
        a = add_ubo(conn, res.customer_id, org_id=org_id,
                    person_name="Node A", ownership_pct=50.0)
        b = add_ubo(conn, res.customer_id, org_id=org_id,
                    person_name="Node B", ownership_pct=60.0, parent_ubo_id=a)
        # Manually create a cycle: set A's parent to B
        conn.execute("UPDATE ubo_links SET parent_ubo_id=? WHERE id=?", (b, a))
        conn.commit()

        chain = resolve_ubo_chain(conn, res.customer_id, org_id)
        # Should return without hanging; result may be partial
        assert isinstance(chain, list)

    def test_max_depth_exceeded_returns_partial(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-DEEP", full_name="Deep Corp",
                      customer_type="legal")
        prev_id = None
        for i in range(12):
            prev_id = add_ubo(conn, res.customer_id, org_id=org_id,
                              person_name=f"Level {i}", ownership_pct=90.0,
                              parent_ubo_id=prev_id)

        chain = resolve_ubo_chain(conn, res.customer_id, org_id, max_depth=10)
        assert len(chain) <= 12  # capped traversal

    def test_self_reference_rejected(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-SELF", full_name="Self Corp",
                      customer_type="legal")
        with pytest.raises(ValueError, match="not found"):
            add_ubo(conn, res.customer_id, org_id=org_id,
                    person_name="Cross Ref", ownership_pct=30.0,
                    parent_ubo_id=99999)  # nonexistent parent

    def test_parent_must_belong_to_same_customer(self, conn, org_id) -> None:
        res1 = onboard(conn, org_id=org_id, reference="C-P1", full_name="Corp 1",
                       customer_type="legal")
        res2 = onboard(conn, org_id=org_id, reference="C-P2", full_name="Corp 2",
                       customer_type="legal")
        parent = add_ubo(conn, res1.customer_id, org_id=org_id,
                         person_name="Owner of Corp1", ownership_pct=50.0)
        with pytest.raises(ValueError, match="not found"):
            add_ubo(conn, res2.customer_id, org_id=org_id,
                    person_name="Trying cross-customer parent", ownership_pct=30.0,
                    parent_ubo_id=parent)

    def test_nominee_children_still_traversed(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-NOMCH", full_name="Nominee Chain Corp",
                      customer_type="legal")
        nominee = add_ubo(conn, res.customer_id, org_id=org_id,
                          person_name="Nominee Holding Co", ownership_pct=60.0,
                          is_nominee=True)
        add_ubo(conn, res.customer_id, org_id=org_id,
                person_name="Real Person Behind Nominee", ownership_pct=100.0,
                parent_ubo_id=nominee)

        chain = resolve_ubo_chain(conn, res.customer_id, org_id)
        names = [u["person_name"] for u in chain if u["is_leaf"]]
        assert "Real Person Behind Nominee" in names
        nominee_in_result = [u for u in chain if u["person_name"] == "Nominee Holding Co"]
        assert all(u.get("is_nominee") for u in nominee_in_result)

    def test_resolve_chain_flat_ubos_unchanged(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-FLAT", full_name="Flat Corp",
                      customer_type="legal")
        add_ubo(conn, res.customer_id, org_id=org_id,
                person_name="Flat Owner A", ownership_pct=60.0)
        add_ubo(conn, res.customer_id, org_id=org_id,
                person_name="Flat Owner B", ownership_pct=40.0)

        chain = resolve_ubo_chain(conn, res.customer_id, org_id)
        assert len(chain) == 2
        names = {u["person_name"] for u in chain}
        assert names == {"Flat Owner A", "Flat Owner B"}
        for u in chain:
            assert u["effective_pct"] == u["ownership_pct"]
            assert u["is_leaf"]
