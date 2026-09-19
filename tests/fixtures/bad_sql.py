"""Test fixture: SQL queries with tenant-isolation violations.

These are intentional violations to test the security scanner.
"""

import sqlite3


def update_customer_no_org_filter(conn: sqlite3.Connection, customer_id: int, name: str):
    """VIOLATION: UPDATE on org-scoped table without org_id in WHERE clause."""
    conn.execute(
        "UPDATE customers SET full_name = ? WHERE id = ?",
        (name, customer_id)
    )


def delete_alert_no_org_filter(conn: sqlite3.Connection, alert_id: int):
    """VIOLATION: DELETE on org-scoped table without org_id in WHERE clause."""
    conn.execute(
        "DELETE FROM alerts WHERE id = ?",
        (alert_id,)
    )


def select_screenings_no_org_filter(conn: sqlite3.Connection, customer_id: int):
    """VIOLATION: SELECT on org-scoped table without org_id in WHERE clause."""
    return conn.execute(
        "SELECT * FROM screenings WHERE customer_id = ?",
        (customer_id,)
    ).fetchall()


def use_fetched_org_id(conn: sqlite3.Connection, customer_id: int, new_status: str):
    """VIOLATION: Uses org_id from fetched row instead of session."""
    # Fetch customer with org_id
    row = conn.execute(
        "SELECT org_id FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()

    # WRONG: Using org_id from database row for write operation
    # Should use org_id from session instead
    conn.execute(
        "UPDATE customers SET status = ? WHERE id = ? AND org_id = ?",
        (new_status, customer_id, row["org_id"])
    )


# This function is CORRECT - it should NOT be flagged
def update_dataset_error(conn: sqlite3.Connection, dataset_key: str, error: str):
    """Shared datasets table - no org_id required (documented exception)."""
    conn.execute(
        "UPDATE datasets SET last_error = ? WHERE key = ?",
        (error, dataset_key)
    )
