"""Quotation / access requests from the public /apply form.

An application is a lead, not an account: saving one creates no organization,
no operator and no access. It exists so a prospective firm can tell Grovisor
about itself and ask for a quotation. (Plans and payment will replace this
manual step later; the stored fields are the ones a quote needs.)

Pure validation plus one insert -- no web or mail concerns -- so routes stay
thin and the rules are testable on their own.

Known gaps (deliberately not built yet): applicant personal data (name, email,
phone) sits in the unscoped `applications` table with no retention period and
no admin screen to view or delete requests. Before launch, decide a retention
period under the UAE PDPL and add a viewer plus a delete/anonymise action.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from ..auth import looks_like_email
from ..db import utcnow

# Who will use groAML. This drives how a quotation is built: a consultant
# needs several isolated client workspaces, the others need one.
APPLICANT_TYPES = [
    ("Single entity", "One company or firm using groAML for its own compliance."),
    ("B2B consultant", "A consultancy or outsourced MLRO running compliance for several client firms."),
    ("Natural person", "An individual who holds a licence or trades in their own name, such as a sole proprietor."),
    ("Professional", "A licensed professional in independent practice, such as a lawyer, accountant or auditor."),
]
APPLICANT_TYPE_VALUES = [v for v, _ in APPLICANT_TYPES]
CONSULTANT = "B2B consultant"
# A natural person has no firm, so the form never asks for a firm name or a job
# title: their own name stands in for both. A professional may practise under a
# practice name, so for them the name is offered but optional.
NO_FIRM_TYPES = {"Natural person"}
NAME_OPTIONAL_TYPES = {"Professional"}
CLIENT_FIRMS = ["1-5", "6-20", "21-50", "More than 50"]

# What the applicant is, in the vocabulary of the UAE AML/CFT regime.
CATEGORIES = [
    "Real estate broker or agency",
    "Dealer in precious metals or stones",
    "Accountant or auditor",
    "Corporate service provider",
    "Law firm or notary",
    "Other designated non-financial business",
]
JURISDICTIONS = [
    "Abu Dhabi", "Dubai", "Sharjah", "Ajman", "Umm Al Quwain", "Ras Al Khaimah",
    "Fujairah", "DIFC", "ADGM", "Other free zone",
]
TEAM_SIZES = ["1", "2-5", "6-15", "16-50", "More than 50"]
CUSTOMERS_PER_YEAR = ["Fewer than 100", "100-500", "500-2,000", "More than 2,000"]
SCREENINGS_PER_MONTH = ["Not sure yet", "Fewer than 100", "100-500", "500-2,000", "More than 2,000"]
NEEDS = [
    "Sanctions and PEP screening",
    "Customer due diligence and onboarding",
    "Risk assessment",
    "Transaction monitoring",
    "goAML STR/SAR reporting",
    "Adverse media",
]

_PHONE = re.compile(r"^[0-9+()\-\s.]{5,40}$")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _one_line(value: str, limit: int) -> str:
    """Collapse to a single trimmed line: no CR/LF can reach an email header."""
    return re.sub(r"\s+", " ", _CTRL.sub("", value or "")).strip()[:limit]


def validate(form: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Return (clean values, errors keyed by field). Errors empty means valid."""
    errors: dict[str, str] = {}
    clean: dict[str, Any] = {
        "org_name": _one_line(form.get("org_name", ""), 120),
        "contact_name": _one_line(form.get("contact_name", ""), 120),
        "job_title": _one_line(form.get("job_title", ""), 120),
        "email": _one_line(form.get("email", ""), 254).lower(),
        "phone": _one_line(form.get("phone", ""), 40),
        # The message may be multi-line; only control characters are removed.
        "message": _CTRL.sub("", (form.get("message", "") or "").replace("\r\n", "\n")).strip()[:2000],
    }
    applicant_type = (form.get("applicant_type") or "").strip()
    clean["applicant_type"] = applicant_type
    if applicant_type not in APPLICANT_TYPE_VALUES:
        errors["applicant_type"] = "Choose who will use groAML."

    if not clean["contact_name"]:
        errors["contact_name"] = "Enter your name."
    if applicant_type in NO_FIRM_TYPES:
        # Ignore anything sent for a firm: the person is the applicant.
        clean["org_name"] = clean["contact_name"]
        clean["job_title"] = ""
    elif not clean["org_name"]:
        if applicant_type in NAME_OPTIONAL_TYPES:
            # The practice name is optional, so never error on it. Their own name
            # stands in; if that is missing too, the "Enter your name." error
            # on the contact field is the only message they need.
            clean["org_name"] = clean["contact_name"]
        else:
            errors["org_name"] = ("Enter your firm's name." if applicant_type != CONSULTANT
                                  else "Enter your consultancy's name.")

    # Only a consultant runs several client workspaces, so only they are asked.
    client_firms = (form.get("client_firms") or "").strip()
    if applicant_type == CONSULTANT:
        clean["client_firms"] = client_firms
        if client_firms not in CLIENT_FIRMS:
            errors["client_firms"] = "Choose how many client firms you would run."
    else:
        clean["client_firms"] = ""
    if not looks_like_email(clean["email"]):
        errors["email"] = "Enter a work email address we can reply to."
    if clean["phone"] and not _PHONE.match(clean["phone"]):
        errors["phone"] = "Enter a phone number using digits, spaces, + ( ) or -."

    for field, options, label in (
        ("category", CATEGORIES, "what kind of business you are"),
        ("jurisdiction", JURISDICTIONS, "where you are licensed"),
        ("team_size", TEAM_SIZES, "how many people will use it"),
        ("customers_per_year", CUSTOMERS_PER_YEAR, "how many customers you onboard in a year"),
    ):
        value = (form.get(field) or "").strip()
        clean[field] = value
        if value not in options:
            errors[field] = f"Choose {label}."
    shots = (form.get("screenings_per_month") or "").strip()
    clean["screenings_per_month"] = shots if shots in SCREENINGS_PER_MONTH else ""

    needs = form.get("needs") or []
    if isinstance(needs, str):
        needs = [needs]
    clean["needs"] = [n for n in NEEDS if n in needs]

    if not form.get("consent"):
        errors["consent"] = "Please tick the box so we know we may contact you about this request."
    return clean, errors


def save(conn: sqlite3.Connection, clean: dict[str, Any]) -> int:
    now = utcnow()
    cur = conn.execute(
        """INSERT INTO applications
           (created_at, applicant_type, client_firms, org_name, category, jurisdiction, contact_name, job_title, email, phone,
            team_size, customers_per_year, screenings_per_month, needs, message, consent_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (now, clean["applicant_type"], clean["client_firms"] or None, clean["org_name"], clean["category"], clean["jurisdiction"], clean["contact_name"],
         clean["job_title"] or None, clean["email"], clean["phone"] or None, clean["team_size"],
         clean["customers_per_year"], clean["screenings_per_month"] or None,
         json.dumps(clean["needs"]), clean["message"] or None, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def record_delivery(conn: sqlite3.Connection, application_id: int, outcome: str) -> None:
    conn.execute("UPDATE applications SET email_delivery=? WHERE id=?", (outcome, application_id))
    conn.commit()
