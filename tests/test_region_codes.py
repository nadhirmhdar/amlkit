"""Tests for T-009: CLDR region codes, multi-nationality, subregion, establishment_date."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.datamodel import (
    UAE_EMIRATES,
    validate_country_code,
    validate_emirate,
)


class TestCountryCodeValidation:
    def test_valid_code_accepted(self):
        validate_country_code("AE")

    def test_lowercase_normalized(self):
        validate_country_code("ae")

    def test_invalid_code_rejected(self):
        with pytest.raises(ValueError, match="country"):
            validate_country_code("XX")

    def test_none_accepted(self):
        validate_country_code(None)

    def test_empty_accepted(self):
        validate_country_code("")


class TestEmirateValidation:
    def test_valid_emirates(self):
        for e in ["ABU_DHABI", "DUBAI", "SHARJAH", "AJMAN", "UMM_AL_QUWAIN", "RAS_AL_KHAIMAH", "FUJAIRAH"]:
            validate_emirate(e)

    def test_invalid_emirate_rejected(self):
        with pytest.raises(ValueError, match="emirate"):
            validate_emirate("MUSCAT")

    def test_none_accepted(self):
        validate_emirate(None)

    def test_empty_accepted(self):
        validate_emirate("")


class TestNationalitiesBackfill:
    def test_backfill_single_nationality(self):
        from amlkit.db import connect, _backfill_nationalities
        conn = connect(":memory:")
        org_id = _create_test_org(conn)
        cust_id = _create_test_customer(conn, org_id, nationality="AE")
        conn.execute("UPDATE customers SET nationalities=NULL WHERE id=?", (cust_id,))
        conn.commit()
        _backfill_nationalities(conn)
        conn.commit()
        row = conn.execute("SELECT nationalities FROM customers WHERE id=?", (cust_id,)).fetchone()
        assert json.loads(row["nationalities"]) == ["AE"]

    def test_backfill_null_nationality_gets_empty_list(self):
        from amlkit.db import connect, _backfill_nationalities
        conn = connect(":memory:")
        org_id = _create_test_org(conn)
        cust_id = _create_test_customer(conn, org_id, nationality=None)
        conn.execute("UPDATE customers SET nationalities=NULL WHERE id=?", (cust_id,))
        conn.commit()
        _backfill_nationalities(conn)
        conn.commit()
        row = conn.execute("SELECT nationalities FROM customers WHERE id=?", (cust_id,)).fetchone()
        assert json.loads(row["nationalities"]) == []

    def test_backfill_idempotent(self):
        from amlkit.db import connect, _backfill_nationalities
        conn = connect(":memory:")
        org_id = _create_test_org(conn)
        cust_id = _create_test_customer(conn, org_id, nationality="US")
        conn.execute("UPDATE customers SET nationalities=NULL WHERE id=?", (cust_id,))
        conn.commit()
        _backfill_nationalities(conn)
        _backfill_nationalities(conn)
        conn.commit()
        row = conn.execute("SELECT nationalities FROM customers WHERE id=?", (cust_id,)).fetchone()
        assert json.loads(row["nationalities"]) == ["US"]


class TestOnboardWithNewFields:
    def _setup(self):
        from amlkit.db import connect, utcnow
        from amlkit.cases.manager import onboard
        conn = connect(":memory:")
        org_id = _create_test_org(conn)
        conn.execute(
            "INSERT INTO datasets (key, title, publisher, is_mandatory, "
            "last_refresh, entity_count, max_age_hours) "
            "VALUES ('test_list', 'Test', 'Test', 1, ?, 1, 24)",
            (utcnow(),),
        )
        conn.commit()
        return conn, org_id

    def test_invalid_nationality_code_rejected(self):
        from amlkit.cases.manager import onboard
        conn, org_id = self._setup()
        with pytest.raises(ValueError, match="country"):
            onboard(
                conn, org_id=org_id, reference="BAD-NAT",
                full_name="Bad Nat", customer_type="natural",
                nationality="XX", actor="test",
            )

    def test_valid_subregion_for_uae(self):
        from amlkit.cases.manager import onboard
        conn, org_id = self._setup()
        result = onboard(
            conn, org_id=org_id, reference="UAE-SUB",
            full_name="UAE Subregion", customer_type="natural",
            country="AE", subregion="DUBAI", actor="test",
        )
        row = conn.execute(
            "SELECT subregion FROM customers WHERE id=?",
            (result.customer_id,),
        ).fetchone()
        assert row["subregion"] == "DUBAI"

    def test_invalid_emirate_for_uae_rejected(self):
        from amlkit.cases.manager import onboard
        conn, org_id = self._setup()
        with pytest.raises(ValueError, match="emirate"):
            onboard(
                conn, org_id=org_id, reference="BAD-EMI",
                full_name="Bad Emirate", customer_type="natural",
                country="AE", subregion="MUSCAT", actor="test",
            )

    def test_multiple_nationalities_stored(self):
        from amlkit.cases.manager import onboard
        conn, org_id = self._setup()
        result = onboard(
            conn, org_id=org_id, reference="DUAL-NAT",
            full_name="Dual National", customer_type="natural",
            nationality="AE", nationalities=["AE", "US"],
            actor="test",
        )
        row = conn.execute(
            "SELECT nationalities FROM customers WHERE id=?",
            (result.customer_id,),
        ).fetchone()
        assert json.loads(row["nationalities"]) == ["AE", "US"]

    def test_establishment_date_for_legal(self):
        from amlkit.cases.manager import onboard
        conn, org_id = self._setup()
        result = onboard(
            conn, org_id=org_id, reference="LEGAL-EST",
            full_name="Test Corp", customer_type="legal",
            establishment_date="2020-01-15", actor="test",
        )
        row = conn.execute(
            "SELECT establishment_date FROM customers WHERE id=?",
            (result.customer_id,),
        ).fetchone()
        assert row["establishment_date"] == "2020-01-15"

    def test_establishment_date_rejected_for_natural(self):
        from amlkit.cases.manager import onboard
        conn, org_id = self._setup()
        with pytest.raises(ValueError, match="establishment_date"):
            onboard(
                conn, org_id=org_id, reference="NAT-EST",
                full_name="Natural Person", customer_type="natural",
                establishment_date="2020-01-15", actor="test",
            )


def _create_test_org(conn):
    cur = conn.execute(
        "INSERT INTO organizations (name, slug, created_at) "
        "VALUES ('Test Org', 'test-org', '2026-01-01')"
    )
    conn.commit()
    return cur.lastrowid


class TestScorerMultiNationality:
    """score_entity must accept query_countries (plural) so that a dual national
    who matches on ANY nationality avoids the country_mismatch penalty."""

    def test_no_mismatch_when_any_nationality_matches(self):
        from amlkit.match.scorer import score_entity
        result = score_entity(
            "Kim Jong Un",
            ["Kim Jong Un"],
            query_countries=["AE", "KP"],
            cand_countries=["KP"],
        )
        adjustments = result.features.get("adjustments", {})
        assert "country_mismatch" not in adjustments

    def test_mismatch_when_no_nationality_matches(self):
        from amlkit.match.scorer import score_entity
        result = score_entity(
            "Kim Jong Un",
            ["Kim Jong Un"],
            query_countries=["AE", "US"],
            cand_countries=["KP"],
        )
        adjustments = result.features.get("adjustments", {})
        assert "country_mismatch" in adjustments

    def test_backward_compat_single_country(self):
        from amlkit.match.scorer import score_entity
        result = score_entity(
            "Kim Jong Un",
            ["Kim Jong Un"],
            query_country="KP",
            cand_countries=["KP"],
        )
        adjustments = result.features.get("adjustments", {})
        assert "country_mismatch" not in adjustments


class TestJurisdictionTierFromNationalities:
    """The highest-risk nationality must determine the jurisdiction tier."""

    def _setup_fatf(self, conn):
        conn.execute(
            """CREATE TABLE IF NOT EXISTS fatf_countries (
                country_code TEXT PRIMARY KEY,
                country_name TEXT NOT NULL,
                list_type TEXT NOT NULL
            )"""
        )
        conn.execute("DELETE FROM fatf_countries")
        conn.execute(
            "INSERT INTO fatf_countries VALUES ('KP', 'DPRK', 'blacklist')"
        )
        conn.execute(
            "INSERT INTO fatf_countries VALUES ('IR', 'Iran', 'blacklist')"
        )
        conn.execute(
            "INSERT INTO fatf_countries VALUES ('NG', 'Nigeria', 'greylist')"
        )
        conn.commit()

    def test_blacklist_nationality_forces_blacklist_tier(self):
        from amlkit.db import connect
        from amlkit.cases.manager import jurisdiction_tier_for_nationalities
        conn = connect(":memory:")
        self._setup_fatf(conn)
        tier = jurisdiction_tier_for_nationalities(conn, ["AE", "IR"])
        assert tier == "fatf_blacklist"

    def test_greylist_nationality_elevates_tier(self):
        from amlkit.db import connect
        from amlkit.cases.manager import jurisdiction_tier_for_nationalities
        conn = connect(":memory:")
        self._setup_fatf(conn)
        tier = jurisdiction_tier_for_nationalities(conn, ["AE", "NG"])
        assert tier == "fatf_greylist"

    def test_safe_nationalities_remain_standard(self):
        from amlkit.db import connect
        from amlkit.cases.manager import jurisdiction_tier_for_nationalities
        conn = connect(":memory:")
        self._setup_fatf(conn)
        tier = jurisdiction_tier_for_nationalities(conn, ["AE", "US"])
        assert tier == "standard"

    def test_empty_list_returns_standard(self):
        from amlkit.db import connect
        from amlkit.cases.manager import jurisdiction_tier_for_nationalities
        conn = connect(":memory:")
        self._setup_fatf(conn)
        tier = jurisdiction_tier_for_nationalities(conn, [])
        assert tier == "standard"


class TestOnboardDualNationalRisk:
    """A dual national where one nationality is high-risk must have the
    jurisdiction factor elevated, even if the other nationality is safe."""

    def _setup(self):
        from amlkit.db import connect, utcnow
        conn = connect(":memory:")
        org_id = _create_test_org(conn)
        conn.execute(
            "INSERT INTO datasets (key, title, publisher, is_mandatory, "
            "last_refresh, entity_count, max_age_hours) "
            "VALUES ('test_list', 'Test', 'Test', 1, ?, 1, 24)",
            (utcnow(),),
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS fatf_countries (
                country_code TEXT PRIMARY KEY,
                country_name TEXT NOT NULL,
                list_type TEXT NOT NULL
            )"""
        )
        conn.execute("DELETE FROM fatf_countries")
        conn.execute(
            "INSERT INTO fatf_countries VALUES ('IR', 'Iran', 'blacklist')"
        )
        conn.execute(
            "INSERT INTO fatf_countries VALUES ('NG', 'Nigeria', 'greylist')"
        )
        conn.commit()
        return conn, org_id

    def test_dual_national_blacklist_elevates_risk(self):
        from amlkit.cases.manager import onboard
        conn, org_id = self._setup()
        result = onboard(
            conn, org_id=org_id, reference="DUAL-BL",
            full_name="Test Dual", customer_type="natural",
            nationality="AE", nationalities=["AE", "IR"],
            actor="test",
        )
        assert result.risk.factors["jurisdiction"]["value"] == "fatf_blacklist"

    def test_dual_national_greylist_elevates_risk(self):
        from amlkit.cases.manager import onboard
        conn, org_id = self._setup()
        result = onboard(
            conn, org_id=org_id, reference="DUAL-GL",
            full_name="Test Dual Grey", customer_type="natural",
            nationality="AE", nationalities=["AE", "NG"],
            actor="test",
        )
        assert result.risk.factors["jurisdiction"]["value"] == "fatf_greylist"


def _create_test_org(conn):
    cur = conn.execute(
        "INSERT INTO organizations (name, slug, created_at) "
        "VALUES ('Test Org', 'test-org', '2026-01-01')"
    )
    conn.commit()
    return cur.lastrowid


def _create_test_customer(conn, org_id, nationality=None):
    cur = conn.execute(
        "INSERT INTO customers (org_id, reference, full_name, customer_type, "
        "canonical_key, nationality, status, onboarded_at, created_at, updated_at) "
        "VALUES (?, 'REF-001', 'Test', 'natural', 'test', ?, "
        "'active', '2026-01-01', '2026-01-01', '2026-01-01')",
        (org_id, nationality),
    )
    conn.commit()
    return cur.lastrowid
