"""Risk model and CDD case-management tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import (  # noqa: E402
    RETENTION_YEARS,
    UBO_THRESHOLD_PCT,
    StaleDatasetsError,
    add_ubo,
    close_relationship,
    onboard,
    ownership_state,
    purge_expired,
)
from amlkit.ingest.loader import datasets_fresh  # noqa: E402
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
    # Make dataset fresh so onboarding tests pass
    c.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
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
    def test_natural_person_transparent(self, conn, org_id) -> None:
        assert ownership_state(conn, 1, org_id, "natural") == "fully_transparent"

    def test_company_without_ubo_is_opaque(self, conn, org_id) -> None:
        """Absence of UBO data must not default to transparent."""
        assert ownership_state(conn, 999, org_id, "legal") == "ubo_undisclosed"

    def test_sub_threshold_holder_is_not_a_ubo(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-1", full_name="Test LLC",
                      customer_type="legal")
        add_ubo(conn, res.customer_id, org_id=org_id, person_name="Minor Holder",
                ownership_pct=15.0)
        assert ownership_state(conn, res.customer_id, org_id, "legal") == "ubo_undisclosed"

    def test_ownership_state_ignores_other_org_ubo(self, conn, org_id) -> None:
        """A UBO row inserted under a different org must not count toward
        this org's own customer's ownership-opacity band."""
        other_org = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
            " RETURNING id",
            ("Other Firm", "other-firm", "active", utcnow()),
        ).fetchone()["id"]
        conn.commit()
        res = onboard(conn, org_id=org_id, reference="C-3", full_name="Test LLC 3",
                      customer_type="legal")
        # Simulate a cross-tenant row directly (add_ubo itself now rejects this).
        conn.execute(
            """INSERT INTO ubo_links
               (org_id, customer_id, person_name, canonical_key, ownership_pct,
                control_type, is_ubo, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (other_org, res.customer_id, "Injected Holder", "injected holder",
             100.0, "ownership", 1, utcnow()),
        )
        conn.commit()
        assert ownership_state(conn, res.customer_id, org_id, "legal") == "ubo_undisclosed"

    def test_add_ubo_rejects_customer_from_other_org(self, conn, org_id) -> None:
        other_org = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
            " RETURNING id",
            ("Other Firm 2", "other-firm-2", "active", utcnow()),
        ).fetchone()["id"]
        conn.commit()
        res = onboard(conn, org_id=org_id, reference="C-4", full_name="Test LLC 4",
                      customer_type="legal")
        with pytest.raises(ValueError):
            add_ubo(conn, res.customer_id, org_id=other_org, person_name="Attacker Holder",
                   ownership_pct=100.0)

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

    def test_add_ubo_rejects_ownership_over_100(self, conn, org_id) -> None:
        """Ownership percentage cannot exceed 100%."""
        res = onboard(conn, org_id=org_id, reference="C-5", full_name="Test LLC 5",
                      customer_type="legal")
        with pytest.raises(ValueError, match="ownership percentage must be between 0 and 100"):
            add_ubo(conn, res.customer_id, org_id=org_id, person_name="Over Holder",
                   ownership_pct=150.0)

    def test_add_ubo_rejects_negative_ownership(self, conn, org_id) -> None:
        """Negative ownership percentage is invalid."""
        res = onboard(conn, org_id=org_id, reference="C-6", full_name="Test LLC 6",
                      customer_type="legal")
        with pytest.raises(ValueError, match="ownership percentage must be between 0 and 100"):
            add_ubo(conn, res.customer_id, org_id=org_id, person_name="Negative Holder",
                   ownership_pct=-25.0)

    def test_add_ubo_accepts_zero_ownership(self, conn, org_id) -> None:
        """Zero ownership is valid for control without equity."""
        res = onboard(conn, org_id=org_id, reference="C-7", full_name="Test LLC 7",
                      customer_type="legal")
        uid = add_ubo(conn, res.customer_id, org_id=org_id, person_name="Control Only",
                     ownership_pct=0.0, control_type="voting_rights")
        row = conn.execute("SELECT ownership_pct, is_ubo FROM ubo_links WHERE id=?", (uid,)).fetchone()
        assert row["ownership_pct"] == 0.0
        assert row["is_ubo"] == 0  # Below 25% threshold

    def test_add_ubo_accepts_hundred_percent_ownership(self, conn, org_id) -> None:
        """100% ownership is valid."""
        res = onboard(conn, org_id=org_id, reference="C-8", full_name="Test LLC 8",
                      customer_type="legal")
        uid = add_ubo(conn, res.customer_id, org_id=org_id, person_name="Sole Owner",
                     ownership_pct=100.0)
        row = conn.execute("SELECT ownership_pct, is_ubo FROM ubo_links WHERE id=?", (uid,)).fetchone()
        assert row["ownership_pct"] == 100.0
        assert row["is_ubo"] == 1


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
    def test_add_ubo_nominee_flag_stored(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-NOM1", full_name="Test Corp",
                      customer_type="legal")
        ubo_id = add_ubo(conn, res.customer_id, org_id=org_id, person_name="Nominee Person",
                         ownership_pct=30.0, is_nominee=True)
        row = conn.execute("SELECT is_nominee, is_ubo FROM ubo_links WHERE id=?", (ubo_id,)).fetchone()
        assert row["is_nominee"] == 1

    def test_nominee_ubo_is_never_beneficial_owner(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-NOM2", full_name="Test Corp 2",
                      customer_type="legal")
        ubo_id = add_ubo(conn, res.customer_id, org_id=org_id, person_name="Big Nominee",
                         ownership_pct=100.0, is_nominee=True)
        row = conn.execute("SELECT is_ubo FROM ubo_links WHERE id=?", (ubo_id,)).fetchone()
        assert row["is_ubo"] == 0, "nominee must never be marked as beneficial owner"

    def test_ownership_state_excludes_nominees(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-NOM3", full_name="Test Corp 3",
                      customer_type="legal")
        add_ubo(conn, res.customer_id, org_id=org_id, person_name="Real Owner",
                ownership_pct=80.0)
        add_ubo(conn, res.customer_id, org_id=org_id, person_name="Nominee Holder",
                ownership_pct=20.0, is_nominee=True)
        state = ownership_state(conn, res.customer_id, org_id, "legal")
        assert state == "fully_transparent", (
            "nominee ownership should be excluded; 80% real owner = transparent"
        )

    def test_nominee_visible_in_customer_detail(self, conn, org_id) -> None:
        from amlkit import queries
        res = onboard(conn, org_id=org_id, reference="C-NOM4", full_name="Test Corp 4",
                      customer_type="legal")
        add_ubo(conn, res.customer_id, org_id=org_id, person_name="Visible Nominee",
                ownership_pct=10.0, is_nominee=True)
        data = queries.customer(conn, res.customer_id, org_id)
        nominee_ubos = [u for u in data["ubos"] if u.get("is_nominee")]
        assert len(nominee_ubos) == 1
        assert nominee_ubos[0]["person_name"] == "Visible Nominee"

    def test_retention_years_is_ten(self) -> None:
        assert RETENTION_YEARS == 10

    def test_close_relationship_sets_ten_year_retention(self, conn, org_id) -> None:
        res = onboard(conn, org_id=org_id, reference="C-300", full_name="Ahmed Al Mansoori")
        until = close_relationship(conn, res.customer_id, org_id=org_id)
        row = conn.execute(
            "SELECT status, retention_until FROM customers WHERE id=?", (res.customer_id,)
        ).fetchone()
        assert row["status"] == "closed"
        assert row["retention_until"] == until
        from datetime import date
        today = date.today()
        # Cabinet Resolution 134/2025 requires 10-year retention.
        # Allow ±1 day tolerance for leap-year edge cases.
        expected = today.replace(year=today.year + 10)
        delta = abs((date.fromisoformat(until) - expected).days)
        assert delta <= 1, f"retention_until {until!r} should be ~10 years from today ({expected})"


