"""Test FATF country risk fallback behavior (t16 / p29).

When fatf_countries table is populated (via load_fatf_data or refresh),
KYT screening uses those codes as the authoritative baseline.

When fatf_countries table is empty (fresh DB, no refresh yet),
KYT falls back to HIGH_RISK_COUNTRIES module constant.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect
from amlkit.ingest.fatf import load_fatf_data
from amlkit.screening.kyt import _get_high_risk_countries


def test_fatf_fallback_when_table_empty(tmp_path):
    """When fatf_countries table is empty, fall back to HIGH_RISK_COUNTRIES constant."""
    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))

    # Ensure fatf_countries table exists but is empty
    conn.execute(
        """CREATE TABLE IF NOT EXISTS fatf_countries (
            country_code TEXT PRIMARY KEY,
            country_name TEXT NOT NULL,
            list_type TEXT NOT NULL
        )"""
    )
    conn.execute("DELETE FROM fatf_countries")
    conn.commit()

    # _get_high_risk_countries should fall back to HIGH_RISK_COUNTRIES constant
    from amlkit.screening.kyt import HIGH_RISK_COUNTRIES
    result = _get_high_risk_countries(conn, org_additional=[])

    # Result should match the hardcoded constant (as sorted list)
    assert set(result) == set(HIGH_RISK_COUNTRIES), \
        "When FATF table empty, should fall back to HIGH_RISK_COUNTRIES constant"

    conn.close()


def test_fatf_overrides_constant_when_populated(tmp_path):
    """When fatf_countries is populated, it overrides the hardcoded constant."""
    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))

    # Populate FATF table
    load_fatf_data(conn)
    conn.commit()

    # Fetch FATF codes from table
    fatf_rows = conn.execute("SELECT country_code FROM fatf_countries").fetchall()
    fatf_codes = {row["country_code"] for row in fatf_rows}

    assert len(fatf_codes) > 0, "FATF data should be loaded"

    # _get_high_risk_countries should use FATF table
    result = _get_high_risk_countries(conn, org_additional=[])

    # Result should match FATF table, not the constant (as sorted list)
    assert set(result) == fatf_codes, \
        "When FATF table populated, should use table data not constant"

    conn.close()


def test_org_additional_is_additive(tmp_path):
    """org_additional countries are added to FATF baseline, not replaced."""
    db_file = tmp_path / "test.db"
    conn = connect(str(db_file))

    # Populate FATF table
    load_fatf_data(conn)
    conn.commit()

    fatf_rows = conn.execute("SELECT country_code FROM fatf_countries").fetchall()
    fatf_codes = {row["country_code"] for row in fatf_rows}

    # Add custom org countries
    org_custom = ["XX", "YY"]
    result = _get_high_risk_countries(conn, org_additional=org_custom)

    # Result should be FATF + org_custom (as sorted list)
    expected = fatf_codes | set(org_custom)
    assert set(result) == expected, \
        "org_additional should be union with FATF baseline, not replacement"

    conn.close()
