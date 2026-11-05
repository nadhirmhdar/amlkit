# Compliance specialist — daily report 2026-11-05

**Instructions I ran under.** Standing role from Nadhir: Regulatory Compliance Specialist for Law 10/2025, Cabinet Resolution 134/2025, Cabinet Decision 109/2023 and Cabinet Resolution 74/2020, citation-grounded, additive only, no production access, no `/system/*` calls, no secrets. This run's routine prompt: review changes since the previous report against UAE AML/CFT obligations, then one previously not-checked item; push the report to `routine/<DATE>-compliance-specialist`, never master. The no-change shortcut did not apply because master moved (one commit). No message from dreamon arrived. `corpus/` and `citation_register.json` do not exist in the repo, so every Article is unverified (PLAUSIBLE). Not legal advice.

**Headline: AMBER (unchanged).** The one new commit is CI wiring with no application change, and the not-checked item I took, the sanctions refresh schedule (CS-5), is confirmed open: refresh runs only at 00:00 and 20:00 UTC, so a designation can wait up to 20 hours to be ingested.

## What I did, with evidence

- `git ls-remote origin refs/heads/master` at 01:16 UTC on 2026-11-05: `6560fb021f6ea2cadefcd6e60d67ee274d871e73` (`6560fb0`). Previous report SHA was `c5da8aa06f192ec6ec3f90534b6c9264e4088da1`.
- `git log c5da8aa..origin/master`: one commit, `6560fb0` #459 "CI: pass EU FSF token to the source checks so EU coverage is actually verified (#85)", merged 2026-11-04. 2 files, +28: `.github/workflows/source-canary.yml` (adds `AMLKIT_EU_FSF_TOKEN: ${{ secrets.EU_FSF_TOKEN }}` to the `sources` and `heartbeat` jobs) and a new `tests/test_workflow_env.py`. `git diff --stat c5da8aa 6560fb0 -- amlkit scripts requirements*` is empty, so application code, scripts and dependencies are byte-identical to `c5da8aa`.
- Tests: the full suite last passed on `c5da8aa` (**2860 passed, 2 skipped**, 2026-11-04) and applies unchanged. On `6560fb0` I ran `tests/test_workflow_env.py` and `tests/test_freeze_scope.py`: **18 passed**.
- PR list: #459 is the only PR merged since #458. Draft #411 was updated at 00:47 UTC today and #412 is still open; neither reviewed.

## Review of the new commit

- Effect: until now the daily source canary and the connectivity heartbeat ran without an EU token, so the EU adapter (`ingest/eu.py`, optional, `is_mandatory=False`, raises "EU FSF token not configured" when the token is unset) always failed in CI and EU coverage was never actually verified. With the secret wired in, CI can detect a broken EU feed. No secret value is committed; it is read from GitHub secrets. The deploy job already passed the same variable (`test_deploy_job_still_passes_eu_fsf_token`).
- Compliance relevance: low and positive. The EU list is not a UAE freeze list (`sanctions_scope.py`; Res 74/2020 per EOCN, unverified), so EU data supports EDD and STR/SAR judgement, not the 24-hour freeze.
- INFO: the module docstring of `ingest/eu.py` still says a published default token makes the adapter "work out of the box"; the code now raises when no token is set. The docstring is stale and could mislead a deployer. Not a regulatory issue.

## Not-checked item taken this run: CS-5, sanctions refresh cadence

Question: can the time between a list publisher changing a designation and this tool ingesting it eat the 24-hour window? I re-derived the cadence from the deploy workflow rather than from my earlier notes.

