"""WP-4 screening correctness (L-53, L-28, L-29, L-30, L-9, L-6, L-54).

Each test passes after the fix and fails before it. Real SQLite, no DB mocks,
same fixtures as test_api.py (web) and test_mobile_api.py (JSON API).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_api import LISTED, _csrf, _db, client  # noqa: E402,F401
from tests.test_mobile_api import api  # noqa: E402,F401

CYRILLIC = "Иван Петров"


def _org_id(conn) -> int:
    return conn.execute("SELECT id FROM organizations ORDER BY id LIMIT 1").fetchone()[0]


def _manager_conn(client):
    """Direct connection to the test DB (client fixture has registered an org)."""
    from amlkit.db import connect
    import os
    conn = connect(os.environ["AMLKIT_DB"])
    return conn, _org_id(conn)


def _new_customer_form(client, **over):
    data = {"reference": "C-1", "full_name": "Jane Roe", "customer_type": "natural",
            "csrf_token": _csrf(client)}
    data.update(over)
    return client.post("/customers", data=data, follow_redirects=False)


# ------------------------------------------------------------ L-53 blank name
class TestBlankName:
    @pytest.mark.parametrize("blank", ["", "   ", "\t\n", "​​", "　", "️"])
    def test_manager_rejects_blank_full_name(self, client, blank):
        from amlkit.cases import manager
        conn, org = _manager_conn(client)
        with pytest.raises(ValueError, match="full_name is required"):
            manager.onboard(conn, org_id=org, reference="B-1", full_name=blank)
        assert conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0

    def test_web_whitespace_name_is_400_with_form_error(self, client):
        r = _new_customer_form(client, full_name="   ")
        assert r.status_code == 400
        assert "full_name is required" in r.text
        assert "<form" in r.text  # the onboarding form is re-shown
        conn = _db()
        assert conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0

    def test_web_invisible_only_name_is_400(self, client):
        assert _new_customer_form(client, full_name="​⠀").status_code == 400

    def test_mobile_whitespace_name_is_422(self, api):
        c, h = api
        r = c.post("/api/v1/customers", headers=h,
                   json={"reference": "M-1", "full_name": "   "})
        assert r.status_code == 422, r.text
        assert "full_name is required" in r.json()["detail"]
        assert c.get("/api/v1/customers", headers=h).json()["customers"] == []

    def test_blank_owner_rejected_before_customer_is_created(self, client):
        from amlkit.cases import manager
        conn, org = _manager_conn(client)
        with pytest.raises(ValueError, match="person_name is required"):
            manager.onboard(conn, org_id=org, reference="B-2", full_name="Jane Roe",
                            ubos=[{"person_name": "  ", "ownership_pct": 30}])
        assert conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0

    def test_add_ubo_rejects_blank(self, client):
        from amlkit.cases import manager
        conn, org = _manager_conn(client)
        res = manager.onboard(conn, org_id=org, reference="B-3", full_name="Jane Roe")
        with pytest.raises(ValueError, match="person_name is required"):
            manager.add_ubo(conn, res.customer_id, org_id=org, person_name="   ")

    def test_web_ubo_add_blank(self, client):
        from amlkit.cases import manager
        conn, org = _manager_conn(client)
        cid = manager.onboard(conn, org_id=org, reference="B-4", full_name="Jane Roe").customer_id
        r = client.post(f"/customers/{cid}/ubo",
                        data={"person_name": "   ", "csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "person_name is required" in r.text
        assert _db().execute("SELECT COUNT(*) FROM ubo_links").fetchone()[0] == 0

    def test_mobile_ubo_add_blank_is_422(self, api):
        c, h = api
        cid = c.post("/api/v1/customers", headers=h,
                     json={"reference": "M-2", "full_name": "Jane Roe"}).json()["customer_id"]
        r = c.post(f"/api/v1/customers/{cid}/ubo", headers=h, json={"person_name": "  "})
        assert r.status_code == 422, r.text

    def test_adhoc_screen_rejects_blank_web(self, client):
        r = client.post("/screen", data={"name": "​  ", "csrf_token": _csrf(client)})
        assert "Enter a name to screen." in r.text

    def test_adhoc_screen_rejects_blank_mobile(self, api):
        c, h = api
        assert c.post("/api/v1/screen", headers=h, json={"name": "​️ "}).status_code == 400
        assert c.post("/api/v1/screen", headers=h, json={"name": "   "}).status_code == 400

    def test_engine_never_reports_blank_as_clear(self, client):
        from amlkit.match.engine import screen
        conn, org = _manager_conn(client)
        res = screen(conn, "", org_id=org, trigger="adhoc", persist=False)
        assert res.unscreenable and not res.clear


# ------------------------------------------------------------ L-28 unscreenable
class TestUnscreenablePersisted:
    def test_onboard_persists_flag_and_result(self, client):
        from amlkit.cases import manager
        conn, org = _manager_conn(client)
        res = manager.onboard(conn, org_id=org, reference="U-1", full_name=CYRILLIC)
        assert res.unscreenable and res.unscreenable_names == [CYRILLIC]
        row = conn.execute("SELECT unscreenable, hits FROM screenings WHERE customer_id=?",
                           (res.customer_id,)).fetchone()
        assert row["unscreenable"] == 1 and row["hits"] == 0

    def test_normal_name_is_not_flagged(self, client):
        from amlkit.cases import manager
        conn, org = _manager_conn(client)
        res = manager.onboard(conn, org_id=org, reference="U-2", full_name="Jane Roe")
        assert not res.unscreenable
        assert conn.execute("SELECT unscreenable FROM screenings").fetchone()[0] == 0

    def test_web_onboarding_warns_and_customer_page_shows_banner(self, client):
        r = _new_customer_form(client, reference="U-3", full_name=CYRILLIC)
        assert r.status_code == 303
        page = client.get(r.headers["location"])
        assert "could NOT be screened" in page.text          # onboarding flash
        assert 'id="unscreenable-banner"' in page.text       # persistent banner
        assert "not</strong> a clear result" in page.text

    def test_clear_customer_has_no_banner(self, client):
        r = _new_customer_form(client, reference="U-4", full_name="Jane Roe")
        page = client.get(r.headers["location"])
        assert 'id="unscreenable-banner"' not in page.text

    def test_mobile_onboarding_and_ubo_add_surface_flag(self, api):
        c, h = api
        r = c.post("/api/v1/customers", headers=h,
                   json={"reference": "M-3", "full_name": CYRILLIC})
        assert r.status_code == 200, r.text
        assert r.json()["unscreenable"] is True
        cid = c.post("/api/v1/customers", headers=h,
                     json={"reference": "M-4", "full_name": "Jane Roe"}).json()
        assert cid["unscreenable"] is False
        u = c.post(f"/api/v1/customers/{cid['customer_id']}/ubo", headers=h,
                   json={"person_name": CYRILLIC})
        assert u.json()["unscreenable"] is True

    def test_web_ubo_add_says_not_screened(self, client):
        from amlkit.cases import manager
        conn, org = _manager_conn(client)
        cid = manager.onboard(conn, org_id=org, reference="U-5", full_name="Jane Roe").customer_id
        r = client.post(f"/customers/{cid}/ubo",
                        data={"person_name": CYRILLIC, "ownership_pct": "40",
                              "csrf_token": _csrf(client)}, follow_redirects=True)
        assert "NOT screened" in r.text and "screened clear" not in r.text

    def test_rescreen_all_counts_unscreenable(self, client):
        from amlkit.cases import manager
        from amlkit.match.engine import rescreen_all
        conn, org = _manager_conn(client)
        manager.onboard(conn, org_id=org, reference="U-6", full_name=CYRILLIC)
        out = rescreen_all(conn, org)
        assert out["unscreenable"] == 1


# ------------------------------------------------------------ L-29 invisible chars
INVISIBLE_VARIANTS = {
    "VS16": "AHMED ABD AL-JA️LEEL AL-HASNAWI",
    "combining grapheme joiner": "AHMED ABD AL-JA͏LEEL AL-HASNAWI",
    "C0 control": "AHMED ABD AL-JA\x01LEEL AL-HASNAWI",
    "DEL": "AHMED ABD AL-JA\x7fLEEL AL-HASNAWI",
    "braille blank": "AHMED ABD AL-JA⠀LEEL AL-HASNAWI",
    "private use": "AHMED ABD AL-JALEEL AL-HASNAWI",
    "ideographic space": "AHMED　ABD AL-JALEEL AL-HASNAWI",
}


class TestInvisibleCharacters:
    @pytest.mark.parametrize("label", sorted(INVISIBLE_VARIANTS))
    def test_variant_hits_plain_name_at_full_score(self, client, label):
        from amlkit.match.engine import screen
        conn, org = _manager_conn(client)
        res = screen(conn, INVISIBLE_VARIANTS[label], org_id=org, trigger="adhoc", persist=False)
        assert res.hits, f"{label}: MISS"
        assert res.hits[0].score == pytest.approx(1.0)

    def test_clean_name_text_drops_or_normalises(self):
        from amlkit.names.arabic import canonical_key, clean_name_text
        assert clean_name_text("A️B͏C\x01D\x7fE⠀FG") == "ABCDEFG"
        assert clean_name_text("A　B C D") == "A B C D"
        assert clean_name_text("A\tB\nC") == "A B C"
        # Arabic marks that canonicalisation relies on survive
        assert canonical_key("مُحَمَّد") == canonical_key("محمد")

    def test_fullwidth_nfkc(self):
        from amlkit.names.arabic import canonical_key
        assert canonical_key("ＡＨＭＥＤ") == canonical_key("AHMED")


# ------------------------------------------------------------ L-30 banner
class TestRescreenBanner:
    def test_rescreen_all_shows_success_banner_not_failure(self, client):
        r = client.post("/admin/rescreen", data={"csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert r.status_code == 200
        assert "Re-screening failed" not in r.text
        assert "Re-screened" in r.text

    def test_banner_reports_new_alerts(self, client):
        from amlkit.cases import manager
        conn, org = _manager_conn(client)
        manager.onboard(conn, org_id=org, reference="R-1", full_name="Jane Roe")
        manager.add_ubo(conn, 1, org_id=org, person_name=LISTED, ownership_pct=10)
        conn.commit()
        r = client.post("/admin/rescreen", data={"csrf_token": _csrf(client)},
                        follow_redirects=True)
        assert "Re-screened" in r.text and "new alert(s) raised" in r.text


# ------------------------------------------------------------ L-9 re-alert
def _statuses(conn):
    return [(r["id"], r["status"]) for r in conn.execute("SELECT id, status FROM alerts ORDER BY id")]


class TestRealertDedupe:
    @pytest.fixture()
    def seeded(self, client):
        from amlkit.cases import manager
        conn, org = _manager_conn(client)
        manager.onboard(conn, org_id=org, reference="D-1", full_name=LISTED)
        conn.commit()
        assert _statuses(conn) == [(1, "open")]
        return conn, org

    def test_pending_review_is_not_duplicated(self, seeded):
        from amlkit.match.engine import rescreen_all
        conn, org = seeded
        conn.execute("UPDATE alerts SET status='pending_review' WHERE id=1")
        out = rescreen_all(conn, org)
        assert out["alerts"] == 0
        assert _statuses(conn) == [(1, "pending_review")]

    def test_dismissed_unchanged_entity_is_not_reopened(self, seeded):
        from amlkit.match.engine import rescreen_all
        conn, org = seeded
        conn.execute("UPDATE alerts SET status='false_positive',"
                     " dispositioned_at='2026-01-02T00:00:00+00:00' WHERE id=1")
        conn.execute("UPDATE entities SET content_changed_at='2026-01-01T00:00:00+00:00'")
        assert rescreen_all(conn, org)["alerts"] == 0
        assert rescreen_all(conn, org)["alerts"] == 0
        assert _statuses(conn) == [(1, "false_positive")]

    def test_dismissed_entity_never_hashed_is_not_reopened(self, seeded):
        from amlkit.match.engine import rescreen_all
        conn, org = seeded
        conn.execute("UPDATE alerts SET status='false_positive',"
                     " dispositioned_at='2026-01-02T00:00:00+00:00' WHERE id=1")
        assert conn.execute("SELECT content_changed_at FROM entities").fetchone()[0] is None
        assert rescreen_all(conn, org)["alerts"] == 0

    def test_dismissed_then_entity_changed_is_reopened(self, seeded):
        from amlkit.match.engine import rescreen_all
        conn, org = seeded
        conn.execute("UPDATE alerts SET status='false_positive',"
                     " dispositioned_at='2026-01-02T00:00:00+00:00' WHERE id=1")
        conn.execute("UPDATE entities SET content_changed_at='2026-01-03T00:00:00+00:00'")
        assert rescreen_all(conn, org)["alerts"] == 1
        assert _statuses(conn) == [(1, "false_positive"), (2, "open")]
        # ...and the new open alert is itself deduped on the next run
        assert rescreen_all(conn, org)["alerts"] == 0

    def test_true_positive_keeps_realerting(self, seeded):
        from amlkit.match.engine import rescreen_all
        conn, org = seeded
        conn.execute("UPDATE alerts SET status='true_positive' WHERE id=1")
        assert rescreen_all(conn, org)["alerts"] == 1

    def test_open_still_deduped(self, seeded):
        from amlkit.match.engine import rescreen_all
        conn, org = seeded
        assert rescreen_all(conn, org)["alerts"] == 0

    def test_loader_bumps_content_changed_at_only_on_real_change(self, tmp_path):
        from amlkit.db import connect
        from amlkit.ingest.base import SourceEntity
        from amlkit.ingest.loader import load

        class Adapter:
            key, title, publisher = "wp4_list", "WP4", "test"
            source_url, licence, is_mandatory = "x", "test", False

            def __init__(self, dob):
                self.dob = dob

            def fetch(self):
                return b""

            def parse(self, payload):
                yield SourceEntity(source_id="E1", schema_type="Person", caption=LISTED,
                                   names=[], countries=["ly"], birth_date=self.dob,
                                   topics=["sanction"])

        conn = connect(str(tmp_path / "ld.db"))
        load(conn, Adapter("1975-03-12"))
        first = dict(conn.execute("SELECT content_hash, content_changed_at FROM entities").fetchone())
        assert first["content_hash"] and first["content_changed_at"] is None
        load(conn, Adapter("1975-03-12"))
        same = dict(conn.execute("SELECT content_hash, content_changed_at FROM entities").fetchone())
        assert same == first
        load(conn, Adapter("1976-01-01"))
        changed = dict(conn.execute("SELECT content_hash, content_changed_at FROM entities").fetchone())
        assert changed["content_hash"] != first["content_hash"]
        assert changed["content_changed_at"] is not None


# ------------------------------------------------------------ L-6 coverage
class TestRescreenCoversAllRelatedParties:
    def test_ten_percent_owner_is_screened(self, client):
        from amlkit.cases import manager
        from amlkit.match.engine import rescreen_all
        conn, org = _manager_conn(client)
        cid = manager.onboard(conn, org_id=org, reference="O-1", full_name="Jane Roe").customer_id
        uid = manager.add_ubo(conn, cid, org_id=org, person_name=LISTED, ownership_pct=10)
        assert conn.execute("SELECT is_ubo FROM ubo_links WHERE id=?", (uid,)).fetchone()[0] == 0
        out = rescreen_all(conn, org)
        assert out["alerts"] == 1
        row = conn.execute("SELECT ubo_id FROM screenings WHERE trigger='list_update'"
                           " AND ubo_id IS NOT NULL").fetchone()
        assert row["ubo_id"] == uid

    def test_nominee_is_screened(self, client):
        from amlkit.cases import manager
        from amlkit.match.engine import rescreen_all
        conn, org = _manager_conn(client)
        cid = manager.onboard(conn, org_id=org, reference="O-2", full_name="Jane Roe").customer_id
        manager.add_ubo(conn, cid, org_id=org, person_name=LISTED, is_nominee=True)
        assert rescreen_all(conn, org)["alerts"] == 1


# ------------------------------------------------------------ L-54 sector
class TestSectorValidation:
    def test_validator_rejects_unknown_sector(self):
        from amlkit.risk.model import validate_risk_inputs
        with pytest.raises(ValueError, match="Invalid sector: 'realestate'"):
            validate_risk_inputs(sector="realestate")
        validate_risk_inputs(sector="real_estate")
        validate_risk_inputs(sector=None)

    def test_onboard_rejects_unknown_sector_without_creating_customer(self, client):
        from amlkit.cases import manager
        conn, org = _manager_conn(client)
        with pytest.raises(ValueError, match="Invalid sector"):
            manager.onboard(conn, org_id=org, reference="S-1", full_name="Jane Roe",
                            sector="realestate")
        assert conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0

    def test_mobile_create_and_patch_reject_unknown_sector(self, api):
        c, h = api
        r = c.post("/api/v1/customers", headers=h,
                   json={"reference": "S-2", "full_name": "Jane Roe", "sector": "realestate"})
        assert r.status_code == 422 and "Invalid sector" in r.json()["detail"]
        cid = c.post("/api/v1/customers", headers=h,
                     json={"reference": "S-3", "full_name": "Jane Roe",
                           "sector": "real_estate"}).json()["customer_id"]
        r = c.patch(f"/api/v1/customers/{cid}/risk-factors", headers=h,
                    json={"sector": "realestate"})
        assert r.status_code == 422 and "Invalid sector" in r.json()["detail"]

    def test_web_onboarding_shows_error_for_unknown_sector(self, client):
        r = _new_customer_form(client, reference="S-4", sector="realestate")
        assert r.status_code == 303
        page = client.get(r.headers["location"])
        assert "Invalid sector" in page.text
