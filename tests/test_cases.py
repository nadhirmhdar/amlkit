"""Risk model and CDD case-management tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import (  # noqa: E402
    UBO_THRESHOLD_PCT,
    add_ubo,
    close_relationship,
    onboard,
    ownership_state,
)
from amlkit.db import connect, upsert_dataset, utcnow  # noqa: E402
from amlkit.names.arabic import blocking_keys, canonical_key  # noqa: E402
from amlkit.risk.model import CustomerProfile, assess, ruleset  # noqa: E402

LISTED = "AHMED ABD AL-JALEEL AL-HASNAWI"

# disposition_alert() and its tests were removed: cases/manager.py's
# single-shot disposition function was superseded by the four-eyes workflow
# in cases/review.py (propose_disposition/confirm_disposition), which is what
# every route actually calls. Nothing in the application called the old
# function any more -- keeping it around meant a weaker, bypass-capable
# disposition path sitting next to the real one, which is worse than no
# fallback at all. Its two properties (score never rewritten; invalid status
# rejected) are covered against the real workflow in test_api.py.


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
    ds = upsert_dataset(c, "test_list", "Synthetic Test List", is_mandatory=True)
    now = utcnow()
    cur = c.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           countries, birth_date, gender, topics, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (ds, "SYN-1", "Person", LISTED, '["ly"]', "1975-03-12", "male",
         '["sanction"]', "{}", now, now),
    )
    eid = cur.lastrowid
    c.execute(
        "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
        " VALUES (?,?,?,?,?)", (eid, LISTED, "primary", canonical_key(LISTED), "latin"))
    for tok in blocking_keys(LISTED):
        c.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)", (tok, eid))
    c.commit()
    yield c
    c.close()


class TestRiskModel:
    def test_clean_individual_is_low(self) -> None:
        r = assess(CustomerProfile(sector="professional_services"))
        assert r.rating == "low"
        assert not r.requires_edd

    def test_sanctions_hit_forces_high(self) -> None:
        """A sanctions match is a prohibition, not a factor to be averaged."""
        r = assess(CustomerProfile(sanctions_hit=True))
        assert r.rating == "high"
        assert r.requires_edd

    def test_blacklist_jurisdiction_forces_high(self) -> None:
        r = assess(CustomerProfile(jurisdiction_tier="fatf_blacklist"))
        assert r.rating == "high"

    def test_pep_triggers_edd_even_at_low_score(self) -> None:
        """PEP status is not suspicion but always mandates EDD."""
        r = assess(CustomerProfile(pep_status="domestic_pep"))
        assert r.requires_edd

    def test_cumulative_factors_reach_high(self) -> None:
        r = assess(
            CustomerProfile(
                sector="precious_metals_stones",
                ownership_state="ubo_undisclosed",
                delivery_channel="non_face_to_face_unverified",
                cash_level="predominantly_cash",
                structure="offshore_company",
            )
        )
        assert r.rating == "high"

    def test_assessment_records_ruleset_version(self) -> None:
        """A rating without a dated ruleset version is not evidence."""
        r = assess(CustomerProfile())
        assert r.ruleset_version == ruleset()["version"]

    def test_factors_are_explained(self) -> None:
        r = assess(CustomerProfile(sector="real_estate"))
        assert "sector" in r.factors
        assert "real_estate" in r.explain()

    def test_review_interval_shortens_with_risk(self) -> None:
        low = assess(CustomerProfile())
        high = assess(CustomerProfile(sanctions_hit=True))
        assert high.next_review < low.next_review


class TestOwnershipState:
    def test_natural_person_transparent(self, conn) -> None:
        assert ownership_state(conn, 1, "natural") == "fully_transparent"

    def test_company_without_ubo_is_opaque(self, conn) -> None:
        """Absence of UBO data must not default to transparent."""
        assert ownership_state(conn, 999, "legal") == "ubo_undisclosed"

    def test_sub_threshold_holder_is_not_a_ubo(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-1", full_name="Test LLC",
                      customer_type="legal")
        add_ubo(conn, res.customer_id, org_id=org_id, person_name="Minor Holder",
               ownership_pct=15.0)
        assert ownership_state(conn, res.customer_id, "legal") == "ubo_undisclosed"

    def test_senior_official_fallback_counts(self, conn, org_id) -> None:
        """Cabinet Res. 134/2025 fallback when nobody meets the 25% test."""
        res = onboard(conn, org_id=org_id, reference="C-2", full_name="Test LLC 2",
                      customer_type="legal")
        uid = add_ubo(conn, res.customer_id, org_id=org_id, person_name="The Director",
                      control_type="senior_official")
        row = conn.execute("SELECT is_ubo FROM ubo_links WHERE id=?", (uid,)).fetchone()
        assert row["is_ubo"] == 1

    def test_threshold_is_twenty_five(self) -> None:
        assert UBO_THRESHOLD_PCT == 25.0


class TestOnboarding:
    def test_clean_customer_not_blocked(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-100", full_name="Ahmed Al Mansoori",
                      customer_type="natural", nationality="ae")
        assert not res.blocked
        assert res.screening.clear

    def test_listed_customer_is_blocked(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-101", full_name=LISTED,
                      customer_type="natural")
        assert res.blocked
        assert res.risk.rating == "high"

    def test_listed_ubo_blocks_clean_company(self, conn, org_id) -> None:
        """The gap cheap tools leave: the company screens clean, the owner does not."""
        res = onboard(
            conn, org_id=org_id, reference="C-102", full_name="Falcon Holdings FZE",
            customer_type="legal", sector="real_estate",
            ubos=[{"person_name": LISTED, "ownership_pct": 60.0, "nationality": "ly"}],
        )
        assert res.screening.clear, "company itself should screen clean"
        assert res.blocked, "listed UBO must block the relationship"
        assert res.risk.rating == "high"

    def test_onboarding_is_audited(self, conn, org_id) -> None:
        onboard(conn, org_id=org_id, reference="C-103", full_name="Test Person",
               actor="mlro@firm.ae")
        n = conn.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE action='customer.onboard'"
        ).fetchone()["c"]
        assert n >= 1

    def test_clear_screening_still_recorded(self, conn, org_id) -> None:
        """Evidence that a customer WAS screened matters even when clean."""
        res = onboard(conn, org_id=org_id, reference="C-104", full_name="Ahmed Al Mansoori")
        n = conn.execute(
            "SELECT COUNT(*) c FROM screenings WHERE customer_id=?", (res.customer_id,)
        ).fetchone()["c"]
        assert n >= 1

    def test_second_org_can_reuse_the_same_reference(self, conn, org_id) -> None:
        """References are unique per firm, not globally -- two different
        firms will plausibly both pick the same first reference."""
        onboard(conn, org_id=org_id, reference="C-DUP", full_name="Firm One Customer")
        other_org = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
            " RETURNING id",
            ("Other Firm", "other-firm", "active", utcnow()),
        ).fetchone()["id"]
        res = onboard(conn, org_id=other_org, reference="C-DUP", full_name="Firm Two Customer")
        assert res.reference == "C-DUP"


class TestRetention:
    def test_five_year_retention_recorded(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-300", full_name="Ahmed Al Mansoori")
        until = close_relationship(conn, res.customer_id, org_id=org_id)
        row = conn.execute(
            "SELECT status, retention_until FROM customers WHERE id=?", (res.customer_id,)
        ).fetchone()
        assert row["status"] == "closed"
        assert row["retention_until"] == until
        from datetime import date
        assert int(until[:4]) - date.today().year == 5
