"""UAE PASS (UAE's national digital-identity OIDC provider) adapter boundary.

Mirrors the `amlkit/ingest/base.py` adapter-boundary style: pure functions and
dataclasses, no database access, no FastAPI imports. Routes in `api/app.py`
call into this module and are the only place that touches `auth.py`/`db.py`.

Two consumers, both built on the same OIDC authorization-code flow:

1. Operator/MLRO SSO ("Sign in with UAE PASS") -- an additional login method
   alongside email+password.
2. Customer identity verification during CDD onboarding -- UAE PASS's
   verified attributes (Emirates ID number, legal name, nationality, mobile,
   email) as stronger evidence than the OCR passport/Emirates-ID-scan
   fallback in `cases/ocr.py`.

Staging only, for now. The organisation has not yet completed UAE PASS's
formal Service Provider onboarding, so this targets
https://stg-id.uaepass.ae with UAE PASS's own published POC sandbox
credentials (`sandbox_stage` / `sandbox_stage`) as the credentials a deployer
would set via UAEPASS_CLIENT_ID/UAEPASS_CLIENT_SECRET -- NOT a hardcoded
default: `load_config()` returns `None`, and the whole feature stays inert,
until those env vars are actually set. Swapping to real staging/production
credentials later is a config change, not a code change (see UAEPASS_ENV).

ACR level: UAE PASS's own published docs (docs.uaepass.ae, both the POC
quick-start guide and the web-application authorization-code guide) document
only `urn:safelayer:tws:policies:authentication:level:low` for the sandbox/
POC flow; a `level:high` urn is referenced in passing by third-party
integration write-ups but is not documented end-to-end by UAE PASS itself for
the sandbox credentials this integration uses. Per that uncertainty, both the
operator-SSO and customer-verification flows default to `level:low` here --
see ACR_LEVEL_DEFAULT below and the PR description for the explicit follow-up
to revisit this once the org has real staging credentials and can confirm a
stronger ACR value directly with the UAE PASS team.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------- endpoints
_STAGING_BASE = "https://stg-id.uaepass.ae/idshub"
_PRODUCTION_BASE = "https://id.uaepass.ae/idshub"

# UAE PASS's own published POC sandbox credentials (staging only). These are
# NOT secret -- UAE PASS documents them for exactly this purpose -- but they
# are deliberately not wired in as a silent default anywhere in this module:
# load_config() returns None unless UAEPASS_CLIENT_ID/UAEPASS_CLIENT_SECRET
# are actually set in the environment, so a bare deploy with nothing
# configured shows no "Sign in with UAE PASS" button and 404s the routes
# rather than quietly talking to the sandbox. Kept here only as a documented
# constant a deployer can copy into their own env for a manual staging test.
SANDBOX_CLIENT_ID = "sandbox_stage"
SANDBOX_CLIENT_SECRET = "sandbox_stage"

# See the module docstring's "ACR level" section for why this is "low" for
# both the operator-SSO and customer-verification flows, for now.
ACR_LEVEL_DEFAULT = "urn:safelayer:tws:policies:authentication:level:low"

# UAE PASS's own request/response field naming (snake_case mixed with
# camelCase, e.g. `idn`, `nationalityEN`) is kept verbatim in this module
# rather than translated to a house style, so the field list stays easy to
# cross-reference against UAE PASS's own docs and sample responses.
_SCOPE = "urn:uae:digitalid:profile:general"


@dataclass(slots=True, frozen=True)
class UaePassConfig:
    client_id: str
    client_secret: str
    environment: str  # "staging" | "production"
    authorize_url: str
    token_url: str
    userinfo_url: str
    logout_url: str


def load_config() -> UaePassConfig | None:
    """Build a UaePassConfig from the environment, or None if unconfigured.

    `None` is the inert state the rest of the feature keys off: no "Sign in
    with UAE PASS" button is rendered, and the routes that depend on this
    404 rather than 500 (see api/app.py) -- this entire integration is a
    config change away from being live, never a code change away from being
    silently half-on.
    """
    client_id = os.environ.get("UAEPASS_CLIENT_ID")
    client_secret = os.environ.get("UAEPASS_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    environment = (os.environ.get("UAEPASS_ENV") or "staging").strip().lower()
    base = _PRODUCTION_BASE if environment == "production" else _STAGING_BASE

    return UaePassConfig(
        client_id=client_id,
        client_secret=client_secret,
        environment=environment,
        authorize_url=f"{base}/authorize",
        token_url=f"{base}/token",
        userinfo_url=f"{base}/userinfo",
        logout_url=f"{base}/logout",
    )


class UaePassError(RuntimeError):
    """Raised when a UAE PASS call fails: non-200, or a 200 with a shape that
    doesn't carry what the caller needed (e.g. no access_token in the token
    response). Deliberately loud, same reasoning as ingest/base.py's
    AdapterError: a silently-half-working identity provider is worse than one
    that fails visibly."""


def build_authorize_url(config: UaePassConfig, *, state: str, redirect_uri: str, acr: str) -> str:
    """Build the UAE PASS `/authorize` redirect URL.

    The authorization code UAE PASS returns to redirect_uri is one-time-use
    and expires in 10 minutes (UAE PASS's own documented behaviour) -- callers
    must exchange it promptly via exchange_code().
    """
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "client_id": config.client_id,
        "scope": _SCOPE,
        "state": state,
        "redirect_uri": redirect_uri,
        "acr_values": acr,
    }
    return f"{config.authorize_url}?{urlencode(params)}"


def exchange_code(config: UaePassConfig, *, code: str, redirect_uri: str) -> dict[str, Any]:
    """POST the authorization code to UAE PASS's /token endpoint.

    redirect_uri must be byte-for-byte the same value sent to /authorize --
    this is an OAuth2 requirement, not a UAE-PASS-specific quirk. Raises
    UaePassError on a non-200 response or a 200 response missing
    access_token, rather than handing the caller a dict it then has to
    re-validate itself.
    """
    import httpx

    try:
        r = httpx.post(
            config.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            auth=(config.client_id, config.client_secret),
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise UaePassError(f"uaepass: token exchange request failed — {exc}") from exc

    if r.status_code != 200:
        raise UaePassError(
            f"uaepass: token exchange returned HTTP {r.status_code}"
        )

    try:
        payload = r.json()
    except ValueError as exc:
        raise UaePassError("uaepass: token exchange returned non-JSON body") from exc

    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise UaePassError("uaepass: token exchange response had no access_token")

    return payload


@dataclass(slots=True)
class UaePassProfile:
    """UAE PASS's /userinfo claims, defensively parsed.

    Field names come from a third-party summary of UAE PASS's sample
    response, not a primary PDF spec (see module docstring), so every field
    below is read with `.get()` and nothing assumes a key exists. `raw` keeps
    the full, unmodified response so a shape this parser didn't anticipate
    can still be inspected later rather than silently dropped.
    """

    sub: str | None
    uuid: str | None
    idn: str | None                 # Emirates ID number (15 digits)
    fullname_en: str | None
    fullname_ar: str | None
    firstname_en: str | None
    lastname_en: str | None
    gender: str | None
    mobile: str | None
    email: str | None
    nationality_en: str | None      # ISO-3166-1 ALPHA-3 (e.g. "ARE"), not alpha-2
    nationality_ar: str | None
    # Account assurance level: SOP1 (weakest/self-registered), SOP2
    # (bank/telco-verified), SOP3 (strongest/ICA-biometric-verified). Kept
    # verbatim -- for CDD purposes a customer's assurance level is itself
    # evidence, not metadata to discard.
    user_type: str | None
    raw: dict[str, Any] = field(default_factory=dict)


def _parse_userinfo(payload: dict[str, Any]) -> UaePassProfile:
    get = payload.get
    return UaePassProfile(
        sub=get("sub"),
        uuid=get("uuid"),
        idn=get("idn"),
        fullname_en=get("fullnameEN"),
        fullname_ar=get("fullnameAR"),
        firstname_en=get("firstnameEN"),
        lastname_en=get("lastnameEN"),
        gender=get("gender"),
        mobile=get("mobile"),
        email=get("email"),
        nationality_en=get("nationalityEN"),
        nationality_ar=get("nationalityAR"),
        user_type=get("userType"),
        raw=payload,
    )


def fetch_userinfo(config: UaePassConfig, access_token: str) -> UaePassProfile:
    """GET UAE PASS's /userinfo endpoint and parse the claims.

    Raises UaePassError on non-200 or a non-JSON / non-dict body -- the same
    fail-loud contract as exchange_code(). A shape that IS a dict but missing
    expected keys does NOT raise: that is exactly what the defensive
    `.get()`-based parsing in _parse_userinfo is for, with `raw` preserving
    whatever was actually returned for later inspection.
    """
    import httpx

    try:
        r = httpx.get(
            config.userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise UaePassError(f"uaepass: userinfo request failed — {exc}") from exc

    if r.status_code != 200:
        raise UaePassError(f"uaepass: userinfo returned HTTP {r.status_code}")

    try:
        payload = r.json()
    except ValueError as exc:
        raise UaePassError("uaepass: userinfo returned non-JSON body") from exc

    if not isinstance(payload, dict):
        raise UaePassError("uaepass: userinfo response was not a JSON object")

    return _parse_userinfo(payload)


# --------------------------------------------------------- CDD field mapping
# amlkit.datamodel.COUNTRY_CODES is alpha-2 (CLDR/ISO 3166-1), validated by
# validate_country_code() which RAISES on a 3-letter code. UAE PASS's
# nationalityEN is alpha-3. datamodel.py carries no alpha-3 table at all (the
# COUNTRY_CODES set is alpha-2 only), so this is a small, UAE-PASS-specific
# lookup scoped to this module rather than guessing at an undocumented
# mapping silently. Only entries needed to cover amlkit.datamodel.COUNTRY_CODES
# are included; an unmapped/unrecognised alpha-3 code is left as-is by
# alpha3_to_alpha2() (returned unchanged) so the caller's own
# validate_country_code() raises a clear, visible error instead of this
# module silently inventing a guess.
ALPHA3_TO_ALPHA2: dict[str, str] = {
    "AND": "AD", "ARE": "AE", "AFG": "AF", "ATG": "AG", "ALB": "AL", "ARM": "AM",
    "AGO": "AO", "ARG": "AR", "AUT": "AT", "AUS": "AU", "AZE": "AZ", "BIH": "BA",
    "BRB": "BB", "BGD": "BD", "BEL": "BE", "BFA": "BF", "BGR": "BG", "BHR": "BH",
    "BDI": "BI", "BEN": "BJ", "BRN": "BN", "BOL": "BO", "BRA": "BR", "BHS": "BS",
    "BTN": "BT", "BWA": "BW", "BLR": "BY", "BLZ": "BZ", "CAN": "CA", "COD": "CD",
    "CAF": "CF", "COG": "CG", "CHE": "CH", "CIV": "CI", "CHL": "CL", "CMR": "CM",
    "CHN": "CN", "COL": "CO", "CRI": "CR", "CUB": "CU", "CPV": "CV", "CYP": "CY",
    "CZE": "CZ", "DEU": "DE", "DJI": "DJ", "DNK": "DK", "DMA": "DM", "DOM": "DO",
    "DZA": "DZ", "ECU": "EC", "EST": "EE", "EGY": "EG", "ERI": "ER", "ESP": "ES",
    "ETH": "ET", "FIN": "FI", "FJI": "FJ", "FSM": "FM", "FRA": "FR", "GAB": "GA",
    "GBR": "GB", "GRD": "GD", "GEO": "GE", "GHA": "GH", "GMB": "GM", "GIN": "GN",
    "GNQ": "GQ", "GRC": "GR", "GTM": "GT", "GNB": "GW", "GUY": "GY", "HND": "HN",
    "HRV": "HR", "HTI": "HT", "HUN": "HU", "IDN": "ID", "IRL": "IE", "ISR": "IL",
    "IND": "IN", "IRQ": "IQ", "IRN": "IR", "ISL": "IS", "ITA": "IT", "JAM": "JM",
    "JOR": "JO", "JPN": "JP", "KEN": "KE", "KGZ": "KG", "KHM": "KH", "KIR": "KI",
    "COM": "KM", "KNA": "KN", "PRK": "KP", "KOR": "KR", "KWT": "KW", "KAZ": "KZ",
    "LAO": "LA", "LBN": "LB", "LCA": "LC", "LIE": "LI", "LKA": "LK", "LBR": "LR",
    "LSO": "LS", "LTU": "LT", "LUX": "LU", "LVA": "LV", "LBY": "LY", "MAR": "MA",
    "MCO": "MC", "MDA": "MD", "MNE": "ME", "MDG": "MG", "MHL": "MH", "MKD": "MK",
    "MLI": "ML", "MMR": "MM", "MNG": "MN", "MRT": "MR", "MLT": "MT", "MUS": "MU",
    "MDV": "MV", "MWI": "MW", "MEX": "MX", "MYS": "MY", "MOZ": "MZ", "NAM": "NA",
    "NER": "NE", "NGA": "NG", "NIC": "NI", "NLD": "NL", "NOR": "NO", "NPL": "NP",
    "NRU": "NR", "NZL": "NZ", "OMN": "OM", "PAN": "PA", "PER": "PE", "PNG": "PG",
    "PHL": "PH", "PAK": "PK", "POL": "PL", "PRT": "PT", "PLW": "PW", "PRY": "PY",
    "QAT": "QA", "ROU": "RO", "SRB": "RS", "RUS": "RU", "RWA": "RW", "SAU": "SA",
    "SLB": "SB", "SYC": "SC", "SDN": "SD", "SWE": "SE", "SGP": "SG", "SVN": "SI",
    "SVK": "SK", "SLE": "SL", "SMR": "SM", "SEN": "SN", "SOM": "SO", "SUR": "SR",
    "SSD": "SS", "STP": "ST", "SLV": "SV", "SYR": "SY", "SWZ": "SZ", "TCD": "TD",
    "TGO": "TG", "THA": "TH", "TJK": "TJ", "TLS": "TL", "TKM": "TM", "TUN": "TN",
    "TON": "TO", "TUR": "TR", "TTO": "TT", "TUV": "TV", "TZA": "TZ", "UKR": "UA",
    "UGA": "UG", "USA": "US", "URY": "UY", "UZB": "UZ", "VAT": "VA", "VCT": "VC",
    "VEN": "VE", "VNM": "VN", "VUT": "VU", "WSM": "WS", "YEM": "YE", "ZAF": "ZA",
    "ZMB": "ZM", "ZWE": "ZW",
}


def alpha3_to_alpha2(code: str | None) -> str | None:
    """Map an ISO-3166-1 alpha-3 code (e.g. UAE PASS's `nationalityEN`) to
    alpha-2. Returns the input unchanged (not None) when it isn't a
    recognised alpha-3 code -- including when it already looks like alpha-2 --
    so that `datamodel.validate_country_code()` is the single place that
    raises on an invalid value, instead of this function silently
    swallowing an unrecognised code into None.
    """
    if not code:
        return code
    normalized = code.strip().upper()
    return ALPHA3_TO_ALPHA2.get(normalized, normalized)


# UAE PASS's "Male"/"Female" (see sample userinfo response) mapped to the
# values amlkit's own onboarding form/select uses (see
# web/templates/customer_new.html's <select name="gender">), which are
# lower-case "male"/"female" -- not UAE PASS's capitalisation.
_GENDER_MAP: dict[str, str] = {"male": "male", "female": "female"}


def normalize_gender(value: str | None) -> str | None:
    if not value:
        return None
    return _GENDER_MAP.get(value.strip().lower())


# cases/ocr.py's extract_emirates_id_data() sets id_type="emirates_id" for an
# OCR'd Emirates ID scan; UAE PASS's idn is the same identifier captured a
# stronger way, so it is tagged with the same id_type string rather than a
# new one, keeping the two IDV paths collapsible on a shared field.
EMIRATES_ID_TYPE = "emirates_id"
