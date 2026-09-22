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
import time
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

# Step 7: Per-connection, per-org config cache. Invalidated on save_rule_config().
#
# Keyed by (id(conn), org_id), NOT bare org_id. This app is single-tenant-
# per-database (org_id is only unique within one database), so a bare
# org_id key lets two different databases opened in the same process that
# both happen to have an org 1 -- two independent test suites, two
# in-memory sqlite connections, anything -- silently read each other's
# cached config. That is not just a test hazard: deps.get_db() hands every
# HTTP request its own fresh connection (closed at request end), so keying
# on connection identity also means a request never sees another request's
# -- or another worker process's -- cached read; each request re-reads the
# DB once and caches only for the rest of that request (e.g. a batch import
# screening many transactions in a loop against the same conn). That closes
# the multi-instance drift risk this cache used to create: previously, an
# operator changing large_cash_threshold_aed via /admin/rule-config only
# invalidated the process that handled the save -- every other worker
# instance kept screening against the stale threshold until it happened to
# restart, a live compliance-control gap under Cabinet Resolution 134/2025's
# risk-based approach, not merely a test artifact.
#
# _CACHE_TTL_SECONDS is a memory-hygiene bound, not the freshness mechanism:
# without it, a long-lived connection (a batch script, scripts/refresh.py-
# style tooling) that calls get_rule_config for many orgs over a long
# session would accumulate cache entries forever. Expired entries are swept
# opportunistically on a cache miss, which is the hot path for the per-
# request pattern above anyway, so this adds no cost to the normal case.
_CACHE_TTL_SECONDS = 300.0

_config_cache: dict[tuple[int, int], tuple[dict[str, Any], float]] = {}


def _cache_key(conn, org_id: int) -> tuple[int, int]:
    return (id(conn), org_id)


def _prune_expired_cache_entries(now: float) -> None:
    expired = [k for k, (_, expires_at) in _config_cache.items() if expires_at <= now]
    for k in expired:
        del _config_cache[k]