class TestPurgeExpired:
    def test_purge_expired_deletes_closed_customer(self, conn, org_id) -> None:
        """Closed customer past retention_until is purged."""
        res = onboard(conn, org_id=org_id, reference="P-1", full_name="Old Customer")
        conn.execute(
            "UPDATE customers SET status='closed', retention_until='2020-01-01' WHERE id=?",
            (res.customer_id,),
        )
        conn.commit()
        result = purge_expired(conn, org_id)
        assert result["purged"] == 1
        row = conn.execute("SELECT id FROM customers WHERE id=?", (res.customer_id,)).fetchone()
        assert row is None

    def test_purge_expired_skips_active_customer(self, conn, org_id) -> None:
        """Active customer is NOT purged even with retention_until set."""
        res = onboard(conn, org_id=org_id, reference="P-2", full_name="Active Customer")
        conn.execute(
            "UPDATE customers SET retention_until='2020-01-01' WHERE id=?",
            (res.customer_id,),
        )
        conn.commit()
        result = purge_expired(conn, org_id)
        assert result["purged"] == 0
        row = conn.execute("SELECT id FROM customers WHERE id=?", (res.customer_id,)).fetchone()
        assert row is not None

    def test_purge_expired_skips_null_retention(self, conn, org_id) -> None:
        """Closed customer without retention_until is NOT purged."""
        res = onboard(conn, org_id=org_id, reference="P-3", full_name="No Date Customer")
        conn.execute(
            "UPDATE customers SET status='closed', retention_until=NULL WHERE id=?",
            (res.customer_id,),
        )
        conn.commit()
        result = purge_expired(conn, org_id)
        assert result["purged"] == 0

    def test_purge_expired_deletes_associated_data(self, conn, org_id) -> None:
        """UBOs, screenings, alerts, transactions, notes all deleted with customer."""
        res = onboard(conn, org_id=org_id, reference="P-4", full_name="Cascade Customer",
                      customer_type="legal",
                      ubos=[{"person_name": "Some Owner", "ownership_pct": 60.0}])
        cid = res.customer_id
        from amlkit.cases.manager import add_case_note, record_transaction
        add_case_note(conn, cid, org_id, author="test", body="Test note")
        record_transaction(conn, cid, org_id, direction="inbound", method="wire",
                          amount=1000.0, actor="test")
        conn.execute(
            "UPDATE customers SET status='closed', retention_until='2020-01-01' WHERE id=?",
            (cid,),
        )
        conn.commit()
        purge_expired(conn, org_id)
        assert conn.execute("SELECT COUNT(*) c FROM ubo_links WHERE customer_id=?", (cid,)).fetchone()["c"] == 0
        assert conn.execute("SELECT COUNT(*) c FROM screenings WHERE customer_id=?", (cid,)).fetchone()["c"] == 0
        assert conn.execute("SELECT COUNT(*) c FROM case_notes WHERE customer_id=?", (cid,)).fetchone()["c"] == 0
        assert conn.execute("SELECT COUNT(*) c FROM transactions WHERE customer_id=?", (cid,)).fetchone()["c"] == 0

    def test_purge_expired_audit_survives(self, conn, org_id) -> None:
        """Audit log entry for purge exists after customer row is deleted."""
        res = onboard(conn, org_id=org_id, reference="P-5", full_name="Audit Survivor")
        conn.execute(
            "UPDATE customers SET status='closed', retention_until='2020-01-01' WHERE id=?",
            (res.customer_id,),
        )
        conn.commit()
        purge_expired(conn, org_id)
        purge_entries = conn.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE action='customer.purge' AND object_id=?",
            (str(res.customer_id),),
        ).fetchone()["c"]
        assert purge_entries >= 1

    def test_purge_dry_run_does_not_delete(self, conn, org_id) -> None:
        """dry_run returns list but leaves data intact."""
        res = onboard(conn, org_id=org_id, reference="P-6", full_name="Dry Run Customer")
        conn.execute(
            "UPDATE customers SET status='closed', retention_until='2020-01-01' WHERE id=?",
            (res.customer_id,),
        )
        conn.commit()
        result = purge_expired(conn, org_id, dry_run=True)
        assert result["purged"] == 1
        row = conn.execute("SELECT id FROM customers WHERE id=?", (res.customer_id,)).fetchone()
        assert row is not None, "dry_run must not delete anything"


