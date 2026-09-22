"""Tenant isolation tests (Issue #71).

Two layers of defence:

1. **Static analysis** — inspect source code of queries.py and cases/manager.py
   to ensure every SQL query touching a tenant-scoped table includes an org_id
   filter. Catches missing scoping before it reaches production.

2. **Runtime integration** — register two independent organisations and verify
   that operator A cannot read, write, or disposition operator B's data through
   any API route.
"""

from __future__ import annotations

import ast
import inspect
import os
import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# Tenant-scoped tables: every SQL touching these MUST include org_id filtering.
# Shared reference tables (datasets, entities, entity_names, name_tokens,
# entity_identifiers, auth_log) are intentionally excluded.
# ---------------------------------------------------------------------------
TENANT_TABLES = {
    "customers",
    "ubo_links",
    "screenings",
    "alerts",
    "alert_reviews",
    "risk_assessments",
    "documents",
    "case_notes",
    "transactions",
    "transaction_alerts",
    "adverse_media_screenings",
    "adverse_media_findings",
    "signatures",
    "reports",
    "freeze_obligations",
    "compliance_deadlines",
    "policy_documents",
    "feedback",
    "operators",
    "sessions",
    "setup_tokens",
    "org_settings",
}

# Functions that legitimately touch tenant tables without org_id in their
# own signature (they iterate orgs internally or are private helpers).
ALLOWED_EXCEPTIONS = {
    "console_overview",  # super-admin cross-org dashboard
    "_category",         # pure classification, no SQL
    "_prior_value",      # dict helper, no SQL
    "adverse_media_severity",  # pure classification, no SQL
    "_adverse_media_interval_months",  # pure lookup, no SQL
}

LISTED = "AHMED ABD AL-JALEEL AL-HASNAWI"


# ===================================================================
# Part 1: Static analysis — source inspection
# ===================================================================

def _extract_sql_strings(source: str) -> list[tuple[int, str]]:
    """Extract SQL string literals from Python source, excluding docstrings.

    Returns (line_number, sql_text) pairs for strings that are SQL statements
    (not docstrings or comments).
    """
    results = []
    tree = ast.parse(source)
    sql_keywords = re.compile(
        r"\b(SELECT|INSERT|UPDATE|DELETE)\b",
        re.IGNORECASE,
    )

    docstring_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                docstring_lines.add(node.body[0].value.lineno)

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.lineno in docstring_lines:
                continue
            if sql_keywords.search(node.value):
                results.append((node.lineno, node.value))
        elif isinstance(node, ast.JoinedStr):
            parts = []
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    parts.append(v.value)
                else:
                    parts.append("?")
            combined = "".join(parts)
            if sql_keywords.search(combined):
                results.append((node.lineno, combined))
    return results


def _mentions_tenant_table(sql: str) -> set[str]:
    """Return set of tenant-scoped tables mentioned in an SQL statement."""
    sql_upper = sql.upper()
    found = set()
    for table in TENANT_TABLES:
        pattern = rf"\b{re.escape(table.upper())}\b"
        if re.search(pattern, sql_upper):
            found.add(table)
    return found


def _has_org_id_filter(sql: str) -> bool:
    """Check if an SQL statement filters by org_id."""
    return bool(re.search(r"\borg_id\b", sql, re.IGNORECASE))


# SQL statements that are safe despite not having org_id directly in the
# WHERE clause. These are validated by prior org_id checks in the same
# function, or operate on IDs that are inherently org-scoped (e.g.,
# session.operator_id from a validated session).
SAFE_SQL_PATTERNS = [
    # UBO self-reference cleanup: add_ubo() already validated org_id
    r"DELETE FROM ubo_links WHERE id=\?",
    # Operator deactivation: prior query validates org_id ownership
    r"UPDATE operators SET is_active=0 WHERE id=\?",
    # Password lookups: session.operator_id is inherently org-scoped
    r"SELECT password_hash FROM operators WHERE id=\?",
    r"SELECT id, password_hash FROM operators WHERE id=\?",
    # Freeze obligation update: freeze_id already validated with org_id
    r"UPDATE freeze_obligations\s+SET report_id",
]
_SAFE_PATTERNS_RE = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in SAFE_SQL_PATTERNS]


