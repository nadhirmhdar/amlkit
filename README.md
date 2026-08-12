# amlkit — UAE AML screening & CDD

Sanctions/PEP screening and customer due diligence for UAE-regulated entities,
built around the obligations in **Federal Decree-Law No. 10 of 2025** and
**Cabinet Resolution No. 134 of 2025**.

Built for the segment the market prices out: DNFBPs — real estate brokers,
precious-metals dealers, corporate service providers, auditors and law firms —
who carry the same legal obligations as a bank but cannot justify $25k–75k/yr
of enterprise tooling. Commercial entry floors run $99–$375/month *before*
per-customer costs, which is the actual barrier for a 40-client firm.

---

## ⚠️ Licence boundary — read before any commercial use

The active data source is **OpenSanctions**, which is free for
**non-commercial use only**. There are no exemptions for commercial users.

**While the OpenSanctions adapter is in use, this tool must not be sold or used
to provide a paid service.** Every source sits behind the adapter interface in
`amlkit/ingest/base.py` precisely so it can be swapped for direct
primary-source ingestion (OFAC, UN, EU, UK, EOCN — all public domain and free
to redistribute) before commercial launch.

This is a hard line, not a formality.

---

## What works today

- **Sanctions screening** against the UAE Local Terrorist List (335 screenable
  entities, refreshed daily from source)
- **Arabic-aware matching** — the differentiator. Cross-script queries,
  transliteration variants, patronymic particles, reordered name chains
- **Scored alerts with full evidence** — every alert stores its per-feature
  breakdown, because "the algorithm said so" is not an answer to an examiner
- **Append-only audit log**, enforced by database trigger rather than convention
- **Staleness monitoring** against the EOCN 24-hour list-update rule

Measured on the real UAE list: 12/12 Latin self-match, 12/12 Arabic-script
self-match, **0 false positives** across the benign-name suite.

- **CDD case management** — onboarding that screens the whole ownership graph,
  UBO capture at the 25% threshold with senior-official fallback, versioned risk
  model, five-year retention
- **Proliferation-financing classification** — PF is a standalone offence under
  Law 10/2025; designations are classified by sanctions programme
- **Web interface** — dashboard, ad-hoc screening, alert triage, case files and
  a printable evidence pack
- **Multi-tenant, password-authenticated, LAN-ready** — each organization's
  data (customers, screenings, alerts, audit trail) is isolated from every
  other's on the same deployment; sanctions/PEP reference data is shared
- **Alert assignment** — workflow routing to an operator, separate from the
  four-eyes/reason-code disposition machinery
- **Case notes** — investigative narrative not tied to any one alert; appears
  in the case file and the printable evidence pack
- **CSV export** — alerts and customers, org-scoped, no new dependency
- **Configurable alert threshold** — one global per-org knob (MLRO-only, in
  Admin), not per-list-type "screening profiles"

Measured on the real UAE list: 12/12 Latin self-match, 12/12 Arabic-script
self-match, **0 false positives** across the benign-name suite. 181 tests.

## Not built yet

Adverse media · goAML STR/SAR export · identity-document verification · MFA ·
evidence-document upload · UBO ownership diagram · dedicated monitoring page.
See `research/compliance-traceability.md` for the full gap list.

---

## Running the interface

```bash
python scripts/refresh.py      # load sanctions lists (also re-screens every org's customers)
python scripts/serve.py        # http://127.0.0.1:8000
```

First run: register your organization at `/register-organization`. If you're
upgrading an existing pre-tenancy database, `serve.py` prints a one-time
`/setup?token=...` link on first startup instead — use it to claim the first
login for the organization your existing data was migrated into.

Binds to **localhost only** by default. Real login now gates every action, but
the deployment is still only as safe as its transport: binding beyond loopback
(`AMLKIT_BIND_HOST`) **without also configuring TLS** sends passwords and
customer PII across the LAN in cleartext — the app refuses to stay quiet about
this and prints a warning at startup. Set `AMLKIT_SSL_KEYFILE` /
`AMLKIT_SSL_CERTFILE` to a certificate this firm controls, or put a
TLS-terminating reverse proxy (e.g. Caddy) in front instead.

### Alert disposition

Routine closes take a **structured reason code**; a written narrative is
required only for confirmed matches and escalations. Mandatory free text on
every alert sounds more rigorous but degrades into "FP" typed a hundred times at
false-positive volume — the same thin record, reached more slowly.

**Dismissing** a sanctions or proliferation match requires a second operator.
Confirming one does not: that path leads to freezing and reporting, which
carries its own scrutiny. Firms with one compliance officer set:

```bash
set AMLKIT_SINGLE_OPERATOR_MODE=1
```

which records **"no independent review"** on the alert and in the evidence pack
rather than pretending the review happened.

---

## Quick start

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Load the mandatory UAE list and screen a name:

```python
from amlkit.db import connect, utcnow
from amlkit.ingest.loader import load
from amlkit.ingest.opensanctions import uae_local_terrorists
from amlkit.match.engine import screen

conn = connect()
load(conn, uae_local_terrorists())

# Screening is tenant-scoped -- org_id is mandatory, not optional, on every
# call. In the web interface this comes from the signed-in session; scripted
# use needs a real organization row.
org_id = conn.execute(
    "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id",
    ("My Firm", "my-firm", "active", utcnow()),
).fetchone()["id"]

result = screen(conn, "Mohammed bin Rashid", org_id=org_id, trigger="onboarding")
print(result.summary())
for hit in result.hits:
    print(hit.score, hit.caption, hit.detail)
```

Run the tests:

```bash
.venv\Scripts\python -m pytest tests -q
```

---

## Why Arabic matching is the wedge

Every major platform treats Arabic as a transliteration problem solved by
generic cross-script reference data. In the UAE it is *the* matching problem.
`Mohd` and `Muhammad` are 6 edits apart on an 8-character string — no
edit-distance threshold catches that without also matching half the database.

`amlkit/names/arabic.py` handles it linguistically instead: orthographic
normalisation, positional semivowels, theophoric compound rejoining
(`Abd al-Rahman` → `Abdulrahman`), particle tokenisation, and order-independent
canonical keys. Arabic-script and Latin queries land in one canonical space.

One consequence worth knowing: `Hassan` (حسن) and `Hussein` (حسين) share a
consonant skeleton and *will* collapse under skeleton-only logic. Arabic
spellings are therefore consulted directly before transliteration — see
`ARABIC_FORMS`.

---

## Design decisions

| Decision | Why |
|---|---|
| SQLite, not Postgres | Runs on a compliance officer's laptop. One file, no daemon, backup = copy |
| Own matcher, not `yente` | yente needs Elasticsearch at 8–16GB; and the Arabic layer needs to be ours |
| OpenSanctions `logic-v2` weights | Publicly documented, well tested — better than inventing weights |
| Replace-on-refresh ingest | A delisted person must actually disappear; merge semantics leave stale hits |
| Loud adapter failures | A silently-lapsed sanctions feed shows green while coverage is gone |
| argon2 for passwords | Regulated financial-crime data for multiple firms; the "no new dependency" default doesn't apply here |
| org_id required on every tenant query | Per-route discipline guarantees an eventual leak; the function signature itself is the enforcement |
| Sessions snapshot org_id at login | An operator moved between orgs, deactivated, or password-changed has every session explicitly revoked, not left to drift out of sync with a live join |

## Not legal advice

Built from published legal sources. Before this touches real client files, a
UAE-qualified adviser should sign off on the risk model and STR workflow.
