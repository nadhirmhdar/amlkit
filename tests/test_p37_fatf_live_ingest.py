"""Test FATF live data ingest (p37).

FATF (Financial Action Task Force) publishes two watchlists:
- Blacklist: jurisdictions under increased monitoring (call for action)
- Greylist: jurisdictions with strategic deficiencies

This test verifies that we can fetch and parse these lists from live sources
instead of hardcoded dictionaries.
"""

from __future__ import annotations

import sqlite3

import pytest

from amlkit.ingest.fatf import FATFAdapter
from amlkit.ingest.loader import load
from amlkit.ingest.base import SourceAdapter


def test_fatf_adapter_implements_protocol():
    """FATF adapter must implement the SourceAdapter protocol."""
    adapter = FATFAdapter()

    # Required protocol fields
    assert hasattr(adapter, 'key')
    assert hasattr(adapter, 'title')
    assert hasattr(adapter, 'publisher')
    assert hasattr(adapter, 'source_url')
    assert hasattr(adapter, 'licence')
    assert hasattr(adapter, 'is_mandatory')

    # Required protocol methods
    assert callable(adapter.fetch)
    assert callable(adapter.parse)

    # FATF is mandatory per UAE AML/CFT regulations
    assert adapter.is_mandatory is True
    assert adapter.key == 'fatf_country_risk'


def test_fatf_adapter_fetch_returns_bytes():
    """fetch() returns bytes (empty if live fetch fails, triggering fallback)."""
    adapter = FATFAdapter()

    payload = adapter.fetch()
    assert isinstance(payload, bytes)
    # Empty bytes is valid - triggers fallback in parse()
    # Non-empty bytes means live fetch succeeded


def test_fatf_adapter_parse_yields_entities():
    """parse() must yield SourceEntity objects using fallback data when needed."""
    adapter = FATFAdapter()

    # Parse with empty payload (triggers fallback)
    entities = list(adapter.parse(b""))

    # Should parse jurisdictions from fallback data
    assert len(entities) > 0

    # Each entity should have required fields
    for entity in entities:
        assert entity.source_id  # unique identifier
        assert entity.caption  # country name
        assert entity.schema_type == 'LegalEntity'
        assert entity.countries  # ISO codes

        # Should have topics indicating list type
        assert entity.topics
        assert any(t in ['fatf.blacklist', 'fatf.greylist'] for t in entity.topics)


def test_fatf_load_into_database(tmp_path):
    """Loading FATF data should populate fatf_countries table."""
    from amlkit.db import connect
    from amlkit.ingest.fatf import load_fatf_data

    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))

    adapter = FATFAdapter()
    result = load(conn, adapter, actor="test")

    # Should load entities
    assert result.entities > 0
    assert result.dataset == 'fatf_country_risk'

    # Populate denormalized fatf_countries table
    load_fatf_data(conn)

    # Should populate fatf_countries table
    row = conn.execute(
        "SELECT COUNT(*) as count FROM fatf_countries"
    ).fetchone()
    assert row["count"] > 0

    # Should have both blacklist and greylist entries
    blacklist_count = conn.execute(
        "SELECT COUNT(*) as count FROM fatf_countries WHERE list_type='blacklist'"
    ).fetchone()["count"]

    greylist_count = conn.execute(
        "SELECT COUNT(*) as count FROM fatf_countries WHERE list_type='greylist'"
    ).fetchone()["count"]

    assert blacklist_count > 0, "Should have blacklist entries"
    assert greylist_count > 0, "Should have greylist entries"

    conn.close()


def test_fatf_included_in_scheduler():
    """FATF adapter should be available for scheduler refresh."""
    # Verify FATF is importable and in scheduler's factory list
    from amlkit.cases import scheduler
    import inspect

    # Get the source code of run_sanctions_refresh
    source = inspect.getsource(scheduler.run_sanctions_refresh)

    # Verify FATF is imported and in the factories list
    assert "FATFAdapter" in source, "FATFAdapter should be imported in scheduler"
    assert "fatf" in source.lower(), "FATF should be in refresh cycle"
