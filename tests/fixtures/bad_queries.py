"""Test fixture: Query functions with tenant-isolation violations.

These are intentional violations to test the security scanner.
"""

import sqlite3


def get_customer_list(conn: sqlite3.Connection) -> list[dict]:
    """VIOLATION: Missing org_id parameter - can query across all tenants."""
    return conn.execute("SELECT * FROM customers").fetchall()


def get_screening_results(conn: sqlite3.Connection, customer_id: int) -> list[dict]:
    """VIOLATION: Missing org_id parameter."""
    return conn.execute(
        "SELECT * FROM screenings WHERE customer_id = ?", (customer_id,)
    ).fetchall()


def get_alerts(conn: sqlite3.Connection, status: str = "open") -> list[dict]:
    """VIOLATION: Missing org_id parameter."""
    return conn.execute(
        "SELECT * FROM alerts WHERE status = ?", (status,)
    ).fetchall()


# This function is CORRECT - it should NOT be flagged
def get_entities(conn: sqlite3.Connection, search: str) -> list[dict]:
    """Shared sanctions data - no org_id required (documented exception)."""
    return conn.execute(
        "SELECT * FROM entities WHERE name LIKE ?", (f"%{search}%",)
    ).fetchall()
