# code-reviewer daily report, 2026-11-22

**Instructions I ran under:** scheduled routine "groAML daily: code-reviewer" (fired 2026-11-22 00:45 UTC). Review current origin/master, the changes since the SHA in my previous report, and PRs opened or updated since; one-paragraph shortcut only if master is unchanged and no PR opened or merged. Standing rules: no production access, no `/system/*` calls, no secrets, local test data only, additive-only, never push to master, stop after delivering.

**Headline: GREEN.** origin/master moved from `bfb0253ee88acabb4d8561f6e9cac2021fa3e12d` to `c42c77ce59179c86b3ed5107b78e65e227326c0d` by one PR (#467, deploy flag `--no-cpu-throttling` plus a docs line); it touches no Python, the flag is correctly placed in the only deploy command, and I found no defect.

**What I did (evidence):**
- `git ls-remote origin refs/heads/master` returned `c42c77c…`; `git log bfb0253..origin/master` lists exactly one commit, #467 "Deploy with --no-cpu-throttling: keep the replica current and stop request stalls" (merged 2026-11-21). Highest PR ref is now 467 (was 466). `git diff --stat`: 2 files, +20/-1: `.github/workflows/source-canary.yml`, `CLAUDE.md`. No file under `amlkit/` or `tests/` changed.
- Read the whole diff. The workflow change is one added line, `--no-cpu-throttling \`, in the `gcloud run deploy amlkit` command, plus 18 comment lines. I parsed the workflow with PyYAML (scratchpad venv): valid; the workflow has exactly one `gcloud run deploy` step, and it now contains `--no-cpu-throttling`, `--cpu-boost` and `--min-instances 1`. The flag is a real `gcloud run deploy` option and sits mid-continuation with the backslash intact, so the shell command is not broken.
- Checked what else the flag interacts with: `--max-instances 1` is unchanged (still one writer on the replica), `--startup-probe` and `--timeout 900` are unchanged, and `--set-env-vars` is untouched. The CLAUDE.md edit replaces the "unless it also sets `--no-cpu-throttling`" conditional with the now-true statement; it is consistent with `litestream.yml` (default 1 s sync interval, control socket kept) and with `AMLKIT_SYNC_REPLICA`, which still adds a durability wait for critical writes.
- Searched tests for readers of either changed file: only three docstrings mention `source-canary.yml`; none read it or CLAUDE.md. Because no Python changed, I did not re-run the suite; the last full baseline stands (`bfb0253`: 3010 passed, 2 skipped).
- Sanity check on the cost claim in the comment (about USD 58-63/month always-allocated vs about 19-21 request-billed, 1 vCPU / 1 GiB): my back-of-envelope using Cloud Run's published instance-based rates gives roughly USD 52 at Tier 1, so about 65 at a ~1.25x Tier 2 multiplier. The order of magnitude is plausible; I did not confirm the rates.

**Findings:**
- None blocking. No CONFIRMED defect.
- CR-50 (INFO, CONFIRMED, stale comments): three comments still describe the old throttled-CPU deploy as current: `amlkit/replication.py:5` ("Cloud Run throttles the container's CPU outside requests"), `litestream.yml:42` ("Cloud Run throttles the CPU between requests"), and `docs/incidents/2026-10-04-groaml-cold-start-outage.md:68-69,106-108` (the incident note is a point-in-time record, so that one may be left as is). The `replication.py`/`litestream.yml` wording is now only true for a service deployed without the flag, and `amlkit/api/routers/freeze.py:111` and `routers/system.py:91` carry the same assumption. No behaviour impact: `sync_replica()` is still correct and harmless with CPU always allocated. A doc-only follow-up would be to say "unless deployed with `--no-cpu-throttling`".
- CR-51 (INFO, PLAUSIBLE, operational, not a code defect): a deploy with `--max-instances 1` can run the outgoing and incoming revisions side by side briefly, and with always-allocated CPU the outgoing revision's litestream keeps replicating until it is stopped. That overlap already existed with `--min-instances 1`; the flag only makes the old instance's writes more current, not riskier. I could not test Cloud Run's revision cut-over from here.
- Carried unchanged: CR-41, CR-42, CR-47, CR-48, CR-49, CR-4, CR-13, CR-18 and the INFO set from earlier reports.

**BLOCKED / not checked:**
- BLOCKED (by rule): the production effect of the flag (request latency, the "1 in 4 requests ~0.5 s slower" observation on 2026-11-21, replica freshness, actual billing). That needs production metrics and Cloud Run logs, which I may not touch.
- Not checked: the Cloud Run pricing numbers against the live price list (no network use beyond `git`); whether the next real deploy applies the flag cleanly (only a live `gcloud run deploy` shows that).
- Not run: the full test suite, since no Python or test file changed.

**Files and commit:** `reports/daily/2026-11-22/code-reviewer.md`; pushed to `claude/tender-ritchie-mq2xh4` and `routine/2026-11-22-code-reviewer` (commit SHA in the reply).
