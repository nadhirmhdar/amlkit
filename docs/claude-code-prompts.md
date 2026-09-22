# Claude Code prompts — amlkit backlog

Generated 23 Sep 2026 from the amlkit boards, reconciled against `nadhirmhdar/amlkit`
(58 issues, 246 PRs) and against the working tree at `C:\Users\nizam\amlkit`.

Each entry below is a self-contained prompt. Paste the fenced block into Claude Code
from inside the repo. File and line anchors were verified against the current tree,
not copied from the board — where the board was wrong, this document is right.

---

## How to use this

1. `cd C:\Users\nizam\amlkit`
2. Start Claude Code. It reads `CLAUDE.md` automatically.
3. Paste one fenced prompt. One item per session — these are scoped to be finishable.
4. Every prompt ends by opening a PR. Review it before merging.

**Test command** (the one in `CLAUDE.md` had a wrong path; corrected here):

```
.venv\Scripts\python.exe -m pytest tests/ -x -q
```

**Conventions every prompt assumes** (from `CLAUDE.md`, restated because they bite):

- Every query function takes `org_id` as a mandatory argument. No route skips it.
- Tests are integration tests against real SQLite. **No mocks for the DB.**
  Use `TestClient`, and the `_register()` helper in `tests/test_api.py`.
- `db.audit()` requires `org_id` explicitly — pass `None` for shared data, never omit.
- CSRF: synchroniser token, validated on every POST.
- Migrations are additive column-adds in `db._MIGRATIONS`. `connect()` runs them on
  every open, so a migration must be idempotent and safe on a fresh database.

---

## Before you start: four items to close, not build

Verified against the tree. These are on the board as open but should not be worked.

| Item | Status | Evidence |
|---|---|---|
| **p12** — remove hardcoded EU FSF demo token | **Done** | `ingest/eu.py` has no `DEFAULT_TOKEN`. Line 29 defines `ENV_TOKEN`, line 35 raises `EU FSF token not configured` when unset. Landed via #113 / #212. |
| **t9** — test idle session timeout | **Done** | `tests/test_idle_timeout.py::test_idle_session_beyond_timeout_is_rejected`, plus within-timeout, null-grandfather and configurable-timeout cases. |
| **t19** — test MFA TOTP enroll/challenge/revoke | **Done** | 17 tests across `test_p15_mfa_totp.py` and `test_p15_mfa_enforcement.py`, including lockout after five wrong codes and mobile token locking. |
| **t18** — test APScheduler refresh-failure audit | **Obsolete** | p53 removed APScheduler. `requirements.txt` has zero references and `test_p53_no_apscheduler.py::test_apscheduler_not_imported` guards it. Close as won't-do. |

---

# Part 1 — Implementation specs (26)

## Critical

### p1 — Register EU FSF token and set `AMLKIT_EU_FSF_TOKEN` in Cloud Run
`#85` · Critical · **Not a code task**

This is a deployment action, not a change to the repo. `ingest/eu.py` already fails
fast when the variable is missing (that was p12). What is missing is the token itself
in the Cloud Run service config.

Your own automation is complaining about this one: issues #251, #252 and #295 exist
solely because a health check keeps re-flagging #85 as an unassigned critical with no
escalation. Clear it and three issues close with it.

```
Register for an EU Financial Sanctions Files token at
https://webgate.ec.europa.eu/fsd/fsf, then set AMLKIT_EU_FSF_TOKEN on the Cloud Run
service. Do not put the token in the repo, in .env, or in any committed file.

After setting it, verify from the deployed instance that the EU source refreshes:
run scripts/refresh.py (or hit /system/refresh with SCHEDULER_SECRET) and confirm
the EU dataset's last_error is null and its entity count is non-zero.

Then close issues #85, #251, #252 and #295 with a comment stating the token is
configured and naming the verification you ran.
```

---

## High

### p91 — `single_operator_mode()` bypasses maker-checker for every tenant
`#258` · High · Security / Multi-tenancy

**Verified anchors:** `amlkit/cases/review.py:74` (the function), `:81` (the env read),
`scripts/serve.py:16`. The board did not name the file; it is *not* in `app.py`.

This is the most serious item on the board. Four-eyes review is a regulatory control,
and right now one environment variable disables it for every organisation on the
instance simultaneously.

```
Fix issue #258 in amlkit.

amlkit/cases/review.py:74 defines single_operator_mode(), which reads the
process-wide environment variable AMLKIT_SINGLE_OPERATOR_MODE at line 81. Because it
is process-wide, enabling single-operator mode for one tenant disables four-eyes
maker-checker review for every tenant running on the same instance. Four-eyes review
is a regulatory control, so this is a compliance defect, not just a config smell.

Move the flag to per-organisation configuration:
1. Add a single_operator_mode column to the org settings (additive migration in
   db._MIGRATIONS, defaulting to off).
2. Change single_operator_mode() to take org_id and read the org's setting.
3. Update every caller to pass org_id. Find them all - do not leave a zero-arg
   overload that silently falls back to the env var.
4. Keep AMLKIT_SINGLE_OPERATOR_MODE working ONLY as a local-development override,
   and make it a no-op when the app is not running in debug/dev mode. If that is
   awkward, drop it entirely and say so in the PR.

Tests (real SQLite, no DB mocks): create two orgs, enable single-operator mode on
org A only, and assert that a disposition in org A skips four-eyes while the same
action in org B is still blocked pending a second reviewer. Add a test that the env
var alone cannot disable review for a production-mode org.

Branch fix/258-per-org-single-operator. Run the full suite, then open a PR with
gh pr create referencing "Closes #258".
```

---

### p93 — Structuring rule only fires on cash
`#257` · High · Bug

**Verified anchor:** `amlkit/screening/kyt.py:77` — `def evaluate_transaction`.

