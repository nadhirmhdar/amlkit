"""Transaction monitoring (KYT) tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import (  # noqa: E402
    disposition_transaction_alert,
    onboard,
    reassess_transaction_risk,
    record_transaction,
)
from amlkit.db import connect, upsert_dataset, utcnow  # noqa: E402
from amlkit.screening.kyt import LARGE_CASH_THRESHOLD_AED  # noqa: E402


@pytest.fixture()
def conn():
    from amlkit.screening.kyt import _clear_config_cache
    _clear_config_cache()
    c = connect(":memory:")
    # Create a fresh mandatory dataset so onboard() passes the staleness guard
    ds = upsert_dataset(c, "test_list", "Test List", is_mandatory=True)
    now = utcnow()
    c.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    c.commit()
    yield c
    c.close()
    _clear_config_cache()


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
def customer_id(conn, org_id) -> int:
    res = onboard(conn, org_id=org_id, reference="C-TXN-1", full_name="Ahmed Al Mansoori",
                  customer_type="natural", nationality="ae")
    return res.customer_id


class TestLargeCash:
    def test_large_cash_triggers(self, conn, org_id, customer_id) -> None:
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=LARGE_CASH_THRESHOLD_AED, actor="tester",
        )
        assert any(r.rule_key == "large_cash" for r in triggered)

    def test_small_cash_does_not_trigger(self, conn, org_id, customer_id) -> None:
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=1000.0, actor="tester",
        )
        assert not any(r.rule_key == "large_cash" for r in triggered)

    def test_large_wire_does_not_trigger_large_cash(self, conn, org_id, customer_id) -> None:
        """The large_cash rule is specifically about cash -- a large wire is
        not inherently the same risk signal."""
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="wire",
            amount=LARGE_CASH_THRESHOLD_AED * 2, actor="tester",
        )
        assert not any(r.rule_key == "large_cash" for r in triggered)

    def test_alert_row_is_written(self, conn, org_id, customer_id) -> None:
        record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=LARGE_CASH_THRESHOLD_AED, actor="tester",
        )
        n = conn.execute(
            "SELECT COUNT(*) c FROM transaction_alerts WHERE customer_id=? AND rule_key='large_cash'",
            (customer_id,),
        ).fetchone()["c"]
        assert n == 1


class TestStructuring:
    def test_two_near_threshold_deposits_trigger(self, conn, org_id, customer_id) -> None:
        occurred_1 = "2026-08-01T09:00:00+00:00"
        occurred_2 = "2026-08-02T09:00:00+00:00"
        record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=30000.0, occurred_at=occurred_1, actor="tester",
        )
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=30000.0, occurred_at=occurred_2, actor="tester",
        )
        assert any(r.rule_key == "structuring" for r in triggered)

    def test_single_near_threshold_deposit_does_not_trigger(self, conn, org_id, customer_id) -> None:
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=30000.0, actor="tester",
        )
        assert not any(r.rule_key == "structuring" for r in triggered)

    def test_evidence_total_excludes_already_alerted_large_cash(self, conn, org_id, customer_id) -> None:
        """total_aed in the structuring alert's evidence must reflect only the
        sub-threshold transactions that make the structuring case -- not a
        large cash deposit that already fired its own large_cash alert.
        Regression test for the 2026-08-23 continuous-improvement finding."""
        record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=LARGE_CASH_THRESHOLD_AED, occurred_at="2026-08-01T09:00:00+00:00",
            actor="tester",
        )
        record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=30000.0, occurred_at="2026-08-02T09:00:00+00:00", actor="tester",
        )
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=30000.0, occurred_at="2026-08-03T09:00:00+00:00", actor="tester",
        )
        structuring = next(r for r in triggered if r.rule_key == "structuring")
        assert structuring.detail["total_aed"] == pytest.approx(60000.0)
        assert structuring.detail["transaction_count"] == 2

    def test_deposits_outside_window_do_not_combine(self, conn, org_id, customer_id) -> None:
        record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=30000.0, occurred_at="2026-01-01T09:00:00+00:00", actor="tester",
        )
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=30000.0, occurred_at="2026-08-01T09:00:00+00:00", actor="tester",
        )
        assert not any(r.rule_key == "structuring" for r in triggered)


class TestHighRiskCountry:
    def test_high_risk_country_triggers(self, conn, org_id, customer_id) -> None:
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="outbound", method="wire",
            amount=5000.0, counterparty_country="kp", actor="tester",
        )
        assert any(r.rule_key == "high_risk_country" for r in triggered)

    def test_ordinary_country_does_not_trigger(self, conn, org_id, customer_id) -> None:
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="outbound", method="wire",
            amount=5000.0, counterparty_country="ae", actor="tester",
        )
        assert not any(r.rule_key == "high_risk_country" for r in triggered)


class TestVelocity:
    def test_many_transactions_in_a_day_trigger(self, conn, org_id, customer_id) -> None:
        base = "2026-08-01T0{}:00:00+00:00"
        triggered = []
        for i in range(7):
            _, triggered = record_transaction(
                conn, customer_id, org_id, direction="inbound", method="wire",
                amount=100.0, occurred_at=base.format(i), actor="tester",
            )
        assert any(r.rule_key == "velocity" for r in triggered)


class TestRecordTransaction:
    def test_rejects_zero_amount(self, conn, org_id, customer_id) -> None:
        with pytest.raises(ValueError):
            record_transaction(conn, customer_id, org_id, direction="inbound",
                               method="cash", amount=0, actor="tester")

    def test_foreign_currency_requires_amount_aed(self, conn, org_id, customer_id) -> None:
        with pytest.raises(ValueError):
            record_transaction(conn, customer_id, org_id, direction="inbound",
                               method="wire", amount=1000, currency="USD", actor="tester")

    def test_foreign_currency_with_amount_aed_succeeds(self, conn, org_id, customer_id) -> None:
        txn_id, _ = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="wire",
            amount=1000, currency="USD", amount_aed=3670.0, actor="tester",
        )
        row = conn.execute("SELECT amount_aed FROM transactions WHERE id=?", (txn_id,)).fetchone()
        assert row["amount_aed"] == 3670.0

    def test_cross_org_customer_is_rejected(self, conn, org_id, customer_id) -> None:
        """Same tenant-isolation property as add_case_note: a transaction
        cannot be attached to another org's customer."""
        other_org = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
            " RETURNING id",
            ("Other Firm", "other-firm-kyt", "active", utcnow()),
        ).fetchone()["id"]
        with pytest.raises(ValueError):
            record_transaction(conn, customer_id, other_org, direction="inbound",
                               method="cash", amount=1000, actor="tester")
        n = conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"]
        assert n == 0

    def test_transaction_is_audited(self, conn, org_id, customer_id) -> None:
        record_transaction(conn, customer_id, org_id, direction="inbound",
                           method="cash", amount=1000, actor="tester")
        n = conn.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE action='transaction.record'"
        ).fetchone()["c"]
        assert n == 1


