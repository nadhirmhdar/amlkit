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

# Distinguishes "org_id not passed at all" from "org_id passed as None", since
# None is itself a meaningful, deliberate value for audit() (see below).
_UNSET = object()

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

-- ---------------------------------------------------------------- tenancy
CREATE TABLE IF NOT EXISTS organizations (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    slug       TEXT NOT NULL UNIQUE,
    status     TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

-- Session tokens are stored hashed, exactly like a password would be -- the
-- raw token exists only in the browser cookie and briefly in memory on the
-- server. org_id and operator_id are snapshotted at login rather than
-- re-derived by a live join: if an operator is later moved between orgs,
-- deactivated, or has their password changed, every session row for that
-- operator is explicitly revoked at that moment (see auth.py) rather than
-- being left to silently drift out of sync with a join.
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY,
    token_hash  TEXT NOT NULL UNIQUE,
    operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
    org_id      INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    revoked_at  TEXT
);
CREATE INDEX IF NOT EXISTS ix_sessions_token    ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS ix_sessions_operator ON sessions(operator_id);

-- Login attempts, logouts and password resets. Deliberately separate from
-- audit_log and NOT org-scoped: a failed login against an unrecognised email
-- has no known org, and this table exists for lockout/rate-limiting and
-- security forensics, not for the compliance evidence pack.
CREATE TABLE IF NOT EXISTS auth_log (
    id              INTEGER PRIMARY KEY,
    ts              TEXT NOT NULL,
    email_attempted TEXT,
    event           TEXT NOT NULL,   -- login_success|login_failure|logout|password_reset|lockout
    ip              TEXT,
    detail          TEXT
);
CREATE INDEX IF NOT EXISTS ix_authlog_ts    ON auth_log(ts);
CREATE INDEX IF NOT EXISTS ix_authlog_email ON auth_log(email_attempted);

-- One-time tokens for claiming the first admin login after a fresh-from-v1
-- migration. Hashed at rest like everything else login-adjacent; the raw
-- value only ever appears once, printed to the console at startup.
CREATE TABLE IF NOT EXISTS setup_tokens (
    id         INTEGER PRIMARY KEY,
    org_id     INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    used_at    TEXT,
    created_at TEXT NOT NULL
);

-- ---------------------------------------------------------------- customers
CREATE TABLE IF NOT EXISTS customers (
    id             INTEGER PRIMARY KEY,
    org_id         INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    -- Unique per firm, not globally: two different client firms will
    -- plausibly both use "C-1001" as their own first reference. Globally
    -- unique would let one firm's onboarding fail because of a collision
    -- with another firm's data it can never see.
    reference      TEXT NOT NULL,
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
    updated_at     TEXT NOT NULL,
    UNIQUE (org_id, reference)
);
CREATE INDEX IF NOT EXISTS ix_cust_canon ON customers(canonical_key);
-- ix_cust_org is created in Python, after migration, not here: on an
-- upgraded (not fresh) database this table's org_id column does not exist
-- yet at the point this script runs -- see _create_org_indexes() below.

