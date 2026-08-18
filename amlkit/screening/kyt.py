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
    triggered: list[TriggeredRule] = []

    if method == "cash" and amount_aed >= LARGE_CASH_THRESHOLD_AED:
        triggered.append(TriggeredRule(
            rule_key="large_cash",
            severity="high",
            detail={
                "amount_aed": amount_aed,
                "threshold_aed": LARGE_CASH_THRESHOLD_AED,
            },
        ))

    if method == "cash":
        window_start = (
            _parse(occurred_at) - timedelta(days=STRUCTURING_WINDOW_DAYS)
        ).isoformat()
        rows = conn.execute(
            """SELECT amount_aed, occurred_at FROM transactions
               WHERE customer_id=? AND org_id=? AND method='cash'
                 AND occurred_at >= ? AND occurred_at <= ?
                 AND id != ?""",
            (customer_id, org_id, window_start, occurred_at, transaction_id),
        ).fetchall()
        recent_amounts = [amount_aed] + [r["amount_aed"] for r in rows]
        total = sum(recent_amounts)
        under_threshold_count = sum(1 for a in recent_amounts if a < LARGE_CASH_THRESHOLD_AED)
        if (
            total >= LARGE_CASH_THRESHOLD_AED
            and amount_aed < LARGE_CASH_THRESHOLD_AED
            and under_threshold_count >= STRUCTURING_MIN_COUNT
        ):
            triggered.append(TriggeredRule(
                rule_key="structuring",
                severity="high",
                detail={
                    "window_days": STRUCTURING_WINDOW_DAYS,
                    "transaction_count": len(recent_amounts),
                    "total_aed": total,
                    "threshold_aed": LARGE_CASH_THRESHOLD_AED,
                },
            ))

    country = (counterparty_country or "").strip().upper()
    if country and country in HIGH_RISK_COUNTRIES:
        triggered.append(TriggeredRule(
            rule_key="high_risk_country",
            severity="medium",
            detail={"country": country},
        ))

    window_start = (
        _parse(occurred_at) - timedelta(hours=VELOCITY_WINDOW_HOURS)
    ).isoformat()
    count_row = conn.execute(
        """SELECT COUNT(*) c FROM transactions
           WHERE customer_id=? AND org_id=? AND occurred_at >= ? AND occurred_at <= ?""",
        (customer_id, org_id, window_start, occurred_at),
    ).fetchone()
    txn_count = count_row["c"]  # includes the just-inserted row
    if txn_count > VELOCITY_MAX_COUNT:
        triggered.append(TriggeredRule(
            rule_key="velocity",
            severity="medium",
            detail={
                "window_hours": VELOCITY_WINDOW_HOURS,
                "transaction_count": txn_count,
                "threshold": VELOCITY_MAX_COUNT,
            },
        ))

    return triggered


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
