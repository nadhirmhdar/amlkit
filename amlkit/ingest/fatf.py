"""FATF Grey and Black lists country risk mapping."""

from __future__ import annotations

import logging
import re
import sqlite3
from html.parser import HTMLParser
from typing import Iterator

from .base import AdapterError, SourceEntity, fetch_with_retry

log = logging.getLogger("amlkit.ingest.fatf")

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

# Country name → ISO 3166-1 alpha-2. Covers all countries that have appeared
# on FATF black/grey lists since 2019, plus common alternate spellings.
_COUNTRY_TO_ISO: dict[str, str] = {
    "Afghanistan": "AF",
    "Albania": "AL",
    "Algeria": "DZ",
    "Angola": "AO",
    "Antigua and Barbuda": "AG",
    "Barbados": "BB",
    "Botswana": "BW",
    "Bulgaria": "BG",
    "Burkina Faso": "BF",
    "Cambodia": "KH",
    "Cameroon": "CM",
    "Cayman Islands": "KY",
    "Congo": "CD",
    "Côte d'Ivoire": "CI",
    "Cote d'Ivoire": "CI",
    "Croatia": "HR",
    "Cuba": "CU",
    "Democratic People's Republic of Korea": "KP",
    "Democratic Republic of the Congo": "CD",
    "Ghana": "GH",
    "Gibraltar": "GI",
    "Haiti": "HT",
    "Honduras": "HN",
    "Iceland": "IS",
    "Iran": "IR",
    "Iraq": "IQ",
    "Jamaica": "JM",
    "Jordan": "JO",
    "Kenya": "KE",
    "Laos": "LA",
    "Lao People's Democratic Republic": "LA",
    "Lebanon": "LB",
    "Libya": "LY",
    "Madagascar": "MG",
    "Mali": "ML",
    "Malta": "MT",
    "Mauritius": "MU",
    "Monaco": "MC",
    "Morocco": "MA",
    "Mozambique": "MZ",
    "Myanmar": "MM",
    "Namibia": "NA",
    "Nicaragua": "NI",
    "Nigeria": "NG",
    "North Korea": "KP",
    "Pakistan": "PK",
    "Palestine": "PS",
    "Panama": "PA",
    "Philippines": "PH",
    "Senegal": "SN",
    "Serbia": "RS",
    "Somalia": "SO",
    "South Africa": "ZA",
    "South Sudan": "SS",
    "Sri Lanka": "LK",
    "Sudan": "SD",
    "Syria": "SY",
    "Syrian Arab Republic": "SY",
    "Tanzania": "TZ",
    "Trinidad and Tobago": "TT",
    "Tunisia": "TN",
    "Türkiye": "TR",
    "Turkey": "TR",
    "Uganda": "UG",
    "United Arab Emirates": "AE",
    "Vanuatu": "VU",
    "Venezuela": "VE",
    "Vietnam": "VN",
    "Viet Nam": "VN",
    "Yemen": "YE",
    "Zimbabwe": "ZW",
}

# Section header patterns that identify the two FATF lists
_BLACKLIST_PATTERNS = [
    "high-risk jurisdictions subject to a call for action",
    "high risk jurisdictions subject to a call for action",
    "call for action",
    "black list",
    "blacklist",
]
_GREYLIST_PATTERNS = [
    "jurisdictions under increased monitoring",
    "increased monitoring",
    "grey list",
    "greylist",
]