def _is_safe_exception(sql: str) -> bool:
    """Check if an SQL statement matches a known safe pattern."""
    normalized = " ".join(sql.split())
    return any(p.search(normalized) for p in _SAFE_PATTERNS_RE)


class TestStaticQueryInspection:
    """Inspect queries.py and cases/manager.py source code to verify every
    SQL query touching a tenant table includes org_id filtering."""

    def test_queries_module_all_tenant_sql_includes_org_id(self):
        from amlkit import queries
        source = inspect.getsource(queries)
        sql_strings = _extract_sql_strings(source)

        violations = []
        for lineno, sql in sql_strings:
            if "CREATE TABLE" in sql.upper() or "CREATE INDEX" in sql.upper():
                continue
            tables = _mentions_tenant_table(sql)
            if tables and not _has_org_id_filter(sql) and not _is_safe_exception(sql):
                violations.append(
                    f"  line {lineno}: touches {tables} without org_id filter:\n"
                    f"    {sql[:120].strip()}"
                )

        assert not violations, (
            f"queries.py has {len(violations)} SQL statement(s) touching tenant "
            f"tables without org_id:\n" + "\n".join(violations)
        )

    def test_manager_module_all_tenant_sql_includes_org_id(self):
        from amlkit.cases import manager
        source = inspect.getsource(manager)
        sql_strings = _extract_sql_strings(source)

        violations = []
        for lineno, sql in sql_strings:
            if "CREATE TABLE" in sql.upper() or "CREATE INDEX" in sql.upper():
                continue
            tables = _mentions_tenant_table(sql)
            if tables and not _has_org_id_filter(sql) and not _is_safe_exception(sql):
                violations.append(
                    f"  line {lineno}: touches {tables} without org_id filter:\n"
                    f"    {sql[:120].strip()}"
                )

        assert not violations, (
            f"cases/manager.py has {len(violations)} SQL statement(s) touching "
            f"tenant tables without org_id:\n" + "\n".join(violations)
        )

    def test_app_routes_all_tenant_sql_includes_org_id(self):
        from amlkit.api import app as app_module
        source = inspect.getsource(app_module)
        sql_strings = _extract_sql_strings(source)

        violations = []
        for lineno, sql in sql_strings:
            if "CREATE TABLE" in sql.upper() or "CREATE INDEX" in sql.upper():
                continue
            tables = _mentions_tenant_table(sql)
            if tables and not _has_org_id_filter(sql) and not _is_safe_exception(sql):
                violations.append(
                    f"  line {lineno}: touches {tables} without org_id filter:\n"
                    f"    {sql[:120].strip()}"
                )

        assert not violations, (
            f"api/app.py has {len(violations)} SQL statement(s) touching "
            f"tenant tables without org_id:\n" + "\n".join(violations)
        )


class TestFunctionSignatures:
    """Every public function in queries.py and manager.py that touches tenant
    tables must require org_id in its signature (no default value)."""

    def test_queries_public_functions_require_org_id(self):
        from amlkit import queries
        source = inspect.getsource(queries)
        tree = ast.parse(source)

        violations = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name.startswith("_") or node.name in ALLOWED_EXCEPTIONS:
                continue

            body_source = ast.get_source_segment(source, node)
            if not body_source:
                continue

            sql_strings = _extract_sql_strings(body_source)
            touches_tenant = any(
                _mentions_tenant_table(sql) for _, sql in sql_strings
            )
            if not touches_tenant:
                continue

            arg_names = [a.arg for a in node.args.args]
            kwonly_names = [a.arg for a in node.args.kwonlyargs]
            all_params = arg_names + kwonly_names
            if "org_id" not in all_params:
                violations.append(
                    f"  {node.name}() at line {node.lineno}: touches tenant "
                    f"table but has no org_id parameter"
                )

        assert not violations, (
            f"queries.py has {len(violations)} function(s) touching tenant "
            f"tables without org_id parameter:\n" + "\n".join(violations)
        )

    def test_manager_public_functions_require_org_id(self):
        from amlkit.cases import manager
        source = inspect.getsource(manager)
        tree = ast.parse(source)

        violations = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name.startswith("_") or node.name in ALLOWED_EXCEPTIONS:
                continue

            body_source = ast.get_source_segment(source, node)
            if not body_source:
                continue

            sql_strings = _extract_sql_strings(body_source)
            touches_tenant = any(
                _mentions_tenant_table(sql) for _, sql in sql_strings
            )
            if not touches_tenant:
                continue

            arg_names = [a.arg for a in node.args.args]
            kwonly_names = [a.arg for a in node.args.kwonlyargs]
            all_params = arg_names + kwonly_names
            if "org_id" not in all_params:
                violations.append(
                    f"  {node.name}() at line {node.lineno}: touches tenant "
                    f"table but has no org_id parameter"
                )

        assert not violations, (
            f"cases/manager.py has {len(violations)} function(s) touching "
            f"tenant tables without org_id parameter:\n" + "\n".join(violations)
        )