class TestDisposition:
    def test_disposition_updates_status(self, conn, org_id, customer_id) -> None:
        record_transaction(conn, customer_id, org_id, direction="inbound", method="cash",
                           amount=LARGE_CASH_THRESHOLD_AED, actor="tester")
        alert_id = conn.execute(
            "SELECT id FROM transaction_alerts WHERE customer_id=?", (customer_id,)
        ).fetchone()["id"]
        disposition_transaction_alert(conn, alert_id, org_id, status="false_positive",
                                      note="Known payroll run", actor="reviewer")
        row = conn.execute(
            "SELECT status, disposition, dispositioned_by FROM transaction_alerts WHERE id=?",
            (alert_id,),
        ).fetchone()
        assert row["status"] == "false_positive"
        assert row["dispositioned_by"] == "reviewer"

    def test_rejects_invalid_status(self, conn, org_id, customer_id) -> None:
        record_transaction(conn, customer_id, org_id, direction="inbound", method="cash",
                           amount=LARGE_CASH_THRESHOLD_AED, actor="tester")
        alert_id = conn.execute(
            "SELECT id FROM transaction_alerts WHERE customer_id=?", (customer_id,)
        ).fetchone()["id"]
        with pytest.raises(ValueError):
            disposition_transaction_alert(conn, alert_id, org_id, status="open", actor="reviewer")

    def test_cross_org_alert_is_rejected(self, conn, org_id, customer_id) -> None:
        record_transaction(conn, customer_id, org_id, direction="inbound", method="cash",
                           amount=LARGE_CASH_THRESHOLD_AED, actor="tester")
        alert_id = conn.execute(
            "SELECT id FROM transaction_alerts WHERE customer_id=?", (customer_id,)
        ).fetchone()["id"]
        other_org = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
            " RETURNING id",
            ("Other Firm 2", "other-firm-kyt-2", "active", utcnow()),
        ).fetchone()["id"]
        with pytest.raises(ValueError):
            disposition_transaction_alert(conn, alert_id, other_org, status="false_positive",
                                          actor="reviewer")


