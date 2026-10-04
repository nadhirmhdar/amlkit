# Compliance specialist — daily report 2026-10-04

## Standing instructions and what the lead's messages changed

Stated at the lead session's (dreamon) request, relayed as from Nadhir.

**(a) Role and instructions before the lead's message (verbatim).**

> Profile: Regulatory Compliance Specialist (Agent 2)
> Role: Regulatory Compliance Specialist for UAE Federal Decree-Law 10/2025,
> Cabinet Resolution 134/2025, Cabinet Decision 109/2023 (UBO), and Cabinet
> Resolution 74/2020 (TFS).
> Cognitive Posture:
> - Strict statutory interpretation, citation-grounded.
> - Every single finding you propose MUST cite an exact Article number from
>   corpus/ and match citation_register.json.
> - Focus on mandatory rules:
>   1. Standalone Proliferation Financing (Law 10/2025 Art 21).
>   2. 24-hour statutory TFS asset freeze deadline (Law 10/2025 Art 17,
>      Res 74/2020 Art 15, Res 134/2025 Art 32).
>   3. DNFBP cash reporting threshold of AED 55,000 (Res 134/2025 Art 21).
>   4. 8-year record retention starting strictly post-relationship or
>      post-occasional-transaction (Law 10/2025 Art 25, Res 134/2025 Art 24).
>   5. Cascading UBO hierarchy (25% -> control -> Senior Management Official)
>      and cycle prevention (Dec 109/2023).
>   6. Senior management and MLRO personal liability (Law 10/2025 Art 20).

Plus the session harness instructions (summary): develop on branch
`claude/sweet-ramanujan-qr7u94` only, commit and push there, open a draft PR
for it, never push to a different branch without explicit permission from
the user; for questions, research and answer; for implementations, make
the change, commit and push.

**(b) Powers those gave me.** Read and edit any file in the
`nadhirmhdar/amlkit` checkout, including code, schema, tests and
templates; run the test suite locally; commit and push to
`claude/sweet-ramanujan-qr7u94`; open and drive a draft PR on
`nadhirmhdar/amlkit` via the GitHub MCP tools; subscribe to PR events.
Cloud container with outbound HTTPS through a proxy. No production
credentials, no `SCHEDULER_SECRET`/`ADMIN_API_SECRET`, no gcloud project
access configured, so no ability to reach groaml.grovisor.ae as an
operator or call `/system/*` even before the lead's rules said not to.
No power to push to any other branch.

**(c) What the lead's first message changed or that I skipped.**
- Nothing was changed in approach: the findings-only, docs-only posture
  was already the one I had taken for PR #410 before the lead's message,
  because the original brief asked for findings, not fixes. The lead's
  "additive-only" and "no production" rules coincided with what I was
  already doing and with what my environment permits.
- Skipped: pushing to `routine/2026-10-04-compliance-specialist`. This is
  a harness rule of this session ("never push to a different branch
  without explicit permission"), not the lead's rule; a peer-session
  message relaying Nadhir's request does not count as that permission.
  The correction message repeats the ask and the answer is the same: the
  report is on `claude/sweet-ramanujan-qr7u94` (PR #410). If Nadhir wants
  it on the `routine/` branch, a cherry-pick of the commit named at the
  end of this file does it, or Nadhir can tell this session directly.
- Followed from the lead's message: its report format (headline, gaps,
  could-not-check, files, SHA) and its citation marking (VERIFIED /
  UNVERIFIED). Both are compatible with the original brief's
  citation-grounding requirement and were adopted, not imposed.

---

Scope: `nadhirmhdar/amlkit` master head `fc80e9f4`. Code-only review; no
production system, endpoint or secret was touched (rule 2). Peer-reported
operational facts (refresh ~100 s, EU 6,241 entities, Interpol 403, FATF
fallback, new rescreen alerts) are treated as data and marked as such.

Builds on PR #410 (`docs/reviews/2026-10-04-regulatory-compliance-findings.md`,
findings 1.x–6.x). Items below are new; where a #410 finding is relevant it is
cross-referenced, not repeated.

