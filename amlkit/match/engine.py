"""Screening engine: candidate generation, scoring, alert persistence."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from ..db import audit, utcnow
from ..names.arabic import blocking_keys
from ..screening.pf import classify_programs, obligation_note
from .scorer import DEFAULT_THRESHOLD, ScoreResult, score_entity

# Valid screening triggers. EOCN requires screening at each of these points,
# so the trigger is recorded on every run to evidence that the obligation was
# actually met rather than merely claimed.
TRIGGERS = ("onboarding", "list_update", "periodic", "transaction", "adhoc")


@dataclass(slots=True)
class Hit:
    entity_id: int
    dataset: str
    caption: str
    schema_type: str
    score: float
    matched_name: str
    topics: list[str]
    detail: dict[str, Any]
    programs: list[str] = field(default_factory=list)

    @property
    def is_sanction(self) -> bool:
        return "sanction" in self.topics

    @property
    def is_pep(self) -> bool:
        return any(t.startswith("role.pep") or t == "role.pep" for t in self.topics)

    @property
    def categories(self) -> set[str]:
        return classify_programs(self.programs)

    @property
    def is_proliferation(self) -> bool:
        """PF is a standalone offence under Law 10/2025, not a sanctions subtype."""
        return "proliferation" in self.categories

    @property
    def is_terrorism(self) -> bool:
        return "terrorism" in self.categories

    @property
    def obligation(self) -> str:
        return obligation_note(self.categories)


@dataclass(slots=True)
class ScreeningResult:
    query: str
    trigger: str
    threshold: float
    candidates: int
    hits: list[Hit]
    screening_id: int | None = None

    @property
    def clear(self) -> bool:
        return not self.hits

    def summary(self) -> str:
        if self.clear:
            return f"CLEAR  '{self.query}' - {self.candidates} candidates, no hits >= {self.threshold}"
        top = max(h.score for h in self.hits)
        return (
            f"HITS   '{self.query}' - {len(self.hits)} hit(s), "
            f"top score {top:.3f}, {self.candidates} candidates screened"
        )


def _candidates(conn: sqlite3.Connection, name: str, limit: int = 400) -> list[sqlite3.Row]:
    """Retrieve entities sharing at least one blocking key with the query.

    Recall at this stage bounds the recall of the whole system, so the keys are
    deliberately generous: a candidate that is never retrieved can never be
    scored, and a missed sanctions match is a regulatory failure rather than an
    inconvenience. Candidates are ranked by how many keys they share so the
    limit truncates the weakest first.
    """
    keys = blocking_keys(name)
    if not keys:
        return []
    placeholders = ",".join("?" * len(keys))
    sql = f"""
        SELECT e.id, e.caption, e.schema_type, e.countries, e.birth_date,
               e.gender, e.topics, e.programs, d.key AS dataset,
               COUNT(*) AS key_overlap
        FROM name_tokens t
        JOIN entities e ON e.id = t.entity_id
        JOIN datasets d ON d.id = e.dataset_id
        WHERE t.token IN ({placeholders})
        GROUP BY e.id
        ORDER BY key_overlap DESC
        LIMIT ?
    """
    return conn.execute(sql, (*keys, limit)).fetchall()


def _names_for(conn: sqlite3.Connection, entity_id: int) -> list[str]:
    return [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM entity_names WHERE entity_id=?", (entity_id,)
        )
    ]


def _identifiers_for(conn: sqlite3.Connection, entity_id: int) -> list[tuple[str, str]]:
    return [
        (r["id_type"], r["id_value"])
        for r in conn.execute(
            "SELECT id_type, id_value FROM entity_identifiers WHERE entity_id=?", (entity_id,)
        )
    ]


def screen(
    conn: sqlite3.Connection,
    name: str,
    *,
    trigger: str = "adhoc",
    threshold: float = DEFAULT_THRESHOLD,
    country: str | None = None,
    birth_date: str | None = None,
    gender: str | None = None,
    identifiers: list[tuple[str, str]] | None = None,
    customer_id: int | None = None,
    ubo_id: int | None = None,
    persist: bool = True,
    actor: str = "system",
) -> ScreeningResult:
    """Screen one name against every loaded dataset.

    Persists the run and any alerts by default. The screening record is
    evidence of compliance even when the result is clear -- being able to show
    that a customer *was* screened and came back clean is exactly what an
    examiner asks for.
    """
    if trigger not in TRIGGERS:
        raise ValueError(f"unknown trigger {trigger!r}; expected one of {TRIGGERS}")

    rows = _candidates(conn, name)
    hits: list[Hit] = []

    for row in rows:
        result: ScoreResult = score_entity(
            name,
            _names_for(conn, row["id"]),
            query_country=country,
            query_birth_date=birth_date,
            query_gender=gender,
            query_identifiers=identifiers,
            cand_countries=json.loads(row["countries"] or "[]"),
            cand_birth_date=row["birth_date"],
            cand_gender=row["gender"],
            cand_identifiers=_identifiers_for(conn, row["id"]),
        )
        if result.score >= threshold:
            hits.append(
                Hit(
                    entity_id=row["id"],
                    dataset=row["dataset"],
                    caption=row["caption"],
                    schema_type=row["schema_type"],
                    score=result.score,
                    matched_name=result.matched_name,
                    topics=json.loads(row["topics"] or "[]"),
                    programs=json.loads(row["programs"] or "[]"),
                    detail=result.as_dict(),
                )
            )

    hits.sort(key=lambda h: h.score, reverse=True)
    out = ScreeningResult(
        query=name, trigger=trigger, threshold=threshold, candidates=len(rows), hits=hits
    )

    if persist:
        out.screening_id = _persist(conn, out, customer_id, ubo_id, actor)
    return out


def _persist(
    conn: sqlite3.Connection,
    res: ScreeningResult,
    customer_id: int | None,
    ubo_id: int | None,
    actor: str,
) -> int:
    now = utcnow()
    datasets = sorted({h.dataset for h in res.hits})
    with conn:
        cur = conn.execute(
            """INSERT INTO screenings
               (customer_id, ubo_id, query_name, trigger, algorithm, threshold,
                candidates, hits, datasets_used, run_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                customer_id,
                ubo_id,
                res.query,
                res.trigger,
                "amlkit-arabic-v1",
                res.threshold,
                res.candidates,
                len(res.hits),
                json.dumps(datasets),
                now,
            ),
        )
        sid = cur.lastrowid
        for h in res.hits:
            conn.execute(
                """INSERT INTO alerts
                   (screening_id, entity_id, score, score_detail, matched_name, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (sid, h.entity_id, h.score, json.dumps(h.detail, ensure_ascii=False), h.matched_name, now),
            )
        audit(
            conn,
            actor=actor,
            action="screening.run",
            object_type="screening",
            object_id=sid,
            detail={
                "query": res.query,
                "trigger": res.trigger,
                "candidates": res.candidates,
                "hits": len(res.hits),
            },
        )
    return sid


def rescreen_all(
    conn: sqlite3.Connection, *, threshold: float = DEFAULT_THRESHOLD, actor: str = "system"
) -> dict[str, Any]:
    """Re-screen every active customer and beneficial owner.

    This is the control that satisfies the EOCN requirement to act on list
    updates within 24 hours. It is intended to run immediately after every
    dataset refresh, not on a separate schedule -- a refreshed list that nobody
    has been screened against provides no protection.
    """
    new_alerts = 0
    screened = 0

    for row in conn.execute(
        "SELECT id, full_name, name_arabic, nationality, birth_date, gender"
        " FROM customers WHERE status='active'"
    ).fetchall():
        for nm in filter(None, (row["full_name"], row["name_arabic"])):
            res = screen(
                conn, nm, trigger="list_update", threshold=threshold,
                country=row["nationality"], birth_date=row["birth_date"],
                gender=row["gender"], customer_id=row["id"], actor=actor,
            )
            screened += 1
            new_alerts += len(res.hits)

    for row in conn.execute(
        "SELECT id, customer_id, person_name, name_arabic, nationality, birth_date"
        " FROM ubo_links WHERE is_ubo=1"
    ).fetchall():
        for nm in filter(None, (row["person_name"], row["name_arabic"])):
            res = screen(
                conn, nm, trigger="list_update", threshold=threshold,
                country=row["nationality"], birth_date=row["birth_date"],
                customer_id=row["customer_id"], ubo_id=row["id"], actor=actor,
            )
            screened += 1
            new_alerts += len(res.hits)

    return {"screened": screened, "alerts": new_alerts}