class TestDbAuditOrgIdEnforcement:
    """The db.audit() function must require org_id structurally."""

    def test_audit_rejects_missing_org_id(self, tmp_path):
        from amlkit.db import audit, connect
        db_path = tmp_path / "audit_test.db"
        conn = connect(str(db_path))
        try:
            with pytest.raises(TypeError):
                audit(conn, action="test.action", detail="should fail")
        finally:
            conn.close()


# ===================================================================
# Part 2: Runtime integration — cross-tenant access tests
# ===================================================================

def _seed_sanctions_data(db_file) -> None:
    from amlkit.db import connect, upsert_dataset, utcnow
    from amlkit.names.arabic import blocking_keys, canonical_key

    conn = connect(db_file)
    ds = upsert_dataset(conn, "test_list", "Test Sanctions List", is_mandatory=True)
    now = utcnow()
    cur = conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption, countries,
           birth_date, gender, topics, programs, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, "T-1", "Person", LISTED, '["ly"]', "1975-03-12", "male",
         '["sanction"]', '["AE-UNSC1373"]', "{}", now, now),
    )
    eid = cur.lastrowid
    for nm in [LISTED]:
        conn.execute(
            "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
            " VALUES (?,?,?,?,?)",
            (eid, nm, "primary", canonical_key(nm), "latin"))
        for tok in blocking_keys(nm):
            conn.execute(
                "INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)",
                (tok, eid))
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    conn.commit()
    conn.close()


def _csrf(client) -> str:
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name: str, name: str, email: str,
              password: str = "a-strong-password-1"):
    import re as _re
    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client), "invite_code": "test-invite",
    }, follow_redirects=True)
    assert "Check your email" in r.text, f"registration failed: {r.text[:300]}"
    m = _re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m, f"no dev verification link: {r.text[:500]}"
    r2 = client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    from conftest import settle_mfa  # p15: MLRO sessions start locked
    settle_mfa(client)
    assert any(s in r2.text for s in ("Dashboard", "24-hour", "Two-Factor")), (
        f"verification failed: {r2.text[:300]}"
    )
    return client


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture()
def two_orgs(tmp_path, monkeypatch):
    """Two fully isolated organisations sharing the same database.

    Returns (client_a, client_b) — each logged in as MLRO of their org.
    """
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    app.state.limiter.enabled = False

    client_a = TestClient(app)
    _register(client_a, "Alpha Corp", "alice", "alice@alpha.ae")

    client_b = TestClient(app)
    _register(client_b, "Beta Corp", "bob", "bob@beta.ae")

    return client_a, client_b