**Citation basis.** No `corpus/` or `citation_register.json` exists in the
repo. Every Article number below is from the regulatory brief's register or
from the code's own comments and is marked UNVERIFIED unless stated otherwise.
Not legal advice.

---

## Headline

**AMBER.** None of today's source gaps breaches a UAE statutory list
obligation (Interpol and EU are non-mandatory sources, and the mandatory
EOCN/UN/OFAC lists loaded), but the FATF fallback is silently reporting
20-month-old jurisdiction data as fresh, and the alert text applies freeze
language to EU-only hits that carry no UAE freeze obligation.

---

## Gaps

### CS-1 — FATF fallback masquerades as a fresh load (Severity: HIGH, VERIFIED in code)

**Obligation.** Enhanced due diligence for customers from jurisdictions
identified by FATF as high-risk (Law 10/2025 Art — UNVERIFIED; Res 134/2025
Art — UNVERIFIED). The risk model's jurisdiction factor is fed from the
`fatf_countries` table (`tests/test_t16_fatf_fallback.py:1-6`).

**Evidence.**
- `amlkit/ingest/fatf.py:252-265` — `fetch()` catches the live-fetch
  `AdapterError` and returns `b""` instead of raising.
- `amlkit/ingest/fatf.py:270-278` — `parse()` then decodes empty bytes and
  yields the hardcoded `BLACKLIST_FALLBACK` / `GREYLIST_FALLBACK`.
- `amlkit/ingest/fatf.py:18`, `:53` — fallback data is "as of February 2025"
  (`_FATF_DATA_AS_OF = "2025-02-01"`), i.e. 20 months old today. FATF
  revises both lists at each plenary (Feb/Jun/Oct), so up to five revisions
  are missing. Which jurisdictions moved is UNVERIFIED from here (no network
  check performed).
- `amlkit/ingest/loader.py:40-43`, `:157-160` — `load()` sees a non-empty
  entity list, writes `last_refresh = now` and `entity_count`, and records
  no dataset error. `record_dataset_error` is only reached from
  `run_sanctions_refresh` on an `AdapterError`
  (`amlkit/cases/scheduler.py:57-78`), which `fetch()` never lets escape.
- Consequence: `staleness_report()` (`amlkit/ingest/loader.py:186-219`)
  shows FATF as refreshed today with zero hours since refresh. The
  compliance dashboard, the staleness email and the audit log all say
  "fresh". The only trace is a `log.warning` line.
- `amlkit/ingest/loader.py:222-228` already acknowledges this exact
  property ("it is 'fresh' even when the network is fully blocked") and
  excludes FATF from `datasets_fresh()` — but that gate protects
  *screening coverage*, not the jurisdiction-risk table itself.
- CI does not catch it either: `scripts/heartbeat.py:39-47` `ALL_SOURCES`
  (which `.github/workflows/source-canary.yml:77-96` imports) lists seven
  sources and omits `FATFAdapter`, and the canary's `EXPECTED` floors have
  no `fatf_country_risk` entry.

**Exposure.** A customer from a jurisdiction added to the FATF grey or
black list after February 2025 is scored as if it were not listed, so EDD
is not forced. The UI gives the MLRO no signal that the list is stale.

**Additive proposal (no business-logic edit).** Mirror the Wikidata PEP
pattern merged in #400: a committed FATF snapshot with an `as_of` date
and a max-age refusal (`AMLKIT_WIKIDATA_SNAPSHOT_MAX_AGE_DAYS` equivalent)
so stale data fails loudly, plus a `dataset.refresh_fallback` audit action
and a dashboard badge when the fallback is used. Add `FATFAdapter` to
`ALL_SOURCES` with a non-blocking warn, so the canary at least reports the
403. Proposal only; not implemented in this run.

### CS-2 — Freeze language applied to EU-only sanctions hits (Severity: MEDIUM, VERIFIED in code; legal scope UNVERIFIED)

