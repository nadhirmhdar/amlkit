"""Notify a firm's MLROs when a screening produces a new match.

Two channels, deliberately unequal:

  * the in-app notification (a row per MLRO in `notifications`) is the record
    of truth and is written first, inside the caller's transaction discipline;
  * email is best-effort on top of it and is wrapped so that a mail outage can
    never break a screening -- the screening and its alert have already been
    committed by the time anything here runs.

Recipients are the ACTIVE MLROs of the SAME organization, resolved with an
explicit org_id. No path here can address another firm's operators.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from . import mail
from .db import utcnow

logger = logging.getLogger("amlkit.notifications")

KIND_MATCH = "screening_match"
KIND_DIGEST = "rescreen_digest"


def _active_mlros(conn: sqlite3.Connection, org_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, email FROM operators WHERE org_id=? AND role='mlro' AND is_active=1 ORDER BY id",
        (org_id,),
    ).fetchall()


def _insert(conn: sqlite3.Connection, org_id: int, operators, kind: str, title: str, body: str, link: str) -> None:
    now = utcnow()
    with conn:
        for op in operators:
            conn.execute(
                "INSERT INTO notifications (org_id, operator_id, kind, title, body, link, created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (org_id, op["id"], kind, title, body, link, now),
            )


def notify_new_match(conn: sqlite3.Connection, org_id: int, result: Any, *, customer_id: int | None = None) -> int:
    """Tell every active MLRO of `org_id` about a screening that just created
    new alert(s). Returns how many operators were notified in-app."""
    mlros = _active_mlros(conn, org_id)
    if not mlros or not result.hits:
        return 0

    top = result.hits[0]  # highest score (engine sorts hits descending)
    n = result.alerts_created
    title = f"New screening match: {top.caption}"
    body = (
        f'"{result.query}" matched {top.caption} ({top.dataset}) at {top.score:.2f}.'
        + (f" {n} new alerts." if n > 1 else "")
    )
    link = f"/customers/{customer_id}#alerts" if customer_id else "/alerts"
    _insert(conn, org_id, mlros, KIND_MATCH, title, body, link)

    try:
        mail.send_screening_match_alert(
            [m["email"] for m in mlros],
            query_name=result.query,
            match_caption=top.caption,
            score=top.score,
            alert_url=mail.app_base_url() + link,
        )
    except Exception:  # noqa: BLE001 -- a mail failure must never break a screening
        logger.exception("screening match email failed; in-app notification already written")
    return len(mlros)


def notify_rescreen_digest(conn: sqlite3.Connection, org_id: int, new_alerts: int) -> int:
    """One summary for a whole re-screen run, instead of one email per hit."""
    if new_alerts <= 0:
        return 0
    mlros = _active_mlros(conn, org_id)
    if not mlros:
        return 0
    title = f"List update: {new_alerts} new screening match{'es' if new_alerts != 1 else ''}"
    body = "The daily re-screen after a list refresh found new matches in your customer book."
    _insert(conn, org_id, mlros, KIND_DIGEST, title, body, "/alerts")
    try:
        mail.send_screening_match_alert(
            [m["email"] for m in mlros],
            query_name="Customer book (list update re-screen)",
            match_caption=f"{new_alerts} new alert(s)",
            score=1.0,
            alert_url=mail.app_base_url() + "/alerts",
        )
    except Exception:  # noqa: BLE001
        logger.exception("re-screen digest email failed; in-app notification already written")
    return len(mlros)


def mark_read(conn: sqlite3.Connection, org_id: int, operator_id: int, notification_id: int) -> bool:
    """Mark one of THIS operator's notifications read. False if it is not theirs."""
    with conn:
        cur = conn.execute(
            "UPDATE notifications SET read_at=? WHERE id=? AND org_id=? AND operator_id=? AND read_at IS NULL",
            (utcnow(), notification_id, org_id, operator_id),
        )
    return cur.rowcount > 0


def mark_all_read(conn: sqlite3.Connection, org_id: int, operator_id: int) -> int:
    with conn:
        cur = conn.execute(
            "UPDATE notifications SET read_at=? WHERE org_id=? AND operator_id=? AND read_at IS NULL",
            (utcnow(), org_id, operator_id),
        )
    return cur.rowcount