-- Beneficial owners. MOET requires screening BOs and related persons, not
-- just the contracting party, so these are first-class screenable records.
-- org_id is denormalized from customers.org_id (customer_id is always
-- present here) so every tenant-scoped table can be filtered directly on
-- org_id without a join -- see the note on the alerts table below.
CREATE TABLE IF NOT EXISTS ubo_links (
    id            INTEGER PRIMARY KEY,
    org_id        INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
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
    -- org_id is required even though customer_id is not: an ad-hoc screening
    -- (customer_id NULL) still belongs to whichever firm's operator ran it,
    -- and that is the only way to scope it -- there is no customer row to
    -- derive it from.
    org_id        INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
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
    -- Denormalized from screenings.org_id. Every tenant table in this schema
    -- carries org_id directly rather than requiring a join to enforce the
    -- boundary -- a fetch function can filter "WHERE org_id = ?" on its own
    -- table with no risk of a join being written (or later refactored) in a
    -- way that quietly drops the tenant filter.
    org_id        INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
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

-- Operators are both the audit-trail actor identity AND, from this version,
-- the login credential. `name` stays the audit-facing display identity;
-- `email` is the login handle and is globally unique -- this is what lets
-- login be a single email+password form with no organization-picker screen.
-- `name` is only unique WITHIN an org (two different firms will plausibly
-- both have an "Ahmed"), which is why this is org-scoped rather than the
-- original bare UNIQUE(name).
--
-- On a fresh install this CREATE TABLE gives the final shape directly. On an
-- upgrade from the pre-tenancy version, this statement is a no-op (the table
-- already exists) and `_migrate_operators_table()` below performs the
-- rebuild that changes the uniqueness constraint, which SQLite cannot do via
-- a plain ALTER TABLE.
CREATE TABLE IF NOT EXISTS operators (
    id                 INTEGER PRIMARY KEY,
    org_id             INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
    name               TEXT NOT NULL,
    email              TEXT UNIQUE,
    password_hash      TEXT,
    role               TEXT NOT NULL DEFAULT 'officer',   -- officer | mlro
    is_active          INTEGER NOT NULL DEFAULT 1,
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until       TEXT,
    created_at         TEXT NOT NULL,
    UNIQUE (org_id, name)
);
-- ix_operators_org: see the note by ix_cust_org above -- created in Python
-- after migration, not here.

-- Each review step is a row rather than an overwritten field. Four-eyes is
-- meaningless if the first reviewer's proposal disappears when the second
-- confirms it -- the whole point is that both decisions survive.
CREATE TABLE IF NOT EXISTS alert_reviews (
    id          INTEGER PRIMARY KEY,
    org_id      INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    alert_id    INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    action      TEXT NOT NULL,       -- propose | confirm | override
    status      TEXT NOT NULL,       -- the disposition being proposed/applied
    reason_code TEXT NOT NULL,
    narrative   TEXT,
    operator    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_review_alert ON alert_reviews(alert_id);

-- ---------------------------------------------------------------- risk & CDD
CREATE TABLE IF NOT EXISTS risk_assessments (
    id           INTEGER PRIMARY KEY,
    org_id       INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
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
    org_id      INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    doc_type    TEXT NOT NULL,
    filename    TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    uploaded_at TEXT NOT NULL
);
-- ix_documents_org: created in Python after migration, see note above.

-- ---------------------------------------------------------------- reporting
CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY,
    org_id      INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    alert_id    INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    report_type TEXT NOT NULL,              -- STR | SAR | FFR | PNMR
    reference   TEXT,
    status      TEXT NOT NULL DEFAULT 'draft',
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    submitted_at TEXT
);
-- ix_reports_org: created in Python after migration, see note above.

-- ---------------------------------------------------------------- audit
-- org_id is nullable here alone: a handful of actions (sanctions-list
-- refreshes) act on shared reference data and are not tenant-specific. Every
-- org is shown those rows in addition to its own -- they carry no PII and
-- knowing when a list last refreshed is relevant to every firm's compliance
-- posture. Every other action writes a real org_id.
CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY,
    org_id     INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
    ts         TEXT NOT NULL,
    actor      TEXT NOT NULL,
    action     TEXT NOT NULL,
    object_type TEXT,
    object_id  TEXT,
    detail     TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_ts  ON audit_log(ts);
-- ix_audit_org: created in Python after migration, see note above.

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
#
# org_id on these eight tables is added here as a plain nullable column: none
# of them had a UNIQUE constraint that needs changing (unlike `customers` and
# `operators`, which get the full rebuild treatment below because SQLite
# cannot ALTER a column's uniqueness scope in place). It is nullable at the
# schema level only because SQLite cannot add a NOT NULL column to a
# populated table without a full rebuild; `_migrate_tenancy_data()` backfills
# every row to a real org_id immediately after, and from that point on every
# application code path requires org_id as a mandatory argument on write.
# This is a deliberate, stated tradeoff: a hand-edited database bypassing the
# application is not caught by the schema alone.
_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("entities", "programs", "ALTER TABLE entities ADD COLUMN programs TEXT"),
    ("alerts", "reason_code", "ALTER TABLE alerts ADD COLUMN reason_code TEXT"),
    # How the four-eyes requirement was satisfied, or why it was not:
    #   completed          - a second operator confirmed the dismissal
    #   not_required       - risk category did not call for independent review
    #   single_operator    - firm runs one compliance officer; gap RECORDED
    # Stored rather than inferred so the evidence pack can state it plainly.
    ("alerts", "independent_review", "ALTER TABLE alerts ADD COLUMN independent_review TEXT"),
    ("ubo_links", "org_id", "ALTER TABLE ubo_links ADD COLUMN org_id INTEGER"),
    ("screenings", "org_id", "ALTER TABLE screenings ADD COLUMN org_id INTEGER"),
    ("alerts", "org_id", "ALTER TABLE alerts ADD COLUMN org_id INTEGER"),
    ("alert_reviews", "org_id", "ALTER TABLE alert_reviews ADD COLUMN org_id INTEGER"),
    ("risk_assessments", "org_id", "ALTER TABLE risk_assessments ADD COLUMN org_id INTEGER"),
    ("documents", "org_id", "ALTER TABLE documents ADD COLUMN org_id INTEGER"),
    ("reports", "org_id", "ALTER TABLE reports ADD COLUMN org_id INTEGER"),
    ("audit_log", "org_id", "ALTER TABLE audit_log ADD COLUMN org_id INTEGER"),
)