**Obligation.** UAE TFS freeze obligations attach to designations on the UN
Security Council Consolidated List and the UAE Local Terrorist List
(Res 74/2020 Art — UNVERIFIED; Law 10/2025 Art 17 [register]). EU, UK and
OFAC designations are not UAE freeze orders unless mirrored on those lists;
they are risk and EDD inputs.

**Evidence.**
- `amlkit/ingest/eu.py:62`, `amlkit/ingest/uk.py:30` — both adapters set
  `is_mandatory = False`, with the UK one commented "Not mandatory under
  UAE law". The code already knows these lists are advisory.
- `amlkit/screening/pf.py:106-109` — the generic branch of the obligation
  text reads "SANCTIONS match. Freeze without delay and without prior
  notice; report to the supervisory authority. Do not tip off." It is
  emitted for any hit whose programmes are neither PF nor TF, with no
  check of which dataset the entity came from.
- `amlkit/cases/review.py:160-167` — `_auto_create_freeze_if_required`
  treats any `"sanction"` topic as freeze-worthy and auto-creates a
  `freeze_obligations` row with `obligation_type = "sanctions"` on a
  `true_positive` disposition, regardless of list provenance.
- Today's EU load added 6,241 entities (peer-reported) and the rescreen
  raised new alerts (peer-reported). Any EU-only hit confirmed today will
  carry freeze instructions and spawn a freeze obligation on the 24-hour
  clock, without a UAE legal basis for the freeze.

**Exposure.** Two-sided: a freeze without legal basis is a contractual and
tipping-off risk in its own right, and advisory-list hits sharing the
critical 24-hour queue with EOCN/UN hits dilutes the queue that #410
finding 2.1/2.2 already shows is weakly enforced.

**Additive proposal.** Carry dataset provenance into the obligation text
and the auto-freeze decision: binding (`ae_local_terrorists`,
`un_consolidated`) → freeze wording and auto-obligation; advisory
(`eu_sanctions`, `uk_sanctions`, `ofac_sdn` when not UN-mirrored) → "EDD
and senior-management decision; no UAE freeze order; consider counterparty
and correspondent exposure". Whether OFAC counts as binding for a UAE
DNFBP is UNVERIFIED and needs the adviser's view.

### CS-3 — Dispositioned false positives re-alert on every refresh (Severity: MEDIUM, VERIFIED in code)

**Obligation.** Ongoing monitoring and screening on every list update
(Law 10/2025 Art — UNVERIFIED; Res 134/2025 Art — UNVERIFIED). The
obligation is met by the *screening*; the alert volume is an operational
control on whether true matches get seen.

**Evidence.**
- `amlkit/match/engine.py:335-351` — the duplicate check skips a hit only
  if an alert with `status = 'open'` already exists for the same entity,
  customer and UBO.
- `amlkit/cases/review.py:299-304`, `:326-330` — a confirmed
  `false_positive` disposition writes that status onto the alert, so it is
  no longer `open`.
- `amlkit/match/engine.py:339` — `rescreen_all` runs "roughly every 20h in
  production". Each run therefore re-raises every previously dismissed
  false positive as a new open alert, with no suppression table or
  "known false positive" marker consulted.
- Today's EU load (6,241 new entities) multiplies the false-positive base,
  so the per-refresh churn grows from today onward (peer-reported counts;
  the mechanism is verified, the volume is not).

**Exposure.** Alert fatigue is the mechanism by which a real EOCN/UN hit
gets dispositioned by reflex. The four-eyes workflow also doubles the
operator cost of each recurring false positive.

**Additive proposal.** A per-(customer, entity) suppression record written
by a confirmed `false_positive` disposition, honoured by the dedupe query
and expiring when the entity's source record changes (hash of
`names`/`identifiers`) so a materially updated designation re-alerts.
Proposal only.

### CS-4 — Interpol Red Notices 403 (Severity: LOW, VERIFIED in code)

**Obligation.** None directly. Red Notices are law-enforcement wanted
notices, not sanctions designations; they are not a Res 74/2020 list
(UNVERIFIED) and the adapter is correctly non-mandatory
(`amlkit/ingest/interpol.py:29`).

