"""SQLite storage layer.

SQLite rather than Postgres is deliberate. This tool is meant to run on a
compliance officer's own machine: one portable file, no daemon, no container
runtime, and a backup story that is "copy the file". At the data volumes UAE
screening actually involves -- the Local Terrorist List is ~770 entities and
the full consolidated set is in the low hundreds of thousands -- SQLite is not
a compromise, it is the correct size of tool.

The audit log is append-only by trigger, not by convention. Cabinet Resolution
134 of 2025 places personal liability on senior management for compliance
failures, so "we promise not to edit it" is not an adequate control.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "aml.db"

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- sanctions
CREATE TABLE IF NOT EXISTS datasets (
    id            INTEGER PRIMARY KEY,
    key           TEXT NOT NULL UNIQUE,      -- 'ae_local_terrorists'
    title         TEXT NOT NULL,
    publisher     TEXT,
    source_url    TEXT,
    licence       TEXT,
    is_mandatory  INTEGER NOT NULL DEFAULT 0, -- required by UAE law
    last_refresh  TEXT,
    entity_count  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS entities (
    id           INTEGER PRIMARY KEY,
    dataset_id   INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    source_id    TEXT NOT NULL,              -- id in the upstream source
    schema_type  TEXT NOT NULL,              -- Person | Company | Organization | Vessel
    caption      TEXT NOT NULL,
    countries    TEXT,                       -- json array
    birth_date   TEXT,
    gender       TEXT,
    topics       TEXT,                       -- json array: sanction, role.pep, ...
    -- Sanction programme identifiers (UN-SC1718, NPWMD, ...). Retained because
    -- proliferation financing is a standalone offence under Law 10/2025 and is
    -- only distinguishable from terrorism financing by the designating regime.
    programs     TEXT,                       -- json array
    listed_at    TEXT,
    raw          TEXT,                       -- json of the full source record
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    UNIQUE (dataset_id, source_id)
);

CREATE TABLE IF NOT EXISTS entity_names (
    id            INTEGER PRIMARY KEY,
    entity_id     INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    name_type     TEXT NOT NULL DEFAULT 'alias',  -- primary | alias | weak
    canonical_key TEXT NOT NULL,
    script        TEXT NOT NULL DEFAULT 'latin'   -- latin | arabic
);
CREATE INDEX IF NOT EXISTS ix_names_canon  ON entity_names(canonical_key);
CREATE INDEX IF NOT EXISTS ix_names_entity ON entity_names(entity_id);

-- Blocking index: the candidate-generation stage joins on this. Without it
-- every screening request degrades to a full table scan.
CREATE TABLE IF NOT EXISTS name_tokens (
    token     TEXT NOT NULL,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    PRIMARY KEY (token, entity_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_tokens_token ON name_tokens(token);

CREATE TABLE IF NOT EXISTS entity_identifiers (
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    id_type   TEXT NOT NULL,                 -- lei | swift | passport | tax | crypto
    id_value  TEXT NOT NULL,
    PRIMARY KEY (entity_id, id_type, id_value)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_ident_value ON entity_identifiers(id_value);

-- ---------------------------------------------------------------- customers
CREATE TABLE IF NOT EXISTS customers (
    id             INTEGER PRIMARY KEY,
    reference      TEXT NOT NULL UNIQUE,
    customer_type  TEXT NOT NULL,            -- natural | legal
    full_name      TEXT NOT NULL,
    name_arabic    TEXT,
    canonical_key  TEXT NOT NULL,
    nationality    TEXT,
    country        TEXT,
    birth_date     TEXT,
    gender         TEXT,
    id_number      TEXT,
    id_type        TEXT,
    trade_licence  TEXT,
    sector         TEXT,
    delivery_channel TEXT,
    is_cash_intensive INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'active',
    onboarded_at   TEXT NOT NULL,
    -- Cabinet Res. 134/2025 requires records retained 5 years after the
    -- relationship ends; this column is what the retention job reads.
    retention_until TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_cust_canon ON customers(canonical_key);

-- Beneficial owners. MOET requires screening BOs and related persons, not
-- just the contracting party, so these are first-class screenable records.
CREATE TABLE IF NOT EXISTS ubo_links (
    id            INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    person_name   TEXT NOT NULL,
    name_arabic   TEXT,
    canonical_key TEXT NOT NULL,
    nationality   TEXT,
    birth_date    TEXT,
    ownership_pct REAL,
    control_type  TEXT NOT NULL DEFAULT 'ownership', -- ownership | senior_official | other
    is_ubo        INTEGER NOT NULL DEFAULT 1,
    notes         TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ubo_cust ON ubo_links(customer_id);

-- ---------------------------------------------------------------- screening
CREATE TABLE IF NOT EXISTS screenings (
    id            INTEGER PRIMARY KEY,
    customer_id   INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    ubo_id        INTEGER REFERENCES ubo_links(id) ON DELETE SET NULL,
    query_name    TEXT NOT NULL,
    trigger       TEXT NOT NULL,   -- onboarding | list_update | periodic | transaction | adhoc
    algorithm     TEXT NOT NULL,
    threshold     REAL NOT NULL,
    candidates    INTEGER NOT NULL DEFAULT 0,
    hits          INTEGER NOT NULL DEFAULT 0,
    datasets_used TEXT,            -- json array of dataset keys screened against
    run_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_scr_cust ON screenings(customer_id);

CREATE TABLE IF NOT EXISTS alerts (
    id            INTEGER PRIMARY KEY,
    screening_id  INTEGER NOT NULL REFERENCES screenings(id) ON DELETE CASCADE,
    entity_id     INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    score         REAL NOT NULL,
    -- Full per-feature breakdown. Stored because an examiner will ask "why
    -- did this alert fire" and "the algorithm said so" is not an answer.
    score_detail  TEXT NOT NULL,
    matched_name  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'open',  -- open | true_positive | false_positive | escalated
    disposition   TEXT,
    dispositioned_by TEXT,
    dispositioned_at TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_alert_status ON alerts(status);
CREATE INDEX IF NOT EXISTS ix_alert_scr    ON alerts(screening_id);

-- ---------------------------------------------------------------- risk & CDD
CREATE TABLE IF NOT EXISTS risk_assessments (
    id           INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    score        REAL NOT NULL,
    rating       TEXT NOT NULL,             -- low | medium | high
    factors      TEXT NOT NULL,             -- json: per-factor contributions
    ruleset_version TEXT NOT NULL,
    requires_edd INTEGER NOT NULL DEFAULT 0,
    assessed_at  TEXT NOT NULL,
    next_review  TEXT
);
CREATE INDEX IF NOT EXISTS ix_risk_cust ON risk_assessments(customer_id);

CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    doc_type    TEXT NOT NULL,
    filename    TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    uploaded_at TEXT NOT NULL
);

-- ---------------------------------------------------------------- reporting
CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    alert_id    INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    report_type TEXT NOT NULL,              -- STR | SAR | FFR | PNMR
    reference   TEXT,
    status      TEXT NOT NULL DEFAULT 'draft',
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    submitted_at TEXT
);

-- ---------------------------------------------------------------- audit
CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY,
    ts         TEXT NOT NULL,
    actor      TEXT NOT NULL,
    action     TEXT NOT NULL,
    object_type TEXT,
    object_id  TEXT,
    detail     TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_log(ts);

-- Append-only enforcement. Any UPDATE or DELETE against the audit log aborts
-- at the database level, so tampering requires bypassing the application
-- entirely rather than merely calling a different function.
CREATE TRIGGER IF NOT EXISTS audit_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Columns added after the initial schema. `CREATE TABLE IF NOT EXISTS` will not
# alter an existing table, so databases created by an earlier version need the
# column added explicitly rather than silently lacking it.
_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("entities", "programs", "ALTER TABLE entities ADD COLUMN programs TEXT"),
)


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, ddl in _MIGRATIONS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(ddl)


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection with sane defaults and the schema applied."""
    target = Path(path) if path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def audit(
    conn: sqlite3.Connection,
    actor: str,
    action: str,
    object_type: str | None = None,
    object_id: str | int | None = None,
    detail: Any = None,
) -> None:
    """Write an audit entry. Never raises on serialisation of `detail`."""
    conn.execute(
        "INSERT INTO audit_log (ts, actor, action, object_type, object_id, detail)"
        " VALUES (?,?,?,?,?,?)",
        (
            utcnow(),
            actor,
            action,
            object_type,
            str(object_id) if object_id is not None else None,
            json.dumps(detail, ensure_ascii=False, default=str) if detail is not None else None,
        ),
    )


def upsert_dataset(
    conn: sqlite3.Connection,
    key: str,
    title: str,
    publisher: str = "",
    source_url: str = "",
    licence: str = "",
    is_mandatory: bool = False,
) -> int:
    conn.execute(
        """INSERT INTO datasets (key, title, publisher, source_url, licence, is_mandatory)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(key) DO UPDATE SET
             title=excluded.title, publisher=excluded.publisher,
             source_url=excluded.source_url, licence=excluded.licence,
             is_mandatory=excluded.is_mandatory""",
        (key, title, publisher, source_url, licence, int(is_mandatory)),
    )
    row = conn.execute("SELECT id FROM datasets WHERE key=?", (key,)).fetchone()
    return int(row["id"])


def fetch_all(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, tuple(params)).fetchall()
