"""Tenant isolation tests for toolbox/tools.yaml (finding #10, 2026-09-21
deployed-site review): search_customers, get_alerts and get_screenings had
no org_id parameter at all, so any MCP client using the toolbox config could
read every tenant's customers, alerts and screenings.

These tests both statically check the YAML (every tenant-table tool declares
and uses an org_id parameter) and actually execute the literal SQL strings
from the file against a real two-tenant database, the same way the
genai-toolbox binary would, to prove the isolation holds in practice.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect, utcnow  # noqa: E402

TOOLS_YAML = Path(__file__).resolve().parent.parent / "toolbox" / "tools.yaml"

# Tools whose queries touch a tenant table and must therefore be org-scoped.
TENANT_SCOPED_TOOLS = ("search_customers", "get_alerts", "get_screenings")


def _load_tools() -> dict:
    return yaml.safe_load(TOOLS_YAML.read_text())["tools"]


class TestToolboxConfigDeclaresOrgId:
    def test_tenant_scoped_tools_declare_an_org_id_parameter(self) -> None:
        tools = _load_tools()
        for name in TENANT_SCOPED_TOOLS:
            param_names = [p["name"] for p in tools[name]["parameters"]]
            assert "org_id" in param_names, (
                f"{name} touches a tenant table but declares no org_id parameter"
            )

    def test_tenant_scoped_tools_filter_by_org_id_in_sql(self) -> None:
        tools = _load_tools()
        for name in TENANT_SCOPED_TOOLS:
            statement = tools[name]["statement"].lower()
            assert "org_id" in statement, (
                f"{name}'s SQL statement never references org_id: {statement!r}"
            )

    def test_list_datasets_has_no_org_id(self) -> None:
        """Sanity check: list_datasets is shared reference data (datasets are
        not tenant-owned, same as elsewhere in this codebase), so it should
        NOT gain an org_id parameter -- there's nothing to scope it to."""
        tools = _load_tools()
        param_names = [p["name"] for p in tools["list_datasets"].get("parameters", [])]
        assert "org_id" not in param_names


@pytest.fixture()
def two_org_db(tmp_path):
    """A real amlkit database with two orgs, each with one customer, one
    screening and one alert, so the literal toolbox SQL can be executed
    against it exactly as genai-toolbox would."""
    db_file = tmp_path / "toolbox_test.db"
    conn = connect(str(db_file))
    now = utcnow()

    orgs = {}
    for slug in ("firm-a", "firm-b"):
        row = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id",
            (slug, slug, "active", now),
        ).fetchone()
        orgs[slug] = row["id"]

    customers = {}
    for slug, org_id in orgs.items():
        row = conn.execute(
            """INSERT INTO customers
               (org_id, reference, full_name, customer_type, canonical_key, status,
                onboarded_at, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?) RETURNING id""",
            (org_id, f"C-{slug}", f"Ahmed of {slug}", "natural", f"ahmed_of_{slug}",
             "active", now, now, now),
        ).fetchone()
        customers[slug] = row["id"]

        ds = conn.execute(
            "INSERT INTO datasets (key, title, is_mandatory) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET title=excluded.title RETURNING id",
            (f"test_list_{slug}", "Test List", 1),
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO entities (dataset_id, source_id, schema_type, caption, first_seen, last_seen) "
            "VALUES (?,?,?,?,?,?)",
            (ds, f"ent-{slug}", "Person", f"Listed {slug}", now, now),
        )
        entity_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        scr = conn.execute(
            """INSERT INTO screenings (org_id, customer_id, query_name, trigger, algorithm, threshold, run_at)
               VALUES (?,?,?,?,?,?,?) RETURNING id""",
            (org_id, customers[slug], f"Ahmed of {slug}", "onboarding", "weighted", 0.65, now),
        ).fetchone()["id"]
        conn.execute(
            """INSERT INTO alerts (org_id, screening_id, entity_id, score, score_detail,
                                   matched_name, status, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (org_id, scr, entity_id, 0.9, "{}", f"Listed {slug}", "open", now),
        )
    conn.commit()

    return conn, orgs, customers


class TestToolboxQueriesActuallyIsolateTenants:
    """Executes the literal SQL from tools.yaml, positional-binding
    parameters in the declared order, exactly as genai-toolbox does."""

    def _run(self, conn: sqlite3.Connection, tool: str, *params) -> list[sqlite3.Row]:
        tools = _load_tools()
        return conn.execute(tools[tool]["statement"], params).fetchall()

    def test_search_customers_is_scoped_to_its_own_org(self, two_org_db) -> None:
        conn, orgs, customers = two_org_db
        rows = self._run(conn, "search_customers", orgs["firm-a"], "Ahmed")
        names = {r["full_name"] for r in rows}
        assert names == {"Ahmed of firm-a"}, (
            f"search_customers leaked another org's customer: {names}"
        )

    def test_get_alerts_is_scoped_to_its_own_org(self, two_org_db) -> None:
        conn, orgs, customers = two_org_db
        # firm-a's org_id with firm-b's customer_id must return nothing.
        rows = self._run(conn, "get_alerts", orgs["firm-a"], customers["firm-b"])
        assert rows == [], "get_alerts returned another org's alerts"

        rows_own = self._run(conn, "get_alerts", orgs["firm-a"], customers["firm-a"])
        assert len(rows_own) == 1

    def test_get_screenings_is_scoped_to_its_own_org(self, two_org_db) -> None:
        conn, orgs, customers = two_org_db
        rows = self._run(conn, "get_screenings", orgs["firm-a"], customers["firm-b"])
        assert rows == [], "get_screenings returned another org's screenings"

        rows_own = self._run(conn, "get_screenings", orgs["firm-a"], customers["firm-a"])
        assert len(rows_own) == 1
