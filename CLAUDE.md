# groAML by Grovisor (package: `amlkit`)

Product name is **groAML by Grovisor** (domain: groaml.grovisor.ae). The code package, `AMLKIT_*` env vars, cookies, DB file and cloud resources intentionally keep the `amlkit` name. Use "groAML" in user-facing text only.

UAE AML/CFT compliance toolkit — sanctions screening, customer due diligence, risk assessment, and regulatory reporting for DNFBPs. Built as a single-tenant-per-database Flask/FastAPI web app backed by SQLite.

## Commands

```bash
# Run tests (always use the venv Python)
cd C:/Users/nizam/bedrock-project/amlkit && .venv/Scripts/python.exe -m pytest tests/ -x -q

# Run a single test file
.venv/Scripts/python.exe -m pytest tests/test_api.py -x -q

# Start the app
.venv/Scripts/python.exe scripts/serve.py

# Refresh sanctions lists
.venv/Scripts/python.exe scripts/refresh.py
```

## Architecture

```
amlkit/
  api/
    app.py          Routes (thin — auth + render, no business logic)
    mobile.py       Mobile API (REST, bearer-token auth)
    deps.py         Request-scoped DB, session, CSRF
  auth.py           Session management, password hashing, CSRF
  db.py             SQLite schema, migrations, connect(), audit()
  queries.py        Read-only query functions (all require org_id)
  mail.py           Email (SendGrid or dev-mode console output)
  storage.py        File storage abstraction
  cases/
    manager.py      Write operations: onboard, disposition, transactions
    review.py       Four-eyes review workflow
    ocr.py          Passport/Emirates ID scanning (MRZ)
    diagram.py      UBO ownership diagrams (Graphviz)
  ingest/
    loader.py       Core load() + staleness_report()
    base.py         Adapter protocol + fetch_with_retry
    eocn.py         UAE Executive Office (Local Terrorist List)
    un.py, ofac.py, eu.py, uk.py  International sanctions sources
    cia.py          CIA World Leaders (PEP list)
    wikidata_peps.py  Wikidata ministers/cabinet-level PEPs (CC0)
    fatf.py         FATF high-risk jurisdictions
  match/
    engine.py       Screening engine + rescreen_all
    scorer.py       Name similarity scoring
  names/
    arabic.py       Arabic name canonicalization (453 lines)
  screening/
    adverse_media.py  GDELT-based negative news search
    kyt.py            Transaction monitoring rules
    pf.py             Proliferation financing screening
  risk/
    model.py        Risk scoring engine
    ruleset.yaml    Risk factor weights and thresholds
  reporting/
    goaml.py        goAML 5.0 STR/SAR XML export
  web/
    templates/      Jinja2 HTML templates
    static/         CSS, JS
```

## Key conventions

- **Tenant isolation**: Every query function takes `org_id` as a mandatory argument. Routes resolve it from the session. No route skips this.
- **Audit trail**: Append-only via DB triggers. `db.audit()` requires `org_id` explicitly (even `None` for shared data).
- **Test style**: Integration tests with real SQLite databases (no mocks for DB). `TestClient` from FastAPI for HTTP tests. Register + verify email flow via `_register()` helper in test_api.py.
- **DB writes**: `busy_timeout=30000` PRAGMA + `retry_on_lock` decorator in db.py for long operations.
- **CSRF**: Synchronizer token pattern — cookie + hidden form field, validated on every POST.
- **MFA (TOTP)**: Mandatory for MLROs only. Every path that mints a session (password login, verify-email auto-login, setup-token claim, UAE PASS SSO, mobile) calls `auth.mfa_lock_session()` right after `create_session()`, which locks an MLRO's session until `/mfa/verify` (or `/mfa/setup` if not enrolled). Backup codes, a 5-miss/15-min lockout, and a 30-day "remember this device" cookie (`amlkit_trusted_device`) are supported. Other roles are not challenged.

## Database

SQLite with WAL mode. Schema is in `db.py:SCHEMA`. Migrations are additive column-adds in `_MIGRATIONS`. Table rebuilds for constraint changes in dedicated functions.

`connect()` handles schema creation + all migrations (plus the `fatf_countries` rebuild) — safe for fresh installs and upgrades alike — but runs that pass (`db._initialise`) **at most once per database file per process**. Later opens only set the per-connection PRAGMAs (WAL, `busy_timeout`, `foreign_keys`), so per-request `get_db()` does no DDL/writes. The cache key is (resolved path, `st_dev`, `st_ino`) checked against `PRAGMA schema_version`, so a file replaced at the same path (restore, a test recreating its DB) or out-of-band DDL re-runs the init; `:memory:` is always initialised. `db._reset_init_cache()` forces a re-init on the next open.