# Actions that operate on shared reference data (sanctions-list refreshes)
# rather than on a specific firm's case data. These audit_log rows stay
# org_id = NULL forever, visible to every org, since they carry no PII.
_SHARED_AUDIT_ACTIONS = frozenset({"dataset.refresh"})


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, ddl in _MIGRATIONS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(ddl)


def _migrate_operators_table(conn: sqlite3.Connection) -> None:
    """Rebuild `operators` to change its uniqueness constraint.

    The original schema made `name` globally unique, which breaks the moment
    two different organizations both have an "Ahmed". SQLite cannot ALTER a
    column's constraints in place, so this rebuilds the table -- guarded by
    the presence of the `email` column, so it runs exactly once. `foreign_keys`
    is turned off for the duration: `sessions` references `operators(id)` and
    SQLite's documented pattern for restructuring a referenced table is to
    disable enforcement around the rebuild, not to drop the referencing table.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(operators)")}
    if "email" in cols:
        return

    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute(
        """CREATE TABLE operators_new (
             id                 INTEGER PRIMARY KEY,
             org_id             INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
             name               TEXT NOT NULL,
             email              TEXT UNIQUE,
             password_hash      TEXT,
             role               TEXT NOT NULL DEFAULT 'officer',
             is_active          INTEGER NOT NULL DEFAULT 1,
             failed_login_count INTEGER NOT NULL DEFAULT 0,
             locked_until       TEXT,
             created_at         TEXT NOT NULL,
             UNIQUE (org_id, name)
           )"""
    )
    conn.execute(
        """INSERT INTO operators_new (id, name, role, is_active, created_at)
           SELECT id, name, role, is_active, created_at FROM operators"""
    )
    conn.execute("DROP TABLE operators")
    conn.execute("ALTER TABLE operators_new RENAME TO operators")
    conn.execute("PRAGMA foreign_keys=ON")


def _migrate_customers_table(conn: sqlite3.Connection) -> None:
    """Rebuild `customers` for the same reason as operators above.

    `reference` was globally unique; two different firms will plausibly both
    pick "C-1001" as their own first reference. Guarded by the presence of
    the `org_id` column so it runs exactly once.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(customers)")}
    if "org_id" in cols:
        return

    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute(
        """CREATE TABLE customers_new (
             id                INTEGER PRIMARY KEY,
             org_id            INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
             reference         TEXT NOT NULL,
             customer_type     TEXT NOT NULL,
             full_name         TEXT NOT NULL,
             name_arabic       TEXT,
             canonical_key     TEXT NOT NULL,
             nationality       TEXT,
             country           TEXT,
             birth_date        TEXT,
             gender            TEXT,
             id_number         TEXT,
             id_type           TEXT,
             trade_licence     TEXT,
             sector            TEXT,
             delivery_channel  TEXT,
             is_cash_intensive INTEGER NOT NULL DEFAULT 0,
             status            TEXT NOT NULL DEFAULT 'active',
             onboarded_at      TEXT NOT NULL,
             retention_until   TEXT,
             created_at        TEXT NOT NULL,
             updated_at        TEXT NOT NULL,
             UNIQUE (org_id, reference)
           )"""
    )
    conn.execute(
        """INSERT INTO customers_new
           (id, reference, customer_type, full_name, name_arabic, canonical_key,
            nationality, country, birth_date, gender, id_number, id_type,
            trade_licence, sector, delivery_channel, is_cash_intensive, status,
            onboarded_at, retention_until, created_at, updated_at)
           SELECT id, reference, customer_type, full_name, name_arabic, canonical_key,
                  nationality, country, birth_date, gender, id_number, id_type,
                  trade_licence, sector, delivery_channel, is_cash_intensive, status,
                  onboarded_at, retention_until, created_at, updated_at
           FROM customers"""
    )
    conn.execute("DROP TABLE customers")
    conn.execute("ALTER TABLE customers_new RENAME TO customers")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_cust_canon ON customers(canonical_key)")
    conn.execute("PRAGMA foreign_keys=ON")


