"""Customer risk rating.

Implements the risk-based approach required by Cabinet Resolution No. 134 of
2025. The rules themselves live in `ruleset.yaml` so that changes are dated,
reviewable documents rather than code diffs -- a supervisor asking why a
customer's rating changed between two dates needs an answer with a version on
it.

Every assessment records the ruleset version and the per-factor contribution
that produced the rating. A rating without its reasoning is not evidence.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from ..db import audit, utcnow

RULESET_PATH = Path(__file__).resolve().parent / "ruleset.yaml"

_cache: dict[str, Any] | None = None
_cache_mtime: float | None = None


def ruleset() -> dict[str, Any]:
    """Load `ruleset.yaml`, reloading it whenever the file changes on disk.

    Cached by mtime rather than loaded once per process: a compliance officer
    editing the ruleset on a long-lived instance (a warm Cloud Run container,
    a machine left running) must see the new rules on the next assessment,
    not only after a process restart.
    """
    global _cache, _cache_mtime
    mtime = RULESET_PATH.stat().st_mtime
    if _cache is None or mtime != _cache_mtime:
        with open(RULESET_PATH, encoding="utf-8") as fh:
            _cache = yaml.safe_load(fh)
        _cache_mtime = mtime
    return _cache


@dataclass(slots=True)
class RiskAssessment:
    score: float
    rating: str
    requires_edd: bool
    factors: dict[str, Any] = field(default_factory=dict)
    ruleset_version: str = ""
    next_review: str | None = None

    def explain(self) -> str:
        lines = [f"Risk rating: {self.rating.upper()}  (score {self.score:.0f})"]
        for name, info in self.factors.items():
            if info.get("points"):
                lines.append(f"  +{info['points']:>3}  {name}: {info.get('value')}")
        if self.requires_edd:
            lines.append("  -> Enhanced Due Diligence required")
        return "\n".join(lines)


@dataclass(slots=True)
class CustomerProfile:
    """Inputs to the risk model. All optional -- an incomplete profile is
    itself informative, and missing UBO data scores as opacity rather than
    being silently skipped."""

    pep_status: str | None = None            # foreign_pep | domestic_pep | rca | ...
    jurisdiction_tier: str = "standard"
    sector: str = "other"
    ownership_state: str = "fully_transparent"
    delivery_channel: str = "face_to_face"
    cash_level: str = "non_cash"
    adverse_media: str = "none"
    structure: str = "natural_person"
    sanctions_hit: bool = False


_ALLOWED_FACTOR_VALUES = (
    # (argument name, ruleset factor, points table)
    ("jurisdiction_tier", "jurisdiction", "points_by_tier"),
    ("delivery_channel", "delivery_channel", "points_by_channel"),
    ("cash_level", "cash_intensity", "points_by_level"),
    ("structure", "structure", "points_by_type"),
    ("sector", "sector", "points_by_sector"),
)


def validate_risk_inputs(
    *,
    jurisdiction_tier: str | None = None,
    delivery_channel: str | None = None,
    cash_level: str | None = None,
    structure: str | None = None,
    sector: str | None = None,
) -> None:
    """Raise ValueError for any risk-factor value the ruleset doesn't know.

    Unknown values would otherwise score 0 points (lowest risk; 5 for an
    unknown sector) via the points-table lookups in assess(). None means "not supplied" and is
    skipped, so callers can validate just the overrides they were given.
    Call this at input boundaries, before anything is written.
    """
    values = {
        "jurisdiction_tier": jurisdiction_tier,
        "delivery_channel": delivery_channel,
        "cash_level": cash_level,
        "structure": structure,
        "sector": sector,
    }
    factors = ruleset()["factors"]
    for arg, factor, table in _ALLOWED_FACTOR_VALUES:
        value = values[arg]
        if value is None:
            continue
        allowed = factors[factor][table].keys()
        if value not in allowed:
            raise ValueError(
                f"Invalid {arg}: {value!r}. Must be one of: {', '.join(allowed)}"
            )


def assess(profile: CustomerProfile) -> RiskAssessment:
    """Compute a risk rating from a customer profile."""
    rs = ruleset()
    f = rs["factors"]

    # Backstop for values that bypassed the input boundaries (e.g. factors
    # carried forward from an older assessment): never score them as 0.
    validate_risk_inputs(
        jurisdiction_tier=profile.jurisdiction_tier,
        delivery_channel=profile.delivery_channel,
        cash_level=profile.cash_level,
        structure=profile.structure,
    )

    factors: dict[str, Any] = {}
    total = 0.0
    force_high = False

    def add(key: str, value: Any, points: float, mandatory: bool = False) -> None:
        nonlocal total, force_high
        factors[key] = {"value": value, "points": points}
        total += points
        if mandatory:
            force_high = True

    if profile.sanctions_hit:
        spec = f["sanctions_hit"]
        add("sanctions_hit", True, spec["points"], spec.get("mandatory_high", False))

    if profile.pep_status:
        spec = f["pep"]
        pts = spec.get("values", {}).get(profile.pep_status, spec["points"])
        add("pep", profile.pep_status, pts)

    spec = f["jurisdiction"]
    tier = profile.jurisdiction_tier
    add(
        "jurisdiction",
        tier,
        spec["points_by_tier"].get(tier, 0),
        tier in spec.get("mandatory_high_tiers", []),
    )

    add("sector", profile.sector,
        f["sector"]["points_by_sector"].get(profile.sector, 5))
    add("ownership_opacity", profile.ownership_state,
        f["ownership_opacity"]["points_by_state"].get(profile.ownership_state, 0))
    add("delivery_channel", profile.delivery_channel,
        f["delivery_channel"]["points_by_channel"].get(profile.delivery_channel, 0))
    add("cash_intensity", profile.cash_level,
        f["cash_intensity"]["points_by_level"].get(profile.cash_level, 0))
    add("adverse_media", profile.adverse_media,
        f["adverse_media"]["points_by_severity"].get(profile.adverse_media, 0))
    add("structure", profile.structure,
        f["structure"]["points_by_type"].get(profile.structure, 0))

    rating = "high" if force_high else _band(total, rs["bands"])

    triggers = set(rs.get("edd_triggers", []))
    requires_edd = (
        rating == "high"
        or ("pep" in triggers and bool(profile.pep_status))
        or ("sanctions_hit" in triggers and profile.sanctions_hit)
        or (
            "high_risk_jurisdiction" in triggers
            and profile.jurisdiction_tier in ("fatf_blacklist", "fatf_greylist")
        )
    )

    # The initial review date, set at onboarding. Later re-assessments carry
    # it forward (see `save(carry_next_review=...)`); only a completed
    # periodic review sets a new one (cases.manager.complete_periodic_review).
    next_review = review_date_for(rating)

    return RiskAssessment(
        score=total,
        rating=rating,
        requires_edd=requires_edd,
        factors=factors,
        ruleset_version=rs["version"],
        next_review=next_review,
    )


def review_date_for(rating: str, today: date | None = None) -> str:
    """Date the next periodic CDD review falls due for a customer of `rating`,
    from the `review_months` interval in ruleset.yaml."""
    months = ruleset()["review_months"].get(rating, 12)
    start = today or datetime.now(timezone.utc).date()
    return (start + timedelta(days=30 * months)).isoformat()


def _band(score: float, bands: dict[str, dict[str, int]]) -> str:
    for name in ("high", "medium", "low"):
        b = bands.get(name)
        if b and b["min"] <= score <= b["max"]:
            return name
    return "high"  # fail safe: unknown score is treated as high, never low


def save(
    conn: sqlite3.Connection,
    customer_id: int,
    assessment: RiskAssessment,
    org_id: int,
    actor: str = "system",
    carry_next_review: bool = False,
) -> int:
    """Persist an assessment.

    `carry_next_review=True` is for event-driven re-assessments (transaction
    alert, adverse media, rescreen, factor correction): the new row keeps the
    customer's previous `next_review` rather than the freshly computed one, so
    an unrelated event can never clear an overdue periodic review.
    """
    with conn:
        if carry_next_review:
            prior = conn.execute(
                "SELECT next_review FROM risk_assessments"
                " WHERE customer_id=? AND org_id=? ORDER BY id DESC LIMIT 1",
                (customer_id, org_id),
            ).fetchone()
            if prior is not None and prior["next_review"]:
                # Mutated in place so the caller's copy matches the saved row.
                assessment.next_review = prior["next_review"]
        cur = conn.execute(
            """INSERT INTO risk_assessments
               (org_id, customer_id, score, rating, factors, ruleset_version,
                requires_edd, assessed_at, next_review)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                org_id,
                customer_id,
                assessment.score,
                assessment.rating,
                json.dumps(assessment.factors, ensure_ascii=False),
                assessment.ruleset_version,
                int(assessment.requires_edd),
                utcnow(),
                assessment.next_review,
            ),
        )
        audit(
            conn,
            actor=actor,
            action="risk.assess",
            object_type="customer",
            object_id=customer_id,
            detail={
                "rating": assessment.rating,
                "score": assessment.score,
                "ruleset": assessment.ruleset_version,
                "edd": assessment.requires_edd,
            },
            org_id=org_id,
        )
        return cur.lastrowid