- The Cloud Scheduler job `amlkit-sanctions-refresh` is created by `.github/workflows/source-canary.yml` with `--schedule "0 */20 * * *"` (both the create and update branches). In cron, `*/20` in the hour field fires at hours 0 and 20 only, so the job runs at **00:00 and 20:00 UTC**. The gaps are **20 hours and 4 hours**, not "every 20 hours" as the comments in the repo describe it (for example the "roughly every 20h" note in `match/engine.py` and the "00:00/20:00" note beside the freeze-check job).
- Worst case: a UN or UAE Local Terrorist List change published just after 00:00 UTC is not ingested until 20:00 UTC, about 20 hours later, plus up to three scheduler retries (60 to 300 s back-off, 900 s attempt deadline) if the first attempt fails. Customers are re-screened after each refresh (`rescreen_all`), so the earliest an existing customer can be matched to that designation is the ingest time.
- The staleness control is a 24-hour default (`datasets.max_age_hours`, `staleness_report` in `ingest/loader.py`, whose docstring says "EOCN requires list updates to be implemented within 24 hours"). A dataset only counts as breached when `hours_since_refresh` exceeds 24, so a missed 20:00 run does not alert until the next day, and on a normal day the data is up to 20 hours old without any alert.
- Combined with CS-13 (the 24-hour freeze clock starts only at confirmed disposition, not at designation), the designation-to-freeze path can exceed 24 hours even when every step works as designed: up to 20 hours of ingest lag, then screening, then four-eyes confirmation, then the freeze.
- The reason for the sparse schedule is stated in the workflow: the hourly freeze check runs at :15 and the refresh was kept off that minute to avoid two jobs hitting the single SQLite writer. A refresh every four to six hours at minute 0 (for example `0 */6 * * *`) would keep that separation.
- Basis: EOCN guidance that list updates apply within 24 hours of publication and that freezing is "without delay" (page fetched 2026-10-06), Law 10/2025 Art 17, Res 74/2020 Art 15, Res 134/2025 Art 32; all unverified against the instruments.

## Findings

| ID | Severity | Status | Finding |
|---|---|---|---|
| CS-5 | MEDIUM | **CONFIRMED (code and workflow), PLAUSIBLE (legal)** — open | The sanctions list refresh runs only at 00:00 and 20:00 UTC (`0 */20 * * *`), up to 20 hours between ingests; the 24-hour staleness limit does not alert on that gap. The repository comments describe this as "every 20h", which is wrong. Suggest a refresh every four to six hours (and a staleness threshold below the refresh gap plus margin), keeping minute 0 clear of the :15 freeze check. |
| N-8 | none | REFUTED | #459 changes no application behaviour; it can only improve CI's ability to detect an EU feed failure. No regression risk to the six mandatory rules. |
| CS-26 | INFO | CONFIRMED (code) | `ingest/eu.py` docstring is stale (says a default token works out of the box; code raises when `AMLKIT_EU_FSF_TOKEN` is unset). |
| CS-13 | HIGH | PLAUSIBLE (legal), CONFIRMED (code) — **open** | Unchanged: the 24-hour clock runs from `freeze_obligations.identified_at`, set at confirmed disposition. Law 10/2025 Art 17, Res 74/2020 Art 15, Res 134/2025 Art 32 (unverified). Now read together with CS-5. |
| CS-14 (PNMR) | MEDIUM | CONFIRMED (code) — **open** | `SUPPORTED_REPORT_TYPES` is still `{"STR","SAR","FFR"}`. |
| CS-24 | MEDIUM | PLAUSIBLE — **open** | UAE PASS verification is still advertised as a CDD feature while the repo documents it as sandbox-only and verification rows do not record the environment (see 2026-11-04). |
| 3.1 | MEDIUM | PLAUSIBLE — **open** | The AED 55,000 cash threshold (Res 134/2025 Art 21) is still organisation-configurable. |

All other findings in earlier reports stand as written (FATF handling, CS-4 Interpol, CS-18, CS-25, the 5-versus-8-year retention question).

## BLOCKED / not checked

- **Primary legal text: BLOCKED**, unchanged. Three official hosts (`rulebook.centralbank.ae`, `uaelegislation.gov.ae`, `fatf-gafi.org`) refused this environment's egress on 2026-10-06; not retried or bypassed. To unblock: provide the official PDFs of the four instruments as `corpus/` plus `citation_register.json`.
- **Actual Cloud Scheduler job state in production:** not checked. I read the schedule the workflow applies; whether the deployed job matches (and whether anyone edited it by hand) can only be seen with `gcloud scheduler jobs describe amlkit-sanctions-refresh`, which I cannot and must not run.
- **UAE PASS production status** (secrets and variables): not checkable.
- Not re-verified individually: CS-15, CS-16.
- Drafts #411 and #412: not reviewed.
- Production: not checked.

## Files and commit

`reports/daily/2026-11-05/compliance-specialist.md` on `routine/2026-11-05-compliance-specialist`, created from `origin/master` `6560fb0`. The commit SHA is in the final reply (a commit cannot name its own SHA).