class TestCrossTenantRuntimeIsolation:
    """Operator A must not be able to access operator B's data via any route."""

    def _create_customer(self, client, ref: str, name: str) -> int:
        client.post("/customers", data={
            "reference": ref, "full_name": name,
            "customer_type": "natural", "csrf_token": _csrf(client),
        }, follow_redirects=True)
        conn = _db()
        cid = conn.execute(
            "SELECT id FROM customers WHERE reference=?", (ref,)
        ).fetchone()["id"]
        conn.close()
        return cid

    def test_customer_list_isolated(self, two_orgs):
        client_a, client_b = two_orgs
        self._create_customer(client_a, "A-001", "Alpha Customer One")

        r = client_b.get("/customers")
        assert "Alpha Customer One" not in r.text

    def test_cross_org_customer_detail_returns_redirect(self, two_orgs):
        """Cross-tenant customer_id must be indistinguishable from nonexistent."""
        client_a, client_b = two_orgs
        cid = self._create_customer(client_a, "A-002", "Alpha Secret Client")

        r = client_b.get(f"/customers/{cid}", follow_redirects=False)
        assert r.status_code == 303

    def test_cross_org_customer_close_rejected(self, two_orgs):
        client_a, client_b = two_orgs
        cid = self._create_customer(client_a, "A-003", "Alpha Private")

        r = client_b.post(f"/customers/{cid}/close", data={
            "exit_reason": "customer_request",
            "csrf_token": _csrf(client_b),
        }, follow_redirects=False)
        assert r.status_code == 303

        conn = _db()
        status = conn.execute(
            "SELECT status FROM customers WHERE id=?", (cid,)
        ).fetchone()["status"]
        conn.close()
        assert status == "active", "cross-tenant close must not change status"

    def test_cross_org_case_note_rejected(self, two_orgs):
        client_a, client_b = two_orgs
        cid = self._create_customer(client_a, "A-004", "Alpha Notes Target")

        client_b.post(f"/customers/{cid}/notes", data={
            "body": "Cross-tenant note attempt",
            "csrf_token": _csrf(client_b),
        }, follow_redirects=True)

        conn = _db()
        count = conn.execute(
            "SELECT COUNT(*) c FROM case_notes WHERE customer_id=?", (cid,)
        ).fetchone()["c"]
        conn.close()
        assert count == 0, "cross-tenant note must not be written"

    def test_cross_org_alert_disposition_rejected(self, two_orgs):
        client_a, client_b = two_orgs
        client_a.post("/customers", data={
            "reference": "A-005", "full_name": "Falcon Iso FZE",
            "customer_type": "legal",
            "ubo_names": [LISTED], "ubo_pcts": ["60"],
            "ubo_controls": ["ownership"],
            "csrf_token": _csrf(client_a),
        }, follow_redirects=True)
        conn = _db()
        row = conn.execute(
            "SELECT id FROM alerts ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        assert row, "no alert created"
        alert_id = row["id"]

        client_b.post(f"/alerts/{alert_id}/disposition", data={
            "status": "true_positive", "reason_code": "confirmed_match",
            "narrative": "Cross-tenant disposition attempt.",
            "csrf_token": _csrf(client_b),
        }, follow_redirects=True)

        conn = _db()
        status = conn.execute(
            "SELECT status FROM alerts WHERE id=?", (alert_id,)
        ).fetchone()["status"]
        conn.close()
        assert status == "open", "cross-tenant disposition must not change alert"

    def test_cross_org_report_isolated(self, two_orgs):
        client_a, client_b = two_orgs

        conn = _db()
        org_a = conn.execute(
            "SELECT id FROM organizations WHERE name='Alpha Corp'"
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO reports (org_id, report_type, status, payload, created_at) "
            "VALUES (?, 'STR', 'draft', '{}', datetime('now'))",
            (org_a,),
        )
        report_id = conn.execute(
            "SELECT id FROM reports ORDER BY id DESC LIMIT 1"
        ).fetchone()["id"]
        conn.commit()
        conn.close()

        r = client_b.get(f"/reports/{report_id}", follow_redirects=False)
        assert r.status_code == 303

    def test_cross_org_audit_trail_isolated(self, two_orgs):
        client_a, client_b = two_orgs
        self._create_customer(client_a, "A-007", "Audited Customer")

        r = client_b.get("/audit", follow_redirects=True)
        assert "A-007" not in r.text
        assert "Audited Customer" not in r.text

    def test_cross_org_db_level_isolation(self, two_orgs):
        """Verify at the database level that org_id filtering prevents
        cross-tenant reads through the query layer."""
        client_a, client_b = two_orgs
        self._create_customer(client_a, "DB-001", "Alpha DB Customer")
        self._create_customer(client_b, "DB-002", "Beta DB Customer")

        from amlkit import queries
        conn = _db()
        org_a = conn.execute(
            "SELECT id FROM organizations WHERE name='Alpha Corp'"
        ).fetchone()["id"]
        org_b = conn.execute(
            "SELECT id FROM organizations WHERE name='Beta Corp'"
        ).fetchone()["id"]

        alpha_customers = queries.customer_list(conn, org_a)
        beta_customers = queries.customer_list(conn, org_b)
        conn.close()

        alpha_refs = {c["reference"] for c in alpha_customers}
        beta_refs = {c["reference"] for c in beta_customers}

        assert "DB-001" in alpha_refs
        assert "DB-001" not in beta_refs
        assert "DB-002" in beta_refs
        assert "DB-002" not in alpha_refs