class TestRiskFeedback:
    def test_transaction_alert_raises_cash_intensity(self, conn, org_id, customer_id) -> None:
        """Three large-cash alerts should push cash_intensity to predominantly_cash."""
        for _ in range(3):
            record_transaction(
                conn, customer_id, org_id, direction="inbound", method="cash",
                amount=LARGE_CASH_THRESHOLD_AED, actor="tester",
            )
        # After 3 open alerts, reassess_transaction_risk should have been called
        # by record_transaction and stored a higher cash_intensity rating.
        row = conn.execute(
            "SELECT factors FROM risk_assessments WHERE customer_id=? AND org_id=?"
            " ORDER BY id DESC LIMIT 1",
            (customer_id, org_id),
        ).fetchone()
        import json
        factors = json.loads(row["factors"])
        assert factors["cash_intensity"]["value"] == "predominantly_cash"

    def test_no_alert_no_reassessment(self, conn, org_id, customer_id) -> None:
        """A transaction that fires no rules must not create a new risk assessment."""
        initial_count = conn.execute(
            "SELECT COUNT(*) c FROM risk_assessments WHERE customer_id=? AND org_id=?",
            (customer_id, org_id),
        ).fetchone()["c"]
        record_transaction(
            conn, customer_id, org_id, direction="inbound", method="wire",
            amount=100.0, actor="tester",
        )
        final_count = conn.execute(
            "SELECT COUNT(*) c FROM risk_assessments WHERE customer_id=? AND org_id=?",
            (customer_id, org_id),
        ).fetchone()["c"]
        assert final_count == initial_count

    def test_reassess_transaction_risk_direct(self, conn, org_id, customer_id) -> None:
        """Direct call: 1 open alert → cash_intensity = mixed."""
        record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=LARGE_CASH_THRESHOLD_AED, actor="tester",
        )
        # Manually call to verify the mapping
        rating = reassess_transaction_risk(conn, customer_id, org_id, actor="tester")
        assert rating is not None
        row = conn.execute(
            "SELECT factors FROM risk_assessments WHERE customer_id=? AND org_id=?"
            " ORDER BY id DESC LIMIT 1",
            (customer_id, org_id),
        ).fetchone()
        import json
        factors = json.loads(row["factors"])
        assert factors["cash_intensity"]["value"] == "mixed"

    def test_reassess_transaction_risk_no_prior_returns_none(self, conn, org_id) -> None:
        """No prior assessment → returns None without writing anything."""
        # Onboard without completing risk assessment by deleting the auto-created one
        res = onboard(conn, org_id=org_id, reference="C-BARE", full_name="Bare Customer",
                      customer_type="natural", nationality="ae")
        conn.execute(
            "DELETE FROM risk_assessments WHERE customer_id=?", (res.customer_id,)
        )
        conn.commit()
        result = reassess_transaction_risk(conn, res.customer_id, org_id, actor="tester")
        assert result is None