def _clear_config_cache(conn=None, org_id: int | None = None) -> None:
    """Clear the rule config cache.

    conn=None: clear every cached entry, for every database and org. This
    is the coarse reset tests should use between runs -- it doesn't depend
    on knowing the exact cache key, so it stays correct even if the caching
    strategy above changes.
    conn given, org_id=None: clear every org cached for that connection.
    conn and org_id given: clear just that connection's entry for that org.
    """
    global _config_cache
    if conn is None:
        _config_cache.clear()
        return
    if org_id is None:
        conn_id = id(conn)
        for k in [k for k in _config_cache if k[0] == conn_id]:
            del _config_cache[k]
    else:
        _config_cache.pop(_cache_key(conn, org_id), None)


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
    from ..money import Money

    # Load org-specific configuration (falls back to module defaults)
    config = get_rule_config(conn, org_id)
    large_cash_threshold = config["large_cash_threshold_aed"]
    structuring_window_days = config["structuring_window_days"]
    structuring_min_count = config["structuring_min_count"]
    velocity_window_hours = config["velocity_window_hours"]
    velocity_max_count = config["velocity_max_count"]
    high_risk_countries = set(config["high_risk_countries"])

    threshold_money = Money.from_float(large_cash_threshold, "AED")
    current_money = Money.from_float(amount_aed, "AED")

    triggered: list[TriggeredRule] = []

    if method == "cash" and current_money >= threshold_money:
        triggered.append(TriggeredRule(
            rule_key="large_cash",
            severity="high",
            detail={
                "amount_aed": amount_aed,
                "threshold_aed": large_cash_threshold,
            },
        ))

    # Structuring detection applies to ALL payment methods (cash, wire, virtual-asset)
    # Issue #257: previously only monitored cash, blind to wire/virtual-asset structuring
    window_start = (
        _parse(occurred_at) - timedelta(days=structuring_window_days)
    ).isoformat()
    rows = conn.execute(
        """SELECT amount_aed, amount_units, amount_nanos, occurred_at
           FROM transactions
           WHERE customer_id=? AND org_id=?
             AND occurred_at >= ? AND occurred_at <= ?
             AND id != ?""",
        (customer_id, org_id, window_start, occurred_at, transaction_id),
    ).fetchall()

    def _row_to_money(r) -> Money:
        if r["amount_units"] is not None:
            return Money("AED", r["amount_units"], r["amount_nanos"] or 0)
        return Money.from_float(r["amount_aed"], "AED")

    recent_money = [current_money] + [_row_to_money(r) for r in rows]
    under_threshold = [m for m in recent_money if m < threshold_money]
    zero = Money("AED", 0, 0)
    under_threshold_total = zero
    for m in under_threshold:
        under_threshold_total = under_threshold_total + m
    under_threshold_count = len(under_threshold)
    if (
        under_threshold_total >= threshold_money
        and current_money < threshold_money
        and under_threshold_count >= structuring_min_count
    ):
        triggered.append(TriggeredRule(
            rule_key="structuring",
            severity="high",
            detail={
                "window_days": structuring_window_days,
                "transaction_count": under_threshold_count,
                "total_aed": float(under_threshold_total.to_decimal()),
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

    Cached per (connection, org) to avoid repeated DB queries during batch
    transaction processing on one connection. Invalidated on
    save_rule_config() for that connection and org; see the module-level
    comment above _config_cache for why the key includes the connection.

    Returns:
        {
            "large_cash_threshold_aed": 55000.0,
            "structuring_window_days": 7,
            "structuring_min_count": 2,
            "velocity_window_hours": 24,
            "velocity_max_count": 5,
            "high_risk_countries": ["KP", "IR", "MM", "SY", "AF", "YE", "SS", "SD"],
        }

    Note: structuring_min_count is not yet org-configurable; it always
    returns the STRUCTURING_MIN_COUNT module constant.
    """
    global _config_cache
    key = _cache_key(conn, org_id)
    cached = _config_cache.get(key)
    if cached is not None:
        config, expires_at = cached
        if time.monotonic() < expires_at:
            return config

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
        config = {
            "large_cash_threshold_aed": row["kyt_large_cash_threshold"] if row["kyt_large_cash_threshold"] is not None else LARGE_CASH_THRESHOLD_AED,
            "structuring_window_days": row["kyt_structuring_window_days"] if row["kyt_structuring_window_days"] is not None else STRUCTURING_WINDOW_DAYS,
            "structuring_min_count": STRUCTURING_MIN_COUNT,  # Not configurable yet
            "velocity_window_hours": row["kyt_velocity_window_hours"] if row["kyt_velocity_window_hours"] is not None else VELOCITY_WINDOW_HOURS,
            "velocity_max_count": row["kyt_velocity_max_count"] if row["kyt_velocity_max_count"] is not None else VELOCITY_MAX_COUNT,
            "high_risk_countries": _get_high_risk_countries(conn, org_additional),
        }
    else:
        config = {
            "large_cash_threshold_aed": LARGE_CASH_THRESHOLD_AED,
            "structuring_window_days": STRUCTURING_WINDOW_DAYS,
            "structuring_min_count": STRUCTURING_MIN_COUNT,
            "velocity_window_hours": VELOCITY_WINDOW_HOURS,
            "velocity_max_count": VELOCITY_MAX_COUNT,
            "high_risk_countries": _get_high_risk_countries(conn, None),
        }

    now = time.monotonic()
    _prune_expired_cache_entries(now)
    _config_cache[key] = (config, now + _CACHE_TTL_SECONDS)
    return config


def save_rule_config(
    conn,
    org_id: int,
    config: dict[str, Any],
    *,
    actor: str = "system",
) -> None:
    """Save KYT rule configuration to DB.

    Validates:
        - Thresholds > 0 and within sane upper bounds
        - Window days/hours > 0 and within sane upper bounds
        - high_risk_countries is a list (if provided)

    Raises:
        ValueError: invalid configuration values
    """
    from ..db import audit, utcnow

    # Validate lower bounds
    if "large_cash_threshold_aed" in config and config["large_cash_threshold_aed"] <= 0:
        raise ValueError("large_cash_threshold must be positive")
    if "structuring_window_days" in config and config["structuring_window_days"] <= 0:
        raise ValueError("structuring_window_days must be positive")
    if "velocity_window_hours" in config and config["velocity_window_hours"] <= 0:
        raise ValueError("velocity_window_hours must be positive")
    if "velocity_max_count" in config and config["velocity_max_count"] <= 0:
        raise ValueError("velocity_max_count must be positive")

    # Validate upper bounds (sanity checks to prevent misconfiguration)
    if "large_cash_threshold_aed" in config and config["large_cash_threshold_aed"] > 1_000_000:
        raise ValueError("large_cash_threshold cannot exceed 1,000,000 AED (would disable detection)")
    if "structuring_window_days" in config and config["structuring_window_days"] > 90:
        raise ValueError("structuring_window_days cannot exceed 90 days")
    if "velocity_window_hours" in config and config["velocity_window_hours"] > 168:
        raise ValueError("velocity_window_hours cannot exceed 168 hours (7 days)")
    if "velocity_max_count" in config and config["velocity_max_count"] > 1000:
        raise ValueError("velocity_max_count cannot exceed 1000 transactions")

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

    _clear_config_cache(conn, org_id)
