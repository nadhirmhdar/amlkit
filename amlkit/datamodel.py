"""Google AML AI data model alignment: region codes and validation.

CLDR/ISO 3166-1 alpha-2 country code validation, UAE emirate subregion
validation, and helper functions for multi-nationality handling.
"""

from __future__ import annotations

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
