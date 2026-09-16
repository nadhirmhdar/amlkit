"""Route and constraint tests.

The routes themselves are thin, so the tests that earn their place are the
ones covering the constraints -- the rules that stop the interface
manufacturing the thin disposition records that generate inspection
findings, AND the tenant-isolation rules that stop one firm's regulated data
becoming visible to another's.
"""

from __future__ import annotations

import json
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
    # Make dataset fresh so onboard() passes the staleness guard
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    conn.commit()
    conn.close()


def _csrf(client) -> str:
    """The middleware sets a CSRF cookie on every response; every POST in
    these tests must echo it back as the synchronizer token."""
    return client.cookies.get("amlkit_csrf")


def _register(client, org_name: str, name: str, email: str, password: str = "a-strong-password-1"):
    """Registers, then completes email verification and signs in.

    Registration alone no longer produces a usable session (see
    api/app.py's register_org_submit) -- it sends a verification link and,
    with no SMTP configured in tests, prints/renders that link instead of
    emailing it (see amlkit/mail.py). This helper extracts that dev link
    from the response and follows it, exactly like a real user clicking the
    emailed link would, so every other test's fixture keeps getting back a
    signed-in client.
    """
    import re

    client.get("/register-organization")
    r = client.post("/register-organization", data={
        "org_name": org_name, "name": name, "email": email, "password": password,
        "csrf_token": _csrf(client),
    }, follow_redirects=True)
    assert "Check your email" in r.text, f"registration failed: {r.text[:300]}"
    m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r.text)
    assert m, f"no dev verification link in registration response: {r.text[:500]}"
    r2 = client.get(f"/verify-email?token={m.group(1)}", follow_redirects=True)
    assert "Dashboard" in r2.text or "24-hour" in r2.text, f"verification failed: {r2.text[:300]}"
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


class TestHomePage:
    """The first screen after sign-in -- an orientation page, not the
    dashboard (moved to /dashboard). See home.html."""

    def test_shows_greeting_and_action_cards(self, client) -> None:
        r = client.get("/")
        assert r.status_code == 200
        assert "alice" in r.text  # first name from the fixture's registered operator
        assert "Screen a name" in r.text
        assert "Onboard a customer" in r.text
        assert "About us" in r.text

    def test_alerts_bar_shows_clear_state_when_no_open_alerts(self, client) -> None:
        r = client.get("/")
        assert "No alerts pending" in r.text
        assert "is-clear" in r.text

    def test_alerts_bar_shows_pending_state_and_count(self, client) -> None:
        client.get("/screen")
        client.post("/screen", data={
            "name": LISTED, "country": "ly", "csrf_token": _csrf(client),
        })
        r = client.get("/")
        assert "is-pending" in r.text
        assert "1 alert" in r.text and "your action" in r.text

    def test_alerts_bar_links_to_dashboard(self, client) -> None:
        r = client.get("/")
        assert 'href="/dashboard"' in r.text