```
Fix issue #257 in amlkit.

amlkit/screening/kyt.py:77, evaluate_transaction(), applies the structuring rule only
when the payment method is 'cash'. Structured wire transfers and virtual-asset
transfers therefore generate no alert at all - the exact typologies a UAE DNFBP is
most likely to see.

Apply the structuring rule across payment methods. Do not simply delete the cash
check: thresholds legitimately differ by method, so introduce per-method thresholds
(cash, wire, virtual asset, other) with the current cash threshold preserved as-is so
existing behaviour for cash is unchanged. Put the thresholds in
amlkit/risk/ruleset.yaml alongside the other tunable weights rather than hardcoding
them, and document each one with a short comment.

Tests (real SQLite, no DB mocks): for each payment method, a sequence of transactions
that sits just under the single-transaction reporting threshold but aggregates above
the structuring threshold within the rule's window must raise a structuring alert.
Add a negative case per method that stays below and must not alert. Keep the existing
cash tests passing unchanged - if any of them break, the cash threshold moved and
that is a bug in your change.

Branch fix/257-structuring-all-methods. Run the full suite, then open a PR with
gh pr create referencing "Closes #257".
```

---

### p92 — `auto_rescreen.py` aborts the whole run on one org's exception
`#259` · High · Bug / Reliability

**Verified anchors:** `scripts/auto_rescreen.py` — `main()` at `:89`, the vulnerable
loop `for org in orgs:` at `:134`, `for row in new_alert_customers:` at `:159`.

```
Fix issue #259 in amlkit.

scripts/auto_rescreen.py:134 iterates `for org in orgs:` with no per-organisation
error isolation, so one organisation raising an exception aborts the entire batch.
Every tenant after the failing one is silently left un-rescreened - they believe
ongoing monitoring ran when it did not.

Isolate each organisation:
1. Wrap the per-org body in try/except. On exception, log it, write an audit_log
   entry for that org (db.audit() takes org_id explicitly), and continue to the next
   organisation.
2. Do the same for the per-customer risk re-assessment loop at :159.
3. Accumulate failures and, at the end of main(), return a non-zero exit code if any
   organisation failed, with a summary line naming which ones. A partially successful
   run must not look like a clean run to Cloud Scheduler.
4. Do not swallow KeyboardInterrupt or SystemExit.

Tests (real SQLite, no DB mocks): set up three orgs, force the second to raise inside
the rescreen path, and assert that orgs one and three are still rescreened, that an
audit row exists for org two, and that main() returns non-zero.

Branch fix/259-auto-rescreen-isolation. Run the full suite, then open a PR with
gh pr create referencing "Closes #259".
```

---

### p2 — Confirm the statutory retention period, then align the code
`#78` · High · Question, blocking

**This one is not really a coding task and should not be handed to Claude Code cold.**
Issue #78 is open and labelled `question`. It asks whether the legally required
retention period is 8 or 10 years. PR #86 already implemented 10 years, and
`cases/manager.py:52` defines `RETENTION_YEARS`. So the code moved but the legal
question was never formally answered and closed.

You are the tax and compliance specialist here — this needs your determination against
Cabinet Resolution 134/2025, not an agent's reading. Once you have decided, this
becomes a two-minute change:

```
Issue #78 is resolved: the statutory retention period for amlkit is <N> years,
per <cite the article of Cabinet Resolution 134/2025 you relied on>.

Confirm amlkit/cases/manager.py:52 RETENTION_YEARS matches <N>. Check every other
place the retention period appears - code, templates, docs and tests - and make them
agree. Add the citation as a comment next to RETENTION_YEARS so the next person does
not have to re-derive it.

Branch chore/78-confirm-retention-period. Run the full suite, then open a PR with
gh pr create referencing "Closes #78".
```

---

### p3 — Extend `retention_until` dates written under the old 5-year rule
`#79` · High · Bug

**Verified anchors:** `cases/manager.py:52` (`RETENTION_YEARS`), `:169`, `:171`,
`purge_expired` at `:440`.

Depends on p2. Do not run this until the period is confirmed — a migration that writes
the wrong date is worse than no migration.

```
Fix issue #79 in amlkit.

Customers closed before PR #66 carry a retention_until computed under the old 5-year
rule. amlkit/cases/manager.py:440 purge_expired() evaluates against that column, so
those records will be deleted years early - destroying records the firm is legally
required to retain.

Write an idempotent migration that recomputes retention_until for affected customers
using the current RETENTION_YEARS (manager.py:52) applied to each customer's closure
date. Requirements:
- Idempotent: running it twice must not shift dates a second time. Key off the
  closure date, never off the existing retention_until.
- Never shorten a retention_until. If the recomputed date is earlier than the stored
  one, keep the stored one and log it.
- Scope it per org_id and write one audit_log entry per org summarising how many rows
  were extended.
- It must be safe on a fresh database with zero customers.

Put it in db._MIGRATIONS if that is where comparable data migrations live; if the
existing migrations are column-adds only, add it as a dedicated function following
the "table rebuilds in dedicated functions" pattern CLAUDE.md describes, and call it
from connect().

Tests (real SQLite, no DB mocks): seed customers with 5-year retention_until values
and varied closure dates, run the migration twice, and assert dates are correct,
unchanged on the second run, never shortened, and org-scoped. Add a fresh-database
test.

Branch fix/79-extend-retention-dates. Run the full suite, then open a PR with
gh pr create referencing "Closes #79".
```

---

### p48 — Server-side evidence-pack PDF
High · Feature · **Premise needs checking first**

I could not find `window.print` anywhere in `amlkit/web/templates/`, and no Python
file references WeasyPrint. The board describes replacing a browser print export that
may no longer exist. Start by finding the current state.

```
Investigate, then implement, the server-side evidence pack PDF for amlkit.

FIRST, establish the current state and report it before writing code:
- How is the customer evidence pack currently exported? Search templates and routes
  for evidence, print, and export. The board claims a browser window.print() export
  exists, but I could not find window.print in amlkit/web/templates/ - confirm
  whether it exists, was removed, or never did.
- Is WeasyPrint or any PDF library already a dependency?

THEN implement GET /customers/<id>/evidence.pdf:
- Server-side render of the existing evidence view to PDF.
- Footer on every page: generation timestamp (UTC), amlkit version, and the ruleset
  version from amlkit/risk/ruleset.yaml.
- org_id scoped - an operator must not be able to fetch another org's evidence pack
  by guessing an id. This is the first thing to test.
- Requires an authenticated session; log the export to audit_log with org_id.
- If a browser print path exists, keep it working as a fallback.
- Add the PDF library to requirements.txt and regenerate requirements.lock.

Tests (real SQLite, no DB mocks): 200 and a valid PDF magic-byte header for the
owning org; 404 or 403 for a different org; audit row written; footer contains the
version strings.

Branch feat/evidence-pdf. Run the full suite, then open a PR with gh pr create.
```