class TestStalenessGuard:
    def test_datasets_fresh_with_good_data(self, conn) -> None:
        """Mandatory dataset with entities and recent refresh → True."""
        from amlkit.db import upsert_dataset, utcnow
        ds_id = upsert_dataset(conn, "fresh_list", "Fresh List", is_mandatory=True)
        conn.execute(
            "UPDATE datasets SET entity_count=100, last_refresh=? WHERE id=?",
            (utcnow(), ds_id),
        )
        conn.commit()
        assert datasets_fresh(conn) is True

    def test_datasets_fresh_with_stale_data(self, conn) -> None:
        """Mandatory dataset past max_age_hours → False."""
        from amlkit.db import upsert_dataset
        conn.execute("DELETE FROM datasets")
        ds_id = upsert_dataset(conn, "stale_list", "Stale List", is_mandatory=True)
        conn.execute(
            "UPDATE datasets SET entity_count=100, last_refresh='2020-01-01T00:00:00+00:00' WHERE id=?",
            (ds_id,),
        )
        conn.commit()
        assert datasets_fresh(conn) is False

    def test_datasets_fresh_with_zero_entities(self, conn) -> None:
        """Mandatory dataset with entity_count=0 → False."""
        from amlkit.db import upsert_dataset, utcnow
        conn.execute("DELETE FROM datasets")
        ds_id = upsert_dataset(conn, "empty_list", "Empty List", is_mandatory=True)
        conn.execute(
            "UPDATE datasets SET entity_count=0, last_refresh=? WHERE id=?",
            (utcnow(), ds_id),
        )
        conn.commit()
        assert datasets_fresh(conn) is False

    def test_datasets_fresh_no_mandatory_datasets(self, conn) -> None:
        """Only non-mandatory datasets → False."""
        from amlkit.db import upsert_dataset, utcnow
        conn.execute("DELETE FROM datasets")
        ds_id = upsert_dataset(conn, "optional_list", "Optional List", is_mandatory=False)
        conn.execute(
            "UPDATE datasets SET entity_count=100, last_refresh=? WHERE id=?",
            (utcnow(), ds_id),
        )
        conn.commit()
        assert datasets_fresh(conn) is False

    def test_datasets_fresh_no_datasets(self, conn) -> None:
        """Empty datasets table → False."""
        conn.execute("DELETE FROM datasets")
        conn.commit()
        assert datasets_fresh(conn) is False

    def test_onboard_blocked_when_stale(self, conn, org_id) -> None:
        """onboard raises StaleDatasetsError when datasets are stale."""
        conn.execute("DELETE FROM datasets")
        conn.commit()
        with pytest.raises(StaleDatasetsError):
            onboard(conn, org_id=org_id, reference="STALE-1", full_name="Test Customer")

    def test_onboard_succeeds_when_fresh(self, conn, org_id) -> None:
        """onboard proceeds normally when datasets are fresh."""
        res = onboard(conn, org_id=org_id, reference="FRESH-1", full_name="Test Customer")
        assert res.customer_id > 0


