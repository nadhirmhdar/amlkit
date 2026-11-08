# Compliance specialist — daily report 2026-11-08

**Instructions I ran under.** Standing role from Nadhir: Regulatory Compliance Specialist for Law 10/2025, Cabinet Resolution 134/2025, Cabinet Decision 109/2023 and Cabinet Resolution 74/2020, citation-grounded, additive only, no production access, no `/system/*` calls, no secrets. This run's routine prompt: review changes since the previous report against UAE AML/CFT obligations, then one previously not-checked item; push the report to `routine/<DATE>-compliance-specialist`, never master. The no-change shortcut did not apply because master moved. No message from dreamon arrived. `corpus/` and `citation_register.json` do not exist in the repo, so every Article is unverified (PLAUSIBLE). Not legal advice.

**Headline: AMBER (improving).** Three commits fix two of my findings in the repo (the 20-hour sanctions refresh gap, CS-5, and the overstated freeze-scope and UAE PASS public claims, CS-25 and most of CS-24), but the 24-hour freeze clock (CS-13) and PNMR (CS-14) are still open and the new schedule has not been confirmed live.

## What I did, with evidence

- `git ls-remote origin refs/heads/master` at 01:16 UTC on 2026-11-08: `9219e2623b3a3ba7e73a20e44c703ab80df7e900` (`9219e26`). Previous report SHA was `6560fb021f6ea2cadefcd6e60d67ee274d871e73`.
- `git log 6560fb0..origin/master`: three commits merged 2026-11-07: `fab52e2` #460 (SEO round 2: HEAD on public pages, static JSON-LD, snippets, gzip), `bbc035d` #461 WP-30 (reason codes must fit the disposition; sanctions refresh every 4 hours), `9219e26` #462 WP-29 (launch blockers: sign-up enumeration, honest email-failure page, accurate public claims, unpaid-org scans, PR secret gating). 29 files, +788/-83; 21 non-test source files.
- I read the whole non-test diff of `.github/workflows/source-canary.yml`, `cases/review.py`, `cases/operators.py`, `mail.py`, `billing/limits.py`, `api/routers/{auth,public,alerts,customers}.py`, `api/mobile.py`, `match/engine.py` and the changed `landing.html` and `aml_law.html` text. Not line by line: `api/head.py` and `compress.py` (SEO/gzip), `jsonld.js`, other template edits.
- **Full test suite on `9219e26`** (detached worktree): **2945 passed, 2 skipped in 870 s, exit 0.** Supersedes `2860 passed, 2 skipped` on `c5da8aa`.
- PR list: #460 to #462 are the only PRs merged since #459. Draft #411 was updated at 01:02 UTC today; not reviewed.

## Findings

