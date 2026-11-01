"""UBO ownership validation + property-based tests (Issue #253).

One validator (datamodel.validate_ownership_pct) is used by the web routes,
the mobile models and cases.manager.add_ubo/onboard. The property tests drive
ownership_state() and the diagram with random structures: totals never exceed
100, no owner is counted twice, nothing raises.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases import manager  # noqa: E402
from amlkit.cases.diagram import generate_ubo_diagram  # noqa: E402
from amlkit.cases.manager import _identified_ownership, add_ubo, ownership_state  # noqa: E402
from amlkit.datamodel import validate_ownership_pct  # noqa: E402
from amlkit.db import connect  # noqa: E402


# ------------------------------------------------------------ the validator
@pytest.mark.parametrize("bad", [-0.01, -5, 100.01, 250, float("nan"), float("inf"), -float("inf"), "abc", True])
def test_validator_rejects_bad_values(bad):
    with pytest.raises(ValueError):
        validate_ownership_pct(bad)


def test_validator_combined_total():
    assert validate_ownership_pct(40, 60) == 40.0
    with pytest.raises(ValueError, match="cannot exceed 100"):
        validate_ownership_pct(40.01, 60)
    assert validate_ownership_pct(None, 99) is None
    assert validate_ownership_pct("", 99) is None
    assert validate_ownership_pct("25.5") == 25.5


@given(v=st.floats(allow_nan=True, allow_infinity=True), existing=st.floats(min_value=0, max_value=100))
def test_validator_never_raises_anything_but_valueerror(v, existing):
    try:
        out = validate_ownership_pct(v, existing)
    except ValueError:
        return
    assert math.isfinite(out) and 0 <= out <= 100 and round(out + existing, 2) <= 100


# ------------------------------------------------------------ DB-level
@pytest.fixture()
def conn(tmp_path):
    c = connect(tmp_path / "u.db")
    c.execute("INSERT INTO organizations (name, slug, created_at) VALUES ('O', 'o', '2026-01-01')")
    c.execute("INSERT INTO customers (org_id, reference, full_name, canonical_key, customer_type, onboarded_at, created_at, updated_at)"
              " VALUES (1, 'C1', 'Holding LLC', 'holding llc', 'legal', '2026-01-01', '2026-01-01', '2026-01-01')")
    c.commit()
    yield c
    c.close()


def test_add_ubo_rejects_each_bad_case(conn):
    for bad in (-1, 100.5, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            add_ubo(conn, 1, org_id=1, person_name="X", ownership_pct=bad)
    add_ubo(conn, 1, org_id=1, person_name="A", ownership_pct=60)
    with pytest.raises(ValueError, match="cannot exceed 100"):
        add_ubo(conn, 1, org_id=1, person_name="B", ownership_pct=40.5)
    assert conn.execute("SELECT COUNT(*) FROM ubo_links").fetchone()[0] == 1


def test_chain_does_not_double_count(conn):
    corp = add_ubo(conn, 1, org_id=1, person_name="Corp A", ownership_pct=60, control_type="ownership")
    add_ubo(conn, 1, org_id=1, person_name="Person P", ownership_pct=50, parent_ubo_id=corp)
    rows = conn.execute("SELECT * FROM ubo_links").fetchall()
    assert _identified_ownership(rows) == pytest.approx(30.0)  # 60% x 50%, not 60 + 50
    assert ownership_state(conn, 1, 1) == "multi_layer_offshore"


# --------------------------------------------------------- property tests
def _build_conn():
    c = connect(":memory:")
    c.execute("INSERT INTO organizations (name, slug, created_at) VALUES ('O', 'o', '2026-01-01')")
    c.execute("INSERT INTO customers (org_id, reference, full_name, canonical_key, customer_type, onboarded_at, created_at, updated_at)"
              " VALUES (1, 'C1', 'Holding LLC', 'holding llc', 'legal', '2026-01-01', '2026-01-01', '2026-01-01')")
    c.commit()
    return c


_SHARED = None


def _fresh_conn():
    """One in-memory DB for all examples (building one per example is slow); ubo_links is emptied each time."""
    global _SHARED
    if _SHARED is None:
        _SHARED = _build_conn()
    _SHARED.execute("DELETE FROM ubo_links")
    _SHARED.commit()
    return _SHARED


names = st.sampled_from(["Ali Hassan", "Sara Khan", "Omar Said", "Lina Haddad", "Acme Holdings"])
pct = st.one_of(st.none(), st.floats(min_value=0, max_value=100, allow_nan=False))
controls = st.sampled_from(["ownership", "senior_official", "other"])

# (name, pct, control, is_nominee, parent index into earlier entries or None)
entries = st.lists(
    st.tuples(names, pct, controls, st.booleans(), st.one_of(st.none(), st.integers(0, 7))),
    max_size=8,
)


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(entries=entries)
def test_random_structures_hold_invariants(entries):
    conn = _fresh_conn()
    ids: list[int] = []
    for name, p, control, nominee, parent_ix in entries:
        parent = ids[parent_ix] if parent_ix is not None and parent_ix < len(ids) else None
        try:
            ids.append(add_ubo(conn, 1, org_id=1, person_name=name, ownership_pct=p, control_type=control,
                               is_nominee=nominee, parent_ubo_id=parent))
        except ValueError:
            continue  # rejected by validation (e.g. total > 100): fine, never a crash
    # direct stakes can never exceed 100 in storage
    direct = conn.execute(
        "SELECT COALESCE(SUM(ownership_pct),0) FROM ubo_links WHERE parent_ubo_id IS NULL").fetchone()[0]
    assert round(direct, 2) <= 100
    rows = conn.execute("SELECT * FROM ubo_links").fetchall()
    ident = _identified_ownership(rows)
    assert 0 <= ident <= 100
    # corporate owners with children are never counted themselves: each counted row is a leaf
    assert ident <= sum(r["ownership_pct"] or 0 for r in rows) + 1e-9
    assert ownership_state(conn, 1, 1) in {
        "ubo_undisclosed", "nominee_or_bearer", "multi_layer_offshore",
        "single_layer_foreign", "fully_transparent"}
    svg = generate_ubo_diagram(conn, 1, 1)
    assert svg is None or "<svg" in svg


@settings(max_examples=100, deadline=None)
@given(pcts=st.lists(st.floats(min_value=0, max_value=100, allow_nan=False), min_size=1, max_size=5),
       child=st.floats(min_value=0, max_value=100, allow_nan=False))
def test_two_level_chain_effective_share_is_product(pcts, child):
    """Corporate owner at level 1, natural person inside it at level 2: the person's
    share is the product, the corporate row is not added on top, and the total <= 100."""
    conn = _fresh_conn()
    total = 0.0
    corp = None
    for i, p in enumerate(pcts):
        if round(total + p, 2) > 100:
            break
        total += p
        cid = add_ubo(conn, 1, org_id=1, person_name=f"Corp {i}", ownership_pct=p)
        corp = corp if corp is not None else (cid, p)
    if corp is None:
        return
    add_ubo(conn, 1, org_id=1, person_name="Person Z", ownership_pct=child, parent_ubo_id=corp[0])
    rows = conn.execute("SELECT * FROM ubo_links").fetchall()
    ident = _identified_ownership(rows)
    assert ident <= 100 + 1e-9
    assert ident <= total + 1e-9  # looking through a corporate never adds ownership


@settings(max_examples=100, deadline=None)
@given(p=st.floats(min_value=25, max_value=100, allow_nan=False), n=st.integers(2, 4))
def test_duplicate_owner_under_same_parent_counted_once(p, n):
    conn = _fresh_conn()
    kept = 0
    for _ in range(n):
        try:
            add_ubo(conn, 1, org_id=1, person_name="Ali Hassan", ownership_pct=p / n if p / n >= 25 else p)
            kept += 1
        except ValueError:
            break
    rows = conn.execute("SELECT * FROM ubo_links").fetchall()
    assert _identified_ownership(rows) <= max(r["ownership_pct"] for r in rows) + 1e-9


# ------------------------------------------------------------ HTTP boundary
from tests.test_ubo_http_validation import api  # noqa: E402,F401  (fixture)


def test_mobile_add_ubo_total_and_range_are_422_not_500(api):
    client, headers = api
    r = client.post("/api/v1/customers", headers=headers, json={
        "reference": "C-P1", "full_name": "Prop Corp", "customer_type": "legal",
        "ubos": [{"person_name": "Owner A", "ownership_pct": 70.0}]})
    assert r.status_code == 200, r.text
    cid = r.json()["customer_id"]
    for pct, code in ((-1, 422), (100.5, 422), (40, 422), (30, 200)):
        r = client.post(f"/api/v1/customers/{cid}/ubo", headers=headers,
                        json={"person_name": "Owner B", "ownership_pct": pct})
        assert r.status_code == code, (pct, r.status_code, r.text)
