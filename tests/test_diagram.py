"""UBO ownership diagram generation.

Regression coverage for the unescaped-name Graphviz bug: customer/UBO names
were interpolated raw into HTML-like table labels, so a name containing a
literal &, <, or > (not unusual in real company names, e.g. "Al Futtaim &
Sons") broke the label's pseudo-XML syntax, dot.pipe() raised, and the bare
except swallowed it -- the diagram silently disappeared from customer.html
for that customer with no error surfaced anywhere.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.diagram import generate_ubo_diagram  # noqa: E402
from amlkit.cases.manager import add_ubo, onboard  # noqa: E402
from amlkit.db import connect, upsert_dataset, utcnow  # noqa: E402


@pytest.fixture()
def org_id(conn) -> int:
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
        " RETURNING id",
        ("Test Firm", "test-firm", "active", utcnow()),
    ).fetchone()
    conn.commit()
    return row["id"]


@pytest.fixture()
def conn():
    c = connect(":memory:")
    # Create a fresh mandatory dataset so onboard() passes the staleness guard
    ds = upsert_dataset(c, "test_list", "Test List", is_mandatory=True)
    now = utcnow()
    c.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    c.commit()
    yield c
    c.close()


class TestUboDiagram:
    def test_ampersand_and_angle_brackets_in_names_do_not_break_generation(
        self, conn, org_id
    ) -> None:
        res = onboard(conn, org_id=org_id, reference="C-1",
                      full_name="Al Futtaim & Sons <Trading>", customer_type="legal")
        add_ubo(conn, res.customer_id, org_id=org_id, person_name="O'Brien & <Co>",
               ownership_pct=100.0)

        svg = generate_ubo_diagram(conn, res.customer_id, org_id)
        assert svg is not None, "diagram generation must not fail on special characters in names"
        assert "Al Futtaim &amp; Sons &lt;Trading&gt;" in svg
        assert "&amp; &lt;Co&gt;" in svg

    def test_normal_names_still_render(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-2", full_name="Desert Rose Trading LLC",
                      customer_type="legal")
        add_ubo(conn, res.customer_id, org_id=org_id, person_name="Ahmed Al Mansoori",
               ownership_pct=60.0)

        svg = generate_ubo_diagram(conn, res.customer_id, org_id)
        assert svg is not None
        assert "Desert Rose Trading LLC" in svg
        assert "Ahmed Al Mansoori" in svg

    def test_unknown_customer_returns_none(self, conn, org_id) -> None:
        assert generate_ubo_diagram(conn, 999, org_id) is None
