"""Match scoring.

Feature weights follow the OpenSanctions `logic-v2` model, which is publicly
documented and well tested against real sanctions data. Adopting a proven
weighting is better practice than inventing one: these numbers encode a lot of
accumulated experience about what actually distinguishes two people.

What is added on top is the Arabic-aware name comparison in `names.arabic`,
which is where generic screening engines are weakest and where UAE screening
needs the most help.

Every score carries a full per-feature breakdown. An examiner asking "why did
this alert fire?" -- or a compliance officer tuning thresholds -- must be able
to see the arithmetic, not just the verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rapidfuzz.distance import JaroWinkler

from ..names.arabic import canonical_tokens

# --- feature weights (OpenSanctions logic-v2) ------------------------------
W_IDENTIFIER_MATCH = 0.95   # exact LEI/BIC/passport/tax hit
P_COUNTRY_MISMATCH = -0.20
P_DOB_DAY_MISMATCH = -0.25
P_DOB_YEAR_MISMATCH = -0.15
P_GENDER_MISMATCH = -0.20

# Family names carry more discriminating power than given names -- "Mohammed"
# is near-noise in this market, "Al Maktoum" is not.
FAMILY_NAME_WEIGHT = 1.3

# Below this, two tokens are treated as unrelated rather than weakly similar.
FUZZY_CUTOFF = 0.82

# Share of the name score attributable to recall alone. The remainder scales
# with precision (how much of the listed name the query accounts for). See the
# calibration note in `name_score`.
PRECISION_FLOOR = 0.60

# Default alert threshold. Tuned in tests/test_matching.py against a golden set
# plus a false-positive suite; changing it should mean re-running those.
DEFAULT_THRESHOLD = 0.85


@dataclass(slots=True)
class ScoreResult:
    score: float
    name_score: float
    matched_name: str
    features: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "name_score": round(self.name_score, 4),
            "matched_name": self.matched_name,
            "features": self.features,
        }


def token_similarity(a: str, b: str) -> float:
    """Similarity between two already-canonicalised name tokens."""
    if a == b:
        return 1.0
    # Canonicalisation has already folded transliteration variants together,
    # so what remains is genuine spelling drift -- Jaro-Winkler handles that
    # well and rewards shared prefixes, which suits names.
    return JaroWinkler.similarity(a, b)


def name_score(query: str, candidate: str) -> tuple[float, dict[str, Any]]:
    """Compare two full names. Returns (score, detail).

    Combines recall (how much of the query is present in the candidate) with
    precision (how much of the candidate is accounted for by the query),
    weighted towards recall. Recall-only scoring makes a single-token query
    match every long name containing it; precision-only punishes legitimate
    partial names. The blend below keeps "Mohammed" from matching everything
    while letting "Mohammed Rashid" still reach a reviewable score against
    "Mohammed bin Rashid Al Maktoum".
    """
    qt = canonical_tokens(query)
    ct = canonical_tokens(candidate)
    if not qt or not ct:
        return 0.0, {"reason": "empty after canonicalisation"}

    if sorted(qt) == sorted(ct):
        return 1.0, {"exact_canonical": True, "tokens": len(qt)}

    weights = [FAMILY_NAME_WEIGHT if i == len(qt) - 1 else 1.0 for i in range(len(qt))]

    used: set[int] = set()
    earned = 0.0
    total = 0.0
    pairs: list[tuple[str, str, float]] = []

    for i, t in enumerate(qt):
        best, best_j = 0.0, None
        for j, u in enumerate(ct):
            if j in used:
                continue
            s = token_similarity(t, u)
            if s > best:
                best, best_j = s, j
        if best >= FUZZY_CUTOFF and best_j is not None:
            used.add(best_j)
            pairs.append((t, ct[best_j], round(best, 3)))
        else:
            best = 0.0
        earned += best * weights[i]
        total += weights[i]

    recall = earned / total if total else 0.0
    precision = len(used) / len(ct) if ct else 0.0

    # The precision weight is calibrated, not arbitrary. At 0.25 a one-token
    # query ("Mohammed") scored 0.875 against a two-token listed name and
    # cleared the 0.85 threshold -- a false-positive generator, since roughly
    # every third name in this market contains "Mohammed". At 0.40:
    #   precision 0.50 (1 of 2 tokens)  -> 0.80  no alert
    #   precision 0.67 (2 of 3 tokens)  -> 0.87  alert, correctly reviewable
    #   precision 1.00                  -> 1.00
    # Changing this constant requires re-running tests/test_matching.py.
    score = recall * (PRECISION_FLOOR + (1 - PRECISION_FLOOR) * precision)

    detail = {
        "recall": round(recall, 3),
        "precision": round(precision, 3),
        "query_tokens": qt,
        "candidate_tokens": ct,
        "matched_pairs": pairs,
    }
    # A single-token query is weak evidence whatever it scores. Surfaced so the
    # UI can warn the user rather than silently swallowing the ambiguity.
    if len(qt) < 2:
        detail["low_confidence_query"] = "single name token - screen with a full name"
    return score, detail


def _year(d: str | None) -> str | None:
    return d[:4] if d and len(d) >= 4 else None


def score_entity(
    query_name: str,
    candidate_names: list[str],
    *,
    query_country: str | None = None,
    query_countries: list[str] | None = None,
    query_birth_date: str | None = None,
    query_gender: str | None = None,
    query_identifiers: list[tuple[str, str]] | None = None,
    cand_countries: list[str] | None = None,
    cand_birth_date: str | None = None,
    cand_gender: str | None = None,
    cand_identifiers: list[tuple[str, str]] | None = None,
) -> ScoreResult:
    """Score a query against one candidate entity across all its aliases.

    Takes the best-scoring alias: sanctions entries routinely list the same
    person under several transliterations, and matching any one of them is a
    match on the person.
    """
    best_score, best_name, best_detail = 0.0, "", {}
    for cname in candidate_names:
        s, detail = name_score(query_name, cname)
        if s > best_score:
            best_score, best_name, best_detail = s, cname, detail

    features: dict[str, Any] = {"name": best_detail}
    score = best_score

    # --- identifiers: strongest available evidence -------------------------
    if query_identifiers and cand_identifiers:
        q_ids = {(k, v.strip().upper()) for k, v in query_identifiers if v}
        c_ids = {(k, v.strip().upper()) for k, v in cand_identifiers if v}
        shared = q_ids & c_ids
        if shared:
            # An exact identifier hit outweighs name similarity entirely -- a
            # matching passport number is not a coincidence.
            score = max(score, W_IDENTIFIER_MATCH)
            features["identifier_match"] = sorted(f"{k}:{v}" for k, v in shared)

    # --- contradicting features -------------------------------------------
    adjustments: dict[str, float] = {}

    all_countries = query_countries or ([query_country] if query_country else [])
    if all_countries and cand_countries:
        qc_set = {c.strip().lower() for c in all_countries if c}
        cc = {c.strip().lower() for c in cand_countries if c}
        if qc_set and cc and not (qc_set & cc):
            adjustments["country_mismatch"] = P_COUNTRY_MISMATCH

    if query_birth_date and cand_birth_date:
        if _year(query_birth_date) != _year(cand_birth_date):
            adjustments["dob_year_mismatch"] = P_DOB_YEAR_MISMATCH
        elif len(query_birth_date) >= 10 and len(cand_birth_date) >= 10:
            if query_birth_date[:10] != cand_birth_date[:10]:
                adjustments["dob_day_mismatch"] = P_DOB_DAY_MISMATCH

    if query_gender and cand_gender:
        if query_gender.strip().lower()[:1] != cand_gender.strip().lower()[:1]:
            adjustments["gender_mismatch"] = P_GENDER_MISMATCH

    if adjustments:
        features["adjustments"] = adjustments
        score += sum(adjustments.values())

    score = max(0.0, min(1.0, score))
    return ScoreResult(score=score, name_score=best_score, matched_name=best_name, features=features)
