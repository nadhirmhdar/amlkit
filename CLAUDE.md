# amlkit

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
- **No MFA yet**: Auth is email + password + session cookie only.

## Database

SQLite with WAL mode. Schema is in `db.py:SCHEMA`. Migrations are additive column-adds in `_MIGRATIONS`. Table rebuilds for constraint changes in dedicated functions.

`connect()` handles schema creation + all migrations on every open — safe for fresh installs and upgrades alike.

## Automated routines

Recurring triggers registered in the claude.ai Routines UI (Settings → Routines). All fire in fresh sessions.

| ID | Name | Schedule (UTC) | Environment | Purpose |
|----|------|----------------|-------------|---------|
| `trig_01ETKZRFYHGqii6o5K8WH9wR` | Issue triage | `50 */6 * * *` | Default (trusted network) | CI health check, GitHub issue triage, Monday improvement log |
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

## Environment variables

- `AMLKIT_DB` — path to SQLite database (default: `data/aml.db`)
- `AMLKIT_BIND_HOST` / `AMLKIT_PORT` — server bind address
- `AMLKIT_SSL_KEYFILE` / `AMLKIT_SSL_CERTFILE` — TLS config
- `AMLKIT_BEHIND_PROXY` — set to `1` when behind a reverse proxy
- `SCHEDULER_SECRET` — bearer token for `/system/refresh`
- `ADMIN_API_SECRET` — bearer token for `/system/create-operator`
- `AMLKIT_SINGLE_OPERATOR_MODE` — skip four-eyes review requirement
