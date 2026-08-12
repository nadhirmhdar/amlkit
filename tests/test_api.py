"""Route and constraint tests.

The routes themselves are thin, so the tests that earn their place are the
ones covering the constraints -- the rules that stop the interface
manufacturing the thin disposition records that generate inspection
findings, AND the tenant-isolation rules that stop one firm's regulated data
becoming visible to another's.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LISTED = "AHMED ABD AL-JALEEL AL-HASNAWI"
LISTED_AR = "أحمد عبد الجليل الحسناوي"


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
    for i, nm in enumerate([LISTED, LISTED_AR]):
        conn.execute(
            "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
            " VALUES (?,?,?,?,?)",
            (eid, nm, "primary" if i == 0 else "alias", canonical_key(nm),
             "arabic" if i else "latin"))
        for tok in blocking_keys(nm):
            conn.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)",
                         (tok, eid))
    conn.commit()
    conn.close()


def _csrf(client) -> str:
    """The middleware sets a CSRF cookie on every response; every POST in
    these tests must echo it back as the synchronizer token."""
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name: str, name: str, email: str, password: str = "a-strong-password-1"):
    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert "Dashboard" in r.text or "24-hour" in r.text, f"registration failed: {r.text[:300]}"
    return client


def _login(client, email: str, password: str = "a-strong-password-1"):
    client.get("/login")
    r = client.post("/login", data={
        "email": email, "password": password, "csrf_token": _csrf(client),
    }, follow_redirects=True)
    return r


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """App wired to a throwaway database seeded with one sanctioned person,
    with a fresh organization registered and logged in as its MLRO ("alice")."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    _seed_sanctions_data(db_file)

    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    _register(c, "Test Firm", "alice", "alice@testfirm.ae")
    return c


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    return conn


