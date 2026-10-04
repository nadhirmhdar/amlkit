# Compliance specialist — daily report 2026-10-04

## Instructions I ran under

**Standing instructions (from Nadhir, in force throughout).** Regulatory
Compliance Specialist (Agent 2) for UAE Federal Decree-Law 10/2025,
Cabinet Resolution 134/2025, Cabinet Decision 109/2023 (UBO) and Cabinet
Resolution 74/2020 (TFS). Strict statutory interpretation, citation
grounded; every finding must cite an exact Article from `corpus/` and
match `citation_register.json`; focus on six mandatory rules (standalone
PF, 24-hour TFS freeze, AED 55,000 cash threshold, 8-year retention,
cascading UBO hierarchy and cycle prevention, senior-management/MLRO
liability). Session harness: develop on `claude/sweet-ramanujan-qr7u94`,
commit, push, open a draft PR; no push to another branch without explicit
permission from Nadhir. Nadhir's later message (this run) added: report to
dreamon via this file on branch `routine/2026-10-04-compliance-specialist`
plus the session's final reply; run autonomously; record blockers as
BLOCKED; use the format headline / what I did / findings with
CONFIRMED-PLAUSIBLE-REFUTED / BLOCKED / files + SHA.

**Changed because of dreamon.** Adopted dreamon's report format and its
VERIFIED/UNVERIFIED marking (now mapped to CONFIRMED/PLAUSIBLE per
Nadhir's format). Declined dreamon's two requests to push to the
`routine/` branch while only dreamon had asked; that push is now done
because Nadhir authorised it directly. Nothing else in approach changed:
the review was findings-only before dreamon's "additive-only" rule
arrived.

**Assumptions.** No `corpus/` or `citation_register.json` exists in the
repository, so Article numbers come from the brief's own register or from
code comments and are marked PLAUSIBLE, never CONFIRMED, as legal
citations. "Scope: master head fc80e9f4" was dreamon's instruction;
`origin/master` has since advanced to `05e612d` (#406, sign-in page
design), which touches no file cited below, so the findings stand.
Not legal advice.

---

## Headline

**AMBER.** No mandatory UAE list obligation is breached today (Interpol
and EU are non-mandatory sources; EOCN, UN and OFAC loaded), but the FATF
adapter silently reports February 2025 fallback data as a fresh load, and
the alert text applies freeze language to EU-only hits that carry no UAE
freeze obligation.

---

## What I did, with evidence

1. **Six-rule statutory review** of the codebase, filed as
   `docs/reviews/2026-10-04-regulatory-compliance-findings.md` on PR #410
   (commit `de7f94a`). Method: `grep`/`sed` over `amlkit/`, `tests/`,
   `scripts/`, `.github/workflows/`; no network, no production access.
2. **Today's source-gap assessment** (this file), covering the four
   peer-reported events: refresh ~100 s with EU loading 6,241 entities,
   Interpol Red Notices 403, FATF live fetch falling back, rescreen
   raising new alerts. Peer-reported figures are data; the mechanisms
   below are read from code.
3. **Delivery.** Report pushed to `claude/sweet-ramanujan-qr7u94` (PR
   #410) and to `routine/2026-10-04-compliance-specialist`. SHAs at the
   end of this file.

Repo check used for scope: `git log --oneline -6 origin/master` →
`05e612d`, `fc80e9f`, `83bc984`, `557244b`, `d498cc6`, `379e4a2`;
`fc80e9f` is an ancestor of the current head.

---

## Findings

Severity: **H** statutory exposure in behaviour or user-facing copy ·
**M** control incomplete or unwired · **L** citation/documentation.
Status: **CONFIRMED** = mechanism read in code at the cited lines;
**PLAUSIBLE** = mechanism confirmed but the legal scope or a production
fact is not verifiable from here; **REFUTED** = checked and not a gap.

### CS-1 — FATF fallback masquerades as a fresh load (H, CONFIRMED)

Obligation: EDD for customers from FATF-identified high-risk jurisdictions
(Law 10/2025 and Res 134/2025, Article PLAUSIBLE: no corpus). The risk
model's jurisdiction factor reads `fatf_countries`
(`tests/test_t16_fatf_fallback.py:1-6`).

- `amlkit/ingest/fatf.py:252-265` — `fetch()` catches the `AdapterError`
  and returns `b""`.
- `amlkit/ingest/fatf.py:270-278` — `parse()` yields
  `BLACKLIST_FALLBACK`/`GREYLIST_FALLBACK`.
- `amlkit/ingest/fatf.py:18`, `:53` — fallback "as of February 2025"
  (`_FATF_DATA_AS_OF = "2025-02-01"`), 20 months old; FATF revises at
  each Feb/Jun/Oct plenary, so up to five revisions are missing (which
  jurisdictions: PLAUSIBLE, not fetched).
- `amlkit/ingest/loader.py:40-43`, `:157-160` — `load()` receives a
  non-empty list, writes `last_refresh = now`, records no error.
  `record_dataset_error` is only reached on an `AdapterError`
  (`amlkit/cases/scheduler.py:57-78`), which never escapes `fetch()`.
- `amlkit/ingest/loader.py:186-219` — `staleness_report()` therefore
  shows FATF refreshed today. `amlkit/ingest/loader.py:222-228` already
  admits this ("it is 'fresh' even when the network is fully blocked")
  but only excludes FATF from the *screening* freshness gate.
- CI blind too: `scripts/heartbeat.py:39-47` `ALL_SOURCES` (imported by
  `.github/workflows/source-canary.yml:77-96`) lists seven sources and
  omits `FATFAdapter`; the canary's `EXPECTED` floors have no
  `fatf_country_risk` entry.

Exposure: a customer from a jurisdiction listed after February 2025 is
not forced into EDD, and the MLRO sees a green dataset. Proposal
(additive): a committed FATF snapshot with `as_of` and max-age refusal,
mirroring the Wikidata PEP pattern from #400; a `dataset.refresh_fallback`
audit action and dashboard badge; add `FATFAdapter` to `ALL_SOURCES` as
non-blocking.

### CS-2 — Freeze language and auto-freeze on EU-only hits (M, PLAUSIBLE)

Obligation: UAE TFS freeze duties attach to UN Consolidated List and UAE
Local Terrorist List designations (Res 74/2020, Article PLAUSIBLE; Law
10/2025 Art 17 per register, PLAUSIBLE). EU/UK designations are risk and
EDD inputs, not UAE freeze orders unless mirrored. Whether OFAC counts as
binding for a UAE DNFBP is an adviser question.

- `amlkit/ingest/eu.py:62`, `amlkit/ingest/uk.py:30` — both
  `is_mandatory = False`, UK commented "Not mandatory under UAE law".
- `amlkit/screening/pf.py:106-109` — generic branch emits "SANCTIONS
  match. Freeze without delay and without prior notice… Do not tip off."
  for any non-PF/TF hit, with no dataset check.
- `amlkit/cases/review.py:160-167` — any `"sanction"` topic is
  freeze-worthy; a `true_positive` disposition auto-creates a
  `freeze_obligations` row regardless of provenance.
- Today's EU load (6,241 entities, peer-reported) means EU-only hits
  confirmed from now on enter the 24-hour freeze queue.

Mechanism CONFIRMED; the legal conclusion that an EU-only freeze has no
UAE basis is PLAUSIBLE pending the corpus. Proposal: carry dataset
provenance into obligation text and the auto-freeze decision (binding:
`ae_local_terrorists`, `un_consolidated`; advisory: `eu_sanctions`,
`uk_sanctions`, and `ofac_sdn` subject to adviser view).

### CS-3 — Dismissed false positives re-alert on every refresh (M, CONFIRMED)

Obligation: ongoing monitoring and screening on every list update (Law
10/2025 / Res 134/2025, Article PLAUSIBLE). Met by the screening; alert
volume is the operational control on whether true matches get seen.

- `amlkit/match/engine.py:335-351` — dedupe skips a hit only if an alert
  with `status = 'open'` exists for the same entity/customer/UBO.
- `amlkit/cases/review.py:299-304`, `:326-330` — a confirmed
  `false_positive` disposition writes that status, so the alert is no
  longer `open`.
- `amlkit/match/engine.py:339` — `rescreen_all` runs "roughly every 20h
  in production". Each run re-raises every dismissed false positive; no
  suppression table is consulted.

Exposure: alert fatigue, doubled by four-eyes cost; today's EU load grows
the false-positive base. Proposal: a per-(customer, entity) suppression
written by a confirmed false positive, honoured by the dedupe query,
expiring when the entity's names/identifiers hash changes.

### CS-4 — Interpol Red Notices 403 (L, REFUTED as a statutory gap)

Not a Res 74/2020 list (PLAUSIBLE); correctly non-mandatory
(`amlkit/ingest/interpol.py:29`). `amlkit/cases/scheduler.py:56-78`
catches the error, upserts the dataset row, records the error and a
`dataset.refresh_failed` audit row, and continues. Coverage loss for an
adverse-signal input only. Note: also absent from
`scripts/heartbeat.py:39-47`, so CI will not show the 403.

### CS-5 — 24-hour refresh depends on an un-inspectable scheduler (M, PLAUSIBLE)

Obligation: implement list updates within 24 hours (EOCN guidance; Res
74/2020 Art 15 per register, PLAUSIBLE).

- `amlkit/api/app.py:109`, `:151`, `:162` — refresh is a daily Cloud
  Scheduler call to `/system/refresh`.
- `.github/workflows/source-canary.yml:334-371` — the workflow records
  that this path "silently stopped working" for an unknown period
  (`SCHEDULER_SECRET` regenerated per deploy) and that the read-back was
  fixed. Whether the job is enabled, its header matches today, and it
  fired on 2026-10-04 is not verifiable from the repo and I made no
  production call. The peer-reported ~100 s refresh does not prove the
  schedule.
- `amlkit/ingest/loader.py:207` — breach at `max_age_hours` (default 24),
  so a daily cron has zero slack: one missed firing is a breach.
  `amlkit/cases/scheduler.py:205-230` notifies MLROs once per breach.
- Related: PR #410 finding 2.2 (overdue freeze check only runs from a
  Windows Task Scheduler script; nothing on Cloud Run invokes it).

Proposal: a read-only `scripts/verify_scheduler.py` (`gcloud scheduler
jobs describe`) and a canary line reporting the job's `state` and
`lastAttemptTime`; consider a 12-hour cron against the 24-hour threshold.

### Carried from PR #410 (six-rule review), for consolidation

| Id | Sev | Status | One line | Evidence |
|---|---|---|---|---|
| 2.1 | H | CONFIRMED | 24-hour freeze clock starts at `true_positive` disposition (after four-eyes), not at detection or designation | `amlkit/cases/review.py:132-215`, `amlkit/cases/manager.py:1970-1988` |
| 2.2 | H | CONFIRMED | Overdue-freeze MLRO email runs only from a Windows Task Scheduler script; nothing in Dockerfile/workflows/scheduler invokes it | `scripts/check_freeze_obligations.py:1-15`, `amlkit/cases/scheduler.py` |
| 3.1 | H | CONFIRMED | AED 55,000 cash threshold is org-configurable up to 1,000,000 | `amlkit/screening/kyt.py:30`, `:408-419`, `amlkit/api/app.py:3683-3684` |
| 3.2 | M | CONFIRMED | `CTR` branch unreachable; no cash-transaction report type | `amlkit/cases/reports.py:97-118`, `amlkit/reporting/goaml.py:44` |
| 4.1 | H | PLAUSIBLE | Statutory retention stated as 5 years citing Res 134/2025 Art 25(2); register says 8 years (Law 10/2025 Art 25, Res 134/2025 Art 24). Firm policy 10y still exceeds it | `amlkit/cases/manager.py:88-95`, `customer.html:55-56`, `privacy.html:94-95` |
| 4.2 | M | CONFIRMED | No retention anchor for occasional transactions / ad-hoc screenings | `amlkit/cases/manager.py:273`, `:505-535` |
| 5.1 | H | CONFIRMED | UBO tier 2 (control through other means) cannot be recorded as a UBO | `amlkit/cases/manager.py:395-403`, `customer.html:112-116` |
| 5.2 | M | CONFIRMED | `senior_official` accepted while a ≥25 % owner exists; cascade order not enforced | `amlkit/cases/manager.py:376-450` |
| 5.3 | M | CONFIRMED | Indirect ownership % not resolved through the parent chain | `amlkit/cases/manager.py:421-431`, `:455-505` |
| 5.4 | L | REFUTED | UBO cycles: structurally impossible today (parent must pre-exist, never updated); self-parent guard is dead code | `amlkit/cases/manager.py:411-419`, `:446-448` |
| 1.1, 2.4, 3.3, 6.1 | L | PLAUSIBLE | Article citations missing or inconsistent (Art 21, Art 15/32 vs blog's "Art 21 of Dec 74/2020", Art 20) | see PR #410 doc |

---

## BLOCKED / not checked

- **BLOCKED (now cleared):** push to `routine/2026-10-04-compliance-specialist`
  was blocked while only dreamon had asked; Nadhir's direct instruction
  this run authorised it and it is done.
- **Not checked, no means:** primary legal text (no corpus in repo);
  Cloud Scheduler job state and today's refresh audit rows; the actual
  new-alert count and which datasets produced them; the Interpol 403
  body; whether FATF's live page is reachable from Cloud Run; which FATF
  jurisdictions changed since February 2025; whether OFAC SDN is treated
  as binding for UAE DNFBPs. No production system, endpoint, secret or
  network call was used.
- **SendMessage to dreamon:** attempted once; outcome recorded in the
  session's final reply. Not retried.

## Files created and commits

| File | Branch | Commit |
|---|---|---|
| `docs/reviews/2026-10-04-regulatory-compliance-findings.md` | `claude/sweet-ramanujan-qr7u94` (PR #410) | `de7f94a` |
| `reports/daily/2026-10-04/compliance-specialist.md` (this file) | `claude/sweet-ramanujan-qr7u94` (PR #410) | see `git log -1 -- reports/daily/2026-10-04/compliance-specialist.md` on that branch |
| `reports/daily/2026-10-04/compliance-specialist.md` (this file) | `routine/2026-10-04-compliance-specialist` | see `git log -1 routine/2026-10-04-compliance-specialist` |

Both SHAs are quoted in the session's final reply.