---

### p59 — Complete the Privacy Policy and link it from registration
High · Legal / Privacy · **Needs your inputs before any code**

Blocked on facts only you have. Gather these first, then the code part is small.

Required: registered firm name · registered address · trade licence number · MLRO
contact email · effective date. Depends on p88 (the data audit) for the processing
description to be accurate rather than boilerplate.

```
Complete the amlkit Privacy Policy and wire it into the product.

Use these values to fill the template placeholders:
  Firm legal name: <...>
  Registered address: <...>
  Trade licence number: <...>
  MLRO contact email: <...>
  Effective date: <...>

Then:
1. Link the policy from the registration flow so it is visible BEFORE account
   creation, not after - UAE PDPL consent must be informed and prior.
2. Add the policy URL to the Google Play Store listing metadata in the repo if the
   listing is tracked here.
3. Make sure the policy is reachable without authentication.

Do not invent any factual claim about data handling. If the template contains a
statement you cannot verify against the code, flag it in the PR description instead
of leaving it in.

Branch feat/privacy-policy-complete. Run the full suite, then open a PR with
gh pr create referencing "Closes the privacy policy item".
```

---

### p88 — Audit what client data amlkit collects, processes, stores and transmits
High · Research · Prerequisite for p59 and p90

```
Produce a data inventory for amlkit. This is a research and documentation task - no
behaviour changes.

Enumerate every category of personal and client data the system touches:
1. Customer PII fields - read db.py SCHEMA and list every column holding personal
   data, with its table.
2. Document uploads - what is stored, where (amlkit/storage.py), and for how long.
3. Screening results and alerts - what is retained about a match.
4. Audit log entries - what personal data ends up in them.
5. Session tokens and auth_log - including the IP column.
6. OCR extraction (cases/ocr.py) - passport and Emirates ID fields.

For every third party that receives or supplies data, state exactly what crosses the
boundary: the sanctions sources in amlkit/ingest/ (EOCN, UN, OFAC, EU, UK, CIA),
GDELT via amlkit/screening/adverse_media.py, SendGrid via amlkit/mail.py, goAML via
amlkit/reporting/goaml.py, Google Cloud Run, and Litestream/GCS replication.

For each entry give: data category, where it lives, why it is collected, retention
period, who it is shared with, and the lawful basis under UAE PDPL where you can
infer it - marking clearly where you cannot.

Write it to docs/data-inventory.md. Where the code contradicts what a privacy policy
would typically claim, call that out in a "Discrepancies" section at the end - that
section is the point of the exercise.

Branch docs/data-inventory. Open a PR with gh pr create.
```

---

### p89 — Catalogue every API dependency
High · Research

```
Produce an API dependency catalogue for amlkit at docs/api-dependencies.md. Research
and documentation only - no behaviour changes.

Cover every external dependency, reading the actual adapter code rather than assuming:
EU FSF (ingest/eu.py), OFAC (ingest/ofac.py), UN (ingest/un.py), UK (ingest/uk.py),
EOCN (ingest/eocn.py), CIA PEP (ingest/cia.py), FATF (ingest/fatf.py), Interpol
(ingest/interpol.py), OpenSanctions (ingest/opensanctions.py), GDELT
(screening/adverse_media.py and screening/gdelt_bq.py), SendGrid (mail.py), goAML
(reporting/goaml.py), BigQuery (reporting/bigquery.py), Gemini (ai/gemini.py),
Cloud Run, and Litestream/GCS.

For each: provider, purpose, what data is sent and received, auth mechanism and which
env var holds the credential, cost (free / paid / quota), what happens on failure
(read the actual except branches - does it fail loud, fail silent, or fall back?),
commercial redistribution rights, and security implications.

Classify each as mandatory / recommended / optional / future, and put the mandatory
list in a summary table at the top.

Flag prominently: any source whose failure mode is silent, and any that currently has
no credential configured.

Branch docs/api-dependencies. Open a PR with gh pr create.
```

---

### p85 — Decide Stripe pricing tiers, trial model and overage policy
High · Billing · **Decision, not implementation**

A commercial decision that gates p86 and p87, and feeds the ARR model (i4) on the
Investment board. Don't hand this to an agent — but you can have one prepare the
inputs:

```
Prepare a pricing decision brief for amlkit at docs/pricing-decision-brief.md. Do not
implement anything.

Inputs to gather:
1. From research/pricing-teardown.md and research/vendor-matrix.md, summarise what
   the alternatives charge and how they meter.
2. From the code, work out what is actually meterable today: screening counts,
   customer counts, operator seats, adverse-media checks, report filings. Name the
   table or counter that would back each meter, and flag any that are not currently
   recorded at all - those cannot be billed on without new instrumentation.
3. From research/commercial-launch-costs.md, summarise the per-tenant cost floor.

Then lay out, without choosing for me: two or three candidate tier structures by org
size, trial-length options with their conversion trade-offs, and overage handling
options (hard cap / soft cap with warning / metered overage), each with what it
implies for the code.

End with the specific questions I need to answer before any billing code is written.
```

---

### p86 — Stripe subscription management
High · Billing · Blocked by p85

Do not start before p85 is decided. Note the hard architectural constraint below —
it is the part most likely to be got wrong.

```
Implement Stripe subscription management for amlkit.

Decisions already made (from the pricing brief): <paste tiers, trial, overage here>.

Scope:
1. Org-level billing, never user-level. The billing subject is the organisation.
2. Upgrade and downgrade flows, with proration handled by Stripe.
3. Failed-payment retry and lockout: define what a locked-out org can still do -
   at minimum it must retain read access to its own records, because a billing
   dispute must never destroy a firm's ability to meet a regulatory records request.
4. Cancellation with a data-retention grace period consistent with RETENTION_YEARS.

HARD CONSTRAINT: strict separation between billing data and AML/client data. The
billing layer must not query AML tables and must not join across them. Keep billing
in its own module with its own tables, and if you find yourself needing a customer or
alert row to answer a billing question, stop and flag it rather than reaching across.

Never log or store raw card data or full Stripe secrets. Webhook endpoints must
verify the Stripe signature and must be exempt from CSRF (document why in a comment).

Tests (real SQLite, no DB mocks): subscription lifecycle transitions, a locked-out
org retaining read access, webhook signature rejection, and a test asserting the
billing module issues no queries against AML tables.

Branch feat/stripe-subscriptions. Run the full suite, then open a PR with
gh pr create.
```