def _migrate_tenancy_data(conn: sqlite3.Connection) -> str | None:
    """One-time backfill: create a default org, assign every pre-tenancy row
    to it, and print a setup token for claiming the first login.

    Runs once, guarded by whether any row anywhere still has org_id IS NULL
    among tables that require one. A fresh install has zero rows in these
    tables, so the guard is vacuously false and this is a correct no-op.

    Prints the raw (unhashed) setup token to the console when one is
    generated -- the only place it ever exists in plaintext. This fires
    exactly once, on the single real upgrade from a pre-tenancy database,
    never on ordinary connect() calls (a fresh install has nothing to
    migrate) and never in tests (which use `:memory:` databases that start
    empty). Also returns the token, purely so tests can assert on it without
    scraping stdout.
    """
    import secrets

    legacy = conn.execute(
        "SELECT COUNT(*) c FROM customers WHERE org_id IS NULL"
    ).fetchone()["c"]
    if legacy == 0:
        # Either a fresh install (no customers at all) or already migrated.
        return None

    now = utcnow()
    cur = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?)",
        ("Grovisor Business Consultants", "grovisor", "active", now),
    )
    org_id = cur.lastrowid

    for table in (
        "customers", "ubo_links", "screenings", "alerts", "alert_reviews",
        "risk_assessments", "documents", "reports", "operators",
    ):
        conn.execute(f"UPDATE {table} SET org_id=? WHERE org_id IS NULL", (org_id,))

    # audit_log: everything EXCEPT the shared-reference-data actions gets the
    # default org. dataset.refresh rows stay NULL -- shared across every org.
    #
    # This is the one legitimate exception to "audit_log is append-only": the
    # trigger exists to stop someone rewriting WHAT happened (actor, action,
    # detail, timestamp). This UPDATE touches none of that -- it only
    # populates a structural column that did not exist, and could not have
    # been populated, at the time these rows were written, because the
    # concept of "organization" did not exist yet. Leaving it NULL forever
    # was considered and rejected: NULL is reserved for genuinely shared
    # rows visible to every org, and a historical customer.onboard row is
    # tenant-owned data, not shared data -- leaving it NULL would mean either
    # hiding a firm's own history from itself, or leaking it to every other
    # org that later joins the deployment. Trigger is dropped and recreated
    # around this single, narrow, one-time statement rather than weakened
    # generally.
    conn.execute("DROP TRIGGER audit_no_update")
    placeholders = ",".join("?" * len(_SHARED_AUDIT_ACTIONS))
    conn.execute(
        f"UPDATE audit_log SET org_id=? WHERE org_id IS NULL AND action NOT IN ({placeholders})",
        (org_id, *_SHARED_AUDIT_ACTIONS),
    )
    conn.execute(
        "CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log "
        "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END"
    )

    # password_hash is already NULL by column default on every pre-existing
    # operator row; the login guard checks this explicitly (see auth.py) so
    # none of alice/bob/nadhir.mlro/solo/system can log in until an admin
    # sets a real password for them.
    raw_token = secrets.token_urlsafe(32)
    from hashlib import sha256

    token_hash = sha256(raw_token.encode()).hexdigest()
    conn.execute(
        "INSERT INTO setup_tokens (org_id, token_hash, created_at) VALUES (?,?,?)",
        (org_id, token_hash, now),
    )
    print(
        "\n" + "=" * 72 +
        "\namlkit: upgraded to multi-tenant. Existing data assigned to a new\n"
        f"organization: \"Grovisor Business Consultants\".\n\n"
        f"One-time setup link (used once, then invalid):\n"
        f"  /setup?token={raw_token}\n\n"
        "Use it to create the first login for this organization. Existing\n"
        "operator names from before this upgrade cannot log in until an\n"
        "admin sets a password for them.\n" + "=" * 72 + "\n"
    )
    return raw_token


