"""FATF Grey and Black lists country risk mapping."""

from __future__ import annotations

import sqlite3
from typing import Iterator

from .base import AdapterError

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


def load_fatf_data(conn: sqlite3.Connection) -> None:
    """Create fatf_countries table and insert current lists."""
    with conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS fatf_countries (
                country_code TEXT PRIMARY KEY,
                country_name TEXT NOT NULL,
                list_type TEXT NOT NULL -- blacklist | greylist
            )"""
        )
        # Clear existing
        conn.execute("DELETE FROM fatf_countries")
        
        for code, name in BLACKLIST.items():
            conn.execute(
                "INSERT INTO fatf_countries (country_code, country_name, list_type) VALUES (?, ?, 'blacklist')",
                (code, name)
            )
        for code, name in GREYLIST.items():
            conn.execute(
                "INSERT INTO fatf_countries (country_code, country_name, list_type) VALUES (?, ?, 'greylist')",
                (code, name)
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