---

## Medium

### p94 — Super-admin cross-tenant drill-down writes no audit entry
`#260` · Medium · Security / Audit trail

Rated medium upstream, but for an AML system an unlogged privileged cross-tenant read
is the kind of gap an auditor opens with. Worth pulling forward.

```
Fix issue #260 in amlkit.

Super-admin drill-down into another tenant's customer or alert record writes no
audit_log entry, so privileged cross-tenant access leaves no trail at all.

Find every route that lets a super-admin read a record outside their own org, and log
each access with db.audit(): acting operator id, acting org, target org_id, record
type, record id, and timestamp. Log the read itself - not just mutations. Reads are
the whole point here.

Make it structural rather than per-route if you can: a single choke point that every
cross-tenant read passes through is far better than remembering to add a call to each
handler, because the next new route will forget.

Tests (real SQLite, no DB mocks): a super-admin reading org B's customer while
authenticated to org A produces an audit row naming both orgs; a normal operator
attempting the same is refused; an operator reading within their own org does not
generate a cross-tenant audit row.

Branch fix/260-cross-tenant-audit. Run the full suite, then open a PR with
gh pr create referencing "Closes #260".
```

---

### p95 — goAML serialiser hardcodes institution names
`#261` · Medium · Bug

**Verified anchors:** `amlkit/reporting/goaml.py:44` (`serialize_goaml_xml`),
hardcoded string at `:223`.

Third hardcoding defect in the same file family — p70 and p71 were the reporting
entity, this is the counterparty. Worth checking for a fourth while in there.

```
Fix issue #261 in amlkit.

amlkit/reporting/goaml.py:223 writes the literal strings "Originating Bank" and
"Beneficiary Bank" into the goAML XML instead of the actual institutions on the
transaction. Every STR/SAR filed to the UAE FIU therefore carries fictitious
counterparty institution names.

In serialize_goaml_xml() (goaml.py:44), source the originating and beneficiary
institution details from the transaction record. If the transaction does not carry
them, add the fields rather than substituting a placeholder - a placeholder in a
regulatory filing is worse than a blank, and worse than an error.

Where a field is genuinely unknown, omit the element if the goAML 5.0 schema permits
it, or fail the serialisation with a clear message naming the missing field. Do not
invent a default.

While you are in this file: PRs #179 and #142 fixed the same class of bug for the
reporting entity. Grep the whole file for any other hardcoded institution, address or
name string and report what you find in the PR, even if you do not fix it.

Tests (real SQLite, no DB mocks): a transaction with both institutions serialises
them correctly; a transaction missing one either omits the element or raises, and
never emits "Originating Bank"; add an assertion that the literal strings
"Originating Bank" and "Beneficiary Bank" appear nowhere in generated XML.

Branch fix/261-goaml-institutions. Run the full suite, then open a PR with
gh pr create referencing "Closes #261".
```

---

### p4 — Merge #83 and set `AMLKIT_REGISTRATION_INVITE_CODE`
`#84` · Medium · Deployment ordering

Ordering matters: set the env var **before** merging, or there is a window where
registration is open with no invite code enforced.

```
Close issue #84 in amlkit, in this order:

1. FIRST set AMLKIT_REGISTRATION_INVITE_CODE on the Cloud Run service. Do not commit
   the value anywhere.
2. Verify PR #83 is still green against current main - rebase it if main has moved.
3. Then merge #83.
4. Verify on the deployed instance that self-registration without the invite code is
   refused on BOTH the web flow and the mobile endpoint. The mobile path is the one
   likely to be missed.
5. Close #84 with a comment naming both checks.

If step 4 shows either path still open, do not close the issue - report what is still
reachable.
```

---

### p49 — Tabbed customer detail page
Medium · Feature · `amlkit/web/templates/customer.html`

```
Restructure amlkit/web/templates/customer.html into tabbed or accordion sections.

Sections: Overview (UBOs, risk score, ownership diagram), Alerts, Monitoring
(transactions, adverse media), Case File (notes, signatures), History (screenings,
audit trail).

Requirements:
- The active tab is tracked in the URL hash so the dashboard can deep-link straight
  to, say, a customer's Alerts tab.
- No content may become unreachable without JavaScript. If JS is off, every section
  renders stacked. This page is evidence for an auditor; it cannot depend on script.
- Keyboard navigable: arrow keys between tabs, correct roles and aria-selected.
  p82 and p83 already did an accessibility pass - do not regress it.
- Do not change what data is shown or any query. This is presentation only.

Tests: assert every section's content is present in the rendered HTML, and add a
check that the page carries no inline event handlers (PR #94 removed inline scripts
for CSP - do not reintroduce them).

Branch feat/customer-detail-tabs. Run the full suite, then open a PR with
gh pr create.
```

---

### p57 — Inline alert detail panel on the dashboard
Medium · Feature · Dashboard

Build this before p55 and p56 — all three touch the same alert queue markup, and
doing the structural one first avoids two rounds of conflicts.

```
Add a click-to-inspect alert detail panel to the amlkit dashboard alert queue.

Clicking an alert row opens an inline panel showing customer info, match details and
the available actions, without navigating away from the queue.

Requirements:
- Load the detail lazily on first open, not for every row on page load. The queue can
  be long.
- Every fetch is org_id scoped server-side. Do not trust an alert id from the client.
- Actions taken in the panel go through the same routes, CSRF validation and
  four-eyes checks as the full alert page. No shortcut path.
- Keyboard accessible: focus moves into the panel on open, Escape closes it and
  returns focus to the row.
- External JS file, wired with addEventListener - no inline handlers (CSP, PR #94).

Tests (real SQLite, no DB mocks): the detail endpoint returns the alert for the
owning org and 404s for another org; an action taken via the panel is audited
identically to the same action on the full page.

Branch feat/dashboard-alert-panel. Run the full suite, then open a PR with
gh pr create.
```

---

### p55 — "Assigned to" column on the dashboard alert queue
Medium · Feature · Dashboard

