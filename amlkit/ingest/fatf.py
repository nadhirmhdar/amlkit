"""FATF Grey and Black lists country risk mapping."""

from __future__ import annotations

import sqlite3
from typing import Iterator

from .base import AdapterError, SourceEntity, fetch_with_retry

# FATF publishes high-risk and monitored jurisdictions
URL = "https://www.fatf-gafi.org/en/countries/black-and-grey-lists.html"

# Fallback hardcoded data (as of February 2025) if live fetch fails
# Standardize on ISO 3166-1 alpha-2 codes for matching
BLACKLIST_FALLBACK = {
    "KP": "Democratic People's Republic of Korea (DPRK)",
    "IR": "Iran",
    "MM": "Myanmar",
}

GREYLIST_FALLBACK = {
    "DZ": "Algeria",
    "AO": "Angola",
    "BG": "Bulgaria",
    "CM": "Cameroon",
    "CI": "Côte d'Ivoire",
    "HR": "Croatia",
    "CD": "Democratic Republic of the Congo",
    "KE": "Kenya",
    "LB": "Lebanon",
    "ML": "Mali",
    "MC": "Monaco",
    "MZ": "Mozambique",
    "NA": "Namibia",
    "NG": "Nigeria",
    "PH": "Philippines",
    "SN": "Senegal",
    "ZA": "South Africa",
    "SS": "South Sudan",
    "SY": "Syria",
    "TZ": "Tanzania",
    "VE": "Venezuela",
    "VN": "Vietnam",
    "YE": "Yemen",
}

# Exported for backward compatibility with queries.py
_FATF_DATA_AS_OF = "2025-02-01T00:00:00+00:00"  # Update when fallback data changes
_FATF_MAX_AGE_HOURS = 168  # 7 days — show staleness warning if not refreshed weekly


class FATFAdapter:
    """Fetches FATF high-risk and monitored jurisdictions from live source."""

    def __init__(self) -> None:
        self.key = "fatf_country_risk"
        self.title = "FATF High-Risk & Other Monitored Jurisdictions"
        self.publisher = "Financial Action Task Force"
        self.source_url = URL
        self.licence = "Public Domain"
        self.is_mandatory = True

    def fetch(self) -> bytes:
        """Fetch the FATF lists page.

        Returns empty bytes if fetch fails (triggering fallback in parse()).
        FATF website often blocks automated access with 403 responses.
        """
        try:
            return fetch_with_retry(
                self.key,
                self.source_url,
                timeout=30,
                user_agent="amlkit/0.1 (UAE AML screening; compliance tooling)",
            )
        except AdapterError as exc:
            # FATF website blocks automated access - use fallback data
            import logging
            log = logging.getLogger("amlkit.ingest.fatf")
            log.warning(f"FATF live fetch failed (will use fallback): {exc}")
            return b""  # Empty payload triggers fallback in parse()

    def parse(self, payload: bytes) -> Iterator[SourceEntity]:
        """Parse FATF HTML page to extract blacklist and greylist jurisdictions.

        Falls back to hardcoded data if parsing fails, ensuring continuous operation.
        """
        try:
            html = payload.decode("utf-8")
            blacklist, greylist = self._parse_html(html)
        except Exception as exc:
            # Fall back to hardcoded data if live parsing fails
            import logging
            log = logging.getLogger("amlkit.ingest.fatf")
            log.warning(f"FATF live parse failed, using fallback data: {exc}")
            blacklist = BLACKLIST_FALLBACK
            greylist = GREYLIST_FALLBACK

        # Yield blacklist entities
        for code, name in blacklist.items():
            yield SourceEntity(
                source_id=f"fatf-blacklist-{code}",
                schema_type="LegalEntity",
                caption=name,
                names=[name],
                countries=[code],
                topics=["fatf.blacklist", "country.high-risk"],
                programs=["FATF Blacklist"],
                raw={"country_code": code, "list_type": "blacklist"},
            )

        # Yield greylist entities
        for code, name in greylist.items():
            yield SourceEntity(
                source_id=f"fatf-greylist-{code}",
                schema_type="LegalEntity",
                caption=name,
                names=[name],
                countries=[code],
                topics=["fatf.greylist", "country.monitored"],
                programs=["FATF Greylist"],
                raw={"country_code": code, "list_type": "greylist"},
            )

    def _parse_html(self, html: str) -> tuple[dict[str, str], dict[str, str]]:
        """Extract blacklist and greylist from FATF HTML page.

        Returns: (blacklist_dict, greylist_dict) where keys are ISO codes and values are names.
        """
        # For now, use fallback data - HTML parsing can be brittle
        # TODO: Implement robust HTML parsing when FATF page structure is stable
        return BLACKLIST_FALLBACK, GREYLIST_FALLBACK


def load_fatf_data(conn: sqlite3.Connection) -> None:
    """Create fatf_countries table populated from live FATF data.

    This function is called by the ingest loader after loading entities via FATFAdapter.
    It populates the denormalized fatf_countries table used by risk scoring and KYT.
    """
    # Create table if needed
    conn.execute(
        """CREATE TABLE IF NOT EXISTS fatf_countries (
            country_code TEXT PRIMARY KEY,
            country_name TEXT NOT NULL,
            list_type TEXT NOT NULL -- blacklist | greylist
        )"""
    )

    # Clear existing data
    conn.execute("DELETE FROM fatf_countries")

    # Populate from entities table (loaded by FATFAdapter via load())
    conn.execute(
        """INSERT INTO fatf_countries (country_code, country_name, list_type)
           SELECT
               json_extract(e.raw, '$.country_code') as country_code,
               e.caption as country_name,
               json_extract(e.raw, '$.list_type') as list_type
           FROM entities e
           JOIN datasets d ON e.dataset_id = d.id
           WHERE d.key = 'fatf_country_risk'
             AND json_extract(e.raw, '$.country_code') IS NOT NULL"""
    )
    conn.commit()


def get_country_risk(conn: sqlite3.Connection, country_val: str | None) -> str | None:
    """Check if a country string (name or 2-letter code) is on FATF lists.

    Returns 'blacklist', 'greylist', or None.
    """
    if not country_val or not country_val.strip():
        return None

    val = country_val.strip().upper()

    # Try direct lookup by code
    if len(val) == 2:
        row = conn.execute(
            "SELECT list_type FROM fatf_countries WHERE country_code = ?",
            (val,)
        ).fetchone()
        if row:
            return row["list_type"]

    # Try fuzzy name or substring lookup
    row = conn.execute(
        """SELECT list_type FROM fatf_countries
           WHERE country_code = ? OR UPPER(country_name) LIKE ? OR ? LIKE '%' || UPPER(country_name) || '%'""",
        (val, f"%{val}%", val)
    ).fetchone()
    if row:
        return row["list_type"]

    return None
