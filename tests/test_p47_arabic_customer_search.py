"""p47: Server-side customer search with Arabic name canonicalization."""
import sqlite3
import os

import pytest


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    from amlkit import db as dbmod
    conn = dbmod.connect(str(db_file))
    conn.execute(
        "INSERT INTO organizations (id, name, slug, created_at) VALUES (1, 'Test Firm', 'test-firm', '2025-01-01')"
    )
    conn.commit()
    return conn


def _add_customer(conn, org_id, reference, full_name, name_arabic=None):
    from amlkit.names.arabic import canonical_key
    conn.execute(
        """INSERT INTO customers (org_id, reference, customer_type, full_name, name_arabic,
           canonical_key, nationality, sector, status, onboarded_at, created_at, updated_at)
           VALUES (?, ?, 'natural', ?, ?, ?, 'AE', 'other', 'active', '2025-01-01', '2025-01-01', '2025-01-01')""",
        (org_id, reference, full_name, name_arabic, canonical_key(full_name)),
    )
    conn.commit()


def test_search_by_latin_name(db):
    """Search should find customer by Latin name substring."""
    from amlkit.queries import search_customers
    _add_customer(db, 1, "C-001", "Mohammed Al-Rashidi")
    _add_customer(db, 1, "C-002", "Sara Ahmed")

    results = search_customers(db, 1, "rashidi")
    assert len(results) == 1
    assert results[0]["reference"] == "C-001"


def test_search_by_arabic_name(db):
    """Search should find customer by Arabic script name."""
    from amlkit.queries import search_customers
    _add_customer(db, 1, "C-001", "Mohammed Al-Rashidi", name_arabic="محمد الراشدي")

    results = search_customers(db, 1, "الراشدي")
    assert len(results) == 1
    assert results[0]["reference"] == "C-001"


def test_search_by_reference(db):
    """Search should find customer by reference code."""
    from amlkit.queries import search_customers
    _add_customer(db, 1, "C-001", "Mohammed Al-Rashidi")
    _add_customer(db, 1, "C-002", "Sara Ahmed")

    results = search_customers(db, 1, "C-002")
    assert len(results) == 1
    assert results[0]["full_name"] == "Sara Ahmed"


def test_search_canonical_strips_al_prefix(db):
    """Search for "Rashidi" should match "Al-Rashidi" via canonical key."""
    from amlkit.queries import search_customers
    _add_customer(db, 1, "C-001", "Mohammed Al-Rashidi")

    results = search_customers(db, 1, "Rashidi")
    assert len(results) >= 1
    assert any(r["reference"] == "C-001" for r in results)


def test_search_canonical_transliteration_variants(db):
    """Search for "Mohammad" should find "Mohammed" via canonicalization."""
    from amlkit.queries import search_customers
    _add_customer(db, 1, "C-001", "Mohammed Al-Rashidi")

    results = search_customers(db, 1, "Mohammad")
    assert len(results) >= 1
    assert any(r["reference"] == "C-001" for r in results)


def test_search_respects_org_isolation(db):
    """Search must not return customers from another organization."""
    from amlkit.queries import search_customers
    db.execute(
        "INSERT INTO organizations (id, name, slug, created_at) VALUES (2, 'Other Firm', 'other-firm', '2025-01-01')"
    )
    db.commit()
    _add_customer(db, 1, "C-001", "Mohammed Al-Rashidi")
    _add_customer(db, 2, "C-002", "Mohammed Al-Rashidi")

    results = search_customers(db, 1, "rashidi")
    assert len(results) == 1
    assert results[0]["reference"] == "C-001"


def test_search_empty_returns_all(db):
    """Empty query should return all customers (same as no search)."""
    from amlkit.queries import search_customers
    _add_customer(db, 1, "C-001", "Mohammed Al-Rashidi")
    _add_customer(db, 1, "C-002", "Sara Ahmed")

    results = search_customers(db, 1, "")
    assert len(results) == 2


def test_search_no_match_returns_empty(db):
    """Non-matching query should return empty list."""
    from amlkit.queries import search_customers
    _add_customer(db, 1, "C-001", "Mohammed Al-Rashidi")

    results = search_customers(db, 1, "nonexistent12345")
    assert results == []