class TestConfigurableKYTRules:
    """Tests for configurable KYT rules (Phase 4, Item 3)."""

    def test_get_rule_config_defaults(self, conn, org_id) -> None:
        """Returns module defaults when no DB config exists."""
        from amlkit.screening.kyt import get_rule_config, LARGE_CASH_THRESHOLD_AED

        config = get_rule_config(conn, org_id)

        assert config["large_cash_threshold_aed"] == LARGE_CASH_THRESHOLD_AED
        assert config["structuring_window_days"] == 7
        assert config["velocity_window_hours"] == 24
        assert config["velocity_max_count"] == 5
        assert isinstance(config["high_risk_countries"], list)

    def test_get_rule_config_from_db(self, conn, org_id) -> None:
        """Returns DB values when present."""
        from amlkit.screening.kyt import get_rule_config, save_rule_config

        # Save custom config
        custom = {
            "large_cash_threshold_aed": 100000.0,
            "structuring_window_days": 14,
            "velocity_window_hours": 48,
            "velocity_max_count": 10,
            "high_risk_countries": ["KP", "IR"],
        }
        save_rule_config(conn, org_id, custom, actor="test-admin")
        conn.commit()

        # Load config
        config = get_rule_config(conn, org_id)

        assert config["large_cash_threshold_aed"] == 100000.0
        assert config["structuring_window_days"] == 14
        assert config["velocity_window_hours"] == 48
        assert config["velocity_max_count"] == 10
        # Org countries are additive to FATF baseline, not a replacement
        assert "KP" in config["high_risk_countries"]
        assert "IR" in config["high_risk_countries"]

    def test_save_rule_config_validates_thresholds(self, conn, org_id) -> None:
        """Rejects negative or zero thresholds."""
        from amlkit.screening.kyt import save_rule_config

        with pytest.raises(ValueError, match="threshold must be positive"):
            save_rule_config(conn, org_id, {"large_cash_threshold_aed": -1000}, actor="test")

        with pytest.raises(ValueError, match="window_days must be positive"):
            save_rule_config(conn, org_id, {"structuring_window_days": 0}, actor="test")

    def test_custom_threshold_affects_evaluation(self, conn, org_id, customer_id) -> None:
        """Custom threshold changes which transactions trigger alerts."""
        from amlkit.screening.kyt import save_rule_config

        # Raise threshold to 100k (default is 55k)
        save_rule_config(conn, org_id, {"large_cash_threshold_aed": 100000.0}, actor="test")
        conn.commit()

        # 60k cash transaction should NOT trigger (below new threshold)
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=60000.0, actor="tester",
        )
        assert len(triggered) == 0, "60k should not trigger with 100k threshold"

        # 110k cash transaction SHOULD trigger (above new threshold)
        _, triggered = record_transaction(
            conn, customer_id, org_id, direction="inbound", method="cash",
            amount=110000.0, actor="tester",
        )
        assert any(t.rule_key == "large_cash" for t in triggered), "110k should trigger with 100k threshold"


class TestHighRiskCountriesFATFBaseline:
    """Tests for high-risk countries using FATF dataset as baseline."""

    def test_fatf_countries_used_as_baseline(self, conn, org_id) -> None:
        """High-risk countries come from FATF dataset when available."""
        from amlkit.ingest.fatf import load_fatf_data
        from amlkit.screening.kyt import get_rule_config

        # Load FATF data (includes KP, IR, MM from blacklist)
        load_fatf_data(conn)

        config = get_rule_config(conn, org_id)
        countries = config["high_risk_countries"]

        # FATF blacklist countries must be present
        assert "KP" in countries, "North Korea (FATF blacklist) should be included"
        assert "IR" in countries, "Iran (FATF blacklist) should be included"
        assert "MM" in countries, "Myanmar (FATF blacklist) should be included"

    def test_org_override_is_additive(self, conn, org_id) -> None:
        """Org-specific high-risk countries ADD to FATF, never replace."""
        from amlkit.ingest.fatf import load_fatf_data
        from amlkit.screening.kyt import get_rule_config, save_rule_config

        # Load FATF data
        load_fatf_data(conn)

        # Get baseline (should include FATF countries)
        baseline_config = get_rule_config(conn, org_id)
        baseline_countries = set(baseline_config["high_risk_countries"])

        # Add org-specific country (e.g., "RU")
        save_rule_config(conn, org_id, {"high_risk_countries": ["RU"]}, actor="test")
        conn.commit()

        # Get updated config
        new_config = get_rule_config(conn, org_id)
        new_countries = set(new_config["high_risk_countries"])

        # FATF countries must still be present (not replaced)
        assert baseline_countries.issubset(new_countries), \
            "FATF baseline countries should not be removed by org override"
        # Org-specific country should be added
        assert "RU" in new_countries, "Org-specific country should be added"

    def test_fallback_to_constant_when_fatf_empty(self, conn, org_id) -> None:
        """Falls back to HIGH_RISK_COUNTRIES when FATF table is empty."""
        from amlkit.screening.kyt import get_rule_config, HIGH_RISK_COUNTRIES

        # Ensure FATF table is empty (don't load FATF data)
        conn.execute("DELETE FROM fatf_countries")
        conn.commit()

        config = get_rule_config(conn, org_id)
        countries = set(config["high_risk_countries"])

        # Should match the module constant
        assert countries == HIGH_RISK_COUNTRIES, \
            "Should fall back to HIGH_RISK_COUNTRIES when FATF table is empty"


