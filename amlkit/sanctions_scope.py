"""Which sanctions lists carry a UAE freeze obligation.

Cabinet Decision 74/2020 (targeted financial sanctions) obliges UAE reporting
entities to freeze without delay, and to file a CNMR, only for matches on the
UN Security Council Consolidated List and the UAE Local Terrorist List (EOCN).
Matches on the OFAC, EU or UK lists remain screening alerts (EDD, consider an
STR/SAR) but raise no freeze obligation, 24-hour clock or CNMR.

This module is the single place that decides it. Every freeze gate (obligation
creation, the overdue email, the CNMR route) calls ``is_uae_freeze_list``.
"""

from __future__ import annotations

import sqlite3

# Dataset keys (datasets.key) of the UN and UAE-local lists.
UAE_FREEZE_DATASETS: frozenset[str] = frozenset({
    "un_consolidated",      # amlkit/ingest/un.py
    "un_sc_sanctions",      # OpenSanctions mirror of the UNSC list
    "ae_local_terrorists",  # amlkit/ingest/eocn.py (UAE Local Terrorist List)
})


def is_uae_freeze_list(dataset: str | None) -> bool:
    """True when ``dataset`` (a datasets.key) is a UN or UAE-local sanctions list."""
    if not dataset:
        return False
    key = dataset.strip().lower()
    return key in UAE_FREEZE_DATASETS or key.startswith("eocn_")


def alert_dataset(conn: sqlite3.Connection, alert_id: int, org_id: int) -> str | None:
    """datasets.key of the entity behind an alert (tenant-scoped), or None."""
    row = conn.execute(
        """SELECT d.key FROM alerts a
           JOIN entities e ON e.id = a.entity_id
           JOIN datasets d ON d.id = e.dataset_id
           WHERE a.id = ? AND a.org_id = ?""",
        (alert_id, org_id),
    ).fetchone()
    return row["key"] if row else None


def freeze_obligation_in_scope(
    conn: sqlite3.Connection, freeze_id: int, org_id: int
) -> bool:
    """True when the obligation's linked alert is on a UN / UAE-local list.

    An obligation with no linked alert (raised manually) is in scope: nothing
    says it came from a non-UAE list. Obligations whose alert came from an
    OFAC/EU/UK list (created before this rule) are out of scope, so they get
    no overdue email and no CNMR.
    """
    row = conn.execute(
        "SELECT alert_id FROM freeze_obligations WHERE id = ? AND org_id = ?",
        (freeze_id, org_id),
    ).fetchone()
    if row is None:
        return False
    if row["alert_id"] is None:
        return True
    return is_uae_freeze_list(alert_dataset(conn, row["alert_id"], org_id))
