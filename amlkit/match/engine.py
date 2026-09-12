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
    # How many of `hits` actually became a new alert row -- see _persist's
    # open-alert dedup. Distinct from len(hits): a hit re-detected while an
    # earlier alert for the same entity+customer/UBO is still open produces
    # no new row, so this can be lower than len(hits).
    alerts_created: int = 0

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

    Uses an in-memory cache for name_tokens to avoid repeated SQLite reads on
    every screen() call. Cache is invalidated on refresh.
    """
    from .cache import get_entities_for_tokens

    keys = blocking_keys(name)
    if not keys:
        return []

    # Get entity IDs from cache or database
    token_entity_pairs = get_entities_for_tokens(conn, keys)
    if not token_entity_pairs:
        return []

    # Count key overlaps per entity
    entity_overlap: dict[int, int] = {}
    for _, entity_id in token_entity_pairs:
        entity_overlap[entity_id] = entity_overlap.get(entity_id, 0) + 1

    # Fetch entity details for matching entities
    entity_ids = list(entity_overlap.keys())
    if not entity_ids:
        return []

    placeholders = ",".join("?" * len(entity_ids))
    sql = f"""
        SELECT e.id, e.caption, e.schema_type, e.countries, e.birth_date,
               e.gender, e.topics, e.programs, d.key AS dataset
        FROM entities e
        JOIN datasets d ON d.id = e.dataset_id
        WHERE e.id IN ({placeholders})
    """
    rows = conn.execute(sql, entity_ids).fetchall()

    # Attach key_overlap count and sort
    enriched = []
    for row in rows:
        row_dict = dict(row)
        row_dict["key_overlap"] = entity_overlap[row["id"]]
        enriched.append(row_dict)

    enriched.sort(key=lambda r: r["key_overlap"], reverse=True)

    # Convert back to Row-like objects for compatibility
    class FakeRow:
        def __init__(self, d):
            self._data = d
        def __getitem__(self, key):
            return self._data[key]
        def keys(self):
            return self._data.keys()

    return [FakeRow(r) for r in enriched[:limit]]


def _names_for(conn: sqlite3.Connection, entity_id: int) -> list[str]:
    return [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM entity_names WHERE entity_id=?", (entity_id,)
        )
    ]


def _active_datasets(conn: sqlite3.Connection) -> list[str]:
    """Every dataset with at least one loaded entity -- i.e. every list a
    screening actually had in scope, regardless of whether it produced a
    candidate or a hit. `_candidates()` joins across all of these with no
    per-dataset restriction, so this is the complete, honest answer to "what
    was searched", including on a clear (no-hit) run -- which is exactly the
    result an examiner is most likely to ask about.
    """
    return sorted(
        r["key"] for r in conn.execute(
            "SELECT DISTINCT d.key FROM datasets d JOIN entities e ON e.dataset_id = d.id"
        )
    )


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
    org_id: int,
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
    active_datasets: list[str] | None = None,
) -> ScreeningResult:
    """Screen one name against every loaded dataset.

    Persists the run and any alerts by default. The screening record is
    evidence of compliance even when the result is clear -- being able to show
    that a customer *was* screened and came back clean is exactly what an
    examiner asks for.

    `org_id` is mandatory (not defaulted) even when `persist=False`: an
    unpersisted ad-hoc screening result is still shown to one specific firm's
    operator and must not silently accept a caller that forgot which firm it
    is running for. The datasets screened against (`entities` and friends) are
    shared reference data and are not themselves org-scoped -- only the
    resulting screening/alert records are.

    `active_datasets`, if given, is the already-computed result of
    `_active_datasets()` -- `rescreen_all()` passes one shared value through
    its whole customer/UBO loop instead of every call re-querying reference
    data that cannot change mid-batch. Left unset for the single-call callers
    (ad-hoc /screen, onboarding), which compute it fresh on demand.
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
        # blocking_keys(name) is also computed inside _candidates() -- cheap
        # pure-Python work, recomputed here rather than threaded back out of
        # _candidates() to keep that function's return shape simple. A query
        # with no usable tokens (digits/symbols-only) short-circuits there
        # WITHOUT ever touching entities/name_tokens, so nothing was actually
        # searched; reporting every loaded dataset as "used" in that case
        # would fabricate evidence of a screening that never ran -- worse
        # than the original bug, which merely under-reported real coverage.
        if blocking_keys(name):
            datasets = active_datasets if active_datasets is not None else _active_datasets(conn)
        else:
            datasets = []
        out.screening_id, out.alerts_created = _persist(
            conn, out, org_id, customer_id, ubo_id, actor, datasets
        )
    return out