def _first_alert_id() -> int:
    conn = _db()
    row = conn.execute("SELECT id FROM alerts ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert row is not None, "expected an alert to exist"
    return row["id"]


def _alert(field: str):
    conn = _db()
    row = conn.execute(f"SELECT {field} FROM alerts ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row[field]


def _add_operator(client, name: str, email: str, password: str = "a-strong-password-2",
                  role: str = "officer") -> None:
    """MLRO (the fixture's logged-in session) creates a second operator."""
    client.post("/admin/operators", data={
        "name": name, "email": email, "password": password, "role": role,
        "csrf_token": _csrf(client),
    })


class TestPagesRender:
    @pytest.mark.parametrize("path", ["/", "/screen", "/alerts", "/customers",
                                      "/customers/new", "/audit", "/admin"])
    def test_page_renders_when_authenticated(self, client, path: str) -> None:
        r = client.get(path)
        assert r.status_code == 200
        assert "amlkit" in r.text

    @pytest.mark.parametrize("path", ["/", "/screen", "/alerts", "/customers", "/admin"])
    def test_page_redirects_when_not_authenticated(self, client, path: str) -> None:
        client.cookies.delete("amlkit_session")
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"

    def test_missing_customer_redirects(self, client) -> None:
        r = client.get("/customers/9999", follow_redirects=False)
        assert r.status_code == 303


class TestAuth:
    def test_wrong_password_rejected(self, client) -> None:
        client.cookies.delete("amlkit_session")
        r = _login(client, "alice@testfirm.ae", "not-the-password")
        assert "Incorrect email or password" in r.text

    def test_unknown_email_gives_same_generic_error(self, client) -> None:
        client.cookies.delete("amlkit_session")
        r = _login(client, "nobody@testfirm.ae", "whatever")
        assert "Incorrect email or password" in r.text

    def test_login_without_csrf_rejected(self, client) -> None:
        client.cookies.delete("amlkit_session")
        r = client.post("/login", data={"email": "alice@testfirm.ae", "password": "a-strong-password-1"})
        assert "Incorrect email or password" not in r.text
        # CSRF failure keeps the user on the login page with a distinct error,
        # never a successful sign-in.
        assert "Dashboard" not in r.text and "24-hour" not in r.text

    def test_logout_ends_the_session(self, client) -> None:
        client.post("/logout", data={"csrf_token": _csrf(client)})
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"


class TestScreening:
    def test_latin_query_finds_listed_person(self, client) -> None:
        r = client.post("/screen", data={"name": LISTED, "csrf_token": _csrf(client)})
        assert "match(es)" in r.text
        assert "TERRORISM FINANCING" in r.text

    def test_arabic_query_finds_latin_record(self, client) -> None:
        """The differentiator, exercised through the interface."""
        r = client.post("/screen", data={"name": LISTED_AR, "csrf_token": _csrf(client)})
        assert LISTED in r.text

    def test_clear_result_is_still_recorded(self, client) -> None:
        """Evidence that a check happened and came back clean is the point."""
        r = client.post("/screen", data={"name": "Ahmed Al Mansoori", "csrf_token": _csrf(client)})
        assert "No match" in r.text

        conn = _db()
        screenings = conn.execute("SELECT COUNT(*) FROM screenings").fetchone()[0]
        alerts = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        conn.close()
        assert screenings >= 1, "a clear screening must still be recorded"
        assert alerts == 0, "a clear screening must not create an alert"

    def test_single_token_warns(self, client) -> None:
        r = client.post("/screen", data={"name": "Mohammed", "csrf_token": _csrf(client)})
        assert "Single name token" in r.text

    def test_screening_without_session_redirects_to_login(self, client) -> None:
        client.cookies.delete("amlkit_session")
        r = client.post("/screen", data={"name": LISTED, "csrf_token": _csrf(client)},
                        follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"


class TestOnboarding:
    def test_onboard_and_screen(self, client) -> None:
        r = client.post("/customers", data={
            "reference": "C-1", "full_name": "Ahmed Al Mansoori",
            "customer_type": "natural", "csrf_token": _csrf(client),
        }, follow_redirects=True)
        assert r.status_code == 200
        assert "Risk rating" in r.text

    def test_listed_ubo_blocks_a_clean_company(self, client) -> None:
        """A company that screens clean but whose owner does not."""
        r = client.post("/customers", data={
            "reference": "C-2", "full_name": "Falcon Holdings FZE",
            "customer_type": "legal", "sector": "real_estate",
            "ubo_names": [LISTED], "ubo_pcts": ["60"], "ubo_controls": ["ownership"],
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        assert "MATCH FOUND" in r.text

    def test_duplicate_reference_rejected_within_the_same_org(self, client) -> None:
        data = {"reference": "C-3", "full_name": "Test Co", "customer_type": "legal",
               "csrf_token": _csrf(client)}
        client.post("/customers", data=data, follow_redirects=True)
        r = client.post("/customers", data=data, follow_redirects=True)
        assert "already exists" in r.text

    def test_same_reference_allowed_for_a_different_org(self, client, tmp_path) -> None:
        """References are unique per firm, not globally."""
        client.post("/customers", data={
            "reference": "C-DUP", "full_name": "Firm One Customer", "customer_type": "legal",
            "csrf_token": _csrf(client),
        }, follow_redirects=True)

        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        other = TestClient(app)
        _register(other, "Other Firm", "omar", "omar@otherfirm.ae")
        r = other.post("/customers", data={
            "reference": "C-DUP", "full_name": "Firm Two Customer", "customer_type": "legal",
            "csrf_token": _csrf(other),
        }, follow_redirects=True)
        assert "already exists" not in r.text
        assert "Risk rating" in r.text


class TestTenantIsolation:
    """The property that matters most now: one firm's data must be
    unreachable from another firm's session, and a cross-tenant ID must be
    indistinguishable from one that does not exist."""

    def test_second_org_sees_none_of_the_first_orgs_customers(self, client) -> None:
        client.post("/customers", data={
            "reference": "ISO-1", "full_name": "Isolated Customer",
            "customer_type": "natural", "csrf_token": _csrf(client),
        }, follow_redirects=True)

        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        other = TestClient(app)
        _register(other, "Second Firm", "sara", "sara@secondfirm.ae")
        r = other.get("/customers")
        assert "Isolated Customer" not in r.text

    def test_cross_org_customer_id_is_404_not_empty(self, client) -> None:
        client.post("/customers", data={
            "reference": "ISO-2", "full_name": "Firm One Only",
            "customer_type": "natural", "csrf_token": _csrf(client),
        }, follow_redirects=True)
        conn = _db()
        cid = conn.execute("SELECT id FROM customers WHERE reference='ISO-2'").fetchone()["id"]
        conn.close()

        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        other = TestClient(app)
        _register(other, "Third Firm", "tariq", "tariq@thirdfirm.ae")
        r = other.get(f"/customers/{cid}", follow_redirects=False)
        assert r.status_code == 303
        r2 = other.get(f"/customers/{cid}", follow_redirects=True)
        assert "not found" in r2.text.lower()

    def test_cross_org_alert_disposition_is_rejected(self, client) -> None:
        client.post("/customers", data={
            "reference": "ISO-3", "full_name": "Falcon Iso FZE", "customer_type": "legal",
            "ubo_names": [LISTED], "ubo_pcts": ["60"], "ubo_controls": ["ownership"],
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        alert_id = _first_alert_id()

        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        other = TestClient(app)
        _register(other, "Fourth Firm", "yara", "yara@fourthfirm.ae")
        r = other.post(f"/alerts/{alert_id}/disposition", data={
            "status": "true_positive", "reason_code": "confirmed_match",
            "narrative": "Attempting cross-tenant disposition.",
            "csrf_token": _csrf(other),
        }, follow_redirects=True)
        assert "not found" in r.text.lower()


class TestDispositionConstraints:
    """These are the tests that matter: the interface must not allow a record
    too thin to survive inspection."""

    @pytest.fixture()
    def alert_id(self, client):
        client.post("/customers", data={
            "reference": "C-A", "full_name": "Falcon Holdings FZE",
            "customer_type": "legal",
            "ubo_names": [LISTED], "ubo_pcts": ["60"], "ubo_controls": ["ownership"],
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        return _first_alert_id()

    def test_reason_code_is_required(self, client, alert_id) -> None:
        r = client.post(f"/alerts/{alert_id}/disposition",
                        data={"status": "false_positive", "reason_code": "",
                              "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "invalid reason code" in r.text
        assert _alert("status") == "open"

    def test_true_positive_requires_narrative(self, client, alert_id) -> None:
        r = client.post(f"/alerts/{alert_id}/disposition",
                        data={"status": "true_positive", "reason_code": "confirmed_match",
                              "narrative": "", "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "narrative is required" in r.text
        assert _alert("status") == "open"

    def test_other_reason_requires_narrative(self, client, alert_id) -> None:
        r = client.post(f"/alerts/{alert_id}/disposition",
                        data={"status": "false_positive", "reason_code": "other",
                              "narrative": "", "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "requires a narrative" in r.text

    def test_disposition_without_session_redirects_to_login(self, client, alert_id) -> None:
        client.cookies.delete("amlkit_session")
        r = client.post(f"/alerts/{alert_id}/disposition",
                        data={"status": "false_positive", "reason_code": "different_dob",
                              "csrf_token": _csrf(client)},
                        follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"

    def test_disposition_without_csrf_is_rejected(self, client, alert_id) -> None:
        r = client.post(f"/alerts/{alert_id}/disposition",
                        data={"status": "false_positive", "reason_code": "different_dob"},
                        follow_redirects=True)
        assert _alert("status") == "open"


class TestFourEyes:
    @pytest.fixture()
    def alert_id(self, client):
        client.post("/customers", data={
            "reference": "C-B", "full_name": "Falcon Two FZE", "customer_type": "legal",
            "ubo_names": [LISTED], "ubo_pcts": ["60"], "ubo_controls": ["ownership"],
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        return _first_alert_id()

    def test_dismissal_is_staged_for_review(self, client, alert_id) -> None:
        r = client.post(f"/alerts/{alert_id}/disposition",
                        data={"status": "false_positive", "reason_code": "different_dob",
                              "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "independent review" in r.text.lower()
        assert _alert("status") == "pending_review"

    def test_same_operator_cannot_confirm_own_dismissal(self, client, alert_id) -> None:
        client.post(f"/alerts/{alert_id}/disposition",
                    data={"status": "false_positive", "reason_code": "different_dob",
                          "csrf_token": _csrf(client)},
                    follow_redirects=True)
        r = client.post(f"/alerts/{alert_id}/confirm",
                        data={"agree": "yes", "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "different operator" in r.text
        assert _alert("status") == "pending_review"

    def test_second_operator_completes_review(self, client, alert_id) -> None:
        client.post(f"/alerts/{alert_id}/disposition",
                    data={"status": "false_positive", "reason_code": "different_dob",
                          "csrf_token": _csrf(client)},
                    follow_redirects=True)

        _add_operator(client, "bob", "bob@testfirm.ae")

        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        bob = TestClient(app)
        bob.get("/login")
        _login(bob, "bob@testfirm.ae", "a-strong-password-2")
        bob.post(f"/alerts/{alert_id}/confirm", data={"agree": "yes", "csrf_token": _csrf(bob)},
                 follow_redirects=True)

        assert _alert("status") == "false_positive"
        assert _alert("independent_review") == "completed"

    def test_confirming_a_match_needs_no_second_operator(self, client, alert_id) -> None:
        """Confirmation escalates to freeze and report, which carries its own
        scrutiny; only dismissal needs the second pair of eyes."""
        client.post(f"/alerts/{alert_id}/disposition",
                    data={"status": "true_positive", "reason_code": "confirmed_match",
                          "narrative": "Passport and DOB both match the designation.",
                          "csrf_token": _csrf(client)},
                    follow_redirects=True)
        assert _alert("status") == "true_positive"

    def test_single_operator_mode_records_the_gap(self, client, alert_id, monkeypatch) -> None:
        """The control gap must be visible at inspection, not silently waived."""
        monkeypatch.setenv("AMLKIT_SINGLE_OPERATOR_MODE", "1")
        r = client.post(f"/alerts/{alert_id}/disposition",
                        data={"status": "false_positive", "reason_code": "different_dob",
                              "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert _alert("status") == "false_positive"
        assert _alert("independent_review") == "single_operator"
        assert "no independent review" in r.text.lower()


class TestEvidencePack:
    def test_evidence_pack_contains_the_record(self, client) -> None:
        client.post("/customers", data={
            "reference": "C-E", "full_name": "Falcon Three FZE", "customer_type": "legal",
            "ubo_names": [LISTED], "ubo_pcts": ["60"], "ubo_controls": ["ownership"],
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        conn = _db()
        cid = conn.execute("SELECT id FROM customers ORDER BY id DESC LIMIT 1").fetchone()[0]
        conn.close()

        r = client.get(f"/customers/{cid}/evidence")
        assert r.status_code == 200
        for expected in ["Customer due diligence record", "Beneficial ownership",
                         "Screening record", "Audit trail", LISTED]:
            assert expected in r.text, f"evidence pack missing {expected!r}"


class TestAudit:
    def test_actions_are_attributed(self, client) -> None:
        client.post("/screen", data={"name": LISTED, "csrf_token": _csrf(client)})
        r = client.get("/audit")
        assert "alice" in r.text

    def test_login_is_audited_in_the_tenant_log(self, client) -> None:
        r = client.get("/audit")
        assert "operator.login" in r.text or "login" in r.text.lower()