| ID | Severity | Status | Finding |
|---|---|---|---|
| CS-5 | MEDIUM | **Fixed in the repo; deployment unverified** | #461 changes both the create and the update branch of the Cloud Scheduler step from `0 */20 * * *` to `0 */4 * * *` (00:00, 04:00, 08:00 ... UTC), so the worst-case gap between ingests drops from 20 hours to 4 hours, and the comment now says why. The hourly freeze check stays at :15, so the two jobs still do not share a minute. Caveat: the scheduler step is `continue-on-error: true` and needs Cloud Scheduler IAM on the deploy account; if it fails, the job keeps the old schedule and the run still looks green. Someone with project access should confirm that `amlkit-sanctions-refresh` now shows `0 */4 * * *`. Basis: EOCN 24-hour list-update guidance (fetched 2026-10-06), Law 10/2025 Art 17, Res 74/2020 Art 15, Res 134/2025 Art 32 (unverified). |
| CS-25 | LOW | **Closed in the repo** | `landing.html` now reads "Confirmed matches on the UN Security Council and UAE Local Terrorist lists create freeze obligations..." and `aml_law.html` reads "Freeze obligations created from confirmed UN Security Council and UAE Local Terrorist List matches... Matches on other lists (OFAC, EU, UK) stay alerts for enhanced ..." (the rest of that sentence is cut off in my diff view; it matches the product's scope gate). |
| CS-24 | MEDIUM | **Partly closed** | Public pages mention UAE PASS only when `_uaepass_live()` is true, meaning the integration is configured and `UAEPASS_ENV` is `production` (`routers/public.py`; the new docstring states the sandbox accepts POC credentials only, L-118). This removes the overstated marketing claim. Still open: (a) `uaepass_verifications` rows still do not record which environment produced them (`db.py` and `cases/manager.py` unchanged, `git grep` finds no environment field), and (b) the in-product "Verify via UAE PASS" button on the customer page is gated by `uaepass_enabled` (configured), not by production, so on a sandbox deployment an operator can still record a sandbox "verification" that looks real in the file. Relying on it would not meet a CDD verification duty (Res 134/2025 CDD articles, unverified). |
| N-9 | none | positive | #461 `cases/review.py`: `ALLOWED_REASON_CODES` ties each disposition to the reason codes that make sense with it (false positive: different DOB, different nationality, name coincidence, different entity type, other; true positive: confirmed match, other; escalated: confirmed match, insufficient data, other; open: insufficient data, other). A PEP alert can no longer be cleared as a false positive with the reason "confirmed_match", and "insufficient_data" can no longer close an alert. This tightens the audit trail a supervisor or inspector reads. |
| N-10 | none | positive | #462: open self-serve sign-up now answers identically whether or not an email or firm name is already registered (an existing email gets a no-link notice mail instead of a new account; a duplicate firm name gets a randomised slug), so a visitor cannot enumerate which firms use the service or which emails have accounts. The dev-mode verification link is no longer shown in open sign-up, which would have skipped the email-ownership check, and a mail failure shows an honest "could not send" page. MLRO MFA is untouched. |
| N-11 | none | positive | #462: OCR scans (passport, trade licence, Emirates ID) are refused with HTTP 402 for an organisation still `pending_payment`; reads, ad-hoc screening and feedback are unaffected. The workflow stops passing the EU FSF token on `pull_request` runs so a PR author cannot print it. |
| INFO-8 | INFO | CONFIRMED (code) | Leftover wording: `scripts/grant_scheduler_iam.sh:36` still echoes "every 20h"; `queries.py:1461,1502` flag datasets stale at "> 20h" (now a sensible alarm after five missed 4-hour runs, but the hard breach limit `max_age_hours` is still 24). Cosmetic. |
| CS-13 | HIGH | PLAUSIBLE (legal), CONFIRMED (code) — **open** | Unchanged: the 24-hour freeze clock still runs from `freeze_obligations.identified_at`, set at confirmed disposition. With ingest lag now at most 4 hours the gap is smaller but the designation-to-freeze path still is not measured from designation. Law 10/2025 Art 17, Res 74/2020 Art 15, Res 134/2025 Art 32 (unverified). |
| CS-14 (PNMR) | MEDIUM | CONFIRMED (code) — **open** | `SUPPORTED_REPORT_TYPES` is still `{"STR","SAR","FFR"}`. |
| 3.1 | MEDIUM | PLAUSIBLE — **open** | The AED 55,000 cash threshold (Res 134/2025 Art 21) is still organisation-configurable. |

The previous report's other findings stand as written (FATF handling, CS-4 Interpol, CS-18, the 5-versus-8-year retention question).

## Not-checked item taken this run

CS-5 and CS-24/CS-25 from the 2026-11-04/05 reports were the items I listed as open; I re-checked all three against `9219e26` (above). The earlier "full suite on the new master" item is closed by the 2945-test run.

## BLOCKED / not checked

- **Primary legal text: BLOCKED**, unchanged. Three official hosts (`rulebook.centralbank.ae`, `uaelegislation.gov.ae`, `fatf-gafi.org`) refused this environment's egress on 2026-10-06; not retried or bypassed. To unblock: provide the official PDFs of the four instruments as `corpus/` plus `citation_register.json`.
- **Deployed Cloud Scheduler state:** not checked; whether the 4-hour schedule is live depends on the deploy step succeeding (see CS-5). Needs `gcloud scheduler jobs describe amlkit-sanctions-refresh`, which I cannot and must not run.
- **UAE PASS production status** (secrets and `UAEPASS_ENV`): not checkable.
- Not re-verified individually: CS-15, CS-16.
- Not read line by line: `api/head.py`, `api/compress.py`, `jsonld.js`, SEO template edits.
- Draft #411: not reviewed.
- Production: not checked.

## Files and commit

`reports/daily/2026-11-08/compliance-specialist.md` on `routine/2026-11-08-compliance-specialist`, created from `origin/master` `9219e26`. The commit SHA is in the final reply (a commit cannot name its own SHA).