# org_id indexes for tables that may pre-date tenancy. Created here, after
# every migration step, rather than inline in SCHEMA: on an upgraded (not
# fresh) database the column does not exist until the corresponding
# migration has run, and CREATE INDEX inside the initial executescript()
# pass happens before any Python migration code runs at all.
_ORG_INDEXES: tuple[tuple[str, str], ...] = (
    ("ix_cust_org", "customers"),
    ("ix_ubo_org", "ubo_links"),
    ("ix_scr_org", "screenings"),
    ("ix_alert_org", "alerts"),
    ("ix_operators_org", "operators"),
    ("ix_review_org", "alert_reviews"),
    ("ix_risk_org", "risk_assessments"),
    ("ix_documents_org", "documents"),
    ("ix_reports_org", "reports"),
    ("ix_audit_org", "audit_log"),
)


def _create_org_indexes(conn: sqlite3.Connection) -> None:
    for name, table in _ORG_INDEXES:
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table}(org_id)")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection with sane defaults and the schema applied.

    Migration order matters: the table rebuilds must run before the
    column-add migrations touch tables that reference them, the org_id
    indexes must be created only after every column they index actually
    exists, and the data backfill must run last of all.
    """
    target = Path(path) if path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate_operators_table(conn)
    _migrate_customers_table(conn)
    _migrate(conn)
    _create_org_indexes(conn)
    setup_token = _migrate_tenancy_data(conn)
    if setup_token:
        conn.execute(
            "INSERT INTO audit_log (org_id, ts, actor, action, detail) VALUES (NULL,?,?,?,?)",
            (utcnow(), "system", "tenancy.migrated",
             json.dumps({"note": "setup token generated; see console output"})),
        )
    conn.commit()
    return conn


def audit(
    conn: sqlite3.Connection,
    actor: str,
    action: str,
    object_type: str | None = None,
    object_id: str | int | None = None,
    detail: Any = None,
    *,
    org_id: int | None = _UNSET,
) -> None:
    """Write an audit entry. Never raises on serialisation of `detail`.

    `org_id` is keyword-only and has no default -- every call site must state
    one explicitly, even if the explicit choice is `None` for the small set of
    actions on shared reference data (see `_SHARED_AUDIT_ACTIONS`). This is
    the same "structural, not per-call-site discipline" reasoning applied to
    tenant scoping elsewhere: a forgotten `org_id` fails loudly here rather
    than silently writing a NULL that then can't be attributed to any firm.
    """
    if org_id is _UNSET:
        raise TypeError(
            "audit() requires org_id explicitly -- pass the acting org's id, "
            "or org_id=None only for actions on shared reference data"
        )
    conn.execute(
        "INSERT INTO audit_log (org_id, ts, actor, action, object_type, object_id, detail)"
        " VALUES (?,?,?,?,?,?,?)",
        (
            org_id,
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
