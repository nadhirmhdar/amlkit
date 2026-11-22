# Compliance specialist — daily report 2026-11-22

**Instructions I ran under.** Standing role from Nadhir: Regulatory Compliance Specialist for Law 10/2025, Cabinet Resolution 134/2025, Cabinet Decision 109/2023 and Cabinet Resolution 74/2020, citation-grounded, additive only, no production access, no `/system/*` calls, no secrets. This run's routine prompt: review changes since the previous report against UAE AML/CFT obligations, then one previously not-checked item; push the report to `routine/<DATE>-compliance-specialist`, never master. The no-change shortcut did not apply because master moved (one workflow-only commit). No message from dreamon arrived. `corpus/` and `citation_register.json` do not exist in the repo, so every Article is unverified (PLAUSIBLE). Not legal advice.

**Headline: AMBER.** The new commit (#467) is a deploy-setting change that makes the database replica more durable, and GitHub's CI record now shows the CS-27 screening fix was deployed to Cloud Run on 2026-11-18 at about 14:36 UTC, which narrows the look-back window, but whether a post-deploy re-screen ran and what it found still needs an MLRO to confirm.

## What I did, with evidence

- `git ls-remote origin refs/heads/master` at 01:16 UTC on 2026-11-22: `c42c77ce59179c86b3ed5107b78e65e227326c0d` (`c42c77c`). Previous report SHA was `bfb0253ee88acabb4d8561f6e9cac2021fa3e12d`.
- `git log bfb0253..origin/master`: one commit, `c42c77c` #467 "Deploy with --no-cpu-throttling: keep the replica current and stop request stalls", merged 2026-11-21 11:06 UTC. 2 files, +20/-1: `.github/workflows/source-canary.yml` (adds the `--no-cpu-throttling` flag and a comment block to the Cloud Run deploy step) and one line of `CLAUDE.md`. `git diff --stat bfb0253 origin/master -- amlkit scripts requirements* Dockerfile` is empty, so application code, scripts and dependencies are identical to `bfb0253`.
- Tests: the last full local run, on `bfb0253` (**3010 passed, 2 skipped**, 2026-11-20), still applies to the application code. GitHub's own "Source canary" run #1249 for `c42c77c` also shows its "Test suite" job green (11:07 to 11:25 UTC).
- **Not-checked item taken this run: has the CS-27 fix actually been deployed?** I read GitHub Actions run metadata (read-only; this is CI history, not production access). Results below.
- PR list: #467 is the only PR merged since #466. Draft #405 (the earlier version of the same change) was closed unmerged on 2026-11-21; draft #411 (docs audit) was updated at 00:46 UTC today and not reviewed.

## Deployment evidence for the screening fixes (CS-27)

The deploy job in `source-canary.yml` is gated: on every push to master the run executes "Test suite", "Source connectivity heartbeat" and "Verify upstream sources", then "Check commit is still master head", and only then "Deploy to Cloud Run".

| Change | Source canary run | Test suite job | "Deploy to Cloud Run" step | Run result |
|---|---|---|---|---|
| #464 country comparison fix (`cdf3801`) | #1238, 2026-11-18 14:17 UTC | success (14:18 to 14:32) | success, 14:35:30 to 14:36:17 UTC | success |
| #465 PEP de-duplication (`a524fba`) | #1241, 2026-11-19 07:03 UTC | success | run success | success |
| #466 DOB near-miss (`bfb0253`) | #1243, 2026-11-19 08:13 UTC | success | run success | success |
| #467 no-cpu-throttling (`c42c77c`) | #1249, 2026-11-21 11:06 UTC | success (11:07 to 11:25) | success, 11:28:17 to 11:28:57 UTC | success |

For #464 and #467 I also read the job steps: "Wire up Cloud Scheduler sanctions refresh" and "Wire up Cloud Scheduler freeze obligation check" ran after the deploy and are reported as success (3 to 8 seconds each). Both steps are `continue-on-error`, so a "success" label does not by itself prove the scheduler job changed; it is consistent with it.

What this settles and what it does not:
- **Settled:** the screening fix from #464 was built, tested and deployed through CI to Cloud Run on 2026-11-18 at about 14:36 UTC, and each later master push (the #465, #466 and #467 deploys, the last on 2026-11-21 11:28 UTC) redeployed code that contains it. The exposure window for CS-27 is therefore **at least 2026-10-04 to 2026-11-18 14:36 UTC (about 6.5 weeks)**, and may start earlier (the repository history I can see starts the penalty on 2026-10-04).
- **Not settled:** that the Cloud Run revision is receiving traffic, that the 4-hourly refresh and re-screen (CS-5, #461) ran after the deploy, and what alerts it raised. None of this is visible in CI.

## Review of #467

`--no-cpu-throttling` switches Cloud Run to instance-based CPU. With the default request-based CPU, background work such as `litestream replicate` gets little or no CPU between requests, so the last writes before a quiet spell could sit un-uploaded and be lost if Cloud Run recycled the instance. The commit comment also cites request stalls (about one request in four taking roughly half a second longer on 2026-11-21) and an estimated cost of roughly USD 58 to 63 a month against about USD 19 to 21. This is the setting my earlier notes (`CLAUDE.md`'s restore-time note and the 2026-10-04 incident correction) flagged as the gap.

## Findings

| ID | Severity | Status | Finding |
|---|---|---|---|
| N-15 | none | positive | #467 narrows the window in which recent audit-log, screening, alert, freeze and report records exist only on the instance disk. That supports the record-keeping and audit-trail duties (Law 10/2025 Art 25 and Res 134/2025 Art 24 on retention, as cited in the standing brief; unverified) and complements the explicit `sync_replica()` calls after refresh, report finalisation and freeze execution. The replica is still asynchronous, so a recovery point of zero is not claimed. |
| N-16 | none | positive | The deploy pipeline is gated by tests and by a "still master head" check before it deploys, and the run history shows each of the last four deploys passing both. That is useful change-control evidence for a regulator or auditor. |
| CS-27 | HIGH | **Open (look-back only)** | The defect is fixed and deployed (see above). What remains is the look-back: the MLRO should confirm that a refresh and full re-screen completed after 2026-11-18 14:36 UTC, review every alert it raised for UN-list matches as priority, record the incident (window from at least 2026-10-04), and take legal advice on any report to the supervisory authority or EOCN (Law 10/2025 Art 17, Res 74/2020 Art 15, Res 134/2025 Art 32, unverified). Any UN match found now starts the "without delay" freeze duty now. |
| CS-28 | MEDIUM | CONFIRMED (reproduced 2026-11-20) — **open** | A same-year, different-month birth date takes an exact name match to 0.75 and drops it, while a wrong birth year alerts at 0.85. Not changed by #467. |
| CS-5 | MEDIUM | **Closed in the repo; schedule update reported successful in CI** | The 4-hourly refresh from #461 was wired at deploy (step "Wire up Cloud Scheduler sanctions refresh" reported success on 2026-11-18 and 2026-11-21). The live schedule itself is still not visible to me. |
| CS-13 | HIGH | PLAUSIBLE (legal), CONFIRMED (code) — **open** | Unchanged: the 24-hour freeze clock still runs from `identified_at`, set at confirmed disposition. |
| CS-14 (PNMR) | MEDIUM | CONFIRMED (code) — **open** | `SUPPORTED_REPORT_TYPES` is still `{"STR","SAR","FFR"}`. |
| 3.1 | MEDIUM | PLAUSIBLE — **open** | The AED 55,000 cash threshold (Res 134/2025 Art 21) is still organisation-configurable. |

The remaining findings from earlier reports stand as written (FATF handling, CS-4 Interpol, CS-18, CS-24 UAE PASS sandbox evidence, CS-29 and CS-30 PEP fold edge cases, the 5-versus-8-year retention question).

## BLOCKED / not checked

- **Primary legal text: BLOCKED**, unchanged. Three official hosts (`rulebook.centralbank.ae`, `uaelegislation.gov.ae`, `fatf-gafi.org`) refused this environment's egress on 2026-10-06; not retried or bypassed. To unblock: provide the official PDFs of the four instruments as `corpus/` plus `citation_register.json`.
- **Anything inside production:** whether the new revision serves traffic, the live Cloud Scheduler schedule, whether the post-deploy re-screen ran, and whether any customer or related party was actually affected by CS-27 or CS-28. Needs someone with project access (for example `gcloud run services describe`, `gcloud scheduler jobs describe amlkit-sanctions-refresh`, and the `/admin/ops` page), which I cannot and must not use.
- **UAE PASS production status** (secrets and `UAEPASS_ENV`): not checkable.
- Gender-mismatch penalty against exact name matches: still not tested.
- Not re-verified individually: CS-15, CS-16.
- Draft #411: not reviewed.
- Production: not checked.

## Files and commit

`reports/daily/2026-11-22/compliance-specialist.md` on `routine/2026-11-22-compliance-specialist`, created from `origin/master` `c42c77c`. The commit SHA is in the final reply (a commit cannot name its own SHA).