```
Add an "Assigned to" column to the amlkit dashboard alert queue.

Check first whether alerts already have an assignee concept. If they do not, this
item is larger than the board suggests - report that before building, because
assignment needs a column, an assign action, an audit entry and a permission rule,
not just a table column.

Assuming assignment exists or you add it:
- Show the assigned operator's name per open alert, "Unassigned" where empty.
- Make the column sortable, and make unassigned alerts sort first - an unassigned
  alert is the one at risk.
- org_id scoped: never show an operator from another org.

Tests (real SQLite, no DB mocks): the column renders the right operator, unassigned
alerts sort first, and no cross-org operator name can appear.

Branch feat/alert-assignment-column. Run the full suite, then open a PR with
gh pr create.
```

---

### p56 — Live audit activity feed widget on the dashboard
Medium · Feature · Dashboard

```
Add a compact audit activity feed widget to the amlkit dashboard showing the last 4-6
audit_log entries: who did what, when.

Requirements:
- org_id scoped. This is the single most important constraint on this widget - it
  renders audit data, and a leak here shows one firm another firm's activity.
- Respect the audit access rule: /audit is MLRO-restricted (t3, PR #123). This widget
  must not become a way for an officer-role operator to read the audit trail. Either
  restrict the widget to MLRO and admin, or show only entries the viewing operator
  generated themselves. Pick one and say which in the PR.
- Render entries as readable sentences, not raw rows.
- No polling loop unless you cap it; a page left open overnight must not hammer the
  DB.

Tests (real SQLite, no DB mocks): widget shows only the viewing org's entries; an
officer-role operator sees either nothing or only their own actions per the rule you
chose; entry ordering is newest first.

Branch feat/dashboard-audit-feed. Run the full suite, then open a PR with
gh pr create.
```

---

### p87 — Usage and cost dashboard for operators
Medium · Billing · Blocked by p85 and p86

```
Build a usage and cost dashboard for amlkit operators.

Depends on the metering decided in p85 and the subscription records from p86. Do not
start until both exist.

Show, for the current billing period: consumption against each metered limit,
proximity to each limit with a clear warning state before the limit is hit, and a
cost breakdown by feature.

Constraints:
- org_id scoped.
- Read from the billing module's own tables. Do not query AML tables to compute usage
  - that is the separation p86 establishes. If a usage figure is only derivable from
  AML data, that is a metering design gap: flag it rather than reaching across.
- An org at or over its limit must see what happens next in plain words.

Tests (real SQLite, no DB mocks): figures match seeded usage, warning state triggers
at the configured threshold, no cross-org leakage, and no query against AML tables.

Branch feat/usage-dashboard. Run the full suite, then open a PR with gh pr create.
```

---

### p90 — Legal document review against actual implementation
Medium · Privacy · Blocked by p88

```
Review amlkit's Privacy Policy, Terms of Use and Cookie Policy against what the code
actually does. Use docs/data-inventory.md from p88 as the source of truth.

For each document, go claim by claim and mark it Accurate / Inaccurate / Unverifiable
against the implementation. Do not rewrite anything yet - produce the gap list first,
at docs/legal-review-gaps.md.

Specifically determine, from the code and templates rather than by assumption:
- Are there any advertising, analytics or third-party tracking technologies present?
  Search templates and static assets for third-party scripts, pixels and beacons.
- What cookies does the app actually set? List each with its purpose and lifetime.
  The CSRF cookie and session cookie at minimum.
- Is cookie consent legally required given what you found? If only strictly necessary
  cookies are present, say so plainly - it changes the answer.

Do not copy wording from a competitor's policy. Every sentence must be defensible
against this codebase.

Branch docs/legal-review-gaps. Open a PR with gh pr create.
```

---

## Low

### p9 — Move business logic out of `api/app.py`
`#73` · Low · Tech debt · **Bigger than the board says**

The board says ~2,280 lines. It is now **3,256**. Do not attempt this in one pass.

```
Reduce amlkit/api/app.py, currently 3256 lines, toward thin route handlers.

Do NOT attempt the whole file in one PR. Work in slices and open a separate PR per
slice, so each stays reviewable and conflicts stay small.

For this pass, pick ONE cohesive route group (alerts, customers, reports or admin)
and:
1. Move its inline SQL into amlkit/queries.py (reads) or amlkit/cases/manager.py
   (writes), following the existing signatures. Every function takes org_id.
2. Leave the route handler doing only: resolve session, validate input, call the
   extracted function, render.
3. Change no behaviour. No response body, status code, audit entry or permission
   check may differ. The existing tests are the contract - if any test needs editing,
   you have changed behaviour, so stop and explain why.

Report the line count before and after, and state which group you did so the next
pass can pick a different one.

Branch refactor/73-<group>-extraction. Run the full suite, then open a PR with
gh pr create referencing "#73" but NOT "Closes" - this takes several passes.
```

---

### p10 — Unclassified refresh error
`#40` · Low · Needs triage before work

Issue #40 is image-only with minimal detail, and is probably a symptom of #85 rather
than a defect of its own.

```
Triage issue #40 in amlkit ("Refresh error"). It is an image-only report with almost
no detail.

1. Read the issue and its attachment with: gh issue view 40 -R nadhirmhdar/amlkit
2. Work out which source and which failure mode it shows.
3. Determine whether it is a duplicate of #85 (EU FSF token unset, causing EU refresh
   failures) or something separate.
4. If it is a duplicate, close it as such with a comment linking #85.
5. If it is separate, reproduce it, then either fix it or rewrite the issue with a
   proper description and reproduction steps so it can be worked later.

Do not invent a fix for an error you cannot reproduce.
```

---

### p51 — First-run guided onboarding for empty orgs
Low · Feature · `amlkit/web/templates/home.html`

```
Add first-run guidance to amlkit's home.html for organisations with zero customers.

When the org has no customers, replace the normal home content with a three-step
sequence: "Step 1: Screen a name", "Step 2: Onboard your first customer",
"Step 3: Review your dashboard", each linking to the relevant route, each showing a
done state once that step has been completed.

Detect completion from real data (a screening exists, a customer exists), not from a
dismissible flag - an operator who completes a step elsewhere should see it ticked.

Consider a demo mode with pre-loaded sample data. If you add one, sample records must
be unmistakably fake and must never be counted in dashboards, alerts, reports or any
figure an operator could mistake for real compliance data. If that cannot be
guaranteed cleanly, leave demo mode out and say why.

Tests (real SQLite, no DB mocks): an org with zero customers sees the sequence; an
org with one customer does not; step completion reflects actual data.

Branch feat/first-run-onboarding. Run the full suite, then open a PR with
gh pr create.
```

