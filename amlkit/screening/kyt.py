"""Transaction monitoring (KYT) rule evaluation.

Scope is deliberately narrow: four rules that are standard, defensible, and
checkable from data this tool already asks a DNFBP to record, not a general
behavioral-analytics engine. Getting a small rule set right and explainable
beats a large one that produces alerts nobody can justify to an examiner --
the same trade this codebase makes everywhere else (see screening/pf.py).

Four-eyes review (cases/review.py) is deliberately NOT applied to
transaction_alerts. That machinery exists for sanctions/PF dispositions,
where UAE law places personal liability on getting the freeze-and-report
decision right. A large-cash or structuring flag is a prompt to look closer,
not a designation decision -- narrower in consequence, so narrower in review
burden. This is a stated scope choice, not an oversight.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

# AED 55,000 is the standard UAE DNFBP occasional-transaction CDD trigger
# (aligned with FATF's EUR/USD 15,000 benchmark). Single source of truth here
# rather than copied into the rule functions below. Compliance should confirm
# this against current FTA/EOCN guidance before relying on it for a real
# client file -- same posture as the legal disclaimer in the web footer.
LARGE_CASH_THRESHOLD_AED = 55_000.0

# Structuring: multiple cash transactions individually under the threshold
# that sum to meet or exceed it within this rolling window. 7 days is a
# starting point, not a regulatory figure -- deliberately configurable later
# if evidenced need arises, same "no complexity without evidenced need"
# posture as org_settings.alert_threshold.
STRUCTURING_WINDOW_DAYS = 7
STRUCTURING_MIN_COUNT = 2

# Velocity: an unusually high transaction count in a short window, independent
# of amount -- catches rapid movement that structuring (which requires
# near-threshold amounts) would miss.
VELOCITY_WINDOW_HOURS = 24
VELOCITY_MAX_COUNT = 5

# Illustrative, NOT authoritative. FATF's grey/black lists change; a real
# deployment must keep this current (the same "list currency" obligation
# already enforced for sanctions data via ingest/loader.py's staleness check)
# rather than trust a hardcoded set indefinitely. ISO-3166 alpha-2, upper-case.
HIGH_RISK_COUNTRIES: frozenset[str] = frozenset({
    "KP", "IR", "MM", "SY",              # FATF black list / heavily sanctioned
    "AF", "YE", "SS", "SD",              # unstable / high AML risk
})


@dataclass(slots=True)
class TriggeredRule:
    rule_key: str
    severity: str
    detail: dict[str, Any]

    def to_detail_json(self) -> str:
        return json.dumps(self.detail, ensure_ascii=False, default=str)


def evaluate_transaction(
    conn,
    *,
    org_id: int,
    customer_id: int,
    transaction_id: int,
    method: str,
    amount_aed: float,
    counterparty_country: str | None,
    occurred_at: str,
) -> list[TriggeredRule]:
    """Run every rule against one just-recorded transaction.

    Reads sibling transactions (structuring, velocity) from the database
    rather than requiring the caller to pass transaction history -- this is
    the one place that history is assembled, so a future rule can be added
    here without every call site having to learn what data it now needs.
    """
    # Load org-specific configuration (falls back to module defaults)
    config = get_rule_config(conn, org_id)
    large_cash_threshold = config["large_cash_threshold_aed"]
    structuring_window_days = config["structuring_window_days"]
    velocity_window_hours = config["velocity_window_hours"]
    velocity_max_count = config["velocity_max_count"]
    high_risk_countries = set(config["high_risk_countries"])
    # structuring_min_count is not org-configurable yet, use module constant
    structuring_min_count = STRUCTURING_MIN_COUNT

    triggered: list[TriggeredRule] = []

    if method == "cash" and amount_aed >= large_cash_threshold:
        triggered.append(TriggeredRule(
            rule_key="large_cash",
            severity="high",
            detail={
                "amount_aed": amount_aed,
                "threshold_aed": large_cash_threshold,
            },
        ))

    if method == "cash":
        window_start = (
            _parse(occurred_at) - timedelta(days=structuring_window_days)
        ).isoformat()
        rows = conn.execute(
            """SELECT amount_aed, occurred_at FROM transactions
               WHERE customer_id=? AND org_id=? AND method='cash'
                 AND occurred_at >= ? AND occurred_at <= ?
                 AND id != ?""",
            (customer_id, org_id, window_start, occurred_at, transaction_id),
        ).fetchall()
        recent_amounts = [amount_aed] + [r["amount_aed"] for r in rows]
        under_threshold_amounts = [a for a in recent_amounts if a < large_cash_threshold]
        under_threshold_total = sum(under_threshold_amounts)
        under_threshold_count = len(under_threshold_amounts)
        if (
            under_threshold_total >= large_cash_threshold
            and amount_aed < large_cash_threshold
            and under_threshold_count >= structuring_min_count
        ):
            triggered.append(TriggeredRule(
                rule_key="structuring",
                severity="high",
                detail={
                    "window_days": structuring_window_days,
                    "transaction_count": under_threshold_count,
                    "total_aed": under_threshold_total,
                    "threshold_aed": large_cash_threshold,
                },
            ))

    country = (counterparty_country or "").strip().upper()
    if country and country in high_risk_countries:
        triggered.append(TriggeredRule(
            rule_key="high_risk_country",
            severity="medium",
            detail={"country": country},
        ))

    window_start = (
        _parse(occurred_at) - timedelta(hours=velocity_window_hours)
    ).isoformat()
    count_row = conn.execute(
        """SELECT COUNT(*) c FROM transactions
           WHERE customer_id=? AND org_id=? AND occurred_at >= ? AND occurred_at <= ?""",
        (customer_id, org_id, window_start, occurred_at),
    ).fetchone()
    txn_count = count_row["c"]  # includes the just-inserted row
    if txn_count > velocity_max_count:
        triggered.append(TriggeredRule(
            rule_key="velocity",
            severity="medium",
            detail={
                "window_hours": velocity_window_hours,
                "transaction_count": txn_count,
                "threshold": velocity_max_count,
            },
        ))

    return triggered


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _get_high_risk_countries(conn, org_additional: list[str] | None) -> list[str]:
    """Build high-risk country list: FATF baseline + org additive watchlist.

    Falls back to HIGH_RISK_COUNTRIES constant only when FATF table is empty.
    org_additional (from org_settings.kyt_high_risk_countries) is ADDITIVE (union),
    never replaces the FATF baseline.
    """
    # Query FATF countries as authoritative baseline
    fatf_rows = conn.execute("SELECT country_code FROM fatf_countries").fetchall()
    fatf_codes = {row["country_code"] for row in fatf_rows}

    if fatf_codes:
        # FATF data exists: use it as baseline
        baseline = fatf_codes
    else:
        # FATF table empty (not yet refreshed): fall back to module constant
        baseline = set(HIGH_RISK_COUNTRIES)

    # Add org-specific countries (additive watchlist)
    if org_additional:
        baseline = baseline | set(org_additional)

    return sorted(baseline)


def get_rule_config(conn, org_id: int) -> dict[str, Any]:
    """Load KYT rule configuration from DB, falling back to module defaults.

    Returns:
        {
            "large_cash_threshold_aed": 55000.0,
            "structuring_window_days": 7,
            "velocity_window_hours": 24,
            "velocity_max_count": 5,
            "high_risk_countries": ["KP", "IR", "MM", "SY", "AF", "YE", "SS", "SD"],
        }

    Note: structuring_min_count is not configurable yet and is not included in the
    returned dict. Code using it should reference STRUCTURING_MIN_COUNT directly.
    """
    row = conn.execute(
        """SELECT kyt_large_cash_threshold, kyt_structuring_window_days,
                  kyt_velocity_window_hours, kyt_velocity_max_count,
                  kyt_high_risk_countries
           FROM org_settings WHERE org_id=?""",
        (org_id,)
    ).fetchone()

    # Parse org-specific additional countries
    org_additional = json.loads(row["kyt_high_risk_countries"]) if row and row["kyt_high_risk_countries"] else None

    if row:
        return {
            "large_cash_threshold_aed": row["kyt_large_cash_threshold"] if row["kyt_large_cash_threshold"] is not None else LARGE_CASH_THRESHOLD_AED,
            "structuring_window_days": row["kyt_structuring_window_days"] if row["kyt_structuring_window_days"] is not None else STRUCTURING_WINDOW_DAYS,
            "velocity_window_hours": row["kyt_velocity_window_hours"] if row["kyt_velocity_window_hours"] is not None else VELOCITY_WINDOW_HOURS,
            "velocity_max_count": row["kyt_velocity_max_count"] if row["kyt_velocity_max_count"] is not None else VELOCITY_MAX_COUNT,
            "high_risk_countries": _get_high_risk_countries(conn, org_additional),
        }

    # No org_settings row yet - return module defaults with FATF baseline
    return {
        "large_cash_threshold_aed": LARGE_CASH_THRESHOLD_AED,
        "structuring_window_days": STRUCTURING_WINDOW_DAYS,
        "velocity_window_hours": VELOCITY_WINDOW_HOURS,
        "velocity_max_count": VELOCITY_MAX_COUNT,
        "high_risk_countries": _get_high_risk_countries(conn, None),
    }


def save_rule_config(
    conn,
    org_id: int,
    config: dict[str, Any],
    *,
    actor: str = "system",
) -> None:
    """Save KYT rule configuration to DB.

    Validates:
        - Thresholds > 0
        - Window days/hours > 0
        - high_risk_countries is a list (if provided)

    Raises:
        ValueError: invalid configuration values
    """
    from ..db import audit, utcnow

    # Validate
    if "large_cash_threshold_aed" in config and config["large_cash_threshold_aed"] <= 0:
        raise ValueError("large_cash_threshold must be positive")
    if "structuring_window_days" in config and config["structuring_window_days"] <= 0:
        raise ValueError("structuring_window_days must be positive")
    if "velocity_window_hours" in config and config["velocity_window_hours"] <= 0:
        raise ValueError("velocity_window_hours must be positive")
    if "velocity_max_count" in config and config["velocity_max_count"] <= 0:
        raise ValueError("velocity_max_count must be positive")

    # Upsert org_settings row
    conn.execute(
        """INSERT INTO org_settings (org_id, updated_at) VALUES (?, ?)
           ON CONFLICT(org_id) DO UPDATE SET updated_at=excluded.updated_at""",
        (org_id, utcnow())
    )

    # Update KYT settings columns
    updates = []
    params = []
    if "large_cash_threshold_aed" in config:
        updates.append("kyt_large_cash_threshold = ?")
        params.append(config["large_cash_threshold_aed"])
    if "structuring_window_days" in config:
        updates.append("kyt_structuring_window_days = ?")
        params.append(config["structuring_window_days"])
    if "velocity_window_hours" in config:
        updates.append("kyt_velocity_window_hours = ?")
        params.append(config["velocity_window_hours"])
    if "velocity_max_count" in config:
        updates.append("kyt_velocity_max_count = ?")
        params.append(config["velocity_max_count"])
    if "high_risk_countries" in config:
        updates.append("kyt_high_risk_countries = ?")
        params.append(json.dumps(config["high_risk_countries"]))

    updates.append("updated_at = ?")
    params.append(utcnow())
    params.append(org_id)

    if updates:
        conn.execute(
            f"UPDATE org_settings SET {', '.join(updates)} WHERE org_id=?",
            params
        )

    audit(conn, actor, "settings.kyt_rules_update", detail=config, org_id=org_id)