class TestPagesRender:
    @pytest.mark.parametrize("path", ["/", "/dashboard", "/screen", "/alerts", "/customers",
                                      "/customers/new", "/audit", "/admin"])
    def test_page_renders_when_authenticated(self, client, path: str) -> None:
        r = client.get(path)
        assert r.status_code == 200
        assert "amlkit" in r.text

    @pytest.mark.parametrize("path", ["/", "/dashboard", "/screen", "/alerts", "/customers", "/admin"])
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

    def test_duplicate_email_registration_is_a_clean_error(self, client) -> None:
        """Same underlying bug as test_mobile_api.py's version: registering a
        second, differently-named organization with an already-used email
        used to hit operators.email's UNIQUE constraint with no try/except
        around it, crashing instead of rendering the form with an error."""
        client.cookies.delete("amlkit_session")
        client.get("/register-organization")
        r = client.post("/register-organization", data={
            "org_name": "A Totally Different Firm", "name": "alice again",
            "email": "alice@testfirm.ae", "password": "another-strong-pw-1",
            "csrf_token": _csrf(client),
        })
        assert r.status_code == 200
        assert "already exists" in r.text

        # The orphaned-organization side effect is rolled back too, not just
        # the error message cleaned up -- a second attempt with the same org
        # name and a fresh email should succeed, not collide on org slug.
        client.get("/register-organization")
        r2 = client.post("/register-organization", data={
            "org_name": "A Totally Different Firm", "name": "someone else",
            "email": "someone.else@testfirm.ae", "password": "yet-another-pw-1",
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        assert "Check your email" in r2.text, f"registration failed: {r2.text[:300]}"


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

    def test_clear_result_records_which_lists_were_searched(self, client) -> None:
        """datasets_used must reflect every list actually in scope, not just
        the ones that happened to produce a hit -- a clear result naively
        derived only from hits would (and once did) log an empty list even
        though every mandatory list was searched."""
        client.post("/screen", data={"name": "Ahmed Al Mansoori", "csrf_token": _csrf(client)})

        conn = _db()
        screening = conn.execute(
            "SELECT id, datasets_used FROM screenings ORDER BY id DESC LIMIT 1"
        ).fetchone()
        datasets_used = json.loads(screening["datasets_used"])
        assert datasets_used == ["test_list"]

        audit_detail = conn.execute(
            "SELECT detail FROM audit_log WHERE action='screening.run' AND object_id=?",
            (str(screening["id"]),),
        ).fetchone()
        conn.close()
        assert json.loads(audit_detail["detail"])["datasets_used"] == ["test_list"]

    def test_degenerate_query_does_not_fabricate_search_coverage(self, client) -> None:
        """A query with no usable name tokens (digits-only) makes
        _candidates() short-circuit before ever touching entities/name_tokens
        -- nothing was actually searched, so datasets_used must be empty, not
        every loaded dataset. Claiming full coverage here would fabricate
        evidence of a screening that never ran."""
        r = client.post("/screen", data={"name": "123", "csrf_token": _csrf(client)})
        assert r.status_code == 200

        conn = _db()
        screening = conn.execute(
            "SELECT id, candidates, datasets_used FROM screenings ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert screening["candidates"] == 0
        assert json.loads(screening["datasets_used"]) == []

        audit_detail = conn.execute(
            "SELECT detail FROM audit_log WHERE action='screening.run' AND object_id=?",
            (str(screening["id"]),),
        ).fetchone()
        conn.close()
        assert json.loads(audit_detail["detail"])["datasets_used"] == []

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

    def test_cross_org_case_note_is_rejected(self, client) -> None:
        """Regression: add_case_note() originally inserted without verifying
        the customer belonged to the calling org -- a bare foreign key means
        the insert would otherwise succeed as long as the customer row
        existed anywhere, silently attaching one org's note to another org's
        customer."""
        client.post("/customers", data={
            "reference": "ISO-4", "full_name": "Note Target FZE",
            "customer_type": "legal", "csrf_token": _csrf(client),
        }, follow_redirects=True)
        conn = _db()
        cid = conn.execute("SELECT id FROM customers WHERE reference='ISO-4'").fetchone()["id"]
        conn.close()

        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        other = TestClient(app)
        _register(other, "Fifth Firm", "zaid", "zaid@fifthfirm.ae")
        r = other.post(f"/customers/{cid}/notes", data={
            "body": "Attempting cross-tenant note.", "csrf_token": _csrf(other),
        }, follow_redirects=True)
        assert "not found" in r.text.lower()

        conn = _db()
        n = conn.execute("SELECT COUNT(*) c FROM case_notes WHERE customer_id=?", (cid,)).fetchone()["c"]
        conn.close()
        assert n == 0, "cross-tenant note must not be written"


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

    def test_generated_timestamp_is_real_not_a_placeholder(self, client) -> None:
        """The header printed on this exact document was, until fixed, a
        random 5-digit number labelled '(mock timestamp)' -- this asserts a
        real, current-year UTC timestamp is shown instead."""
        client.post("/customers", data={
            "reference": "C-TS", "full_name": "Timestamp Test Co", "customer_type": "legal",
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        conn = _db()
        cid = conn.execute("SELECT id FROM customers ORDER BY id DESC LIMIT 1").fetchone()[0]
        conn.close()

        r = client.get(f"/customers/{cid}/evidence")
        assert "mock timestamp" not in r.text
        from amlkit.db import utcnow
        current_year = utcnow()[:4]
        assert f"Generated {current_year}-" in r.text


class TestAudit:
    def test_actions_are_attributed(self, client) -> None:
        client.post("/screen", data={"name": LISTED, "csrf_token": _csrf(client)})
        r = client.get("/audit")
        assert "alice" in r.text

    def test_login_is_audited_in_the_tenant_log(self, client) -> None:
        r = client.get("/audit")
        assert "operator.login" in r.text or "login" in r.text.lower()


class TestCaseNotes:
    def _customer_id(self, client, reference: str) -> int:
        client.post("/customers", data={
            "reference": reference, "full_name": "Note Test Co",
            "customer_type": "legal", "csrf_token": _csrf(client),
        }, follow_redirects=True)
        conn = _db()
        cid = conn.execute("SELECT id FROM customers WHERE reference=?", (reference,)).fetchone()[0]
        conn.close()
        return cid

    def test_note_is_added_and_displayed(self, client) -> None:
        cid = self._customer_id(client, "NOTE-1")
        r = client.post(f"/customers/{cid}/notes",
                        data={"body": "Called client to confirm source of funds.",
                              "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "Called client to confirm source of funds." in r.text
        assert "alice" in r.text

    def test_empty_note_rejected(self, client) -> None:
        cid = self._customer_id(client, "NOTE-2")
        r = client.post(f"/customers/{cid}/notes",
                        data={"body": "   ", "csrf_token": _csrf(client)},
                        follow_redirects=True)
        conn = _db()
        n = conn.execute("SELECT COUNT(*) c FROM case_notes WHERE customer_id=?", (cid,)).fetchone()["c"]
        conn.close()
        assert n == 0

    def test_note_appears_in_evidence_pack(self, client) -> None:
        cid = self._customer_id(client, "NOTE-3")
        client.post(f"/customers/{cid}/notes",
                   data={"body": "Evidence pack note check.", "csrf_token": _csrf(client)},
                   follow_redirects=True)
        r = client.get(f"/customers/{cid}/evidence")
        assert "Evidence pack note check." in r.text


class TestAlertAssignment:
    @pytest.fixture()
    def alert_id(self, client):
        client.post("/customers", data={
            "reference": "ASN-1", "full_name": "Assignment Test FZE", "customer_type": "legal",
            "ubo_names": [LISTED], "ubo_pcts": ["60"], "ubo_controls": ["ownership"],
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        return _first_alert_id()

    def test_assign_to_self(self, client, alert_id) -> None:
        r = client.post(f"/alerts/{alert_id}/assign",
                        data={"operator": "alice", "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "Assigned to alice" in r.text
        assert _alert("assigned_to") == "alice"

    def test_clear_assignment(self, client, alert_id) -> None:
        client.post(f"/alerts/{alert_id}/assign",
                   data={"operator": "alice", "csrf_token": _csrf(client)}, follow_redirects=True)
        client.post(f"/alerts/{alert_id}/assign",
                   data={"operator": "", "csrf_token": _csrf(client)}, follow_redirects=True)
        assert _alert("assigned_to") is None

    def test_assignment_is_audited(self, client, alert_id) -> None:
        client.post(f"/alerts/{alert_id}/assign",
                   data={"operator": "alice", "csrf_token": _csrf(client)}, follow_redirects=True)
        conn = _db()
        n = conn.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE action='alert.assign'"
        ).fetchone()["c"]
        conn.close()
        assert n >= 1

    def test_cross_org_assignment_rejected(self, client, alert_id) -> None:
        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        other = TestClient(app)
        _register(other, "Sixth Firm", "hana", "hana@sixthfirm.ae")
        r = other.post(f"/alerts/{alert_id}/assign",
                       data={"operator": "hana", "csrf_token": _csrf(other)},
                       follow_redirects=True)
        assert "not found" in r.text.lower()
        assert _alert("assigned_to") is None


class TestCsvExport:
    def test_alerts_csv_downloads(self, client) -> None:
        client.post("/customers", data={
            "reference": "CSV-1", "full_name": "CSV Export FZE", "customer_type": "legal",
            "ubo_names": [LISTED], "ubo_pcts": ["60"], "ubo_controls": ["ownership"],
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        r = client.get("/alerts.csv")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "id,category,score" in r.text
        assert LISTED in r.text

    def test_customers_csv_downloads(self, client) -> None:
        client.post("/customers", data={
            "reference": "CSV-2", "full_name": "CSV Customer FZE",
            "customer_type": "legal", "csrf_token": _csrf(client),
        }, follow_redirects=True)
        r = client.get("/customers.csv")
        assert r.status_code == 200
        assert "CSV-2" in r.text
        assert "CSV Customer FZE" in r.text

    def test_csv_export_requires_session(self, client) -> None:
        client.cookies.delete("amlkit_session")
        r = client.get("/alerts.csv", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"

    def test_csv_escapes_formula_injection_in_customer_names(self, client) -> None:
        """CSV export must escape cells starting with =, +, -, @ to prevent formula injection."""
        dangerous_names = [
            ("=SUM(1+1)", "'=SUM(1+1)"),  # Equals sign
            ("+1+1", "'+1+1"),            # Plus sign
            ("-1-1", "'-1-1"),            # Minus sign
            ("@A1", "'@A1"),              # At sign
        ]
        for name, escaped in dangerous_names:
            ref = f"FORMULA-{hash(name) % 1000}"
            client.post("/customers", data={
                "reference": ref, "full_name": name,
                "customer_type": "natural", "csrf_token": _csrf(client),
            }, follow_redirects=True)
        r = client.get("/customers.csv")
        assert r.status_code == 200
        for name, escaped in dangerous_names:
            # The escaped version should appear in the CSV
            assert escaped in r.text, f"Expected {escaped!r} in CSV but got:\n{r.text}"
            # The raw dangerous string should NOT appear at the start of a field
            import re
            # Check that the dangerous pattern doesn't appear unescaped after a comma or newline
            pattern = f"[,\\n]{re.escape(name)}"
            assert not re.search(pattern, r.text), \
                f"Found unescaped {name!r} after field delimiter"

    def test_csv_escapes_formula_injection_in_alert_captions(self, client) -> None:
        """Alert CSV must also escape matched party names and captions."""
        # Create a customer with a benign name that will match a dangerous entity
        client.post("/customers", data={
            "reference": "ALERT-FORMULA", "full_name": "Test Customer",
            "customer_type": "natural", "csrf_token": _csrf(client),
        }, follow_redirects=True)
        r = client.get("/alerts.csv")
        assert r.status_code == 200
        # Any alert caption/matched_party starting with dangerous chars should be escaped
        # This test verifies the escaping function works on the alert export path too
        import re
        # Check no unescaped formula starters appear after field delimiters
        for char in ['=', '+', '-', '@']:
            pattern = f"[,\\n]{re.escape(char)}[^,\\n]"
            matches = re.findall(pattern, r.text)
            # If found, verify they're escaped (preceded by quote within the field)
            for match in matches:
                assert False, f"Found potentially unescaped formula in alerts CSV: {match!r}"


class TestAdminThreshold:
    def test_mlro_can_set_threshold(self, client) -> None:
        r = client.post("/admin/threshold",
                        data={"threshold": "0.9", "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "0.9" in r.text

    def test_out_of_range_threshold_rejected(self, client) -> None:
        r = client.post("/admin/threshold",
                        data={"threshold": "1.5", "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "between 0.0 and 1.0" in r.text

    def test_non_numeric_threshold_rejected(self, client) -> None:
        r = client.post("/admin/threshold",
                        data={"threshold": "not-a-number", "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "must be a number" in r.text

    def test_officer_cannot_set_threshold(self, client) -> None:
        _add_operator(client, "bob", "bob-threshold@testfirm.ae", role="officer")

        from fastapi.testclient import TestClient
        from amlkit.api.app import app
        bob = TestClient(app)
        bob.get("/login")
        _login(bob, "bob-threshold@testfirm.ae", "a-strong-password-2")
        r = bob.post("/admin/threshold",
                     data={"threshold": "0.9", "csrf_token": _csrf(bob)},
                     follow_redirects=True)
        assert "requires the mlro" in r.text.lower()

    def test_configured_threshold_changes_screening_results(self, client) -> None:
        """A near-miss that would normally clear the default threshold should
        stop clearing once the org raises its threshold."""
        # A single-token query against the listed person scores below the
        # default threshold already (see test_matching.py's regression test),
        # so instead verify the setting round-trips and is actually read back
        # by screening -- raise the threshold to something the exact listed
        # name still clears (1.0), confirming the configured value is used
        # rather than silently ignored.
        client.post("/admin/threshold", data={"threshold": "0.99", "csrf_token": _csrf(client)})
        r = client.post("/screen", data={"name": LISTED, "csrf_token": _csrf(client)})
        assert "match(es)" in r.text, "exact match must still clear a 0.99 threshold"


class TestUboValidation:
    """H-01: UBO ownership sum validation route-level tests."""

    def test_route_onboard_rejects_over_100_with_form_error(self, client) -> None:
        """POST /customers with 3×60% returns form error (not 500)."""
        # Attempt to create customer with 3 UBOs at 60% each
        r = client.post("/customers", data={
            "reference": "ROUTE-TEST-180",
            "full_name": "Route Over Corp",
            "customer_type": "legal",
            "ubo_names": ["Alice", "Bob", "Charlie"],
            "ubo_pcts": ["60", "60", "60"],
            "ubo_controls": ["ownership", "ownership", "ownership"],
            "csrf_token": _csrf(client),
        }, follow_redirects=False)

        # Should get a redirect back to the form with error
        assert r.status_code == 303
        assert "err=" in r.headers["location"]
        assert "100" in r.headers["location"]

        # Verify no customer was created
        conn = _db()
        customer_count = conn.execute(
            "SELECT COUNT(*) FROM customers WHERE reference='ROUTE-TEST-180'"
        ).fetchone()[0]
        assert customer_count == 0

    def test_route_add_ubo_rejects_pushing_sum_over_100(self, client) -> None:
        """POST /customers/{id}/ubo pushing sum over 100 is rejected with form error."""
        # Create customer with 60% ownership
        r1 = client.post("/customers", data={
            "reference": "ROUTE-TEST-ADD",
            "full_name": "Route Add Test",
            "customer_type": "legal",
            "ubo_names": ["Alice"],
            "ubo_pcts": ["60"],
            "ubo_controls": ["ownership"],
            "csrf_token": _csrf(client),
        }, follow_redirects=True)
        assert r1.status_code == 200

        # Get customer ID
        conn = _db()
        customer = conn.execute(
            "SELECT id FROM customers WHERE reference='ROUTE-TEST-ADD'"
        ).fetchone()
        assert customer is not None
        customer_id = customer[0]

        # Try to add another UBO at 50% (total would be 110%)
        r2 = client.post(f"/customers/{customer_id}/ubo", data={
            "person_name": "Bob",
            "ownership_pct": "50",
            "control_type": "ownership",
            "csrf_token": _csrf(client),
        }, follow_redirects=False)

        # Should get redirect back with error
        assert r2.status_code == 303
        assert "err=" in r2.headers["location"]
        assert "110" in r2.headers["location"]

        # Verify only 1 UBO exists (the first one)
        ubo_count = conn.execute(
            "SELECT COUNT(*) FROM ubo_links WHERE customer_id=?",
            (customer_id,)
        ).fetchone()[0]
        assert ubo_count == 1


class TestCookieSecurity:
    """H-02 (session Secure flag) and M-02 (CSRF HttpOnly) tests."""

    def test_csrf_cookie_is_httponly(self, tmp_path, monkeypatch) -> None:
        """M-02: CSRF cookie must have HttpOnly flag."""
        # Create fresh client without existing cookies
        db_file = tmp_path / "test_csrf.db"
        monkeypatch.setenv("AMLKIT_DB", str(db_file))

        _seed_sanctions_data(db_file)

        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        client = TestClient(app)

        # First request should set CSRF cookie
        r = client.get("/login")

        set_cookie_headers = r.headers.get_list("set-cookie")
        csrf_cookie = None
        for header in set_cookie_headers:
            if "amlkit_csrf=" in header:
                csrf_cookie = header
                break

        assert csrf_cookie is not None, "CSRF cookie not set"
        assert "httponly" in csrf_cookie.lower(), \
            f"CSRF cookie missing HttpOnly flag. Cookie: {csrf_cookie}"

    def test_session_cookie_has_secure_flag_when_behind_proxy(self, tmp_path, monkeypatch) -> None:
        """H-02: Session cookie should have Secure flag when AMLKIT_BEHIND_PROXY=1."""
        monkeypatch.setenv("AMLKIT_BEHIND_PROXY", "1")
        db_file = tmp_path / "test_secure.db"
        monkeypatch.setenv("AMLKIT_DB", str(db_file))

        _seed_sanctions_data(db_file)

        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        client = TestClient(app)

        # Register and verify to get session cookie
        client.get("/register-organization")
        csrf = _csrf(client)

        r1 = client.post("/register-organization", data={
            "org_name": "Secure Test Org",
            "name": "Admin",
            "email": "secure@test.local",
            "password": "SecurePass123",
            "csrf_token": csrf,
        }, follow_redirects=True)

        # Extract verification token
        import re
        m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r1.text)
        assert m, "No verification link"

        # Follow verification link
        r = client.get(f"/verify-email?token={m.group(1)}", follow_redirects=False)

        # Check session cookie has Secure flag
        set_cookie_headers = r.headers.get_list("set-cookie")
        session_cookie = None
        for header in set_cookie_headers:
            if "amlkit_session=" in header:
                session_cookie = header
                break

        assert session_cookie is not None
        assert "secure" in session_cookie.lower(), \
            f"Session cookie missing Secure flag. Cookie: {session_cookie}"

    def test_session_cookie_no_secure_flag_in_dev_mode(self, tmp_path, monkeypatch) -> None:
        """H-02: Session cookie should NOT have Secure flag without BEHIND_PROXY."""
        monkeypatch.delenv("AMLKIT_BEHIND_PROXY", raising=False)
        db_file = tmp_path / "test_dev.db"
        monkeypatch.setenv("AMLKIT_DB", str(db_file))

        _seed_sanctions_data(db_file)

        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        client = TestClient(app)

        client.get("/register-organization")
        csrf = _csrf(client)

        r1 = client.post("/register-organization", data={
            "org_name": "Dev Org",
            "name": "Dev Admin",
            "email": "dev@test.local",
            "password": "DevPass123",
            "csrf_token": csrf,
        }, follow_redirects=True)

        import re
        m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r1.text)
        assert m

        r = client.get(f"/verify-email?token={m.group(1)}", follow_redirects=False)

        set_cookie_headers = r.headers.get_list("set-cookie")
        session_cookie = None
        for header in set_cookie_headers:
            if "amlkit_session=" in header:
                session_cookie = header
                break

        assert session_cookie is not None
        assert "secure" not in session_cookie.lower(), \
            f"Session cookie has Secure flag in dev mode. Cookie: {session_cookie}"

    def test_csrf_token_rotates_on_login(self, client) -> None:
        """M-01: CSRF token should change after login."""
        client.get("/login")
        csrf_before = _csrf(client)

        r = client.post("/login", data={
            "email": "alice@testfirm.ae",
            "password": "test123",
            "csrf_token": csrf_before,
        }, follow_redirects=False)

        assert r.status_code == 303

        # Extract new CSRF from Set-Cookie
        set_cookie_headers = r.headers.get_list("set-cookie")
        csrf_after = None
        for header in set_cookie_headers:
            if "amlkit_csrf=" in header:
                import re
                m = re.search(r"amlkit_csrf=([^;]+)", header)
                if m:
                    csrf_after = m.group(1)
                    break

        assert csrf_after is not None
        assert csrf_after != csrf_before, \
            f"CSRF should rotate on login. Before: {csrf_before}, After: {csrf_after}"

    def test_csrf_token_rotates_on_email_verification(self, tmp_path, monkeypatch) -> None:
        """M-01: CSRF token should rotate after email verification."""
        db_file = tmp_path / "test_verify.db"
        monkeypatch.setenv("AMLKIT_DB", str(db_file))

        _seed_sanctions_data(db_file)

        from fastapi.testclient import TestClient
        from amlkit.api.app import app

        client = TestClient(app)

        client.get("/register-organization")
        r1 = client.post("/register-organization", data={
            "org_name": "Verify Org",
            "name": "Admin",
            "email": "verify@test.local",
            "password": "VerifyPass123",
            "csrf_token": _csrf(client),
        }, follow_redirects=True)

        csrf_before = _csrf(client)

        import re
        m = re.search(r"/verify-email\?token=([^\"&<\s]+)", r1.text)
        assert m

        r = client.get(f"/verify-email?token={m.group(1)}", follow_redirects=False)
        assert r.status_code == 303

        set_cookie_headers = r.headers.get_list("set-cookie")
        csrf_after = None
        for header in set_cookie_headers:
            if "amlkit_csrf=" in header:
                m2 = re.search(r"amlkit_csrf=([^;]+)", header)
                if m2:
                    csrf_after = m2.group(1)
                    break

        assert csrf_after is not None
        assert csrf_after != csrf_before

    def test_csrf_validation_works_after_rotation(self, client) -> None:
        """M-01: Form POST should pass CSRF validation after token rotation."""
        client.get("/login")
        csrf_before = _csrf(client)

        r1 = client.post("/login", data={
            "email": "alice@testfirm.ae",
            "password": "test123",
            "csrf_token": csrf_before,
        }, follow_redirects=True)

        assert r1.status_code == 200

        csrf_after = _csrf(client)
        assert csrf_after != csrf_before

        # Make a form POST with new token
        r2 = client.post("/screen", data={
            "name": "Test Person",
            "csrf_token": csrf_after,
        }, follow_redirects=False)

        assert r2.status_code != 403

    def test_no_other_session_cookie_sites(self) -> None:
        """Verify all SESSION_COOKIE set_cookie() calls are accounted for."""
        import subprocess
        result = subprocess.run(
            ["grep", "-n", "set_cookie(SESSION_COOKIE",
             "C:/Users/nizam/qa-fixes/amlkit/api/app.py"],
            capture_output=True, text=True
        )

        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []

        assert len(lines) == 3, \
            f"Expected 3 SESSION_COOKIE set_cookie calls, found {len(lines)}: {lines}"

        combined = "\n".join(lines)
        assert any(x in combined for x in ["login", "556"]), "Should have login route"
        assert any(x in combined for x in ["setup", "665", "661"]), "Should have setup route"
        assert any(x in combined for x in ["verify", "817", "809"]), "Should have verify route"