---

### p52 — Changelog / "What's new" for operators
Low · Feature

```
Add a changelog section to amlkit so operators can see recent improvements.

Source it from a committed file (docs/CHANGELOG.md) rendered in-app, rather than a
database table - it is the same for every tenant and belongs in version control.

Requirements:
- Reachable from the authenticated nav.
- Newest first, dated, written for compliance operators rather than developers: what
  changed for them, not which function was refactored.
- Do not surface a "new since your last visit" badge unless you store a per-operator
  last-seen timestamp; if you do, keep it in the operator record, org-scoped.

Seed it with the genuinely operator-visible changes already merged: MFA for MLRO
operators (#244), the organisation name in the header (#91), stale sanctions source
warnings (#92), the searchable country dropdown (#147), customer reactivation (#239),
and the compliance calendar (#119).

Branch feat/changelog. Run the full suite, then open a PR with gh pr create.
```

---

### p58 — Global keyboard search (⌘K / Ctrl+K)
Low · Feature · Depends on the p47 Arabic canonicaliser

```
Add a global command-palette search to amlkit, opened with Ctrl+K on Windows and
Cmd+K on Mac, searching customers, open alerts and cases by name or reference number.

Requirements:
- Server-side search at a dedicated endpoint, org_id scoped. Never ship an index to
  the client.
- Reuse the Arabic canonicaliser from amlkit/names/arabic.py, the same path PR #194
  used for customer search, so "Mohd" finds "Mohammed" and "محمد". Do not write a
  second normalisation path - and note that PR #148 fixed a bug where the canonicaliser
  mangled names with an inherent Al- prefix (Ilyas, Ilham), so include those as test
  cases to prevent regression.
- Debounce input and cap results.
- Fully keyboard operable: arrows to move, Enter to open, Escape to close, focus
  returned to where it was.
- External JS, addEventListener, no inline handlers (CSP).

Tests (real SQLite, no DB mocks): results are org-scoped; an Arabic-script query
finds the Latin-script record and vice versa; Ilyas and Ilham match themselves;
results cap is enforced.

Branch feat/global-search. Run the full suite, then open a PR with gh pr create.
```

---

# Part 2 — External-tool runbooks (12)

These are not implementation tasks. Each points an external tool at the codebase and
brings findings back. They produce reports, not PRs — so each one ends by writing its
output somewhere you can act on, and by filing real issues for what it finds.

## Tooling availability — read this first

The board cites paths like `/home/user/gstack`. Those are from a different machine.
On `C:\Users\nizam` I found only two of the twelve:

| Tool | Status |
|---|---|
| `gstack` | **Present** — `C:\Users\nizam\gstack` |
| `superpowers` | **Present** — `C:\Users\nizam\superpowers` (board calls it `superpowers-clone`) |
| ui-ux-skills, awesome-claude-skills, openhands, ai-engg, mcp-servers, public-apis, awsm-llm-apps, langflow, freefordev | **Not found** at the home directory, `Codex-Workspace`, `bedrock-project`, `scratch` or `.agents` |

I only searched those five roots — the missing ten may be on another drive, in WSL, or
gone. Each runbook below starts by locating or cloning its tool rather than assuming a
path, so none of them fail silently on a stale reference.