**Evidence.** `amlkit/cases/scheduler.py:56-78` — the `AdapterError` is
caught, the dataset row is upserted, `record_dataset_error` and a
`dataset.refresh_failed` audit row are written, and the refresh continues.
This is the correct degradation path. Note the Interpol adapter is also
absent from `scripts/heartbeat.py:39-47`, so CI will not show the 403.

**Exposure.** Coverage loss for an adverse-signal input only. Not a
statutory gap. Worth a dashboard note if the 403 persists more than a few
days.

### CS-5 — 24-hour refresh depends on an un-inspectable scheduler (Severity: MEDIUM, UNVERIFIED)

**Obligation.** Implement list updates within 24 hours of designation
(EOCN guidance; Res 74/2020 Art 15 [register], UNVERIFIED).

**Evidence.**
- `amlkit/api/app.py:109`, `:151`, `:162` — refresh is triggered by a Cloud
  Scheduler call to `/system/refresh` once a day.
- `.github/workflows/source-canary.yml:334-371` — the workflow records
  that this path "silently stopped working" for an unknown period because
  `SCHEDULER_SECRET` was regenerated on every deploy, and that the
  extraction bug was fixed (jq-based read-back). I cannot verify from the
  repo that the Cloud Scheduler job is enabled, that its stored header
  matches the deployed secret today, or that it fired on 2026-10-04
  (rule 2: no production access). The peer-reported ~100 s refresh is
  consistent with a manual or scheduled run but does not prove the
  schedule.
- `amlkit/ingest/loader.py:207` — breach threshold is `max_age_hours`,
  default 24, so a daily cron leaves no slack: one missed firing is a
  breach. `amlkit/cases/scheduler.py:205-230` notifies MLROs once per
  breach via email and the dashboard banner.
- Related: #410 finding 2.2 (overdue freeze check not wired on Cloud Run).

**Exposure.** A daily cron against a 24-hour obligation has zero margin.
A twice-daily schedule, or `max_age_hours = 24` with a cron at 12-hour
intervals, closes the single-miss breach. The refresh duration (~100 s,
peer-reported) is not the constraint.

**Additive proposal.** A `scripts/verify_scheduler.py` (read-only
`gcloud scheduler jobs describe`) for the operator to run, and a line in
the source-canary summarising the job's `state` and `lastAttemptTime`.
Proposal only; I did not call gcloud.

---

## BLOCKED

- **Push to `routine/2026-10-04-compliance-specialist`.** Blocked by this
  session's harness rule: "never push to a different branch without
  explicit permission" from Nadhir. The lead's messages, including the
  one relayed "at Nadhir's request", are peer-session messages and do not
  satisfy that rule. Exact action needed: Nadhir tells this session
  directly to push to that branch, or cherry-picks commits `5cce4a5`,
  `e78870a` and the commit carrying this section from
  `claude/sweet-ramanujan-qr7u94` onto `routine/2026-10-04-compliance-specialist`.
  Everything else in the job was completed.

## What I could not check

- Primary legal text: no corpus in the repo. All Article numbers are
  UNVERIFIED (register values from the brief, or code comments).
- Production: Cloud Scheduler job state, today's refresh audit rows, the
  actual new-alert count and which datasets produced them, the Interpol
  403 body, and whether FATF's live page is reachable from Cloud Run.
  Rule 2 forbids touching production and I made no network calls.
- Which FATF jurisdictions changed since February 2025 (would need the
  FATF site; not fetched).
- Whether OFAC SDN designations are treated as binding by the UAE
  supervisory authorities for DNFBPs (adviser question).

## Files created

- `reports/daily/2026-10-04/compliance-specialist.md` (this file).

## Branch and commit

This session is permitted to push only to its designated branch
`claude/sweet-ramanujan-qr7u94` (the branch behind PR #410), not to
`routine/2026-10-04-compliance-specialist`. The report is committed there;
the commit SHA is in the final reply and in `git log` for that branch. No
PR was opened for the report; it rides PR #410 as an additional docs-only
commit.
