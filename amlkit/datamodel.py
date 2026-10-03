"""Google AML AI data model alignment.

Pure mapping/validation functions from amlkit's internal values to Google's
enum names, plus CLDR/ISO 3166-1 alpha-2 country code validation, UAE emirate
subregion validation, and helper functions for multi-nationality handling.
No database access, no side effects — only validation and string mapping.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

COUNTRY_CODES: frozenset[str] = frozenset({
    "AD", "AE", "AF", "AG", "AL", "AM", "AO", "AR", "AT", "AU",
    "AZ", "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI", "BJ",
    "BN", "BO", "BR", "BS", "BT", "BW", "BY", "BZ", "CA", "CD",
    "CF", "CG", "CH", "CI", "CL", "CM", "CN", "CO", "CR", "CU",
    "CV", "CY", "CZ", "DE", "DJ", "DK", "DM", "DO", "DZ", "EC",
    "EE", "EG", "ER", "ES", "ET", "FI", "FJ", "FM", "FR", "GA",
    "GB", "GD", "GE", "GH", "GM", "GN", "GQ", "GR", "GT", "GW",
    "GY", "HN", "HR", "HT", "HU", "ID", "IE", "IL", "IN", "IQ",
    "IR", "IS", "IT", "JM", "JO", "JP", "KE", "KG", "KH", "KI",
    "KM", "KN", "KP", "KR", "KW", "KZ", "LA", "LB", "LC", "LI",
    "LK", "LR", "LS", "LT", "LU", "LV", "LY", "MA", "MC", "MD",
    "ME", "MG", "MH", "MK", "ML", "MM", "MN", "MR", "MT", "MU",
    "MV", "MW", "MX", "MY", "MZ", "NA", "NE", "NG", "NI", "NL",
    "NO", "NP", "NR", "NZ", "OM", "PA", "PE", "PG", "PH", "PK",
    "PL", "PT", "PW", "PY", "QA", "RO", "RS", "RU", "RW", "SA",
    "SB", "SC", "SD", "SE", "SG", "SI", "SK", "SL", "SM", "SN",
    "SO", "SR", "SS", "ST", "SV", "SY", "SZ", "TD", "TG", "TH",
    "TJ", "TL", "TM", "TN", "TO", "TR", "TT", "TV", "TZ", "UA",
    "UG", "US", "UY", "UZ", "VA", "VC", "VE", "VN", "VU", "WS",
    "YE", "ZA", "ZM", "ZW",
})

UAE_EMIRATES: frozenset[str] = frozenset({
    "ABU_DHABI", "DUBAI", "SHARJAH", "AJMAN",
    "UMM_AL_QUWAIN", "RAS_AL_KHAIMAH", "FUJAIRAH",
})


def validate_country_code(code: str | None) -> None:
    if not code:
        return
    normalized = code.strip().upper()
    if normalized not in COUNTRY_CODES:
        raise ValueError(
            f"Invalid country code {code!r}; expected a two-letter CLDR/ISO 3166-1 code"
        )


def validate_emirate(emirate: str | None) -> None:
    if not emirate:
        return
    if emirate not in UAE_EMIRATES:
        raise ValueError(
            f"Invalid emirate {emirate!r}; expected one of {sorted(UAE_EMIRATES)}"
        )


_CUSTOMER_TYPE_MAP: dict[str, str] = {
    "natural": "CONSUMER",
    "legal": "COMPANY",
}

_DIRECTION_MAP: dict[str, str] = {
    "outbound": "DEBIT",
    "inbound": "CREDIT",
}

_METHOD_MAP: dict[str, str] = {
    "wire": "WIRE",
    "cash": "CASH",
    "cheque": "CHECK",
    "card": "CARD",
    "crypto": "CRYPTO",
    "other": "OTHER",
}

VALID_METHODS: frozenset[str] = frozenset(_METHOD_MAP.keys())

CIVIL_STATUS_CODES: frozenset[str] = frozenset({
    "SING",  # Single
    "MARR",  # Married
    "DIVR",  # Divorced
    "WIDW",  # Widowed
    "SEPR",  # Separated
    "UNKNOWN",
})

MAX_OCCUPATION_LENGTH = 200

# Customer names (full_name / name_arabic). Generous for long legal-entity
# names and multi-part Arabic names, but bounds what a hand-crafted POST can
# store and feed into screening.
MAX_NAME_LENGTH = 200

# Strict YYYY-MM-DD: date.fromisoformat alone (3.11+) also takes "20200101"
# and ISO week dates like "2020-W01-1".
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# "Today" for date checks is the UAE calendar date (UTC+4, no DST): the
# server runs in UTC, so for four hours after midnight in Dubai date.today()
# would still be yesterday and reject a date the user sees as today.
_UAE_TZ = timezone(timedelta(hours=4))


def map_customer_type(customer_type: str) -> str:
    key = customer_type.lower()
    if key not in _CUSTOMER_TYPE_MAP:
        raise ValueError(
            f"Unknown customer_type {customer_type!r}; expected 'natural' or 'legal'"
        )
    return _CUSTOMER_TYPE_MAP[key]


def map_direction(direction: str) -> str:
    key = direction.lower()
    if key not in _DIRECTION_MAP:
        raise ValueError(
            f"Unknown direction {direction!r}; expected 'inbound' or 'outbound'"
        )
    return _DIRECTION_MAP[key]


def map_transaction_method(method: str) -> str:
    key = method.lower()
    if key not in _METHOD_MAP:
        raise ValueError(
            f"Unknown method {method!r}; expected one of {sorted(_METHOD_MAP)}"
        )
    return _METHOD_MAP[key]


def validate_civil_status(code: str | None) -> None:
    if not code:
        return
    if code not in CIVIL_STATUS_CODES:
        raise ValueError(
            f"Invalid civil_status_code {code!r}; expected one of {sorted(CIVIL_STATUS_CODES)}"
        )


def validate_occupation(occupation: str | None) -> None:
    if not occupation:
        return
    if len(occupation) > MAX_OCCUPATION_LENGTH:
        raise ValueError(
            f"occupation exceeds {MAX_OCCUPATION_LENGTH} characters"
        )


def validate_customer_type(customer_type: str) -> None:
    # Exact match (no lower()): the stored value drives natural-vs-legal
    # branching elsewhere, so 'Natural' must not slip in as a third type.
    if customer_type not in _CUSTOMER_TYPE_MAP:
        raise ValueError(
            f"Unknown customer_type {customer_type!r}; expected 'natural' or 'legal'"
        )


def validate_name_length(field: str, value: str | None) -> None:
    if value and len(value) > MAX_NAME_LENGTH:
        raise ValueError(f"{field} exceeds {MAX_NAME_LENGTH} characters")


def validate_birth_date(birth_date: str | None) -> None:
    """Empty is allowed; otherwise a real YYYY-MM-DD date not in the future."""
    if not birth_date:
        return
    try:
        if not _ISO_DATE_RE.match(birth_date):
            raise ValueError
        parsed = date.fromisoformat(birth_date)
    except ValueError:
        raise ValueError(
            f"Invalid birth_date {birth_date!r}; expected a date as YYYY-MM-DD"
        ) from None
    if parsed > datetime.now(_UAE_TZ).date():
        raise ValueError("birth_date cannot be in the future")
