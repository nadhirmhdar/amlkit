"""Proposed RED tests for the five highest-value untested / unbuilt behaviours.

Written TDD-first: every test here is expected to FAIL on the current tree
for a behavioural reason (feature missing or bug present), not an import or
fixture error. Each docstring names the production change that would turn it
green. Drop this file into tests/ unchanged -- it reuses the `_register()`
helper and DB seeding from tests/test_api.py.

Sources: PLAN.md 2.14 (MFA login gate), 2.7 (super-admin cross-org access
logged), 2.12 (Cache-Control: no-store), issue #141 (false FIU-submission
claim), and the untested POST /alerts/bulk-dismiss route (bypasses four-eyes).
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parents[3] / "tests"
sys.path.insert(0, str(_TESTS.parent))
sys.path.insert(0, str(_TESTS))

from test_api import LISTED, _csrf, _register, _seed_sanctions_data  # noqa: E402


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Throwaway DB seeded with one sanctioned person; org registered and
    signed in as its MLRO ("alice") -- same shape as tests/test_api.py."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


# ---------------------------------------------------------------------------
# 1. MFA must be enforced at login once an operator has enrolled (PLAN 2.14)
# ---------------------------------------------------------------------------
class TestMfaLoginGate:
    def test_password_alone_does_not_open_a_session_for_an_mfa_enrolled_operator(self, client):
        """Already satisfied by master (see README "Corrections to lane
        reports"): login_submit locks every fresh MLRO session until a valid
        TOTP (or backup code) is presented. `client` already enrolled and
        *confirmed* alice's MFA via `_register()` -> `settle_mfa()`; a second
        `mfa_enroll(conn, op_id)` call here used to re-run against her already
        -confirmed row, which `auth.mfa_enroll()` only reuses when *pending*
        (confirmed_at IS NULL) -- so it fell through to INSERT OR REPLACE and
        silently reset her back to unconfirmed. The assertions below still
        passed, but only because every fresh MLRO session locks regardless of
        enrollment state, not because this exercised the TOTP-challenge path
        for an already-enrolled operator as the test name claims."""
        # Fresh, logged-out client for the same app/DB.
        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        c2 = TestClient(app)
        c2.get("/login")
        r = c2.post("/login", data={
            "email": "alice@testfirm.ae", "password": "a-strong-password-1",
            "csrf_token": _csrf(c2),
        }, follow_redirects=False)

        # A password-only login must not land on the dashboard.
        home = c2.get("/", follow_redirects=False)
        assert home.status_code != 200 or "Dashboard" not in home.text, (
            "operator enrolled in MFA was signed in with password alone; "
            f"login responded {r.status_code} -> {r.headers.get('location')}"
        )
        # And the user must be told what is required next.
        challenge = c2.get(r.headers.get("location", "/login"))
        assert "authentication code" in challenge.text.lower() or "mfa" in challenge.text.lower()


# ---------------------------------------------------------------------------
# 2. Bulk dismiss must honour four-eyes for sanctions matches (untested route)
# ---------------------------------------------------------------------------
class TestBulkDismissFourEyes:
    @pytest.fixture()
    def customer_with_sanctions_alert(self, client) -> int:
        client.post("/customers", data={
            "reference": "C-B", "full_name": "Falcon Two FZE", "customer_type": "legal",
            "ubo_names": [LISTED], "ubo_pcts": ["60"], "ubo_controls": ["ownership"],
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        conn = _db()
        row = conn.execute("SELECT id FROM customers WHERE reference='C-B'").fetchone()
        n_open = conn.execute("SELECT COUNT(*) FROM alerts WHERE status='open'").fetchone()[0]
        conn.close()
        assert row is not None and n_open >= 1, "fixture should have produced an open sanctions alert"
        return row["id"]

    def test_bulk_dismiss_of_a_sanctions_match_is_staged_for_independent_review(
            self, client, customer_with_sanctions_alert):
        """Production change that makes this pass: review.bulk_dismiss_alerts()
        must route each alert through propose_disposition() (or apply the same
        needs_independent_review() rule) so a sanctions/PF/TF match lands in
        'pending_review' for a second operator -- exactly what the single
        /alerts/{id}/disposition path already does (tests/test_api.py
        TestFourEyes). Today it writes status='false_positive' directly."""
        r = client.post("/alerts/bulk-dismiss", data={
            "customer_id": customer_with_sanctions_alert,
            "reason_code": "name_coincidence",
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        assert r.status_code == 200

        conn = _db()
        statuses = [x["status"] for x in conn.execute(
            "SELECT status FROM alerts ORDER BY id").fetchall()]
        conn.close()
        assert statuses and all(s == "pending_review" for s in statuses), (
            f"sanctions match closed by a single operator via bulk dismiss: {statuses}"
        )


# ---------------------------------------------------------------------------
# 3. Report "submit" must not claim transmission to the FIU (issue #141)
# ---------------------------------------------------------------------------
NATURAL_PERSON_FORM = {
    "reporting_entity_name": "Test Firm", "entity_reference": "LIC-1",
    "reporter_name": "Alice MLRO", "reporter_email": "alice@testfirm.ae",
    "first_name": "Ahmed", "last_name": "Al Mansoori", "nationality": "AE",
    "amount": "75000", "transaction_type": "Wire Transfer",
    "source_account": "AE070331234567890123456",
    "destination_account": "AE070339876543210987654",
    "reason_description": "Large wire inconsistent with declared income.",
}


class TestReportSubmitDoesNotClaimFiuTransmission:
    def test_finalising_a_report_does_not_tell_the_mlro_it_reached_the_fiu(self, client):
        """Production change that makes this pass: app.py report_submit must
        stop saying "Report submitted to UAE FIU successfully." -- nothing is
        transmitted; the MLRO still has to upload the goAML XML on the FIU
        portal. The confirmation must describe the real state (finalised /
        ready for goAML upload) and point at the export. Same for the
        already-submitted error string."""
        from amlkit.cases.manager import onboard
        from amlkit.db import connect

        conn = connect(os.environ["AMLKIT_DB"])
        org_id = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
        cid = onboard(conn, org_id=org_id, actor="tester", reference="C-1",
                      full_name="Ahmed Al Mansoori", customer_type="natural",
                      nationality="ae").customer_id
        conn.close()

        client.post("/reports", data={
            "customer_id": cid, "report_type": "STR", "csrf_token": _csrf(client),
            **NATURAL_PERSON_FORM,
        })
        conn = _db()
        rid = conn.execute("SELECT id FROM reports ORDER BY id DESC LIMIT 1").fetchone()["id"]
        conn.close()

        r = client.post(f"/reports/{rid}/submit", data={"csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert r.status_code == 200
        text = r.text.lower()
        assert "submitted to uae fiu" not in text, (
            "UI claims transmission to the FIU, but amlkit performs no transmission (#141)"
        )
        assert "goaml" in text, "confirmation should tell the MLRO the goAML upload is still theirs to do"


# ---------------------------------------------------------------------------
# 4. Authenticated pages must be Cache-Control: no-store (PLAN 2.12)
# ---------------------------------------------------------------------------
class TestNoStoreOnAuthenticatedResponses:
    @pytest.mark.parametrize("path", ["/", "/customers", "/alerts", "/audit"])
    def test_authenticated_html_carries_no_store(self, client, path):
        """Production change that makes this pass: the response middleware in
        api/app.py (the one that already sets the security headers) must add
        `Cache-Control: no-store` (and `Pragma: no-cache`) whenever a session
        is present, so regulated customer data is not left in a shared
        browser's disk cache after logout. Today no Cache-Control header is
        set anywhere in amlkit/api/."""
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        cc = r.headers.get("cache-control", "")
        assert "no-store" in cc.lower(), f"{path}: Cache-Control={cc!r}"

    def test_csv_export_carries_no_store(self, client):
        """Exports are the most sensitive artefacts; same rule applies."""
        r = client.get("/customers.csv")
        assert r.status_code == 200
        assert "no-store" in r.headers.get("cache-control", "").lower()


# ---------------------------------------------------------------------------
# 5. Super-admin cross-org console access must leave an audit row (PLAN 2.7)
# ---------------------------------------------------------------------------
class TestConsoleCrossOrgAccessIsAudited:
    @pytest.fixture()
    def super_admin(self, client):
        """Promote alice to super-admin and register a SECOND org she does not
        belong to, so the console view is genuinely cross-tenant."""
        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        other = TestClient(app)
        _register(other, "Other Firm", "bob", "bob@otherfirm.ae")

        conn = _db()
        conn.execute("UPDATE operators SET super_admin=1 WHERE email='alice@testfirm.ae'")
        other_org = conn.execute(
            "SELECT id FROM organizations WHERE name='Other Firm'").fetchone()["id"]
        conn.commit()
        conn.close()
        # Re-login so the session reflects the super_admin flag.
        client.post("/logout", data={"csrf_token": _csrf(client)})
        client.get("/login")
        client.post("/login", data={"email": "alice@testfirm.ae",
                                    "password": "a-strong-password-1",
                                    "csrf_token": _csrf(client)}, follow_redirects=True)
        return other_org

    def test_viewing_another_orgs_customers_writes_an_audit_row(self, client, super_admin):
        """Production change that makes this pass: console_org_customers and
        console_org_alerts in api/app.py must call db.audit(...) with the
        acting super-admin, an action such as 'console.org_view', and the
        target org_id (the audit_log table is the only evidence trail a regulator
        gets that a platform operator looked at a firm's CDD data). Today the
        console routes contain no audit() call at all."""
        r = client.get(f"/console/org/{super_admin}/customers")
        assert r.status_code == 200, r.text[:200]

        conn = _db()
        rows = conn.execute(
            "SELECT action, org_id, actor FROM audit_log WHERE action LIKE 'console.%'"
        ).fetchall()
        conn.close()
        assert rows, "super-admin viewed another org's customers and no audit row was written"
        assert any(row["org_id"] == super_admin for row in rows), (
            f"audit row does not name the viewed org: {[dict(x) for x in rows]}"
        )
