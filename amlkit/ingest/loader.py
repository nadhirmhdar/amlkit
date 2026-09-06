"""Load a source adapter's entities into the database.

Loading is transactional per dataset and replace-on-refresh: a dataset's
entities are swapped wholesale rather than merged. Sanctions lists are
authoritative snapshots, and a delisted person must actually disappear --
merge semantics would leave stale designations in place and produce alerts on
people who are no longer listed.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..db import audit, upsert_dataset, utcnow
from .base import AdapterError, SourceAdapter


@dataclass(slots=True)
class LoadResult:
    dataset: str
    entities: int
    names: int
    tokens: int
    identifiers: int
    refreshed_at: str

    def __str__(self) -> str:
        return (
            f"{self.dataset:28} {self.entities:>6} entities  "
            f"{self.names:>6} names  {self.tokens:>7} tokens"
        )


def load(conn: sqlite3.Connection, adapter: SourceAdapter, actor: str = "system") -> LoadResult:
    """Fetch, parse and store one dataset. Raises AdapterError on any failure."""
    payload = adapter.fetch()

    # Parse fully before touching the database. A partially-applied sanctions
    # refresh is a compliance gap, so the whole batch is materialised first and
    # only then swapped in under a single transaction.
    entities = list(adapter.parse(payload))
    if not entities:
        raise AdapterError(f"{adapter.key}: no entities parsed; refusing to clear existing data")

    ds_id = upsert_dataset(
        conn,
        key=adapter.key,
        title=adapter.title,
        publisher=adapter.publisher,
        source_url=adapter.source_url,
        licence=adapter.licence,
        is_mandatory=adapter.is_mandatory,
    )

    now = utcnow()
    n_names = n_tokens = n_ids = 0

    with conn:  # single transaction: all-or-nothing
        # Snapshot which source_ids already exist for this dataset. We will
        # UPDATE those rows in place rather than deleting and re-inserting them,
        # so their primary key (entity_id) stays stable. alerts.entity_id
        # references entities(id) ON DELETE CASCADE, so a delete-all strategy
        # would wipe every alert for this dataset on every daily refresh.
        existing: dict[str, int] = {
            row["source_id"]: int(row["id"])
            for row in conn.execute(
                "SELECT id, source_id FROM entities WHERE dataset_id=?", (ds_id,)
            )
        }
        incoming_source_ids: set[str] = set()

        for ent in entities:
            incoming_source_ids.add(ent.source_id)
            eid = existing.get(ent.source_id)

            if eid is not None:
                # Entity still listed: update fields, keep its primary key so
                # alert rows that reference it survive the refresh.
                conn.execute(
                    """UPDATE entities SET
                       schema_type=?, caption=?, countries=?, birth_date=?,
                       gender=?, topics=?, programs=?, listed_at=?, raw=?, last_seen=?
                       WHERE id=?""",
                    (
                        ent.schema_type, ent.caption, _json(ent.countries),
                        ent.birth_date, ent.gender, _json(ent.topics),
                        _json(ent.programs), ent.listed_at, ent.raw_json(), now,
                        eid,
                    ),
                )
                # Child rows (names, tokens, identifiers) have no dependents of
                # their own, so DELETE + re-insert is safe and simple.
                conn.execute("DELETE FROM entity_names WHERE entity_id=?", (eid,))
                conn.execute("DELETE FROM name_tokens WHERE entity_id=?", (eid,))
                conn.execute("DELETE FROM entity_identifiers WHERE entity_id=?", (eid,))
            else:
                cur = conn.execute(
                    """INSERT INTO entities
                       (dataset_id, source_id, schema_type, caption, countries,
                        birth_date, gender, topics, programs, listed_at, raw,
                        first_seen, last_seen)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        ds_id,
                        ent.source_id,
                        ent.schema_type,
                        ent.caption,
                        _json(ent.countries),
                        ent.birth_date,
                        ent.gender,
                        _json(ent.topics),
                        _json(ent.programs),
                        ent.listed_at,
                        ent.raw_json(),
                        now,
                        now,
                    ),
                )
                eid = cur.lastrowid

            rows = ent.name_rows()
            conn.executemany(
                "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
                " VALUES (?,?,?,?,?)",
                [(eid, *r) for r in rows],
            )
            n_names += len(rows)

            toks = ent.tokens()
            conn.executemany(
                "INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)",
                [(t, eid) for t in toks],
            )
            n_tokens += len(toks)

            if ent.identifiers:
                conn.executemany(
                    "INSERT OR IGNORE INTO entity_identifiers (entity_id, id_type, id_value)"
                    " VALUES (?,?,?)",
                    [(eid, k, v) for k, v in ent.identifiers],
                )
                n_ids += len(ent.identifiers)

        # Delete entities that were removed from the source list. The cascade
        # will fire for their child rows (names, tokens, identifiers). Any
        # alerts against a newly-delisted entity will also cascade-delete --
        # an acceptable edge case: if a designation was actively disputed, the
        # compliance officer should have dispositioned it before delisting.
        removed_ids = [existing[sid] for sid in existing if sid not in incoming_source_ids]
        if removed_ids:
            conn.executemany(
                "DELETE FROM entities WHERE id=?",
                [(eid,) for eid in removed_ids],
            )

        conn.execute(
            "UPDATE datasets SET last_refresh=?, entity_count=? WHERE id=?",
            (now, len(entities), ds_id),
        )
        audit(
            conn,
            actor=actor,
            action="dataset.refresh",
            object_type="dataset",
            object_id=adapter.key,
            detail={"entities": len(entities), "names": n_names, "licence": adapter.licence},
            # Shared reference data, not tenant-owned -- visible to every
            # org, so org_id is explicitly None rather than any one firm's id.
            org_id=None,
        )

    return LoadResult(adapter.key, len(entities), n_names, n_tokens, n_ids, now)


def _json(vals) -> str:
    import json

    return json.dumps(list(vals), ensure_ascii=False)


def staleness_report(conn: sqlite3.Connection) -> list[dict]:
    """Hours since each dataset was refreshed.

    EOCN requires list updates to be implemented within 24 hours, so this is a
    compliance control rather than an operational nicety. `breach` marks any
    mandatory dataset past that window.
    """
    from datetime import datetime, timezone

    out = []
    now = datetime.now(timezone.utc)
    for row in conn.execute(
        "SELECT key, title, is_mandatory, last_refresh, entity_count FROM datasets ORDER BY key"
    ):
        hours = None
        if row["last_refresh"]:
            try:
                ts = datetime.fromisoformat(row["last_refresh"])
                hours = round((now - ts).total_seconds() / 3600, 1)
            except ValueError:
                hours = None
        out.append(
            {
                "key": row["key"],
                "title": row["title"],
                "mandatory": bool(row["is_mandatory"]),
                "entities": row["entity_count"],
                "hours_since_refresh": hours,
                "breach": bool(row["is_mandatory"] and (hours is None or hours > 24)),
            }
        )
    return out
