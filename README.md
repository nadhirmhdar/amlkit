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

## Data sources and licensing

Every list is now ingested from its **primary publisher**, and every one of
them is free to redistribute commercially:

| Source | Publisher | Adapter | Licence |
|---|---|---|---|
| UAE Local Terrorist List | EOCN (`uaeiec.gov.ae`) | `ingest/eocn.py` | UAE Government publication |
| UN Consolidated List | UN Security Council | `ingest/un.py` | Public domain |
| OFAC SDN | US Treasury | `ingest/ofac.py` | Public domain |
| UK Sanctions List | UK FCDO/OFSI | `ingest/uk.py` | Public domain |
| EU Financial Sanctions | European Commission | `ingest/eu.py` | Public domain (token, see below) |
| CIA World Leaders (PEPs) | US CIA | `ingest/cia.py` | Public domain (17 U.S.C. §105) |
| Adverse media (news index) | The GDELT Project | `screening/adverse_media.py` | Free for commercial use, attribution required |

**OpenSanctions is no longer in the refresh path.** `ingest/opensanctions.py`
is retained as a working adapter for non-commercial and comparison use, and
carries a licence warning saying so — its data is CC-BY-NC 4.0, free for
non-commercial use only, with no exemption for commercial users. Nothing in
`scripts/refresh.py`, `api/app.py` or the CI canary loads it.

The **EU** list needs an access token. The adapter ships with the token the
Commission publishes in its own documentation, which is why it works out of
the box, but that token is not this deployment's and can be rotated or
rate-limited without notice. Register at
<https://webgate.ec.europa.eu/fsd/fsf> and set `AMLKIT_EU_FSF_TOKEN` before
depending on the EU list. The EU list is the one non-mandatory sanctions
source, so a failure there degrades coverage rather than blocking a refresh.

### PEP coverage is a baseline, not a full programme

CIA World Leaders covers sitting officials — heads of state, ministers,
central bank governors, ambassadors — for ~199 countries. It does **not**
cover former officials, relatives, or close associates, all of which UAE CDD
obligations also reach. Describe it as baseline PEP coverage, not PEP
screening.

---

## What works today

- **Sanctions screening** against the UAE Local Terrorist List (311 listed
  entities — 171 individuals, 75 groups, 65 legal entities — read daily from
  the EOCN's own published workbook, with its delisting sheets excluded)
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
- **Native Android app** — same feature set as the web interface, against
  the `/api/v1/*` JSON API in `amlkit/api/mobile.py`. Lives in its own repo,
  [nadhirmhdar/amlkit-mobile](https://github.com/nadhirmhdar/amlkit-mobile),
  which has its own CI/CD and Play Console publishing pipeline
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
- **Adverse media screening** — negative-news search against the GDELT news
  index, in Latin *and* Arabic script, classified into the risk model's own
  severity bands. See the section below for what it is and is not

Measured on the real UAE list: 12/12 Latin self-match, 12/12 Arabic-script
self-match, **0 false positives** across the benign-name suite. 441 tests.

## Not built yet

goAML STR/SAR export · identity-document verification · MFA ·
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
from amlkit.ingest.eocn import uae_local_terrorists
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

## Adverse media

Negative-news screening against **GDELT DOC 2.0** — a free, key-less index of
global news in 65+ languages. Its terms are the reason it is here: *"all
datasets released by the GDELT Project are available for unlimited and
unrestricted use for any academic, commercial, or governmental use of any kind
without fee"*, conditional only on citing the project. That clears the same
commercial bar every sanctions adapter had to clear.

The `adverse_media` factor has been in `risk/ruleset.yaml` since the risk model
was written, always scoring `none` because nothing fed it. This feeds it.

**What it does.** Searches the customer's name — in Latin *and* Arabic script,
through the same canonicaliser the sanctions matcher uses — against news
carrying financial-crime, regulatory or reputational terms, then classifies
each headline into the ruleset's own three severity bands:

| Severity | Ruleset points | What it means |
|---|---|---|
| `financial_crime_alleged` | 35 | Predicate offence named: laundering, bribery, fraud, an indictment |
| `regulatory_action` | 25 | Supervisory or administrative action: a fine, a revoked licence, a probe |
| `reputational_only` | 10 | Allegation or controversy with no named offence |

Arabic risk terms (`غسل الأموال`, `رشوة`, `غرامة`, …) sit alongside the
English ones, because a Gulf case is frequently reported in Arabic days before
any English outlet picks it up — if one ever does.

**What it is not.** A screening aid, not a curated adverse-media database.
GDELT tells you an article exists; it does not decide whether the allegation
is credible or whether the person named is *your* customer. That analyst layer
is what World-Check and Dow Jones actually sell, and this does not replace it.
So every finding is an unreviewed lead: **nothing changes a risk rating until
an operator marks it relevant**, and confirming one re-rates the customer with
every other factor carried forward from their last assessment.

Three consequences worth knowing before relying on it:

- **It is operator-triggered, not automatic.** GDELT rate-limits to one request
  every 5 seconds per source IP, so this cannot run across a whole customer
  book after every list refresh the way sanctions re-screening does.
- **A provider outage is recorded, not swallowed.** A failed check writes a row
  saying so. "Checked, found nothing" and "the check could not run" are
  different facts about a file, and the evidence pack prints both.
- **Headline vs body matches are labelled.** GDELT matched the name somewhere
  in the article, but only the headline comes back — so a finding whose name is
  not in the headline is flagged as such rather than hidden or trusted.

Findings store metadata and a link only, never article text: GDELT's data is
free to redistribute, the articles it indexes are their publishers' copyright.

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
| OpenSanctions `logic-v2` weights | Publicly documented, well tested — better than inventing weights (the weights are published research; the *data* licence is a separate question, see above) |
| Primary sources, not an aggregator | An aggregator's licence becomes the product's licence. Every list is fetched from the body that publishes it |
| EOCN's Excel, not its PDF | Same table, but as a table. PDF column reconstruction fails silently when a layout shifts |
| Replace-on-refresh ingest | A delisted person must actually disappear; merge semantics leave stale hits |
| Loud adapter failures | A silently-lapsed sanctions feed shows green while coverage is gone |
| argon2 for passwords | Regulated financial-crime data for multiple firms; the "no new dependency" default doesn't apply here |
| org_id required on every tenant query | Per-route discipline guarantees an eventual leak; the function signature itself is the enforcement |
| Sessions snapshot org_id at login | An operator moved between orgs, deactivated, or password-changed has every session explicitly revoked, not left to drift out of sync with a live join |

## Not legal advice

Built from published legal sources. Before this touches real client files, a
UAE-qualified adviser should sign off on the risk model and STR workflow.