class _FATFHTMLParser(HTMLParser):
    """Extract country lists from the FATF black-and-grey-lists page.

    Walks the DOM looking for heading elements (h2/h3/h4/strong) that match
    known FATF section titles, then collects <li> text from the <ul> that
    follows each heading.
    """

    def __init__(self) -> None:
        super().__init__()
        self._in_heading = False
        self._in_li = False
        self._current_text = ""
        self._current_section: str | None = None  # "blacklist" | "greylist" | None
        self._blacklist_names: list[str] = []
        self._greylist_names: list[str] = []
        self._heading_tags = {"h2", "h3", "h4", "strong"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._heading_tags:
            self._in_heading = True
            self._current_text = ""
        elif tag == "li" and self._current_section:
            self._in_li = True
            self._current_text = ""

    def handle_endtag(self, tag: str) -> None:
        if tag in self._heading_tags and self._in_heading:
            self._in_heading = False
            heading_lower = self._current_text.strip().lower()
            if any(p in heading_lower for p in _BLACKLIST_PATTERNS):
                self._current_section = "blacklist"
            elif any(p in heading_lower for p in _GREYLIST_PATTERNS):
                self._current_section = "greylist"
            self._current_text = ""
        elif tag == "li" and self._in_li:
            self._in_li = False
            name = self._current_text.strip()
            if name and self._current_section == "blacklist":
                self._blacklist_names.append(name)
            elif name and self._current_section == "greylist":
                self._greylist_names.append(name)
            self._current_text = ""
        elif tag == "ul":
            pass  # section continues until next heading

    def handle_data(self, data: str) -> None:
        if self._in_heading or self._in_li:
            self._current_text += data

    @property
    def blacklist_names(self) -> list[str]:
        return self._blacklist_names

    @property
    def greylist_names(self) -> list[str]:
        return self._greylist_names


def _resolve_country(name: str) -> tuple[str, str] | None:
    """Map a country name from the FATF page to (ISO code, display name).

    Handles parenthetical abbreviations like "Democratic People's Republic
    of Korea (DPRK)" and strips trailing whitespace/punctuation.
    """
    name = name.strip().rstrip(".")

    # Direct match
    if name in _COUNTRY_TO_ISO:
        return _COUNTRY_TO_ISO[name], name

    # Try without parenthetical: "Democratic People's Republic of Korea (DPRK)"
    base = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()
    if base in _COUNTRY_TO_ISO:
        return _COUNTRY_TO_ISO[base], name

    # Case-insensitive search
    name_lower = name.lower()
    for country, code in _COUNTRY_TO_ISO.items():
        if country.lower() == name_lower:
            return code, name

    base_lower = base.lower()
    for country, code in _COUNTRY_TO_ISO.items():
        if country.lower() == base_lower:
            return code, name

    log.warning(f"FATF country not mapped to ISO code: {name!r}")
    return None


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
            log.warning(f"FATF live fetch failed (will use fallback): {exc}")
            return b""

    def parse(self, payload: bytes) -> Iterator[SourceEntity]:
        """Parse FATF HTML page to extract blacklist and greylist jurisdictions.

        Falls back to hardcoded data if parsing fails, ensuring continuous operation.
        """
        try:
            html = payload.decode("utf-8")
            blacklist, greylist = self._parse_html(html)
        except Exception as exc:
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

        Returns (blacklist_dict, greylist_dict) where keys are ISO codes and
        values are display names.  Falls back to hardcoded data when the page
        cannot be parsed or yields no recognisable countries (Cloudflare
        challenge pages, maintenance pages, restructured HTML).
        """
        if not html or not html.strip():
            return BLACKLIST_FALLBACK, GREYLIST_FALLBACK

        parser = _FATFHTMLParser()
        try:
            parser.feed(html)
        except Exception:
            return BLACKLIST_FALLBACK, GREYLIST_FALLBACK

        blacklist: dict[str, str] = {}
        for name in parser.blacklist_names:
            resolved = _resolve_country(name)
            if resolved:
                blacklist[resolved[0]] = resolved[1]

        greylist: dict[str, str] = {}
        for name in parser.greylist_names:
            resolved = _resolve_country(name)
            if resolved:
                greylist[resolved[0]] = resolved[1]

        if not blacklist and not greylist:
            log.warning("FATF HTML parsed but no countries found, using fallback")
            return BLACKLIST_FALLBACK, GREYLIST_FALLBACK

        return blacklist, greylist


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

    # If entities table had no FATF data (e.g. no network in CI), use hardcoded fallback
    count = conn.execute("SELECT COUNT(*) FROM fatf_countries").fetchone()[0]
    if count == 0:
        for code, name in BLACKLIST_FALLBACK.items():
            conn.execute(
                "INSERT OR REPLACE INTO fatf_countries (country_code, country_name, list_type) VALUES (?, ?, ?)",
                (code, name, "blacklist")
            )
        for code, name in GREYLIST_FALLBACK.items():
            conn.execute(
                "INSERT OR REPLACE INTO fatf_countries (country_code, country_name, list_type) VALUES (?, ?, ?)",
                (code, name, "greylist")
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
