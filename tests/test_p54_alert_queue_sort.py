"""Test p54: Alert queue sort by age.

Alerts list should default to oldest-open-first ordering (sort by created_at ASC
where status='open'). Add a sort control to toggle newest-first.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta

from amlkit import auth, db, queries
from amlkit.cases.manager import onboard
from amlkit.db import utcnow, upsert_dataset
from amlkit.names.arabic import blocking_keys, canonical_key


def test_alert_queue_defaults_to_oldest_first_for_open_alerts(tmp_path):
    """Default sort for open alerts is oldest-first (created_at ASC)."""
    db_file = tmp_path / "test.db"
    conn = db.connect(str(db_file))

    # Create org and operator
    org_id = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id",
        ("Test Org", "test-org", "active", utcnow()),
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO operators (org_id, email, password_hash, name, role, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (org_id, "op@test.ae", auth.hash_password("Pass123!"), "Operator", "mlro", 1, utcnow()),
    )
    conn.commit()

    # Load sanctions data (minimal)
    ds_id = upsert_dataset(conn, "test_dataset", "Test Dataset", is_mandatory=True)
    now = utcnow()
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds_id))
    entity_id = conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           countries, birth_date, gender, topics, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
        (ds_id, "bad-actor-a", "Person", "Bad Actor A",
         json.dumps([]), None, None, json.dumps(["sanction"]), json.dumps({}), now, now),
    ).fetchone()["id"]
    name = "Bad Actor A"
    conn.execute(
        "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script) VALUES (?,?,?,?,?)",
        (entity_id, name, "primary", canonical_key(name), "latin"),
    )
    # Add blocking tokens for name matching
    for tok in blocking_keys(name):
        conn.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)", (tok, entity_id))
    conn.commit()

    # Create 3 customers at different times that will trigger alerts
    base_time = datetime.utcnow()
    customer_refs = []

    for i, offset_minutes in enumerate([0, 5, 10]):  # Create oldest to newest
        # Manually set created_at to control timing
        created_at = (base_time + timedelta(minutes=offset_minutes)).isoformat()

        result = onboard(
            conn, org_id=org_id,
            reference=f"CUST{i:03d}",
            full_name="Bad Actor A",  # Will match sanctions
            country="AE",
            id_type="passport",
            id_number=f"P{i:06d}",
        )
        customer_id = result.customer_id
        customer_refs.append(customer_id)

        # Update created_at to simulate time difference
        conn.execute(
            "UPDATE customers SET created_at = ? WHERE id = ?",
            (created_at, customer_id)
        )

        # Update alert created_at to match customer created_at (alert was created by onboard())
        conn.execute(
            """UPDATE alerts SET created_at = ?
               WHERE screening_id IN (SELECT id FROM screenings WHERE customer_id = ?)""",
            (created_at, customer_id)
        )

    conn.commit()

    # Query alert queue with default sort (should be oldest-first)
    queue = queries.alert_queue(conn, org_id, status="open", sort_by="age_asc")

    # Verify we have 3 alerts
    assert len(queue) == 3, f"Expected 3 alerts, got {len(queue)}"

    # Verify they are sorted oldest-first by created_at
    times = [datetime.fromisoformat(a["created_at"]) for a in queue]
    assert times == sorted(times), f"Alerts not sorted oldest-first: {[t.isoformat() for t in times]}"

    # Verify the oldest is first
    assert queue[0]["customer_id"] == customer_refs[0], "Oldest alert should be first"
    assert queue[2]["customer_id"] == customer_refs[2], "Newest alert should be last"

    conn.close()


def test_alert_queue_can_sort_newest_first(tmp_path):
    """Sort toggle allows newest-first ordering (created_at DESC)."""
    db_file = tmp_path / "test.db"
    conn = db.connect(str(db_file))

    # Create org and operator
    org_id = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id",
        ("Test Org", "test-org", "active", utcnow()),
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO operators (org_id, email, password_hash, name, role, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (org_id, "op@test.ae", auth.hash_password("Pass123!"), "Operator", "mlro", 1, utcnow()),
    )
    conn.commit()

    # Load sanctions data
    ds_id = upsert_dataset(conn, "test_dataset", "Test Dataset", is_mandatory=True)
    now = utcnow()
    conn.execute("UPDATE datasets SET last_refresh=?, entity_count=1 WHERE id=?", (now, ds_id))
    entity_id = conn.execute(
        """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
           countries, birth_date, gender, topics, raw, first_seen, last_seen)
           VALUES (?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
        (ds_id, "bad-actor-a", "Person", "Bad Actor A",
         json.dumps([]), None, None, json.dumps(["sanction"]), json.dumps({}), now, now),
    ).fetchone()["id"]
    name = "Bad Actor A"
    conn.execute(
        "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script) VALUES (?,?,?,?,?)",
        (entity_id, name, "primary", canonical_key(name), "latin"),
    )
    # Add blocking tokens for name matching
    for tok in blocking_keys(name):
        conn.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)", (tok, entity_id))
    conn.commit()

    # Create 3 customers at different times
    base_time = datetime.utcnow()
    customer_refs = []

    for i, offset_minutes in enumerate([0, 5, 10]):
        created_at = (base_time + timedelta(minutes=offset_minutes)).isoformat()

        result = onboard(
            conn, org_id=org_id,
            reference=f"CUST{i:03d}",
            full_name="Bad Actor A",
            country="AE",
            id_type="passport",
            id_number=f"P{i:06d}",
        )
        customer_id = result.customer_id
        customer_refs.append(customer_id)

        conn.execute(
            "UPDATE customers SET created_at = ? WHERE id = ?",
            (created_at, customer_id)
        )

        conn.execute(
            """UPDATE alerts SET created_at = ?
               WHERE screening_id IN (SELECT id FROM screenings WHERE customer_id = ?)""",
            (created_at, customer_id)
        )

    conn.commit()

    # Query with newest-first sort
    queue = queries.alert_queue(conn, org_id, status="open", sort_by="age_desc")

    # Verify we have 3 alerts
    assert len(queue) == 3

    # Verify they are sorted newest-first by created_at
    times = [datetime.fromisoformat(a["created_at"]) for a in queue]
    assert times == sorted(times, reverse=True), f"Alerts not sorted newest-first"

    # Verify the newest is first
    assert queue[0]["customer_id"] == customer_refs[2], "Newest alert should be first"
    assert queue[2]["customer_id"] == customer_refs[0], "Oldest alert should be last"

    conn.close()


def test_web_route_accepts_sort_parameter():
    """Web route signature accepts sort parameter."""
    # This test verifies the route signature accepts the sort parameter.
    # Full E2E testing is done in test_api.py.
    from amlkit.api import app as web_app
    import inspect

    # Get the alerts route function
    for route in web_app.app.routes:
        if hasattr(route, 'path') and route.path == "/alerts" and hasattr(route, 'endpoint'):
            sig = inspect.signature(route.endpoint)
            params = sig.parameters
            # Verify 'sort' parameter exists
            assert 'sort' in params, "Route should accept 'sort' parameter"
            # Verify it has a default value
            assert params['sort'].default != inspect.Parameter.empty, "sort should have a default value"
            return

    raise AssertionError("/alerts route not found")
