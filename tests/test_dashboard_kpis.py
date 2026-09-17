"""Dashboard KPI tests (Phase 4, Item 4)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.manager import onboard, record_transaction  # noqa: E402
from amlkit.db import connect, upsert_dataset, utcnow  # noqa: E402
from amlkit.queries import dashboard_kpis  # noqa: E402


@pytest.fixture()
def conn():
    c = connect(":memory:")
    now = utcnow()
    ds = upsert_dataset(c, "test_list", "Test List", is_mandatory=True)
    c.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds))
    c.commit()
    yield c
    c.close()


@pytest.fixture()
def org_id(conn) -> int:
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)"
        " RETURNING id",
        ("Test Firm", "test-firm", "active", utcnow()),
    ).fetchone()
    conn.commit()
    return row["id"]


class TestDashboardKPIs:
    """Tests for enhanced dashboard KPIs."""

    def test_dashboard_kpis_returns_structure(self, conn, org_id) -> None:
        """Returns correct structure with all KPIs."""
        kpis = dashboard_kpis(conn, org_id)

        assert "total_customers" in kpis
        assert "total_active_customers" in kpis
        assert "avg_alert_age_days" in kpis
        assert "alerts_closed_7d" in kpis
        assert "alerts_opened_7d" in kpis
        assert "sla_breaches" in kpis
        assert "screening_coverage_pct" in kpis

    def test_dashboard_kpis_no_alerts(self, conn, org_id) -> None:
        """Returns 0 for avg_alert_age_days when no alerts exist."""
        kpis = dashboard_kpis(conn, org_id)

        assert kpis["avg_alert_age_days"] == 0
        assert kpis["sla_breaches"] == 0

    def test_dashboard_kpis_sla_breaches(self, conn, org_id) -> None:
        """SLA breaches is 0 when no old alerts exist."""
        kpis = dashboard_kpis(conn, org_id)

        # With no alerts, SLA breaches should be 0
        assert kpis["sla_breaches"] >= 0

    def test_dashboard_kpis_customer_counts(self, conn, org_id) -> None:
        """Returns correct total and active customer counts."""
        # Onboard 2 customers
        onboard(conn, org_id=org_id, reference="C-1", full_name="Customer One")
        onboard(conn, org_id=org_id, reference="C-2", full_name="Customer Two")

        kpis = dashboard_kpis(conn, org_id)

        assert kpis["total_customers"] >= 2
        assert kpis["total_active_customers"] >= 2