A general caution for all twelve: these tools generate findings in volume, and volume
is already a problem on this repo. You have nine open bot-generated issues (#251–#253,
#265–#268, #295–#296) that exist only because automation filed them. Each runbook
below therefore ends with a triage step — file issues for confirmed defects only, and
report the rest in a document.

---

## Present on this machine

### t21 — gstack `/cso` security audit
Critical · `C:\Users\nizam\gstack`

```
Run a security audit of amlkit using gstack's Chief Security Officer workflow.

gstack is at C:\Users\nizam\gstack. Read its README and the /cso and /review command
definitions first to see how it expects to be invoked.

Target, in priority order:
  amlkit/api/app.py        (3256 lines, all routes)
  amlkit/auth.py           (sessions, password hashing, CSRF)
  amlkit/api/mobile.py     (bearer-token auth, upload paths)
  amlkit/api/deps.py       (request-scoped session and CSRF resolution)
  amlkit/cases/review.py   (four-eyes - see open issue #258)

Focus on what this codebase's threat model actually is: multi-tenant isolation
(every query must take org_id), privilege boundaries between officer and MLRO roles,
and the audit trail's completeness. A cross-tenant read that leaves no audit entry is
a finding even if no data is corrupted - see #260 for the shape of that bug.

This supplements scripts/security_scan.py (PR #106), which covers the mechanical
conventions. Do not just re-report what that script already catches; say explicitly
which findings the static scan would have missed.

Output to docs/reviews/gstack-cso-<date>.md. For each finding: severity, file and
line, why it matters for a UAE-regulated AML system specifically, and a suggested
fix. Then file GitHub issues ONLY for findings you have confirmed by reading the
code - not for pattern matches. Cross-check against open issues first so you do not
duplicate #257 through #261.
```

---

### t22 — gstack `/qa` defect-finding pass
Critical · `C:\Users\nizam\gstack`

```
Run a QA pass on amlkit using gstack's /qa and /review workflows.

gstack is at C:\Users\nizam\gstack. Read its README and command definitions first.

Target the routes, auth flow and screening path, plus the existing test suite in
tests/. The suite is large (130+ files) and passing, so the value here is in what it
does NOT exercise, not in what it covers.

Look specifically for:
- Edge cases the integration tests miss: empty result sets, unicode and Arabic-script
  input, boundary values on thresholds, concurrent writes to the same customer.
- Routes with no test file at all. Cross-reference tests/ against the routes in
  app.py and mobile.py and list the uncovered ones.
- State machines that can be entered twice or exited early - report submission,
  four-eyes disposition, customer closure and reactivation.
- Error paths that return the wrong status code. #98 (negative UBO percentage
  returning 500 instead of 422) and #99 (admin route returning 200 for an officer)
  were both this class of bug, so assume there are more.

Output to docs/reviews/gstack-qa-<date>.md, grouped by severity, each finding with a
concrete reproduction. File issues only for defects you have reproduced.
```

---

### t23 — superpowers TDD workflow for unbuilt features
High · `C:\Users\nizam\superpowers`

**The board's premise is out of date.** t23 says to apply this before implementing
p14–p22 — but every one of p14 through p22 has since merged. The workflow is still
worth adopting; the targets have changed.

```
Adopt the superpowers spec-first TDD workflow for amlkit's remaining unbuilt work.

superpowers is at C:\Users\nizam\superpowers (the board calls it superpowers-clone).
Read its README and the writing-plans and test-driven-development skill definitions.

Note: the board says to apply this to p14-p22 (idle timeout, MFA, password change,
concurrent sessions, rate limits). All of those have already merged. Apply it instead
to the features that are still unbuilt and non-trivial:
  - Per-org single_operator_mode (#258)
  - Structuring rule across payment methods (#257)
  - Server-side evidence pack PDF
  - Stripe subscription management

For each, produce the spec and the failing test suite BEFORE any implementation.
Tests must follow this repo's convention: integration tests against real SQLite, no
DB mocks, TestClient for HTTP, the _register() helper from tests/test_api.py.

Write the specs to docs/specs/<feature>.md and commit the failing tests on a branch
per feature, clearly marked as failing-by-design so CI status is not misread.

Do not implement anything in this pass. The output is specs plus red tests.
```

---

## Need locating or cloning first

Each of these begins by finding the tool. If it is not on the machine, clone it from
its public repository into `C:\Users\nizam\tools\<name>` rather than scattering clones
across the home directory — and tell me where you put it.

### t24 — UI/UX audit of the web templates
High · ui-ux-skills

```
Run a UI/UX audit of amlkit's web templates.

First locate the ui-ux-skills toolkit. The board references a ui-ux-skills-clone
directory that is not on this machine. Search for it; if it is absent, find the
public repository, clone it to C:\Users\nizam\tools\ui-ux-skills, and tell me where
you put it. If you cannot identify the right repository with confidence, stop and ask
rather than substituting a different toolkit.

Target amlkit/web/templates/ - forms, dashboard and navigation.

Context on what has already been done, so you do not re-report solved problems:
the searchable country dropdown (#147), the avatar nav restructure (#150), the
freeze-obligations panel (#152), the alerts drawer (#195) and two accessibility
passes (#199, #200) have all merged. The accessibility work in particular means
contrast, focus states and screen-reader labels have had a pass - report regressions,
not the original findings.

The users here are compliance operators doing repetitive, high-stakes data entry
under time pressure. Weight findings accordingly: a form that loses entered data on a
validation error matters far more than a spacing inconsistency.

Output to docs/reviews/ui-ux-audit-<date>.md, findings ranked by operator impact.
```

---

### t25 — Browser-driven testing against the live staging URL
High · webapp-testing

```
Run browser-driven checks against amlkit's deployed instance at
https://amlkit-720622408077.me-central1.run.app

First locate the webapp-testing skill. The board references
awesome-claude-skills-cloned/webapp-testing, which is not on this machine. Locate or
clone it, and tell me where you put it.

BEFORE running anything: this is a live deployment holding real tenant data. Do not
create, modify or delete any record. Do not submit any form that writes. Restrict
yourself to reading pages, checking responses and observing console output. If a
check requires authentication, ask me for a test account - do not attempt to
register one, since invite-code registration (#84) is being locked down.

Look for: JavaScript console errors, broken routes and 404s on linked pages, failed
network requests, missing static assets (PR #133 added a smoke test for this after
the CSP migration moved scripts to static files - verify it holds in production), and
accessibility failures.

Output to docs/reviews/webapp-testing-<date>.md. Note explicitly which pages you
could not reach without credentials.
```

---

### t26 — Autonomous agent pass for bugs and missing test stubs
High · OpenHands

```
Run OpenHands against amlkit to surface bugs and generate test stubs for uncovered
code.

First locate OpenHands. The board references openhands-cloned, which is not on this
machine. Locate or clone it, and tell me where you put it. OpenHands needs an LLM
API key and a container runtime - confirm both are configured before starting, and
tell me what it will cost to run before you run it.

Scope it narrowly. Do not let it loose on the whole repo: point it at the modules
with the thinnest coverage. Cross-reference tests/ against amlkit/ first and report
which modules have no dedicated test file, then target those.

Constraints:
- It may generate test stubs and propose fixes. It must not push, open PRs, or merge
  anything.
- Generated tests must follow the repo convention: real SQLite, no DB mocks.
- Review every generated test before committing. A test that passes for the wrong
  reason is worse than no test, and an autonomous agent will produce some.

Output the proposed tests on a branch chore/openhands-test-stubs and a summary at
docs/reviews/openhands-<date>.md. I will review before anything merges.
```

---

### t28 — Name-matching audit against production RAG patterns
Medium · ai-engg

```
Audit amlkit's name-matching against production information-retrieval patterns.

First locate the ai-engg reference collection (board calls it ai-engg-clone; not on
this machine). Locate or clone it, and tell me where you put it.

Target: amlkit/match/engine.py, amlkit/match/scorer.py and amlkit/names/arabic.py
(453 lines of Arabic canonicalisation).

This is a sanctions-screening matcher, so the trade-off is asymmetric and must drive
every recommendation: a false negative means a sanctioned party is onboarded
undetected - a regulatory breach. A false positive means an operator reviews an alert
and dismisses it. Recall is worth far more than precision here, and any proposal that
improves precision at the cost of recall should be rejected outright rather than
listed as a trade-off.

Compare against ColBERT-style late interaction and corrective-RAG reranking patterns,
but be realistic: this runs on SQLite on Cloud Run, not a vector database. A
recommendation requiring infrastructure the project does not have is not actionable -
say so if that is the conclusion.

Note PR #148 fixed a canonicaliser bug where names with an inherent Al- prefix
(Ilyas, Ilham) scored 0.0 against themselves. That class of bug - over-aggressive
normalisation destroying a name - is exactly what to hunt for.

Output to docs/reviews/name-matching-audit-<date>.md: current approach, concrete
weaknesses with example name pairs that fail, and recommendations ranked by recall
improvement per unit of implementation effort.
```

---

### t29 — Survey MCP servers for the dev workflow
Medium · mcp-servers

```
Survey available MCP servers for amlkit's development workflow.

First locate the MCP server directory (board calls it mcp-servers-cloned; not on this
machine). Locate or clone it, and tell me where you put it.

Look for servers in three categories: SQLite/database inspection, filesystem, and any
sanctions, company-registry or financial-data API servers.

For each candidate: what it does, what credentials it needs, whether it is actively
maintained, and what it would add that the current setup lacks.

Security constraint, and it is the whole point of this task: amlkit's database holds
customer PII, passport and Emirates ID data. Do not recommend any server that would
send database contents to a third party, and for each recommendation state explicitly
where data goes. A local-only server is acceptable; anything that phones home is not.

If you recommend wiring any into .claude/settings.json, show the config as a proposal
in the report. Do not modify the file.

Output to docs/reviews/mcp-server-survey-<date>.md.
```

---

### t30 — Survey public APIs for additional screening sources
Medium · public-apis

```
Survey public API catalogues for sources that could supplement amlkit's screening
coverage.

First locate the public-apis catalogue (board calls it public-apis-cloned; not on
this machine). Locate or clone it, and tell me where you put it.

amlkit currently ingests: EOCN (UAE Local Terrorist List), UN, OFAC, EU FSF, UK,
CIA World Leaders (PEP), FATF, Interpol and GDELT. Read amlkit/ingest/ to confirm
before surveying.

Look in the Finance, Government and Security categories for: additional sanctions or
watchlist sources, beneficial-ownership registries, and PEP sources - with a bias
toward GCC and MENA coverage, since that is where this product's customers are.

For each candidate, the questions that decide it:
1. Commercial redistribution rights. amlkit's README states every current source
   allows commercial redistribution. A source that does not is unusable here
   regardless of quality - check the licence before anything else.
2. Is it a primary publisher or an aggregator? The project deliberately moved off
   OpenSanctions to primary sources in PR #44. Do not recommend re-aggregating.
3. Update frequency, auth, cost, and format.

Output to docs/reviews/public-api-survey-<date>.md, with anything failing test 1 or 2
listed in a rejected section with the reason, so nobody re-evaluates it later.
```

---

### t31 — Agent patterns for compliance automation
Medium · awsm-llm-apps

```
Review agent and LLM application patterns for applicability to amlkit's compliance
automation.

First locate the template collection (board calls it awsm-llm-apps-cloned; not on
this machine). Locate or clone it, and tell me where you put it. Confirm the licence
permits reuse before recommending any pattern - the board claims Apache-2.0; verify.

Look for patterns applicable to three specific jobs: automated periodic CDD refresh,
sanctions-hit triage, and STR narrative drafting.

Hard constraint on all three: amlkit already has an AI narrative endpoint
(POST /api/ai/draft-narrative, amlkit/ai/gemini.py) and #164 found it processing
customer PII against a paid LLM with no CSRF protection and no rate limiting. Any
pattern you recommend must state what customer data would leave the system and to
where. A pattern that sends PII to a third-party model is a PDPL question, not just
an engineering one.

Second constraint: an AI system must not make a regulatory determination. Drafting an
STR narrative for an MLRO to review and sign is acceptable. Deciding whether to file,
or auto-dismissing a sanctions hit, is not. Reject any pattern that removes the human
from a decision that carries legal liability, and say so explicitly.

Output to docs/reviews/agent-patterns-<date>.md.
```

---

### t32 — Model the onboarding-to-STR workflow as a visual pipeline
Medium · Langflow

```
Model amlkit's core compliance workflow as a Langflow pipeline to validate the state
machine.

First locate Langflow (board calls it langflow-cloned; not on this machine - though
there is a .langflow directory in the home folder, which suggests it has been run
before). Locate or install it, and tell me where.

Model the real path: customer onboarding -> sanctions screening -> alert generation
-> alert triage -> four-eyes disposition -> STR generation -> STR submission.

The point is not to replace any code. It is to find gaps in the current route logic
by drawing the state machine explicitly. Read the actual implementation in
amlkit/cases/manager.py, amlkit/cases/review.py, amlkit/match/engine.py and
amlkit/reporting/goaml.py - do not model the idealised workflow from the README.

Specifically look for: states reachable by more than one path with different
validation, transitions with no audit entry, states with no exit (a customer or alert
that can get stuck), and points where four-eyes can be bypassed. Issue #167 was a
four-eyes disposition bug and #141 was a report marked submitted with no
transmission - both are state-machine defects, so that is the class to hunt.

Output the diagram plus a findings list to docs/reviews/workflow-state-machine-<date>.md.
Do not deploy any flow as a REST or MCP endpoint.
```

---

### t33 — Audit CI/CD and monitoring against free-tier alternatives
Low · freefordev

```
Audit amlkit's infrastructure and monitoring stack against free-tier service
catalogues.

First locate the free-for-dev catalogue (board calls it freefordev-cloned; not on
this machine). Locate or clone it, and tell me where you put it.

Current stack, to confirm from the repo before auditing: Google Cloud Run, Litestream
replication to GCS (litestream.yml), GitHub Actions (.github/workflows/ - tests,
codeql, source-canary, backup-verify, recovery-reseed), and Cloud Scheduler since
APScheduler was removed in #207.

The gap worth the most here: there is no error-monitoring or uptime service
configured at all. A scheduled sanctions refresh that starts failing silently is a
compliance exposure - #85 has been open long enough that the repo's own health check
filed three issues about it (#251, #252, #295). Prioritise error tracking and uptime
monitoring over cost savings on things that already work.

For each recommendation: free-tier limits, what happens when exceeded, data residency
(this is a UAE product handling UAE resident PII - a service that stores error
payloads outside permitted jurisdictions is a PDPL problem, and error payloads can
contain PII), and setup effort.

Output to docs/reviews/infra-audit-<date>.md, ordered by risk reduced rather than
money saved.
```

---

## Summary

| | Count |
|---|---|
| Implementation specs | 26 |
| External-tool runbooks | 12 |
| Items to close without work | 4 (p12, t9, t19 done; t18 obsolete) |
| **Total open items reconciled** | **42** |

**Suggested order.** p91 (#258) and p93 (#257) first — both are controls that do not
work, and both are small. Then p92 (#259) and p94 (#260). p1 is not code at all and
closes four issues, so it is the cheapest thing on this list. p2 needs your legal
determination before p3 can be safely run.