class TestSaveRuleConfigValidation:
    """Tests for save_rule_config upper bounds validation."""

    def test_large_cash_threshold_exceeds_max(self, conn, org_id) -> None:
        """Threshold > 1M AED is rejected."""
        from amlkit.screening.kyt import save_rule_config

        with pytest.raises(ValueError) as exc_info:
            save_rule_config(conn, org_id, {"large_cash_threshold_aed": 1_500_000}, actor="test")

        assert "1,000,000" in str(exc_info.value)
        assert "disable detection" in str(exc_info.value).lower()

    def test_structuring_window_exceeds_max(self, conn, org_id) -> None:
        """Window > 90 days is rejected."""
        from amlkit.screening.kyt import save_rule_config

        with pytest.raises(ValueError) as exc_info:
            save_rule_config(conn, org_id, {"structuring_window_days": 100}, actor="test")

        assert "90" in str(exc_info.value)

    def test_velocity_window_exceeds_max(self, conn, org_id) -> None:
        """Window > 168 hours is rejected."""
        from amlkit.screening.kyt import save_rule_config

        with pytest.raises(ValueError) as exc_info:
            save_rule_config(conn, org_id, {"velocity_window_hours": 200}, actor="test")

        assert "168" in str(exc_info.value)

    def test_velocity_count_exceeds_max(self, conn, org_id) -> None:
        """Count > 1000 is rejected."""
        from amlkit.screening.kyt import save_rule_config

        with pytest.raises(ValueError) as exc_info:
            save_rule_config(conn, org_id, {"velocity_max_count": 1500}, actor="test")

        assert "1000" in str(exc_info.value)

    def test_valid_config_within_bounds(self, conn, org_id) -> None:
        """Valid config within bounds is accepted."""
        from amlkit.screening.kyt import save_rule_config

        # Should not raise
        save_rule_config(conn, org_id, {
            "large_cash_threshold_aed": 100_000,
            "structuring_window_days": 14,
            "velocity_window_hours": 48,
            "velocity_max_count": 20,
        }, actor="test")
        conn.commit()


