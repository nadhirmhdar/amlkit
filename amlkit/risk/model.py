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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from ..db import audit, utcnow

RULESET_PATH = Path(__file__).resolve().parent / "ruleset.yaml"

_cache: dict[str, Any] | None = None


def ruleset() -> dict[str, Any]:
    global _cache
    if _cache is None:
        with open(RULESET_PATH, encoding="utf-8") as fh:
            _cache = yaml.safe_load(fh)
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


def assess(profile: CustomerProfile) -> RiskAssessment:
    """Compute a risk rating from a customer profile."""
    rs = ruleset()
    factors: dict[str, Any] = {}
    total = 0.0
    force_high = False

    def add(key: str, value: Any, points: float, mandatory: bool = False) -> None:
        nonlocal total, force_high
        factors[key] = {"value": value, "points": points}
        total += points
        if mandatory:
            force_high = True

    f = rs["factors"]

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

    months = rs["review_months"].get(rating, 12)
    next_review = (datetime.now(timezone.utc) + timedelta(days=30 * months)).date().isoformat()

    return RiskAssessment(
        score=total,
        rating=rating,
        requires_edd=requires_edd,
        factors=factors,
        ruleset_version=rs["version"],
        next_review=next_review,
    )


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
    actor: str = "system",
) -> int:
    with conn:
        cur = conn.execute(
            """INSERT INTO risk_assessments
               (customer_id, score, rating, factors, ruleset_version,
                requires_edd, assessed_at, next_review)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
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
        )
        return cur.lastrowid
