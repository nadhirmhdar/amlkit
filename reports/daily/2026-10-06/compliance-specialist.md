# Compliance specialist — daily report 2026-10-06

Scope: `nadhirmhdar/amlkit` `origin/master` = `b7eeb2f` (full SHA from
`git ls-remote origin refs/heads/master` at 01:17 UTC:
`b7eeb2f32c6f3eae4f29420477189aaf11ea1d02`). Previous report: 2026-10-05,
last named master `28e4b51`.

## Instructions I ran under

**Standing instructions (Nadhir).** Regulatory Compliance Specialist for
Federal Decree-Law 10/2025, Cabinet Resolution 134/2025, Cabinet Decision
109/2023 (UBO) and Cabinet Resolution 74/2020 (TFS). Strict,
citation-grounded interpretation: every finding cites an exact Article from
`corpus/` that matches `citation_register.json`. Six mandatory rules: standalone
proliferation financing, the 24-hour TFS freeze, the AED 55,000 cash
threshold, 8-year retention, the cascading UBO hierarchy, senior-management
liability.

**This run's routine prompt (Nadhir's scheduled routine).** Check changes since
the previous report against UAE AML/CFT obligations, then check one item the
previous report listed as not checked. Mark anything not verified against a
primary source PLAUSIBLE. No production access, no `/system/*` calls, no
secrets. Additive only. Push this file to
`routine/2026-10-06-compliance-specialist`, never master. Stop after delivery:
no polling, no CI re-checks, no self-scheduled reminders.

**Changed because of dreamon.** Nothing. No dreamon message arrived this run.

**Assumptions.**
- No `corpus/` or `citation_register.json` exists in the repo. Article numbers
  come from the brief's register, a code comment or an official page, and are
  never CONFIRMED as statute.
- I read "CONFIRMED" as: reproduced or read in code at cited lines, or stated in
  an official regulator page I fetched. A regulator guidance page is not the
  legal text, so article-level mapping stays PLAUSIBLE.
- Not legal advice.

---

## Headline

**AMBER.** Master now closes the unwired overdue-freeze alert, softens the blog's
unverified legal claims and fixes two screening misses, but official EOCN
guidance shows the freeze clock runs from designation (the code starts it at
disposition), the product cannot file a Partial Name Match Report or track the
five-business-day reporting deadline, and the FATF jurisdiction-data gaps are
unchanged.

---

## What I did, with evidence

1. **Master and delta.** Master moved `28e4b51` to `b7eeb2f`, seven commits:

   ```
   b7eeb2f Repository cleanup policy (#418)
   2f55006 fix(goaml): keep entity reference, CSRF on org-profile/logout, validate export fields at finalise (#424)
   666d9a0 fix(tfs): run overdue freeze-obligation check hourly from Cloud Scheduler (finding 2.2) (#419)
   69b9651 Blog: soften unverified legal claims, adopt 10-year retention plan (follow-up to #416) (#420)
   f3bc458 fix(screening): Unicode-normalise names before canonicalisation (L-2) (#425)
   b9d9db5 Fix tests that fail on a Windows dev machine; UTC retention dates; run-amlkit-tests skill (#423)
   5a08a95 Adverse media: a list of every finding across the firm's customers (/adverse-media) (#403)
   ```

2. **Ran the whole suite on master `b7eeb2f`** in a scratch virtualenv outside
   the repo:

   ```
   2115 passed, 3 skipped, 53 warnings in 700.37s (0:11:40)
   ```

3. **Read each merged change for compliance effect** (CS-16, CS-17 and the
   status table below), and the two open PRs that touch my findings, #421 and
   #422.

4. **Reproduced my alert-paging check on both master and PR #421's branch**
   (CS-8), using real SQLite and no mocks.

5. **Checked the not-checked item.** The retention lead from last time
   (`uaelegislation.gov.ae/en/legislations/3857/download`) is BLOCKED: HTTP 403
   from Cloudflare. As a substitute I fetched the Executive Office's TFS
   guidance and the Ministry's TFS page, which answered (CS-13, CS-14, CS-15).

---

## Status of earlier findings