class TestGetRuleConfigCache:
    """Step 7: get_rule_config() caching per org."""

    def test_get_rule_config_uses_cache(self, conn, org_id) -> None:
        """Second call returns same dict object (cache hit)."""
        from amlkit.screening.kyt import get_rule_config, _clear_config_cache

        _clear_config_cache()
        config1 = get_rule_config(conn, org_id)
        config2 = get_rule_config(conn, org_id)

        # Same object = cache hit
        assert config1 is config2

    def test_get_rule_config_cache_per_org(self, conn) -> None:
        """Different orgs have separate cache entries."""
        from amlkit.screening.kyt import get_rule_config, _clear_config_cache

        _clear_config_cache()
        org_id_1 = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
            " RETURNING id",
            ("Firm 1", "firm-1", "active", utcnow()),
        ).fetchone()["id"]
        org_id_2 = conn.execute(
            "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
            " RETURNING id",
            ("Firm 2", "firm-2", "active", utcnow()),
        ).fetchone()["id"]
        conn.commit()

        config1 = get_rule_config(conn, org_id_1)
        config2 = get_rule_config(conn, org_id_2)

        # Different objects = separate caches
        assert config1 is not config2

    def test_get_rule_config_cache_invalidated_on_save(self, conn, org_id) -> None:
        """Saving config invalidates the cache for that org."""
        from amlkit.screening.kyt import get_rule_config, save_rule_config, _clear_config_cache

        _clear_config_cache()
        config1 = get_rule_config(conn, org_id)
        threshold_1 = config1["large_cash_threshold_aed"]

        # Save new config
        save_rule_config(conn, org_id, {"large_cash_threshold_aed": 200_000}, actor="mlro")
        conn.commit()

        # Get again - should be cache miss (new object)
        config2 = get_rule_config(conn, org_id)
        threshold_2 = config2["large_cash_threshold_aed"]

        assert config1 is not config2
        assert threshold_1 != threshold_2
        assert threshold_2 == 200_000

    def test_get_rule_config_cache_isolated_across_databases_sharing_org_id(self) -> None:
        """Two independent databases that both happen to have an org_id=1
        must never see each other's cached config.

        Regression test for the bug where the cache was keyed on bare
        org_id: this app is single-tenant-per-database, so org_id is only
        unique within one database, not globally. A bare-org_id cache key
        let save_rule_config() on one database's org 1 silently poison
        get_rule_config() reads for a completely unrelated database's org 1
        -- exactly the shape of the order-dependent failures this caused in
        test_api.py / test_new_features_e2e.py / test_mobile_api.py, where
        an unrelated test's admin-rule-config save leaked its threshold into
        the transaction-monitoring tests. See the module comment on
        _config_cache in amlkit/screening/kyt.py.
        """
        from amlkit.screening.kyt import get_rule_config, save_rule_config, _clear_config_cache

        _clear_config_cache()

        conn_a = connect(":memory:")
        conn_b = connect(":memory:")
        try:
            org_a = conn_a.execute(
                "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
                " RETURNING id",
                ("Firm A", "firm-a", "active", utcnow()),
            ).fetchone()["id"]
            conn_a.commit()
            org_b = conn_b.execute(
                "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
                " RETURNING id",
                ("Firm B", "firm-b", "active", utcnow()),
            ).fetchone()["id"]
            conn_b.commit()
            # Both databases independently assign the same numeric org_id --
            # each is the first (and only) org in its own database.
            assert org_a == org_b == 1

            # DB A's operator lowers its threshold and caches the new value.
            save_rule_config(conn_a, org_a, {"large_cash_threshold_aed": 12_345.0}, actor="mlro-a")
            conn_a.commit()
            config_a = get_rule_config(conn_a, org_a)
            assert config_a["large_cash_threshold_aed"] == 12_345.0

            # DB B was never touched: it must still see the true default,
            # not DB A's cached value for "org 1".
            config_b = get_rule_config(conn_b, org_b)
            assert config_b["large_cash_threshold_aed"] == LARGE_CASH_THRESHOLD_AED
        finally:
            conn_a.close()
            conn_b.close()
            _clear_config_cache()

    def test_stale_cache_on_another_connection_does_not_survive_past_ttl(self, tmp_path, monkeypatch) -> None:
        """Simulates two worker processes/instances sharing one real database
        file, each holding its own process-local cache -- this module's
        cache is one dict per Python process, so two Cloud Run instances
        never see each other's writes directly.

        Worker A saves a new threshold and sees it immediately, because
        save_rule_config() invalidates its own connection's cache entry.
        Worker B's already-warm read of the old value lives in a different
        connection's cache entry, so worker A's save can't reach it -- but
        unlike before this fix, it does not stay stale until the process
        restarts: it expires on the TTL, and worker B's next read goes back
        to the database and picks up the change.
        """
        import amlkit.screening.kyt as kyt_module
        from amlkit.screening.kyt import get_rule_config, save_rule_config, _clear_config_cache

        _clear_config_cache()
        db_path = tmp_path / "shared.db"

        conn_a = connect(db_path)  # "worker A"
        conn_b = connect(db_path)  # "worker B", same underlying database file
        try:
            org_id = conn_a.execute(
                "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
                " RETURNING id",
                ("Shared Firm", "shared-firm", "active", utcnow()),
            ).fetchone()["id"]
            conn_a.commit()

            fake_time = [1_000.0]
            monkeypatch.setattr(kyt_module.time, "monotonic", lambda: fake_time[0])

            # Both workers warm their own cache with the default.
            assert get_rule_config(conn_a, org_id)["large_cash_threshold_aed"] == LARGE_CASH_THRESHOLD_AED
            assert get_rule_config(conn_b, org_id)["large_cash_threshold_aed"] == LARGE_CASH_THRESHOLD_AED

            # Worker A's operator changes the threshold.
            save_rule_config(conn_a, org_id, {"large_cash_threshold_aed": 90_000.0}, actor="mlro-a")
            conn_a.commit()

            # Worker A sees it immediately (its own cache entry was cleared).
            assert get_rule_config(conn_a, org_id)["large_cash_threshold_aed"] == 90_000.0

            # Worker B is still within the TTL window: it reads its own
            # cache entry from before the save, since worker A's save
            # cannot reach a different connection's cache entry.
            assert get_rule_config(conn_b, org_id)["large_cash_threshold_aed"] == LARGE_CASH_THRESHOLD_AED

            # Time passes the TTL: worker B's stale entry expires, and its
            # next read goes back to the database and picks up the change --
            # bounded staleness, not "until the next restart".
            fake_time[0] += kyt_module._CACHE_TTL_SECONDS + 1
            assert get_rule_config(conn_b, org_id)["large_cash_threshold_aed"] == 90_000.0
        finally:
            conn_a.close()
            conn_b.close()
            _clear_config_cache()