def _persist(
    conn: sqlite3.Connection,
    res: ScreeningResult,
    org_id: int,
    customer_id: int | None,
    ubo_id: int | None,
    actor: str,
    datasets: list[str],
) -> tuple[int, int]:
    now = utcnow()
    with conn:
        cur = conn.execute(
            """INSERT INTO screenings
               (org_id, customer_id, ubo_id, query_name, trigger, algorithm, threshold,
                candidates, hits, datasets_used, run_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                org_id,
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
        alerts_created = 0
        for h in res.hits:
            # An open (undispositioned) alert already covering this exact
            # entity against this exact customer/UBO means an operator
            # already has this match sitting in their queue -- rescreen_all
            # runs this same query again after every dataset refresh
            # (roughly every 20h in production), so without this check a
            # match nobody has reviewed yet accumulates a fresh duplicate
            # alert on every single refresh. The screening row above is
            # still recorded either way -- "checked again, same known
            # match" is still evidence the obligation was met.
            already_open = conn.execute(
                """SELECT 1 FROM alerts a JOIN screenings s ON s.id = a.screening_id
                   WHERE a.org_id = ? AND a.entity_id = ? AND a.status = 'open'
                     AND s.customer_id IS ? AND s.ubo_id IS ?
                   LIMIT 1""",
                (org_id, h.entity_id, customer_id, ubo_id),
            ).fetchone()
            if already_open:
                continue
            conn.execute(
                """INSERT INTO alerts
                   (org_id, screening_id, entity_id, score, score_detail, matched_name, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (org_id, sid, h.entity_id, h.score, json.dumps(h.detail, ensure_ascii=False),
                 h.matched_name, now),
            )
            alerts_created += 1
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
                "alerts_created": alerts_created,
                "datasets_used": datasets,
            },
            org_id=org_id,
        )
    return sid, alerts_created


def rescreen_all(
    conn: sqlite3.Connection, org_id: int, *, threshold: float = DEFAULT_THRESHOLD,
    actor: str = "system",
) -> dict[str, Any]:
    """Re-screen every active customer and beneficial owner of ONE organization.

    This is the control that satisfies the EOCN requirement to act on list
    updates within 24 hours. It is intended to run immediately after every
    dataset refresh, not on a separate schedule -- a refreshed list that nobody
    has been screened against provides no protection.

    Scoped to a single org rather than every customer in the database: a
    dataset refresh happens once for everyone (the sanctions data is shared),
    but re-screening is per-firm, and a caller re-screening the whole
    deployment loops this once per active organization rather than this
    function reaching across tenant boundaries on its own.
    """
    new_alerts = 0
    screened = 0
    # Computed once for the whole batch: which datasets are loaded cannot
    # change mid-run, so re-querying it per name (thousands of times on a
    # large book) would be pure waste against reference data every call in
    # this loop shares.
    active_datasets = _active_datasets(conn)

    for row in conn.execute(
        "SELECT id, full_name, name_arabic, nationality, birth_date, gender"
        " FROM customers WHERE status='active' AND org_id=?",
        (org_id,),
    ).fetchall():
        for nm in filter(None, (row["full_name"], row["name_arabic"])):
            res = screen(
                conn, nm, org_id=org_id, trigger="list_update", threshold=threshold,
                country=row["nationality"], birth_date=row["birth_date"],
                gender=row["gender"], customer_id=row["id"], actor=actor,
                active_datasets=active_datasets,
            )
            screened += 1
            new_alerts += res.alerts_created

    for row in conn.execute(
        "SELECT id, customer_id, person_name, name_arabic, nationality, birth_date"
        " FROM ubo_links WHERE is_ubo=1 AND is_nominee=0 AND org_id=?",
        (org_id,),
    ).fetchall():
        for nm in filter(None, (row["person_name"], row["name_arabic"])):
            res = screen(
                conn, nm, org_id=org_id, trigger="list_update", threshold=threshold,
                country=row["nationality"], birth_date=row["birth_date"],
                customer_id=row["customer_id"], ubo_id=row["id"], actor=actor,
                active_datasets=active_datasets,
            )
            screened += 1
            new_alerts += res.alerts_created

    return {"screened": screened, "alerts": new_alerts}

