"""Google AML AI data model enum alignment.

Pure mapping functions from amlkit's internal values to Google's enum names.
No database access, no side effects — only validation and string mapping.
"""

from __future__ import annotations

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
