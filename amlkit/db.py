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

import functools
import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "aml.db"


def retry_on_lock(max_retries: int = 3, base_delay: float = 0.1):
    """Retry a function on SQLite "database is locked" errors.

    busy_timeout handles the common case, but a long-running refresh can
    hold the WAL lock beyond the PRAGMA timeout. This decorator retries
    the entire operation with exponential backoff.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except sqlite3.OperationalError as exc:
                    if "locked" not in str(exc):
                        raise
                    last_err = exc
                    if attempt < max_retries:
                        time.sleep(base_delay * (2 ** attempt))
            raise last_err
        return wrapper
    return decorator


# Distinguishes "org_id not passed at all" from "org_id passed as None", since
# None is itself a meaningful, deliberate value for audit() (see below).
_UNSET = object()

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
-- WAL lets readers and a writer proceed concurrently, but two WRITERS still
-- serialize -- without a busy_timeout, the second one gets an immediate
-- "database is locked" OperationalError instead of waiting. Real trigger:
-- the /system/refresh endpoint now holds a connection open for the whole
-- duration of a synchronous multi-source refresh (see api/app.py), which
-- widens the window for an ordinary request's write to land mid-refresh.
-- 30s is comfortably longer than any single write in this codebase takes.
PRAGMA busy_timeout = 30000;

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
    entity_count  INTEGER NOT NULL DEFAULT 0,
    max_age_hours INTEGER NOT NULL DEFAULT 24, -- breach threshold; 24 = daily (sanctions), 2160 = 90d (FATF)
    last_error    TEXT,                        -- last refresh failure message, NULL when healthy
    error_at      TEXT                         -- UTC timestamp of last_error
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
    created_at TEXT NOT NULL,
    -- goAML reporting entity profile fields (p46)
    org_address            TEXT,
    reporting_person_name  TEXT,
    reporting_person_title TEXT,
    reporting_person_phone TEXT
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
-- expires_at bounds how long a forwarded, archived, or leaked setup email
-- stays a live path to create an admin account -- unlike session tokens
-- (SESSION_LIFETIME), this table originally carried no time bound at all.
CREATE TABLE IF NOT EXISTS setup_tokens (
    id         INTEGER PRIMARY KEY,
    org_id     INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    used_at    TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT
);

-- One-time link that proves a registering operator controls the email
-- address they signed up with (see auth.py's login() guard and
-- amlkit/mail.py). operator_id, not org_id: unlike setup_tokens (which
-- creates the operator row on redemption), the operator row here already
-- exists at token-creation time -- registration inserts it immediately, and
-- this token only flips email_verified_at. Hashed at rest for the same
-- reason every other token in this file is: the raw value is a credential
-- for as long as it's live.
CREATE TABLE IF NOT EXISTS email_verify_tokens (
    id          INTEGER PRIMARY KEY,
    operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    used_at     TEXT,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_email_verify_operator ON email_verify_tokens(operator_id);

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
    -- Cabinet Res. 134/2025 requires records retained 8 years after the
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
    is_nominee    INTEGER NOT NULL DEFAULT 0,
    parent_ubo_id INTEGER REFERENCES ubo_links(id) ON DELETE SET NULL,
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
    assigned_to   TEXT,  -- operator name; workflow routing only, not a privilege
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
    -- NULL until the operator clicks the link in their verification email
    -- (see email_verify_tokens below and auth.py's login() guard). Separate
    -- from is_active: is_active is an admin's on/off switch for an operator
    -- that already proved their email once, this is that one-time proof.
    email_verified_at  TEXT,
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

-- Case-level investigative narrative not tied to any one alert -- periodic
-- review commentary, source-of-wealth notes, anything an officer needs to
-- record about a customer that isn't a disposition decision.
CREATE TABLE IF NOT EXISTS case_notes (
    id          INTEGER PRIMARY KEY,
    org_id      INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    author      TEXT NOT NULL,
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_notes_cust ON case_notes(customer_id);
CREATE INDEX IF NOT EXISTS ix_notes_org  ON case_notes(org_id);

-- Per-org configuration. Currently just the alert threshold; deliberately a
-- single key-value row per org rather than a "screening profiles" system --
-- that is real complexity with no evidenced need yet (see research notes).
CREATE TABLE IF NOT EXISTS org_settings (
    org_id           INTEGER PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    alert_threshold  REAL,
    updated_at       TEXT NOT NULL
);

-- ------------------------------------------------------------ transaction monitoring (KYT)
-- amount_aed is a normalized copy of amount for threshold comparisons across
-- currencies -- the rule engine never has to know exchange rates, and a
-- transaction recorded in a foreign currency still triggers correctly. The
-- caller (record_transaction) computes it; this table trusts what it is given.
CREATE TABLE IF NOT EXISTS transactions (
    id            INTEGER PRIMARY KEY,
    org_id        INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    customer_id   INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    reference     TEXT,
    direction     TEXT NOT NULL,             -- inbound | outbound
    method        TEXT NOT NULL DEFAULT 'other',  -- cash | wire | cheque | crypto | other
    amount        REAL NOT NULL,
    currency      TEXT NOT NULL DEFAULT 'AED',
    amount_aed    REAL NOT NULL,
    counterparty_name    TEXT,
    counterparty_country TEXT,               -- ISO-3166 alpha-2, upper-case
    occurred_at   TEXT NOT NULL,
    recorded_by   TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_txn_cust     ON transactions(customer_id);
CREATE INDEX IF NOT EXISTS ix_txn_org      ON transactions(org_id);
CREATE INDEX IF NOT EXISTS ix_txn_occurred ON transactions(occurred_at);

-- One row per rule that fired, not one row per transaction: a single
-- transaction can trip more than one rule (e.g. large cash AND a high-risk
-- counterparty country at once), and each is its own disposition decision --
-- collapsing them into one alert would let a reviewer clear the obvious one
-- and silently drop the other. Deliberately a separate table from `alerts`
-- rather than reusing it: `alerts` structurally requires screening_id and
-- entity_id (an entity-match alert), which don't exist for a rule trigger on
-- a transaction. Four-eyes review is NOT applied here (see kyt.py) -- a
-- narrower scope decision than sanctions/PF alerts, stated explicitly rather
-- than left to be discovered.
CREATE TABLE IF NOT EXISTS transaction_alerts (
    id             INTEGER PRIMARY KEY,
    org_id         INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    customer_id    INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    rule_key       TEXT NOT NULL,       -- large_cash | structuring | high_risk_country | velocity
    severity       TEXT NOT NULL DEFAULT 'medium',  -- low | medium | high
    detail         TEXT NOT NULL,       -- json: what tripped it, threshold vs actual
    status         TEXT NOT NULL DEFAULT 'open',    -- open | true_positive | false_positive
    disposition    TEXT,
    dispositioned_by TEXT,
    dispositioned_at TEXT,
    assigned_to    TEXT,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_txnalert_status ON transaction_alerts(status);
CREATE INDEX IF NOT EXISTS ix_txnalert_org    ON transaction_alerts(org_id);
CREATE INDEX IF NOT EXISTS ix_txnalert_cust   ON transaction_alerts(customer_id);

-- ------------------------------------------------------------ adverse media
-- Adverse media is a query-time check against an external news index (GDELT),
-- not a list that gets ingested, so it gets its own pair of tables rather than
-- reusing `screenings`/`alerts`: those structurally require an entity_id
-- pointing at a row in `entities`, and a news article is not a listed entity.
--
-- The run row is written even when the provider was unreachable. That is the
-- point of `status`: "we checked and found nothing" and "the check could not
-- run" are different facts about a customer's file, and a compliance record
-- that cannot tell them apart is worse than one that records no check at all.
CREATE TABLE IF NOT EXISTS adverse_media_screenings (
    id            INTEGER PRIMARY KEY,
    org_id        INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    -- Nullable for the same reason `screenings.customer_id` is: an ad-hoc
    -- search of a name nobody has onboarded yet is still that firm's record.
    customer_id   INTEGER REFERENCES customers(id) ON DELETE CASCADE,
    ubo_id        INTEGER REFERENCES ubo_links(id) ON DELETE SET NULL,
    query_name    TEXT NOT NULL,
    query_arabic  TEXT,
    trigger       TEXT NOT NULL,   -- onboarding | periodic | adhoc | review
    provider      TEXT NOT NULL DEFAULT 'gdelt',
    window_months INTEGER NOT NULL,
    status        TEXT NOT NULL,   -- ok | unavailable
    -- Set on 'ok' too, when one script's query succeeded and the other did
    -- not: partial coverage is recorded rather than rounded up to full.
    error         TEXT,
    articles_considered INTEGER NOT NULL DEFAULT 0,
    findings      INTEGER NOT NULL DEFAULT 0,
    severity      TEXT NOT NULL DEFAULT 'none',
    run_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_am_scr_org  ON adverse_media_screenings(org_id);
CREATE INDEX IF NOT EXISTS ix_am_scr_cust ON adverse_media_screenings(customer_id);

-- One row per article that mentioned the name AND carried a risk term.
-- Metadata and a link only -- never article text. GDELT's own data is free
-- for commercial use, but the articles it indexes belong to their publishers,
-- and storing their text would be republishing someone else's copyright under
-- this tool's name.
CREATE TABLE IF NOT EXISTS adverse_media_findings (
    id            INTEGER PRIMARY KEY,
    org_id        INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    screening_id  INTEGER NOT NULL REFERENCES adverse_media_screenings(id) ON DELETE CASCADE,
    customer_id   INTEGER REFERENCES customers(id) ON DELETE CASCADE,
    url           TEXT NOT NULL,
    title         TEXT NOT NULL,
    domain        TEXT,
    language      TEXT,
    source_country TEXT,
    published_at  TEXT,
    -- Matches the keys of factors.adverse_media.points_by_severity in
    -- risk/ruleset.yaml exactly, so a finding marked relevant feeds the risk
    -- model with no translation step that could drift out of sync.
    severity      TEXT NOT NULL,
    matched_terms TEXT NOT NULL,   -- json array: why this was classified so
    -- 'title' if the screened name is in the headline, 'body' if GDELT
    -- matched it in text we never see. Recorded, not used to filter: see
    -- screening/adverse_media.py:_name_evidence.
    name_evidence TEXT NOT NULL DEFAULT 'body',
    -- open | relevant | not_relevant. Only 'relevant' feeds the risk model:
    -- a news index cannot decide that an article is about this customer, so
    -- a human decides before anything touches a rating.
    status        TEXT NOT NULL DEFAULT 'open',
    disposition   TEXT,
    dispositioned_by TEXT,
    dispositioned_at TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_am_find_org    ON adverse_media_findings(org_id);
CREATE INDEX IF NOT EXISTS ix_am_find_cust   ON adverse_media_findings(customer_id);
CREATE INDEX IF NOT EXISTS ix_am_find_status ON adverse_media_findings(status);

-- ------------------------------------------------------ Google Cloud media pipeline
-- The "Audit Vault" for screening/media_pipeline.py: a 4-stage pipeline
-- (BigQuery GKG + GDELT DOC + Vertex AI Search acquisition -> Knowledge Graph
-- + Natural Language entity resolution -> Gemini triage) that is a richer,
-- optional *implementation* of adverse-media screening, gated by
-- AMLKIT_MEDIA_PIPELINE. It is not a replacement for the tables above: every
-- pipeline-sourced finding an operator should be able to disposition is ALSO
-- written into adverse_media_findings (see cases/manager.py) so the existing
-- disposition/four-eyes/risk-reassessment flow needs no changes at all. These
-- two tables exist purely so the *evidence for a triage decision* -- which
-- sources were queried, what salience/sentiment/KG-match/model produced a
-- given finding -- is never lost, even though only a handful of that detail
-- fits in adverse_media_findings' existing columns.
CREATE TABLE IF NOT EXISTS media_pipeline_runs (
    id                 INTEGER PRIMARY KEY,
    org_id             INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    customer_id        INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    trigger            TEXT NOT NULL,   -- onboarding | periodic | adhoc | review
    status             TEXT NOT NULL,   -- ok | partial | unavailable
    query_name         TEXT NOT NULL,
    query_arabic       TEXT,
    -- json: {"gdelt_doc": n, "gdelt_bq": n, "vertex_search": n} -- how many
    -- candidate articles each acquisition source contributed, even ones later
    -- dropped at entity-resolution or triage. Lets a reviewer tell "Vertex AI
    -- Search found nothing" apart from "Vertex AI Search was never queried".
    sources_queried    TEXT NOT NULL,
    articles_considered INTEGER NOT NULL DEFAULT 0,
    articles_relevant   INTEGER NOT NULL DEFAULT 0,
    -- json array of adapter-level error strings (never article text or PII --
    -- see amlkit/pii.py and screening/media_pipeline.py's logging discipline).
    errors             TEXT,
    started_at         TEXT NOT NULL,
    finished_at        TEXT,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_mp_run_org  ON media_pipeline_runs(org_id);
CREATE INDEX IF NOT EXISTS ix_mp_run_cust ON media_pipeline_runs(customer_id);

-- One row per article the pipeline scored, whether or not it was ultimately
-- judged relevant -- a triage run that found "nothing adverse" needs the same
-- kind of evidence trail as one that found something, per the reasoning
-- already established for adverse_media_screenings above.
CREATE TABLE IF NOT EXISTS media_pipeline_articles (
    id             INTEGER PRIMARY KEY,
    org_id         INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    run_id         INTEGER NOT NULL REFERENCES media_pipeline_runs(id) ON DELETE CASCADE,
    customer_id    INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    url            TEXT NOT NULL,
    source         TEXT NOT NULL,   -- gdelt_doc | gdelt_bq | vertex_search
    title          TEXT,
    domain         TEXT,
    language       TEXT,
    published_at   TEXT,
    -- Entity resolution (stage 2). NULL when AMLKIT_NL_ENABLED=0 and the
    -- keyword/name-evidence fallback was used instead -- a NULL salience is a
    -- different fact from a NL call that scored the entity at 0.0.
    salience          REAL,
    sentiment_score   REAL,
    sentiment_magnitude REAL,
    kg_match          INTEGER NOT NULL DEFAULT 0,
    -- Triage (stage 3).
    relevant          INTEGER NOT NULL DEFAULT 0,
    categories        TEXT,   -- json array, FATF predicate-offence categories
    severity          TEXT NOT NULL DEFAULT 'none',
    rationale         TEXT,
    english_headline  TEXT,
    model_id          TEXT,   -- e.g. gemini-2.5-flash, or NULL for the keyword fallback
    prompt_version    TEXT,   -- e.g. media-triage-v1:ab12cd34
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_mp_art_org  ON media_pipeline_articles(org_id);
CREATE INDEX IF NOT EXISTS ix_mp_art_run  ON media_pipeline_articles(run_id);
CREATE INDEX IF NOT EXISTS ix_mp_art_cust ON media_pipeline_articles(customer_id);

-- ------------------------------------------------------------ electronic signatures
-- content_hash is computed by the caller over the exact acknowledgment text
-- shown to the signer at signing time (see cases/manager.py:record_signature).
-- Storing the hash rather than trusting `purpose` alone means a later change
-- to a report/acknowledgment template can never be mistaken for what a past
-- signer actually agreed to -- the hash only matches the text that was
-- literally on screen at signed_at.
CREATE TABLE IF NOT EXISTS signatures (
    id              INTEGER PRIMARY KEY,
    org_id          INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    customer_id     INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    purpose         TEXT NOT NULL,
    statement       TEXT NOT NULL,
    signer_name     TEXT NOT NULL,
    signer_role     TEXT NOT NULL DEFAULT 'customer',  -- customer | operator
    content_hash    TEXT NOT NULL,
    ip_address      TEXT,
    user_agent      TEXT,
    signed_by       TEXT NOT NULL,       -- operator who captured it (audit actor)
    signed_at       TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sig_cust ON signatures(customer_id);
CREATE INDEX IF NOT EXISTS ix_sig_org  ON signatures(org_id);

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

-- ---------------------------------------------------------- TFS freeze tracking
-- Targeted Financial Sanctions freeze obligations. Cabinet Resolution 134 of
-- 2025 places personal liability on senior management for TFS compliance
-- failures, so every freeze-and-report decision requires a full audit trail.
-- Lifecycle: identified → executed → reported → resolved.
CREATE TABLE IF NOT EXISTS freeze_obligations (
    id                INTEGER PRIMARY KEY,
    org_id            INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    customer_id       INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    alert_id          INTEGER REFERENCES alerts(id) ON DELETE SET NULL,

    -- Classification: sanctions (generic) | proliferation (Law 10/2025) | terrorism
    obligation_type   TEXT NOT NULL,
    risk_category     TEXT NOT NULL,  -- high | critical

    -- Lifecycle timestamps (NULL = not yet reached that stage)
    identified_at     TEXT NOT NULL,
    identified_by     TEXT NOT NULL,
    executed_at       TEXT,
    executed_by       TEXT,
    reported_at       TEXT,
    report_id         INTEGER REFERENCES reports(id) ON DELETE SET NULL,
    resolved_at       TEXT,
    resolved_by       TEXT,
    resolution_reason TEXT,           -- delisted | false_positive | authority_clearance

    -- Details
    assets_frozen     TEXT,           -- JSON: [{"type": "...", "identifier": "...", "amount_aed": ...}]
    authority_ref     TEXT,           -- external reference from FIU/regulator
    notes             TEXT,

    -- Status: pending_execution | executed_pending_report | reported | resolved
    status            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_freeze_org      ON freeze_obligations(org_id);
CREATE INDEX IF NOT EXISTS ix_freeze_customer ON freeze_obligations(customer_id);
CREATE INDEX IF NOT EXISTS ix_freeze_status   ON freeze_obligations(status);

-- -------------------------------------------------------- compliance calendar (Phase 4, Item 6)
CREATE TABLE IF NOT EXISTS compliance_deadlines (
    id                 INTEGER PRIMARY KEY,
    org_id             INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    title              TEXT NOT NULL,
    description        TEXT,
    due_date           TEXT NOT NULL,
    recurrence         TEXT,             -- one-time | annual | monthly
    reminder_days_before INTEGER NOT NULL DEFAULT 7,
    completed_at       TEXT,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_deadlines_org ON compliance_deadlines(org_id);
CREATE INDEX IF NOT EXISTS ix_deadlines_due ON compliance_deadlines(due_date);

-- ------------------------------------------------- policy document repository (Phase 4, Item 7)
CREATE TABLE IF NOT EXISTS policy_documents (
    id          INTEGER PRIMARY KEY,
    org_id      INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,        -- AML_Policy | CDD_Procedures | Risk_Methodology | Other
    filename    TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    uploaded_by TEXT NOT NULL,
    uploaded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_policies_org ON policy_documents(org_id);

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

-- ---------------------------------------------------------------- feedback
-- User feedback from pilot users. Deliberately org-scoped so each firm's
-- feedback stays with their own data, not mixed into a global pool.
-- operator_id (not just actor name) so deactivated operators' feedback
-- can be retained per the 10-year rule even after the operator row is gone.
CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY,
    org_id      INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    operator_id INTEGER REFERENCES operators(id) ON DELETE SET NULL,
    page        TEXT NOT NULL,
    message     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_feedback_org ON feedback(org_id);

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

-- ----------------------------------------------------------------- MFA/TOTP (p15)
-- One row per operator; replaced on re-enrolment.
CREATE TABLE IF NOT EXISTS mfa_secrets (
    operator_id  INTEGER PRIMARY KEY REFERENCES operators(id) ON DELETE CASCADE,
    secret       TEXT NOT NULL,
    enrolled_at     TEXT NOT NULL,
    confirmed_at    TEXT,                       -- NULL until the operator proves a first TOTP
    failed_attempts INTEGER NOT NULL DEFAULT 0, -- consecutive wrong codes since the last success
    locked_until    TEXT                        -- set after MFA_MAX_FAILURES; cleared on success
);

-- 10 single-use recovery codes per operator.  code_hash is argon2 so the raw
-- token is never stored; used_at is stamped when consumed.
CREATE TABLE IF NOT EXISTS mfa_backup_codes (
    id          INTEGER PRIMARY KEY,
    operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
    code_hash   TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    used_at     TEXT
);
CREATE INDEX IF NOT EXISTS ix_mfa_backup_operator ON mfa_backup_codes(operator_id);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# How long a setup/registration link stays claimable -- mirrors auth.py's
# SESSION_LIFETIME in spirit (a credential-adjacent token should always carry
# a time bound), just for the one-time admin-claim link rather than a session.
SETUP_TOKEN_LIFETIME = timedelta(days=7)

# Shorter than SETUP_TOKEN_LIFETIME: this link is normally acted on within
# minutes of registering, not forwarded around an org later, so there is
# less reason to keep it live for a week. Resending issues a fresh one.
EMAIL_VERIFY_TOKEN_LIFETIME = timedelta(days=3)


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
    # p15: a secret is only "enrolled" once its first TOTP has been verified;
    # merely opening /mfa/setup must not lock an operator behind a code they
    # never scanned. Pre-existing rows stay unconfirmed and re-enrol at login.
    ("mfa_secrets", "confirmed_at", "ALTER TABLE mfa_secrets ADD COLUMN confirmed_at TEXT"),
    # p15: online brute-force guard for the six-digit code (5 strikes, 15 min).
    ("mfa_secrets", "failed_attempts",
     "ALTER TABLE mfa_secrets ADD COLUMN failed_attempts INTEGER NOT NULL DEFAULT 0"),
    ("mfa_secrets", "locked_until", "ALTER TABLE mfa_secrets ADD COLUMN locked_until TEXT"),
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
    ("alerts", "assigned_to", "ALTER TABLE alerts ADD COLUMN assigned_to TEXT"),
    # NULL on any row from before this migration -- _valid_setup_token()
    # treats a NULL expires_at as already expired (fail closed) rather than
    # backfilling a plausible-but-fictitious expiry for a link that may
    # already have been outstanding for months.
    ("setup_tokens", "expires_at", "ALTER TABLE setup_tokens ADD COLUMN expires_at TEXT"),
    ("operators", "email_verified_at", "ALTER TABLE operators ADD COLUMN email_verified_at TEXT"),
    # Customer contact fields. Not present in the original schema (which was
    # AML-field-only). Added as nullable columns so existing rows are unaffected;
    # the application layer treats empty string and NULL identically on write.
    ("customers", "email",          "ALTER TABLE customers ADD COLUMN email          TEXT"),
    ("customers", "phone",          "ALTER TABLE customers ADD COLUMN phone          TEXT"),
    ("customers", "address_line1",  "ALTER TABLE customers ADD COLUMN address_line1  TEXT"),
    ("customers", "address_line2",  "ALTER TABLE customers ADD COLUMN address_line2  TEXT"),
    ("customers", "city",           "ALTER TABLE customers ADD COLUMN city           TEXT"),
    ("customers", "postal_code",    "ALTER TABLE customers ADD COLUMN postal_code    TEXT"),
    # contact_person / contact_phone / contact_email: the human to actually
    # reach at a legal-entity customer; stored separately from full_name so
    # it does not confuse the name-matching / screening pipeline.
    ("customers", "contact_person", "ALTER TABLE customers ADD COLUMN contact_person TEXT"),
    ("customers", "contact_phone",  "ALTER TABLE customers ADD COLUMN contact_phone  TEXT"),
    ("customers", "contact_email",  "ALTER TABLE customers ADD COLUMN contact_email  TEXT"),
    # p35: CDD enhancement — purpose of relationship and expected activity
    ("customers", "purpose_of_relationship", "ALTER TABLE customers ADD COLUMN purpose_of_relationship TEXT"),
    ("customers", "expected_activity",       "ALTER TABLE customers ADD COLUMN expected_activity       TEXT"),
    ("datasets",  "max_age_hours",  "ALTER TABLE datasets ADD COLUMN max_age_hours INTEGER NOT NULL DEFAULT 24"),
    ("operators", "super_admin",    "ALTER TABLE operators ADD COLUMN super_admin INTEGER NOT NULL DEFAULT 0"),
    ("datasets",  "staleness_notified_at", "ALTER TABLE datasets ADD COLUMN staleness_notified_at TEXT"),
    ("ubo_links", "is_nominee",    "ALTER TABLE ubo_links ADD COLUMN is_nominee INTEGER NOT NULL DEFAULT 0"),
    ("ubo_links", "parent_ubo_id", "ALTER TABLE ubo_links ADD COLUMN parent_ubo_id INTEGER REFERENCES ubo_links(id) ON DELETE SET NULL"),
    ("operators", "disclaimer_acknowledged_at", "ALTER TABLE operators ADD COLUMN disclaimer_acknowledged_at TEXT"),
    ("datasets",  "last_error",    "ALTER TABLE datasets ADD COLUMN last_error TEXT"),
    ("datasets",  "error_at",      "ALTER TABLE datasets ADD COLUMN error_at TEXT"),
    # Document expiry date for KYC documents (passport, Emirates ID, trade license).
    # NULL for documents without an expiry (e.g., incorporation certificates).
    ("documents", "expiry_date", "ALTER TABLE documents ADD COLUMN expiry_date TEXT"),
    # Configurable KYT rule settings (Phase 4, Item 3).
    # NULL means use module defaults from kyt.py.
    ("org_settings", "kyt_large_cash_threshold", "ALTER TABLE org_settings ADD COLUMN kyt_large_cash_threshold REAL"),
    ("org_settings", "kyt_structuring_window_days", "ALTER TABLE org_settings ADD COLUMN kyt_structuring_window_days INTEGER"),
    ("org_settings", "kyt_velocity_window_hours", "ALTER TABLE org_settings ADD COLUMN kyt_velocity_window_hours INTEGER"),
    ("org_settings", "kyt_velocity_max_count", "ALTER TABLE org_settings ADD COLUMN kyt_velocity_max_count INTEGER"),
    ("org_settings", "kyt_high_risk_countries", "ALTER TABLE org_settings ADD COLUMN kyt_high_risk_countries TEXT"),  # JSON list
    # p14: Idle session timeout. NULL on existing sessions; grandfathered until absolute expiry.
    ("sessions", "last_active", "ALTER TABLE sessions ADD COLUMN last_active TEXT"),
    # p38: UBO periodic re-verification tracking
    ("ubo_links", "last_verified_at",  "ALTER TABLE ubo_links ADD COLUMN last_verified_at  TEXT"),
    # p46: Organization goAML reporting entity profile fields
    ("organizations", "org_address",            "ALTER TABLE organizations ADD COLUMN org_address            TEXT"),
    ("organizations", "reporting_person_name",  "ALTER TABLE organizations ADD COLUMN reporting_person_name  TEXT"),
    ("organizations", "reporting_person_title", "ALTER TABLE organizations ADD COLUMN reporting_person_title TEXT"),
    ("organizations", "reporting_person_phone", "ALTER TABLE organizations ADD COLUMN reporting_person_phone TEXT"),
    # p15: MFA login enforcement — track whether MLRO session has passed MFA challenge
    ("sessions", "mfa_verified", "ALTER TABLE sessions ADD COLUMN mfa_verified INTEGER NOT NULL DEFAULT 1"),
    # p36: Enhanced due diligence — risk_level, Source of Wealth, Source of Funds
    ("customers", "risk_level",        "ALTER TABLE customers ADD COLUMN risk_level        TEXT"),
    ("customers", "source_of_wealth",  "ALTER TABLE customers ADD COLUMN source_of_wealth  TEXT"),
    ("customers", "source_of_funds",   "ALTER TABLE customers ADD COLUMN source_of_funds   TEXT"),
    # Follow-up to #231/#142: per-org goAML entity reference (replaces hardcoded "AML-REF")
    ("organizations", "goaml_entity_reference", "ALTER TABLE organizations ADD COLUMN goaml_entity_reference TEXT"),
    # T-008: Google AML AI enum alignment — civil status (ISO 20022) and occupation
    ("customers", "civil_status_code", "ALTER TABLE customers ADD COLUMN civil_status_code TEXT"),
    ("customers", "occupation", "ALTER TABLE customers ADD COLUMN occupation TEXT"),
    # T-007: Exact money amounts — Google Money type (units + nanos).
    # Nullable: backfilled by _backfill_money_columns(); NULL means pre-migration row.
    ("transactions", "amount_units", "ALTER TABLE transactions ADD COLUMN amount_units INTEGER"),
    ("transactions", "amount_nanos", "ALTER TABLE transactions ADD COLUMN amount_nanos INTEGER"),
    # Relationship exit: ISO date + fixed reason code (cases.manager.EXIT_REASONS).
    # NULL while the relationship is open; cleared again on reactivation.
    ("customers", "exit_date",   "ALTER TABLE customers ADD COLUMN exit_date   TEXT"),
    ("customers", "exit_reason", "ALTER TABLE customers ADD COLUMN exit_reason TEXT"),
    # Google Cloud media pipeline (screening/media_pipeline.py): links a
    # legacy adverse_media_findings row back to the richer media_pipeline_runs
    # / media_pipeline_articles audit trail it was surfaced from. NULL for
    # every finding from the pre-pipeline GDELT-only path.
    ("adverse_media_findings", "pipeline_run_id",
     "ALTER TABLE adverse_media_findings ADD COLUMN pipeline_run_id INTEGER REFERENCES media_pipeline_runs(id) ON DELETE SET NULL"),
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


def _backfill_retention_until(conn: sqlite3.Connection) -> None:
    """Set retention_until for existing customers where it is NULL.

    UAE Federal Decree-Law No. 10/2025: retention for closed customers runs
    from relationship termination (updated_at); for active customers it runs
    from onboarding (onboarded_at). Called once during connect().
    """
    from .cases.manager import RETENTION_YEARS
    # Closed customers: 10 years from closure date (updated_at).
    conn.execute(
        "UPDATE customers SET retention_until ="
        " date(substr(COALESCE(updated_at, onboarded_at), 1, 10), '+' || ? || ' years')"
        " WHERE status = 'closed' AND retention_until IS NULL"
        " AND (updated_at IS NOT NULL OR onboarded_at IS NOT NULL)",
        (RETENTION_YEARS,),
    )
    # Active / other customers: 10 years from onboarding date.
    conn.execute(
        "UPDATE customers SET retention_until ="
        " date(substr(onboarded_at, 1, 10), '+' || ? || ' years')"
        " WHERE status != 'closed' AND retention_until IS NULL AND onboarded_at IS NOT NULL",
        (RETENTION_YEARS,),
    )


def _backfill_exit_date(conn: sqlite3.Connection) -> None:
    """Closed customers from before exit_date existed: their last update is
    the best available proxy for the closure date. The real reason is unknown."""
    conn.execute(
        "UPDATE customers SET exit_date = date(substr(updated_at, 1, 10)),"
        " exit_reason = COALESCE(exit_reason, 'unspecified')"
        " WHERE status = 'closed' AND exit_date IS NULL"
    )


def _backfill_email_verified(conn: sqlite3.Connection) -> None:
    """One-time grandfathering, run only in the same connect() call that adds
    the email_verified_at column to an existing (pre-verification) database.

    Every operator that already has a password set has already completed the
    old register-organization or /setup flow and has been logging in
    successfully -- there is no historical proof of email control to check,
    and introducing this column should not retroactively lock any of them
    out. Only registrations from this point on go through the real check
    (see api/mobile.py and api/app.py's register routes, and auth.login()'s
    guard). A fresh install never calls this: CREATE TABLE IF NOT EXISTS
    already includes the column, so there is nothing to backfill.
    """
    conn.execute(
        "UPDATE operators SET email_verified_at=created_at "
        "WHERE password_hash IS NOT NULL AND email_verified_at IS NULL"
    )


def _backfill_money_columns(conn: sqlite3.Connection) -> None:
    """Backfill amount_units/amount_nanos from amount_aed for pre-migration rows.

    amount_aed is REAL (IEEE 754 double). We convert via str() -> Decimal to
    avoid float arithmetic drift, then split into integer units and nanos.
    Only touches rows where amount_units IS NULL (idempotent).
    """
    rows = conn.execute(
        "SELECT id, amount_aed FROM transactions WHERE amount_units IS NULL"
    ).fetchall()
    if not rows:
        return
    from decimal import Decimal
    _NANOS = 1_000_000_000
    for row in rows:
        d = Decimal(str(row["amount_aed"]))
        units = int(d)
        nanos = int((d - units) * _NANOS)
        conn.execute(
            "UPDATE transactions SET amount_units=?, amount_nanos=? WHERE id=?",
            (units, nanos, row["id"]),
        )


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
    expires_at = (datetime.now(timezone.utc) + SETUP_TOKEN_LIFETIME).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO setup_tokens (org_id, token_hash, created_at, expires_at) VALUES (?,?,?,?)",
        (org_id, token_hash, now, expires_at),
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
    conn.execute("CREATE INDEX IF NOT EXISTS ix_ubo_parent ON ubo_links(parent_ubo_id)")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection with sane defaults and the schema applied.

    Migration order matters: the table rebuilds must run before the
    column-add migrations touch tables that reference them, the org_id
    indexes must be created only after every column they index actually
    exists, and the data backfill must run last of all.
    """
    target = Path(path) if path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI runs sync dependencies through
    # contextmanager_in_threadpool, which can open the connection on one
    # threadpool worker and run the request body (and the teardown close())
    # on another. That cross-thread use trips sqlite3's default thread guard
    # and surfaced as intermittent HTTP 500s under parallel load (QA-04,
    # 2026-09-21 review). Safe here: deps.get_db() hands each request its own
    # connection and never shares one between concurrent requests.
    conn = sqlite3.connect(target, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(SCHEMA)
    _migrate_operators_table(conn)
    _migrate_customers_table(conn)
    _operators_cols_before_migrate = {
        r["name"] for r in conn.execute("PRAGMA table_info(operators)")
    }
    _migrate(conn)
    if "email_verified_at" not in _operators_cols_before_migrate:
        _backfill_email_verified(conn)
    _backfill_retention_until(conn)
    _backfill_money_columns(conn)
    _backfill_exit_date(conn)
    _create_org_indexes(conn)
    from .ingest.fatf import load_fatf_data
    load_fatf_data(conn)
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


def _redact_secrets(error: str) -> str:
    """Strip query strings (especially ?token=...) and cap length before
    storage to prevent token leakage (EU FSF adapter puts AMLKIT_EU_FSF_TOKEN
    in URLs) and DB bloat."""
    import re
    # Strip query strings from URLs: ?anything → ?[REDACTED]
    redacted = re.sub(r'\?[^\s<>"\']+', '?[REDACTED]', error)
    # Cap at 500 chars
    if len(redacted) > 500:
        redacted = redacted[:497] + "..."
    return redacted


def record_dataset_error(conn: sqlite3.Connection, key: str, error: str) -> None:
    """Persist a refresh failure onto the dataset row so the compliance
    dashboard can surface *which* source failed and *why*, instead of the
    error living only in stderr/logs. Best-effort: the dataset row may not
    exist yet on a first-ever refresh that fails before upsert_dataset(),
    so this is a no-op UPDATE in that case rather than an error."""
    safe_error = _redact_secrets(error)
    conn.execute(
        "UPDATE datasets SET last_error=?, error_at=? WHERE key=?",
        (safe_error, utcnow(), key),
    )
    conn.commit()


def clear_dataset_error(conn: sqlite3.Connection, key: str) -> None:
    """Clear a previously recorded refresh error after a successful load."""
    conn.execute(
        "UPDATE datasets SET last_error=NULL, error_at=NULL WHERE key=?",
        (key,),
    )
    conn.commit()


def fetch_all(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, tuple(params)).fetchall()


def set_org_alert_threshold(conn: sqlite3.Connection, org_id: int, threshold: float | None) -> None:
    """Set (or clear, with threshold=None) an org's configured alert
    threshold. Admin-only in practice; enforced by the caller (the route),
    not here -- this function trusts the org_id it is given, same as every
    other write path in this module."""
    conn.execute(
        """INSERT INTO org_settings (org_id, alert_threshold, updated_at) VALUES (?,?,?)
           ON CONFLICT(org_id) DO UPDATE SET
             alert_threshold=excluded.alert_threshold, updated_at=excluded.updated_at""",
        (org_id, threshold, utcnow()),
    )
    conn.commit()