class TestDocumentExpiry:
    """Tests for document expiry alerts (Phase 4, Item 1)."""

    def test_documents_table_has_expiry_date(self, conn) -> None:
        """Verify migration added expiry_date column to documents table."""
        cursor = conn.execute("PRAGMA table_info(documents)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "expiry_date" in columns, "documents table should have expiry_date column"

    def test_check_document_expiry_finds_expiring(self, conn, org_id) -> None:
        """Document expiring in 15 days appears in 'expiring_soon' list."""
        from datetime import date, timedelta
        from amlkit.cases.manager import check_document_expiry

        # Create customer with document expiring in 15 days
        res = onboard(conn, org_id=org_id, reference="C-EXP1", full_name="Test Customer")
        expiry = (date.today() + timedelta(days=15)).isoformat()
        conn.execute(
            """INSERT INTO documents (org_id, customer_id, doc_type, filename, stored_path,
               sha256, uploaded_at, expiry_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (org_id, res.customer_id, "passport", "pass.pdf", "/tmp/pass.pdf",
             "abc123", utcnow(), expiry)
        )
        conn.commit()

        result = check_document_expiry(conn, org_id, warning_days=30)

        assert len(result["expiring_soon"]) == 1
        doc = result["expiring_soon"][0]
        assert doc["customer_id"] == res.customer_id
        assert doc["doc_type"] == "passport"
        assert doc["days_remaining"] == 15

    def test_check_document_expiry_finds_expired(self, conn, org_id) -> None:
        """Document past expiry_date appears in 'expired' list."""
        from datetime import date, timedelta
        from amlkit.cases.manager import check_document_expiry

        # Create customer with expired document (5 days ago)
        res = onboard(conn, org_id=org_id, reference="C-EXP2", full_name="Test Customer 2")
        expiry = (date.today() - timedelta(days=5)).isoformat()
        conn.execute(
            """INSERT INTO documents (org_id, customer_id, doc_type, filename, stored_path,
               sha256, uploaded_at, expiry_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (org_id, res.customer_id, "trade_license", "lic.pdf", "/tmp/lic.pdf",
             "def456", utcnow(), expiry)
        )
        conn.commit()

        result = check_document_expiry(conn, org_id, warning_days=30)

        assert len(result["expired"]) == 1
        doc = result["expired"][0]
        assert doc["customer_id"] == res.customer_id
        assert doc["doc_type"] == "trade_license"
        assert doc["days_overdue"] == 5

    def test_check_document_expiry_skips_null_expiry(self, conn, org_id) -> None:
        """Document with NULL expiry_date not included in results."""
        from amlkit.cases.manager import check_document_expiry

        # Create customer with document without expiry date
        res = onboard(conn, org_id=org_id, reference="C-EXP3", full_name="Test Customer 3")
        conn.execute(
            """INSERT INTO documents (org_id, customer_id, doc_type, filename, stored_path,
               sha256, uploaded_at, expiry_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
            (org_id, res.customer_id, "other", "doc.pdf", "/tmp/doc.pdf",
             "ghi789", utcnow())
        )
        conn.commit()

        result = check_document_expiry(conn, org_id, warning_days=30)

        assert len(result["expiring_soon"]) == 0
        assert len(result["expired"]) == 0
