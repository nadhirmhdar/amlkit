"""Test p40: adverse media async operation.

Verify run_adverse_media_async() starts background thread and returns immediately.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from amlkit.db import connect
from amlkit.cases.manager import run_adverse_media_async, check_adverse_media_status


def test_async_returns_immediately(tmp_path):
    """Async version should return immediately, not block on HTTP."""
    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))

    # Register org and customer
    cur = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) "
        "VALUES ('Test Firm', 'test-firm', 'active', datetime('now'))"
    )
    org_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO customers (org_id, name, customer_type, onboarded_at) "
        "VALUES (?, 'John Smith', 'individual', datetime('now'))",
        (org_id,)
    )
    customer_id = cur.lastrowid
    conn.commit()

    # Start async search - should return immediately
    start = time.time()
    job_id = run_adverse_media_async(
        conn,
        org_id=org_id,
        name="John Smith",
        customer_id=customer_id,
        actor="test"
    )
    elapsed = time.time() - start

    # Should return in under 1 second (not block on HTTP which takes 5+ seconds)
    assert elapsed < 1.0, f"Took {elapsed}s - should be instant"
    assert job_id is not None

    conn.close()


def test_async_status_pending_then_complete(tmp_path):
    """Status should show pending initially, then complete when done."""
    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))

    cur = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) "
        "VALUES ('Test Firm', 'test-firm', 'active', datetime('now'))"
    )
    org_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO customers (org_id, name, customer_type, onboarded_at) "
        "VALUES (?, 'Test Name', 'individual', datetime('now'))",
        (org_id,)
    )
    customer_id = cur.lastrowid
    conn.commit()

    job_id = run_adverse_media_async(
        conn,
        org_id=org_id,
        name="Test Name",
        customer_id=customer_id,
        actor="test"
    )

    # Should be pending immediately after start
    status = check_adverse_media_status(conn, job_id)
    assert status["status"] == "pending"

    # Wait for completion (with timeout)
    for _ in range(30):  # 30 seconds max
        time.sleep(1)
        status = check_adverse_media_status(conn, job_id)
        if status["status"] != "pending":
            break

    # Should eventually complete
    assert status["status"] in ["complete", "failed"]

    conn.close()


def test_async_stores_results_when_done(tmp_path):
    """Results should be stored in DB when background thread completes."""
    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))

    cur = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) "
        "VALUES ('Test Firm', 'test-firm', 'active', datetime('now'))"
    )
    org_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO customers (org_id, name, customer_type, onboarded_at) "
        "VALUES (?, 'Test Person', 'individual', datetime('now'))",
        (org_id,)
    )
    customer_id = cur.lastrowid
    conn.commit()

    job_id = run_adverse_media_async(
        conn,
        org_id=org_id,
        name="Test Person",
        customer_id=customer_id,
        actor="test"
    )

    # Wait for completion
    for _ in range(30):
        time.sleep(1)
        status = check_adverse_media_status(conn, job_id)
        if status["status"] != "pending":
            break

    # Check that screening record was created
    screening = conn.execute(
        "SELECT * FROM adverse_media_screenings WHERE customer_id=?",
        (customer_id,)
    ).fetchone()

    assert screening is not None
    assert screening["query_name"] == "Test Person"

    conn.close()


def test_async_multiple_concurrent_jobs(tmp_path):
    """Multiple async jobs should run concurrently without blocking each other."""
    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))

    cur = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) "
        "VALUES ('Test Firm', 'test-firm', 'active', datetime('now'))"
    )
    org_id = cur.lastrowid

    # Create multiple customers
    customers = []
    for i in range(3):
        cur = conn.execute(
            "INSERT INTO customers (org_id, name, customer_type, onboarded_at) "
            "VALUES (?, ?, 'individual', datetime('now'))",
            (org_id, f"Person {i}")
        )
        customers.append(cur.lastrowid)
    conn.commit()

    # Start multiple jobs concurrently
    start = time.time()
    job_ids = []
    for i, customer_id in enumerate(customers):
        job_id = run_adverse_media_async(
            conn,
            org_id=org_id,
            name=f"Person {i}",
            customer_id=customer_id,
            actor="test"
        )
        job_ids.append(job_id)
    elapsed = time.time() - start

    # All should start quickly (not serialized)
    assert elapsed < 2.0, f"Took {elapsed}s to start 3 jobs"

    # All should have different job IDs
    assert len(set(job_ids)) == 3

    conn.close()