## Automated routines

Recurring triggers registered in the claude.ai Routines UI (Settings → Routines). All fire in fresh sessions.

| ID | Name | Schedule (UTC) | Environment | Purpose |
|----|------|----------------|-------------|---------|
| `trig_01ETKZRFYHGqii6o5K8WH9wR` | Issue triage | `50 */6 * * *` | Default (trusted network) | CI health check, GitHub issue triage, Monday improvement log. One issue per unresolved condition, updated in place (#252). Prompt is versioned in `docs/routines/issue-triage.md`; paste it into the routine when changing it |
| `trig_01JHC5b92KEvfhgnk5yVdbkM` | amlkit GitHub Issues Sync | `55 */6 * * *` | Full access to internet | Syncs open GitHub issues → artifact DB task tracker (`LvtQxP7THXZEvM1zS8f34p`) |

**Sequence every 6 hours (UTC):**
```
HH:50  Issue triage
HH:55  GitHub Issues Sync  →  updates My Tasks artifact DB
```

**Task dispatch (Desktop, file-based):** As of 2026-09-21 the dreamon workflow uses file-based channels (QUEUE.md / STATUS.md) instead of a scheduled cron trigger. Desktop appends tasks to QUEUE.md; Bedrock workers (lonappan, thankappan, kunjappan) claim and report via those files. No scheduled `/dreamon` trigger exists.

**Task status fields** used in the artifact DB (`tasks` collection):
- `done: true` — completed
- `in_progress: true` — PR opened / work underway
- `blocked: true` — blocked mid-task
- `awaiting_input: true` — waiting on owner input
- (absent / false) — actionable

## UAE PASS integration (operator SSO + customer CDD verification)

Merged in #361. **Switched on in production against the UAE PASS staging sandbox since #378** (the deploy passes the `UAEPASS_*` repo secrets/variable to Cloud Run); inert wherever either credential is unset — see `UAEPASS_*` env vars below. `amlkit/uaepass.py` is a pure OIDC client (no DB access): config loading, authorize-URL building, token exchange, userinfo fetch, plus a UAE-PASS-scoped alpha-3→alpha-2 country lookup (`datamodel.py` has no alpha-3 table) and gender-string normalization.

**Two flows, both session/route-gated the same way as everything else in this codebase:**
1. **Operator/MLRO SSO** — `/auth/uaepass/start` + `/auth/uaepass/callback`, a "Sign in with UAE PASS" alternative to the email+password form. Never auto-provisions an account (provisioning stays admin-only via `/system/create-operator`): links to an existing operator by a stored `uaepass_uuid` first, falls back to matching `lower(email)` only when that operator's `email_verified_at` is set **and** UAE PASS's own `userType` assurance level is SOP2 or SOP3 (SOP1 is self-registered with no bank/telco/ICA verification behind it, so its email claim isn't trusted for linking). A successful SSO login goes through the exact same `create_session` → `mfa_lock_session` path as password login.
2. **Customer CDD identity verification** — `/customers/{id}/uaepass/start` + `/callback`, a "Verify via UAE PASS" button on the customer case-file page. Records an append-only `uaepass_verifications` row (idn, name, nationality, mobile, email, assurance level) plus an audit row carrying the full raw UAE PASS response. Additive to the OCR passport/Emirates-ID-scan flow (`cases/ocr.py`), not a replacement — OCR remains the fallback. Best-effort backfills empty `id_number`/`id_type`/`nationality`/`nationalities`/`email`/`phone`/`gender` on the customer row, but only when the relevant field(s) are already empty (and never splits the `id_number`/`id_type` pair).

**DB:** `operators.uaepass_uuid` (additive nullable column); `uaepass_states` (short-lived one-time OAuth state, modeled on `email_verify_tokens`); `uaepass_verifications` (append-only, modeled on `signatures`/`documents`).

**Security properties worth knowing before touching this code:** the OAuth `state` is bound two ways — a DB row (purpose/expiry/single-use, rejecting a replayed or cross-customer callback) *and* a short-lived HttpOnly `amlkit_uaepass_state` cookie checked at `/callback` before the DB check even runs. The cookie exists specifically to stop login CSRF / session swapping: without it, an attacker completing their own UAE PASS login could capture their own callback URL and hand it to a victim, whose browser would otherwise have no way to tell the `state` wasn't issued to it. Both UAE PASS route pairs carry the same `10/minute` per-IP rate limit as `/login`.

**Testing it:** set `UAEPASS_CLIENT_ID=sandbox_stage` and `UAEPASS_CLIENT_SECRET=sandbox_stage` — UAE PASS's own published POC sandbox credentials, staging-only — and use either button; UAE PASS's staging app prompts a real sandbox login and redirects back with a real authorization code. See `tests/test_uaepass.py`'s module docstring.

**Going live for real operators/customers** requires completing UAE PASS's formal Service Provider onboarding (business registration + trade licence submitted to the UAE PASS team) to get real staging/production `client_id`/`client_secret`. The sandbox credentials above are POC-only.

**Known follow-ups, not yet actioned:**
- ACR level is `urn:safelayer:tws:policies:authentication:level:low` (`uaepass.ACR_LEVEL_DEFAULT`) for both flows — UAE PASS's own docs document only this level for the sandbox/POC flow. Once real staging credentials exist, confirm with the UAE PASS team whether a stronger level suits the customer-verification (CDD) flow specifically.
- Both buttons are plain text links (no UAE PASS official button artwork fetched yet).
- One-UAE-PASS-identity-per-operator is enforced at the application layer (`resolve_uaepass_operator`'s `... AND uaepass_uuid IS NULL` guard), not a SQL unique index — consistent with the rest of this schema, which doesn't use partial/conditional unique indexes anywhere.

## Environment variables

- `AMLKIT_DB` — path to SQLite database (default: `data/aml.db`)
- `AMLKIT_BIND_HOST` / `AMLKIT_PORT` — server bind address
- `AMLKIT_SSL_KEYFILE` / `AMLKIT_SSL_CERTFILE` — TLS config
- `AMLKIT_BEHIND_PROXY` — set to `1` when behind a reverse proxy
- `SCHEDULER_SECRET` — bearer token for `/system/refresh`
- `ADMIN_API_SECRET` — bearer token for `/system/create-operator`
- `AMLKIT_SINGLE_OPERATOR_MODE` — skip four-eyes review requirement
- `AMLKIT_QUOTE_TO` — where `/apply` quotation requests are emailed (comma separated; default `info@grovisor.ae`). Needs `AMLKIT_SMTP_HOST` (and friends, see `mail.py`) or requests are only saved and printed to the log
- `LITESTREAM_REPLICA_URL` — production replica (container refuses to start if unset; no default)
- `AMLKIT_ALLOW_FRESH_START` — `1` lets a brand-new deployment boot with no replica; otherwise a missing replica refuses to start
- `AMLKIT_INTEGRITY_TIMEOUT` — startup integrity-check budget in seconds (default 60)
- `AMLKIT_RESTORE_ATTEMPTS` / `AMLKIT_RESTORE_RETRY_DELAY` — startup litestream restore retries (default 3 attempts, 5s apart) before refusing to start
- `UAEPASS_CLIENT_ID` / `UAEPASS_CLIENT_SECRET` — UAE PASS OIDC credentials; unset (either one) disables the whole UAE PASS integration (operator SSO + customer CDD verification) — no button shown, routes 404
- `AMLKIT_WIKIDATA_MODE` — `auto` (default: use the committed snapshot in `amlkit/ingest/data/` if present, else query Wikidata), `snapshot`, or `live`. Production uses the snapshot because Wikimedia blocks many cloud IPs; refresh it monthly with `scripts/snapshot_wikidata_peps.py` from an unblocked network and commit the result (Wikidata is CC0, so committing it is fine). A snapshot older than `AMLKIT_WIKIDATA_SNAPSHOT_MAX_AGE_DAYS` (default 62) is refused so stale PEP data fails loudly. `AMLKIT_WIKIDATA_SNAPSHOT` overrides the snapshot file's path
- `AMLKIT_WIKIDATA_USER_AGENT` — User-Agent (name + contact) sent to Wikidata's SPARQL endpoint; default identifies groAML and info@grovisor.ae per Wikimedia's policy. Wikimedia blocks some cloud/CI IPs with HTTP 403 ("robot policy"); the adapter fails fast with that cause rather than retrying
- `UAEPASS_ENV` — `staging` (default) or `production`; selects UAE PASS's `stg-id.uaepass.ae` vs `id.uaepass.ae` endpoints
