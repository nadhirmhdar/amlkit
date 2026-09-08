"""FATF Grey and Black lists country risk mapping."""

from __future__ import annotations

import sqlite3

# As of FATF update: October 2024 / February 2025
# Standardize on ISO 3166-1 alpha-2 and alpha-3 codes for matching,
# plus common English names.
BLACKLIST = {
    "KP": "Democratic People's Republic of Korea (DPRK)",
    "IR": "Iran",
    "MM": "Myanmar",
}

GREYLIST = {
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


_FATF_DATA_AS_OF = "2025-02-01T00:00:00+00:00"  # update this when BLACKLIST/GREYLIST change
_FATF_MAX_AGE_HOURS = 2160  # 90 days — aligns with quarterly FATF plenary cycle


def load_fatf_data(conn: sqlite3.Connection) -> None:
    """Create fatf_countries table and insert current lists.

    Skips the DELETE+INSERT when the stored data already matches the current
    _FATF_DATA_AS_OF version, so concurrent requests don't contend on a write lock.
    """
    conn.execute(
        """CREATE TABLE IF NOT EXISTS fatf_countries (
            country_code TEXT PRIMARY KEY,
            country_name TEXT NOT NULL,
            list_type TEXT NOT NULL -- blacklist | greylist
        )"""
    )
    conn.commit()

    row = conn.execute(
        "SELECT last_refresh FROM datasets WHERE key = 'fatf_country_risk'"
    ).fetchone()
    if row and row[0] == _FATF_DATA_AS_OF:
        return

    with conn:
        conn.execute("DELETE FROM fatf_countries")

        for code, name in BLACKLIST.items():
            conn.execute(
                "INSERT INTO fatf_countries (country_code, country_name, list_type) VALUES (?, ?, 'blacklist')",
                (code, name),
            )
        for code, name in GREYLIST.items():
            conn.execute(
                "INSERT INTO fatf_countries (country_code, country_name, list_type) VALUES (?, ?, 'greylist')",
                (code, name),
            )

        entity_count = len(BLACKLIST) + len(GREYLIST)
        conn.execute(
            """INSERT INTO datasets (key, title, publisher, source_url, is_mandatory,
                                     last_refresh, entity_count, max_age_hours)
               VALUES ('fatf_country_risk',
                       'FATF High-Risk & Other Monitored Jurisdictions',
                       'Financial Action Task Force',
                       'https://www.fatf-gafi.org/en/countries/black-and-grey-lists.html',
                       0, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                   entity_count  = excluded.entity_count,
                   max_age_hours = excluded.max_age_hours""",
            (_FATF_DATA_AS_OF, entity_count, _FATF_MAX_AGE_HOURS),
        )


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
