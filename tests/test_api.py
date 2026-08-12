"""Route and constraint tests.

The routes themselves are thin, so the tests that earn their place are the ones
covering the constraints — the rules that stop the interface manufacturing the
thin disposition records that generate inspection findings.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LISTED = "AHMED ABD AL-JALEEL AL-HASNAWI"
LISTED_AR = "أحمد عبد الجليل الحسناوي"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """App wired to a throwaway database seeded with one sanctioned person."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)

    from fastapi.testclient import TestClient

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

    from amlkit.api.app import app

    c = TestClient(app)
    c.post("/operator", data={"name": "alice"}, follow_redirects=True)
    return c


def _first_alert_id(client) -> int:
    import sqlite3

    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id FROM alerts ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert row is not None, "expected an alert to exist"
    return row["id"]


def _alert(client, field: str):
    import sqlite3

    conn = sqlite3.connect(os.environ["AMLKIT_DB"])
    conn.row_factory = sqlite3.Row
    row = conn.execute(f"SELECT {field} FROM alerts ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row[field]


class TestPagesRender:
    @pytest.mark.parametrize("path", ["/", "/screen", "/alerts", "/customers",
                                      "/customers/new", "/audit"])
    def test_page_renders(self, client, path: str) -> None:
        r = client.get(path)
        assert r.status_code == 200
        assert "amlkit" in r.text

    def test_missing_customer_redirects(self, client) -> None:
        r = client.get("/customers/9999", follow_redirects=False)
        assert r.status_code == 303


class TestScreening:
    def test_latin_query_finds_listed_person(self, client) -> None:
        r = client.post("/screen", data={"name": LISTED})
        assert "match(es)" in r.text
        assert "TERRORISM FINANCING" in r.text

    def test_arabic_query_finds_latin_record(self, client) -> None:
        """The differentiator, exercised through the interface."""
        r = client.post("/screen", data={"name": LISTED_AR})
        assert LISTED in r.text

    def test_clear_result_is_still_recorded(self, client) -> None:
        """Evidence that a check happened and came back clean is the point."""
        r = client.post("/screen", data={"name": "Ahmed Al Mansoori"})
        assert "No match" in r.text

        import sqlite3
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        screenings = conn.execute("SELECT COUNT(*) FROM screenings").fetchone()[0]
        alerts = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        conn.close()
        assert screenings >= 1, "a clear screening must still be recorded"
        assert alerts == 0, "a clear screening must not create an alert"

    def test_single_token_warns(self, client) -> None:
        r = client.post("/screen", data={"name": "Mohammed"})
        assert "Single name token" in r.text

    def test_screening_requires_an_operator(self, client) -> None:
        client.cookies.clear()
        r = client.post("/screen", data={"name": LISTED})
        assert "Select an operator" in r.text


class TestOnboarding:
    def test_onboard_and_screen(self, client) -> None:
        r = client.post("/customers", data={
            "reference": "C-1", "full_name": "Ahmed Al Mansoori",
            "customer_type": "natural"}, follow_redirects=True)
        assert r.status_code == 200
        assert "Risk rating" in r.text

    def test_listed_ubo_blocks_a_clean_company(self, client) -> None:
        """A company that screens clean but whose owner does not."""
        r = client.post("/customers", data={
            "reference": "C-2", "full_name": "Falcon Holdings FZE",
            "customer_type": "legal", "sector": "real_estate",
            "ubo_names": [LISTED], "ubo_pcts": ["60"], "ubo_controls": ["ownership"],
        }, follow_redirects=True)
        assert "MATCH FOUND" in r.text

    def test_duplicate_reference_rejected(self, client) -> None:
        data = {"reference": "C-3", "full_name": "Test Co", "customer_type": "legal"}
        client.post("/customers", data=data, follow_redirects=True)
        r = client.post("/customers", data=data, follow_redirects=True)
        assert "already exists" in r.text


class TestDispositionConstraints:
    """These are the tests that matter: the interface must not allow a record
    too thin to survive inspection."""

    @pytest.fixture()
    def alert_id(self, client):
        client.post("/customers", data={
            "reference": "C-A", "full_name": "Falcon Holdings FZE",
            "customer_type": "legal",
            "ubo_names": [LISTED], "ubo_pcts": ["60"], "ubo_controls": ["ownership"],
        }, follow_redirects=True)
        return _first_alert_id(client)

    def test_reason_code_is_required(self, client, alert_id) -> None:
        r = client.post(f"/alerts/{alert_id}/disposition",
                        data={"status": "false_positive", "reason_code": ""},
                        follow_redirects=True)
        assert "invalid reason code" in r.text
        assert _alert(client, "status") == "open"

    def test_true_positive_requires_narrative(self, client, alert_id) -> None:
        r = client.post(f"/alerts/{alert_id}/disposition",
                        data={"status": "true_positive", "reason_code": "confirmed_match",
                              "narrative": ""}, follow_redirects=True)
        assert "narrative is required" in r.text
        assert _alert(client, "status") == "open"

    def test_other_reason_requires_narrative(self, client, alert_id) -> None:
        r = client.post(f"/alerts/{alert_id}/disposition",
                        data={"status": "false_positive", "reason_code": "other",
                              "narrative": ""}, follow_redirects=True)
        assert "requires a narrative" in r.text

    def test_disposition_requires_an_operator(self, client, alert_id) -> None:
        client.cookies.clear()
        r = client.post(f"/alerts/{alert_id}/disposition",
                        data={"status": "false_positive", "reason_code": "different_dob"},
                        follow_redirects=True)
        assert "Select an operator" in r.text


class TestFourEyes:
    @pytest.fixture()
    def alert_id(self, client):
        client.post("/customers", data={
            "reference": "C-B", "full_name": "Falcon Two FZE", "customer_type": "legal",
            "ubo_names": [LISTED], "ubo_pcts": ["60"], "ubo_controls": ["ownership"],
        }, follow_redirects=True)
        return _first_alert_id(client)

    def test_dismissal_is_staged_for_review(self, client, alert_id) -> None:
        r = client.post(f"/alerts/{alert_id}/disposition",
                        data={"status": "false_positive", "reason_code": "different_dob"},
                        follow_redirects=True)
        assert "independent review" in r.text.lower()
        assert _alert(client, "status") == "pending_review"

    def test_same_operator_cannot_confirm_own_dismissal(self, client, alert_id) -> None:
        client.post(f"/alerts/{alert_id}/disposition",
                    data={"status": "false_positive", "reason_code": "different_dob"},
                    follow_redirects=True)
        r = client.post(f"/alerts/{alert_id}/confirm",
                        data={"agree": "yes"}, follow_redirects=True)
        assert "different operator" in r.text
        assert _alert(client, "status") == "pending_review"

    def test_second_operator_completes_review(self, client, alert_id) -> None:
        client.post(f"/alerts/{alert_id}/disposition",
                    data={"status": "false_positive", "reason_code": "different_dob"},
                    follow_redirects=True)
        client.post("/operator", data={"name": "bob"}, follow_redirects=True)
        client.post(f"/alerts/{alert_id}/confirm", data={"agree": "yes"},
                    follow_redirects=True)
        assert _alert(client, "status") == "false_positive"
        assert _alert(client, "independent_review") == "completed"

    def test_confirming_a_match_needs_no_second_operator(self, client, alert_id) -> None:
        """Confirmation escalates to freeze and report, which carries its own
        scrutiny; only dismissal needs the second pair of eyes."""
        client.post(f"/alerts/{alert_id}/disposition",
                    data={"status": "true_positive", "reason_code": "confirmed_match",
                          "narrative": "Passport and DOB both match the designation."},
                    follow_redirects=True)
        assert _alert(client, "status") == "true_positive"

    def test_single_operator_mode_records_the_gap(self, client, alert_id, monkeypatch) -> None:
        """The control gap must be visible at inspection, not silently waived."""
        monkeypatch.setenv("AMLKIT_SINGLE_OPERATOR_MODE", "1")
        r = client.post(f"/alerts/{alert_id}/disposition",
                        data={"status": "false_positive", "reason_code": "different_dob"},
                        follow_redirects=True)
        assert _alert(client, "status") == "false_positive"
        assert _alert(client, "independent_review") == "single_operator"
        assert "no independent review" in r.text.lower()


class TestEvidencePack:
    def test_evidence_pack_contains_the_record(self, client) -> None:
        client.post("/customers", data={
            "reference": "C-E", "full_name": "Falcon Three FZE", "customer_type": "legal",
            "ubo_names": [LISTED], "ubo_pcts": ["60"], "ubo_controls": ["ownership"],
        }, follow_redirects=True)
        import sqlite3
        conn = sqlite3.connect(os.environ["AMLKIT_DB"])
        cid = conn.execute("SELECT id FROM customers ORDER BY id DESC LIMIT 1").fetchone()[0]
        conn.close()

        r = client.get(f"/customers/{cid}/evidence")
        assert r.status_code == 200
        for expected in ["Customer due diligence record", "Beneficial ownership",
                         "Screening record", "Audit trail", LISTED]:
            assert expected in r.text, f"evidence pack missing {expected!r}"


class TestAudit:
    def test_actions_are_attributed(self, client) -> None:
        client.post("/screen", data={"name": LISTED})
        r = client.get("/audit")
        assert "alice" in r.text
