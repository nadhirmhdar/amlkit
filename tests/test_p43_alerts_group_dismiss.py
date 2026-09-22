"""Tests for p43: Alerts group-by-customer toggle and dismiss-all action."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3
import pytest

from amlkit import db, queries
from amlkit.cases.review import confirm_disposition, propose_disposition, bulk_dismiss_alerts


def _seed(conn: sqlite3.Connection) -> dict:
    """Create an org with two customers and multiple alerts across them."""
    now = db.utcnow()
    conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
        ("TestOrg", "testorg", "active", now),
    )
    org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        "INSERT INTO operators (org_id, email, password_hash, name, role, is_active, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (org_id, "op@test.com", "x", "Operator", "mlro", 1, now),
    )

    for ref, cname in [("C001", "Alice Corp"), ("C002", "Bob Ltd")]:
        conn.execute(
            "INSERT INTO customers (org_id, reference, full_name, canonical_key, "
            "customer_type, nationality, status, onboarded_at, updated_at, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (org_id, ref, cname, cname.lower(), "legal", "AE", "active", now, now, now),
        )

    c1_id = conn.execute("SELECT id FROM customers WHERE reference='C001'").fetchone()[0]
    c2_id = conn.execute("SELECT id FROM customers WHERE reference='C002'").fetchone()[0]

    conn.execute(
        "INSERT INTO datasets (key, title, is_mandatory, last_refresh, entity_count) "
        "VALUES (?,?,?,?,?)",
        ("test-ds", "Test Dataset", 1, now, 3),
    )
    ds_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    entities = []
    for i, caption in enumerate(["Entity A", "Entity B", "Entity C"]):
        conn.execute(
            "INSERT INTO entities (dataset_id, source_id, schema_type, caption, "
            "topics, programs, countries, first_seen, last_seen) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (ds_id, f"ent-{i}", "Person", caption,
             '["sanction"]', '[]', '[]', now, now),
        )
        entities.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def _make_screening_alert(cust_id, cust_name, ent_id, score):
        conn.execute(
            "INSERT INTO screenings (org_id, customer_id, query_name, trigger, "
            "algorithm, threshold, run_at) VALUES (?,?,?,?,?,?,?)",
            (org_id, cust_id, cust_name, "onboarding", "weighted", 0.65, now),
        )
        scr_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO alerts (org_id, screening_id, entity_id, score, "
            "score_detail, matched_name, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (org_id, scr_id, ent_id, score, "{}", cust_name, "open", now),
        )

    # Customer 1: 2 alerts
    for ent_id in entities[:2]:
        _make_screening_alert(c1_id, "Alice Corp", ent_id, 0.85)

    # Customer 2: 1 alert
    _make_screening_alert(c2_id, "Bob Ltd", entities[2], 0.90)
    conn.commit()

    alert_ids = [r[0] for r in conn.execute(
        "SELECT id FROM alerts WHERE org_id=? ORDER BY id", (org_id,)
    ).fetchall()]

    return {
        "org_id": org_id,
        "c1_id": c1_id,
        "c2_id": c2_id,
        "alert_ids": alert_ids,
    }


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


class TestGroupByCustomer:
    """Tests for grouping alerts by customer."""

    def test_alerts_grouped_by_customer(self, conn: sqlite3.Connection) -> None:
        """alert_queue_grouped returns alerts bucketed by customer_id."""
        seed = _seed(conn)
        grouped = queries.alert_queue_grouped(conn, seed["org_id"])

        assert isinstance(grouped, list)
        assert len(grouped) == 2

        customer_ids = {g["customer_id"] for g in grouped}
        assert seed["c1_id"] in customer_ids
        assert seed["c2_id"] in customer_ids

        for g in grouped:
            assert "customer_name" in g
            assert "alerts" in g
            assert len(g["alerts"]) > 0

    def test_grouped_preserves_alert_count(self, conn: sqlite3.Connection) -> None:
        """Total alerts across all groups equals ungrouped total."""
        seed = _seed(conn)
        grouped = queries.alert_queue_grouped(conn, seed["org_id"])
        total = sum(len(g["alerts"]) for g in grouped)

        flat = queries.alert_queue(conn, seed["org_id"])
        assert total == len(flat)

    def test_grouped_respects_status_filter(self, conn: sqlite3.Connection) -> None:
        """Status filter applies before grouping."""
        seed = _seed(conn)
        # Dismiss one alert
        propose_disposition(
            conn, seed["alert_ids"][0], org_id=seed["org_id"],
            status="false_positive", reason_code="name_coincidence",
            operator="Operator",
        )
        conn.commit()

        grouped_open = queries.alert_queue_grouped(conn, seed["org_id"], status="open")
        total_open = sum(len(g["alerts"]) for g in grouped_open)
        assert total_open == 2  # 3 original minus 1 dismissed


class TestBulkDismiss:
    """Tests for dismiss-all alerts for a customer.

    The seeded alerts (see _seed()) match entities with topics=["sanction"],
    so -- outside single-operator mode -- bulk-dismissing them must be held
    for independent review just like dismissing one at a time would be
    (finding #6, 2026-09-21 deployed-site review: bulk_dismiss_alerts used
    to write status='false_positive' directly, bypassing that gate).
    """

    def test_bulk_dismiss_by_customer(self, conn: sqlite3.Connection) -> None:
        """bulk_dismiss processes all open alerts for a given customer."""
        seed = _seed(conn)
        outcome = bulk_dismiss_alerts(
            conn, seed["org_id"], customer_id=seed["c1_id"],
            reason_code="name_coincidence", operator="Operator",
        )
        assert outcome.total == 2

        remaining = queries.alert_queue(conn, seed["org_id"], status="open")
        customer_ids = {a["customer_id"] for a in remaining if a["customer_id"]}
        assert seed["c1_id"] not in customer_ids

    def test_bulk_dismiss_only_open(self, conn: sqlite3.Connection) -> None:
        """bulk_dismiss only touches alerts that are currently 'open'."""
        seed = _seed(conn)
        # Manually escalate one of customer 1's alerts
        conn.execute(
            "UPDATE alerts SET status='escalated' WHERE id=?",
            (seed["alert_ids"][0],),
        )
        conn.commit()

        outcome = bulk_dismiss_alerts(
            conn, seed["org_id"], customer_id=seed["c1_id"],
            reason_code="name_coincidence", operator="Operator",
        )
        assert outcome.total == 1  # only the open one

    def test_bulk_dismiss_respects_org_isolation(self, conn: sqlite3.Connection) -> None:
        """bulk_dismiss cannot dismiss alerts from another org."""
        seed = _seed(conn)
        outcome = bulk_dismiss_alerts(
            conn, 99999, customer_id=seed["c1_id"],
            reason_code="name_coincidence", operator="Operator",
        )
        assert outcome.total == 0

    def test_bulk_dismiss_creates_audit_trail(self, conn: sqlite3.Connection) -> None:
        """Each dismissed alert gets an audit log entry."""
        seed = _seed(conn)
        bulk_dismiss_alerts(
            conn, seed["org_id"], customer_id=seed["c1_id"],
            reason_code="name_coincidence", operator="Operator",
        )
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE action='alert.bulk_dismiss' AND org_id=?",
            (seed["org_id"],),
        ).fetchall()
        assert len(rows) == 2

    def test_bulk_dismiss_of_sanctions_alerts_requires_second_operator(
        self, conn: sqlite3.Connection, monkeypatch
    ) -> None:
        """Regression test for finding #6: bulk-dismissing a customer's
        sanctions-match alerts must stage them for independent review, not
        clear them outright -- exactly like dismissing one at a time. One
        operator must not be able to single-handedly clear every open
        sanctions match on a customer just by using the bulk action."""
        monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
        seed = _seed(conn)

        outcome = bulk_dismiss_alerts(
            conn, seed["org_id"], customer_id=seed["c1_id"],
            reason_code="name_coincidence", operator="Alice",
        )
        assert outcome.dismissed == 0
        assert outcome.pending_review == 2

        for alert_id in seed["alert_ids"][:2]:
            row = conn.execute(
                "SELECT status, independent_review FROM alerts WHERE id=?", (alert_id,)
            ).fetchone()
            assert row["status"] == "pending_review"
            assert row["independent_review"] == "pending"

        # A second operator (not Alice) must confirm before it actually clears.
        confirm_disposition(
            conn, seed["alert_ids"][0], org_id=seed["org_id"],
            operator="Bob", agree=True,
        )
        row = conn.execute(
            "SELECT status FROM alerts WHERE id=?", (seed["alert_ids"][0],)
        ).fetchone()
        assert row["status"] == "false_positive"

        # The other one is still awaiting review -- bulk dismiss did not
        # let Alice clear it unilaterally.
        row2 = conn.execute(
            "SELECT status FROM alerts WHERE id=?", (seed["alert_ids"][1],)
        ).fetchone()
        assert row2["status"] == "pending_review"

    def test_bulk_dismiss_in_single_operator_mode_still_applies_immediately(
        self, conn: sqlite3.Connection, monkeypatch
    ) -> None:
        """single_operator_mode is the documented, explicit escape hatch: a
        firm with one MLRO can still bulk-dismiss immediately, with the
        absence of review recorded on the alert rather than silently
        pretending four-eyes happened."""
        monkeypatch.setenv("AMLKIT_SINGLE_OPERATOR_MODE", "1")
        seed = _seed(conn)

        outcome = bulk_dismiss_alerts(
            conn, seed["org_id"], customer_id=seed["c1_id"],
            reason_code="name_coincidence", operator="Operator",
        )
        assert outcome.dismissed == 2
        assert outcome.pending_review == 0

        for alert_id in seed["alert_ids"][:2]:
            row = conn.execute(
                "SELECT status, independent_review FROM alerts WHERE id=?", (alert_id,)
            ).fetchone()
            assert row["status"] == "false_positive"
            assert row["independent_review"] == "single_operator"