| Id | Earlier finding | Now | Evidence |
|---|---|---|---|
| 2.2 | Overdue-freeze MLRO email not run on Cloud Run | **Fixed on master** by #419, CONFIRMED. Caveat: the Cloud Scheduler wiring step is `continue-on-error: true`, so the job's existence is UNVERIFIED (no production access). | `amlkit/api/app.py` `system_check_freeze_obligations`; `amlkit/cases/scheduler.py` `run_freeze_obligation_check`; `.github/workflows/source-canary.yml` new step; 82 freeze and endpoint tests pass |
| 2.1 | 24-hour clock starts at disposition, not designation | **Unchanged**, now supported by official guidance (CS-13) | `amlkit/cases/manager.py:2005`, `:2010` still key off `identified_at`; `amlkit/cases/review.py` untouched |
| CS-8 | Mobile alert paging loses category priority across pages | **Unchanged on master, still reproduces.** #421 (open) fixes it, reproduced below. | see CS-8 |
| CS-2 | Freeze wording on non-freeze hits | **Partly addressed by #421 (open):** PEP and "other" hits get non-freeze wording. EU/UK-only sanctions hits keep it; #421's own comment calls that "a legal question, deliberately not decided here". | `amlkit/screening/pf.py` in #421 |
| CS-9, CS-10, CS-11 (#416 wording) | Blog stated 5-year retention, AED 55,000 as CDD only, unsourced 24–48h and penalties | **Addressed on master by #420**, CONFIRMED by reading the merged files | see CS-9, CS-10, CS-11 below |
| 4.1 | Code and UI state a 5-year statutory minimum citing Res 134/2025 Art 25(2) | **Still live on master**; #422 (open) removes it. | `amlkit/cases/manager.py:89`, `:94`; `amlkit/web/templates/customer.html:55` |
| CS-1, CS-6, CS-7 | FATF fallback shown as fresh; five current grey-list names unparseable; list drift | **Unchanged.** None of `fatf.py`, `loader.py`, `heartbeat.py` changed. | `git diff 28e4b51 origin/master` |
| CS-3 | Dismissed false positives re-alert each refresh | **Unchanged.** | `amlkit/match/engine.py:362` still keys on `status = 'open'` |
| CS-4, CS-5 | Interpol edge block; daily refresh cadence | **Unchanged.** | no file change |
| 3.1, 4.2, 5.x | Cash threshold up to 1,000,000; no occasional-transaction retention; UBO tiers | **Unchanged on master.** #422 (open) adds a retention date to ad-hoc screenings only, not to occasional transactions. | no file change |

---

## Findings

Severity: **H** statutory exposure in behaviour or published copy, **M** control
incomplete, **L** citation or wording. Status: **CONFIRMED**, **PLAUSIBLE**,
**REFUTED** as defined above.

### CS-13 — Official guidance puts the 24-hour clock at designation; the code starts it at disposition (H, CONFIRMED against EOCN guidance)

Obligation: freeze "without delay", meaning immediately and in any case within
24 hours. The Executive Office for Control and Non-Proliferation (EOCN) states
the clock runs from designation. Quoted from `uaeiec.gov.ae/en-us/un-page`,
fetched 2026-10-06:

> "'Without delay' means applying freezing measures immediately or in any case
> within 24 hours upon designation of an individual, entity, or group on the UAE
> Local Terrorist List or UNSC Consolidated List."

> "Upon any updates to the Sanctions Lists. In such cases, screening must be
> conducted immediately to ensure compliance with implementing freezing measures
> without delay (within 24 hours)."

The page attributes the main TFS obligations to "Article 21 of Cabinet Decision
74 of 2020". The brief's register gives "Res 74/2020 Art 15" for the 24-hour
rule. The two may cover different duties, but I cannot check either against the
instrument, so the article-level mapping is PLAUSIBLE. The page still cites "Federal
Law No. 20 of 2018" for the legal framework, so it has not been re-pointed to
Law 10/2025 (the brief's Art 17 is likewise unverified).

Code: `check_unexecuted_freeze_obligations` measures `now - identified_at`
(`amlkit/cases/manager.py:2005`, `:2010`), and `identified_at` is set when an
operator records a `true_positive` disposition (`amlkit/cases/review.py`
`_auto_create_freeze_if_required`). Under four-eyes review that is after a second
operator approves. A match that waited two days in review is created with zero
hours pending. The new hourly check (#419) inherits the same anchor, so the MLRO
email also starts late.

Proposal (additive): store the alert's detection time and the list entry's
designation time on the freeze row, compute the deadline from the earlier of
them, and show it as a stored `deadline_at`.

### CS-14 — A Partial Name Match Report cannot be created, though the UI says it can (M, CONFIRMED in code; obligation per EOCN guidance, article PLAUSIBLE)

Obligation, EOCN guidance: where a customer partially matches a listed person
and you cannot verify the match, "you must either suspend the transaction
immediately without delay, refrain from offering any funds ... or reject the
transaction and submit a PNMR to the EOCN and the relevant SA through the goAML
platform within five business days". The guidance also gives 10 business days to
obtain an ID document to discount or confirm a partial match.

Code:
- `amlkit/reporting/goaml.py:62` `SUPPORTED_REPORT_TYPES = {"STR", "SAR", "FFR"}`.
  No PNMR type can be created. PNMR appears only in the module docstring
  (`goaml.py:1`, `:6`) and one status branch (`goaml.py:371`).
- `amlkit/web/templates/reports.html:12` tells users the page covers "Partial
  Name Match Reports (PNMRs)".
- There is no alert disposition for "match cannot be verified" that suspends the
  transaction or starts a PNMR. The freeze flow covers confirmed matches only.

Exposure: an operator who cannot verify a match has no workflow in the product,
and the page implies there is one. A manual goAML filing remains possible.

Proposal: add a PNMR report type and an "unverifiable partial match" disposition,
or correct the `reports.html` copy to say PNMR is filed directly on goAML.

### CS-15 — No tracking of the five-business-day CNMR/PNMR reporting deadline (M, CONFIRMED in code; period per EOCN guidance)

Obligation, EOCN guidance: a CNMR "within five business days from taking any
freezing measure"; a PNMR "within five business days from rejecting the
transaction". Code: the freeze lifecycle has statuses
(`pending_execution`, `executed_pending_report`, `reported`) and an
`executed_at` timestamp, but no report due date and no overdue check on the
reporting step. The only mention of five business days is a line of text in the
alert email (`amlkit/mail.py:296`). `grep` for `overdue`/`due` over the reporting
step finds nothing. #419 covers the 24-hour execution step only.

Exposure: a freeze can sit in `executed_pending_report` past the deadline with no
signal. Proposal: a stored `report_due_at` (five business days from
`executed_at`, UAE working days) and an hourly overdue notice reusing the #419
machinery.

### CS-16 — The new overdue-freeze alert fires only after the 24 hours have lapsed (M, PLAUSIBLE)

#419 emails the MLRO once per obligation, when it has been pending for more than
24 hours (`amlkit/cases/manager.py:2010`, `julianday('now') - julianday(...) > 1.0`).
That is a breach notice, not a warning. Proposal: a second notice at a warning
threshold (for example 18 hours) so the freeze can still be made in time. The job
itself is created by a workflow step marked `continue-on-error: true`, so a
failed wiring is silent; whether the hourly job exists in production is UNVERIFIED.
The send path is sound: it retries when SMTP is unset, records `overdue_notified_at`
only on `mail.SENT`, and tests cover the lock, the no-MLRO and the failed-send cases.

### CS-9, CS-10, CS-11 — #420 addresses the blog claims I flagged (REFUTED as a remaining gap)

Read in the merged files: retention is no longer stated as law (wording is "for
the period the law requires (groAML's default retention plan is 10 years)");
AED 55,000 is now described as also tied to cash-transaction reporting for some
sectors such as dealers in precious metals and stones and real estate
(`uae-dnfbp-cdd-kyc-beneficial-ownership.html:91`); the 24–48 hour STR "outer
edge", the penalty range and the "examiner-ready" claim are gone; the Circular
and FIU-period figures are marked "as reported; confirm". Residual: the 24-hour
post still attributes the duty to "Article 21 of Cabinet Decision No. 74 of 2020"
while the code and emails cite "Cabinet Resolution 134/2025" with no Article
(`amlkit/mail.py:234`, `:297`; `amlkit/cases/review.py:146`;
`amlkit/cases/manager.py:1722`, `:1990`). The EOCN page supports the blog's
wording, so the code and email citations are the ones to align. PLAUSIBLE until
the instrument text is read.

### CS-17 — #425 closes a false "clear" for names that cannot be canonicalised (REFUTED as a gap; L residual, PLAUSIBLE)

Positive: `screen()` now flags a query that contains letters but yields no
blocking keys as `unscreenable`, `clear` becomes false, and the screen page says
"Not screened ... This is not a clear result"
(`amlkit/match/engine.py`, `amlkit/names/arabic.py` `clean_name_text`,
`amlkit/web/templates/screen.html`). Names with zero-width or bidi format
characters, or Arabic Presentation Forms from PDF copy-paste, are now folded
before matching. Residual: list-side name tokens are rebuilt on every refresh
(`amlkit/ingest/loader.py` deletes and re-inserts `name_tokens` per entity), so
a listed name containing such characters is keyed under the old logic until the
next refresh after deploy. Window: one refresh cycle.

### CS-8 — Alert paging still loses category priority across pages on master (M, CONFIRMED mechanism; impact PLAUSIBLE)

Unchanged from the last report, now re-run on both branches with the same
204-PEP-plus-one-proliferation seed:

```
master b7eeb2f:
page 1: 200 alerts {'proliferation': 0, 'pep': 200} | first row category: pep
page 2: 5 alerts   {'proliferation': 1, 'pep': 4}   | row categories: ['proliferation', 'pep', 'pep', 'pep', 'pep']

PR #421 head 26096ea:
page 1: 200 alerts {'proliferation': 1, 'pep': 199} | first row category: proliferation
page 2: 5 alerts   {'proliferation': 0, 'pep': 5}   | row categories: ['pep', 'pep', 'pep', 'pep', 'pep']
```

#421 (open, not merged) orders by category before `LIMIT`/`OFFSET`. Merging it
closes CS-8.

### Reviewed with no compliance gap (REFUTED)

- **#403 adverse-media list.** The route requires a session and every query is
  scoped by `org_id` (`adverse_media_queue`, `adverse_media_counts`). Read-only.
- **#424 goAML.** Finalising now dry-runs the export's required-field rules, so a
  report cannot be locked into a state that can never be exported; the entity
  reference is kept on a blank save; logout and the org-profile form check CSRF.
- **#423.** Retention dates use the UTC date, the same clock as audit timestamps.
  A close recorded between 00:00 and 04:00 UAE time stores the previous UTC date,
  one day earlier on a 10-year plan; immaterial.
- **#418, #422 (open).** Policy and docs. #422 removes the unverified statutory
  figure from code and copy, keeps 10 years as firm policy, adds a retention date to ad-hoc screenings (`screenings.retention_until`, run
  date plus 10 years), and adds a purge guard for customers inside the 10-year
  window. Occasional transactions outside the screening table still have no
  anchor (finding 4.2 stays partly open).

---

## BLOCKED / not checked

- **BLOCKED: primary legal text for retention, the AED 55,000 scope and the UBO
  percentage.** Three official hosts refuse this session's egress and I did not
  try to bypass them: `rulebook.centralbank.ae` (`HTTP/2 403`, `awselb`),
  `uaelegislation.gov.ae/.../3857/download` (`HTTP/2 403`, Cloudflare), and
  `www.fatf-gafi.org` (Cloudflare challenge, last run). Action needed: someone
  fetches Cabinet Resolution 134/2025 and Law 10/2025 from an unblocked network
  and drops the PDFs in the repo as `corpus/`. That unblocks every PLAUSIBLE
  article-level mapping above, including the retention 5-versus-8 question.
- **Not checked, no means:** the Cloud Scheduler job `amlkit-freeze-obligations-check`
  and the refresh job's real state; production alert and freeze counts; whether
  production's FATF fetch fails; the response body of Interpol from Cloud Run;
  whether OFAC is binding for UAE DNFBPs; whether the five unmapped FATF names
  are spelled as the resolver expects.
- **Not done by design:** no comment on any PR, no edit to an existing file, no
  production or `/system/*` call, no secret used. The scratch virtualenv, the
  paging script and the fetched pages are in the session scratchpad and not
  committed. No test or other process is left running.

## Files created and commit

| File | Branch | Commit |
|---|---|---|
| `reports/daily/2026-10-06/compliance-specialist.md` (this file) | `routine/2026-10-06-compliance-specialist` | see the final reply (a commit cannot name its own SHA) |
