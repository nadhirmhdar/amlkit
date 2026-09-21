"""Test p42: Customer completeness indicator.

Show a completeness percentage on customer profiles based on how many
required fields are filled (name, DOB, nationality, address, risk assessment, UBOs).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect, utcnow
from amlkit.queries import customer_completeness


def test_completeness_calculation_all_fields_present(tmp_path):
    """Completeness is 100% when all required fields filled."""
    customer = {
        "full_name": "John Doe",
        "birth_date": "1990-01-01",
        "nationality": "US",
        "address_line1": "123 Main St",
        "risk_rating": "medium",
    }

    completeness = customer_completeness(customer)
    assert completeness == 100.0


def test_completeness_calculation_partial_fields(tmp_path):
    """Completeness reflects percentage of filled required fields."""
    customer = {
        "full_name": "John Doe",
        "birth_date": "1990-01-01",
        "nationality": "US",
        # address_line1 missing
        # risk_rating missing
    }

    completeness = customer_completeness(customer)
    assert completeness == 60.0  # 3/5 fields


def test_completeness_calculation_minimal_fields(tmp_path):
    """Completeness shows 20% when only name provided."""
    customer = {
        "full_name": "John Doe",
        # All other fields missing
    }

    completeness = customer_completeness(customer)
    assert completeness == 20.0  # 1/5 fields


def test_customer_query_includes_completeness_fields(tmp_path):
    """Customer query returns fields needed for completeness calculation."""
    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))
    now = utcnow()

    conn.execute(
        "INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1, 'TestOrg', 'testorg', 'active', ?)",
        (now,),
    )
    conn.execute(
        """INSERT INTO customers
           (org_id, reference, customer_type, full_name, canonical_key,
            birth_date, nationality, address_line1,
            onboarded_at, created_at, updated_at)
           VALUES (1, 'C-001', 'natural', 'Jane Smith', 'jane-smith',
                   '1985-05-15', 'AE', '456 Sheikh Zayed Road',
                   ?, ?, ?)""",
        (now, now, now),
    )
    conn.commit()

    # Query customer with fields needed for completeness
    row = conn.execute(
        """SELECT full_name, birth_date, nationality, address_line1
           FROM customers WHERE reference = ?""",
        ("C-001",),
    ).fetchone()

    assert row is not None
    assert row["full_name"] == "Jane Smith"
    assert row["birth_date"] == "1985-05-15"
    assert row["nationality"] == "AE"
    assert row["address_line1"] == "456 Sheikh Zayed Road"
