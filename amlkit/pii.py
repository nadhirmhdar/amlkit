"""PII redaction for logs, exports, and optional Cloud DLP inspection.

ALWAYS-ON local redaction: regexes for Emirates ID (Luhn-validated to
cut false positives), passport numbers near a label, and emails. No
network calls, no dependencies beyond stdlib.

OPTIONAL Cloud DLP: behind AMLKIT_DLP_ENABLED=0 by default.
"""

from __future__ import annotations

import re

# Emirates ID: 784-YYYY-NNNNNNN-C (15 digits total, check digit is Luhn)
# With dashes: 784-YYYY-NNNNNNN-C
# Without dashes: 784YYYYNNNNNNNC
_EID_DASHED = re.compile(r"\b(784-\d{4}-\d{7}-\d)\b")
_EID_PLAIN = re.compile(r"\b(784\d{12})\b")

# Email: standard pattern
_EMAIL = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")

# Passport: alphanumeric 6-9 chars, but ONLY when preceded by "passport" label
_PASSPORT = re.compile(
    r"(?i)(?:passport\s*(?:number|no\.?|#)?[\s:]*)"
    r"([A-Z0-9]{6,9})\b",
    re.IGNORECASE,
)


def _luhn_check(num_str: str) -> bool:
    """Validate a numeric string using the Luhn algorithm."""
    if not num_str.isdigit() or len(num_str) < 5:
        return False
    digits = [int(d) for d in num_str]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _redact_eid(match: re.Match) -> str:
    """Replace an Emirates ID match only if it passes Luhn validation."""
    raw = match.group(1)
    digits = raw.replace("-", "")
    if len(digits) == 15 and _luhn_check(digits):
        return "[REDACTED-EID]"
    return raw


def redact(text: str | None) -> str:
    """Redact PII from a string.

    Applies three patterns in order:
    1. Emirates ID (784-YYYY-NNNNNNN-C) — Luhn-validated
    2. Email addresses
    3. Passport numbers adjacent to a "passport" label

    Returns the redacted string. None input returns empty string.
    """
    if text is None:
        return ""
    if not text:
        return text

    # Emirates ID with dashes
    text = _EID_DASHED.sub(_redact_eid, text)

    # Emirates ID without dashes
    text = _EID_PLAIN.sub(_redact_eid, text)

    # Emails
    text = _EMAIL.sub("[REDACTED-EMAIL]", text)

    # Passport numbers (only near "passport" label)
    text = _PASSPORT.sub(
        lambda m: m.group(0).replace(m.group(1), "[REDACTED-PASSPORT]"),
        text,
    )

    return text


# ---------------------------------------------------------------- Cloud DLP (optional)


def inspect_document(
    content: bytes,
    mime_type: str = "application/pdf",
) -> list[dict]:
    """Inspect a document for PII using Google Cloud DLP.

    Only runs when AMLKIT_DLP_ENABLED=1. Returns a list of finding dicts
    with keys: info_type, likelihood, quote (redacted).

    Fails closed: if the DLP API rejects the configured location, logs a
    warning and returns an empty list (does not fall back to global).
    """
    import logging
    import os

    log = logging.getLogger("amlkit.pii")

    if os.environ.get("AMLKIT_DLP_ENABLED", "0") != "1":
        return []

    location = os.environ.get("AMLKIT_DLP_LOCATION", "me-central1")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("AMLKIT_TASKS_PROJECT", "")

    if not project:
        log.warning("DLP enabled but no GCP project configured")
        return []

    try:
        from google.cloud import dlp_v2
    except ImportError:
        log.warning("google-cloud-dlp not installed; DLP inspection skipped")
        return []

    client = dlp_v2.DlpServiceClient()
    parent = f"projects/{project}/locations/{location}"

    inspect_config = {
        "info_types": [
            {"name": "EMAIL_ADDRESS"},
            {"name": "PASSPORT"},
            {"name": "PHONE_NUMBER"},
        ],
        "min_likelihood": "POSSIBLE",
        "include_quote": True,
    }

    item = {"byte_item": {"type_": mime_type, "data": content}}

    try:
        response = client.inspect_content(
            request={"parent": parent, "inspect_config": inspect_config, "item": item}
        )
    except Exception as exc:
        log.warning("Cloud DLP inspection failed (fail-closed): %s", exc)
        return []

    findings = []
    for finding in response.result.findings:
        findings.append({
            "info_type": finding.info_type.name,
            "likelihood": finding.likelihood.name,
            "quote": redact(finding.quote) if finding.quote else None,
        })

    return findings
