# code-reviewer daily report, 2026-11-05

**Instructions I ran under:** scheduled routine "groAML daily: code-reviewer" (fired 2026-11-05 00:45 UTC). Review current origin/master, the changes since the SHA in my previous report, and PRs opened or updated since. Standing rules: no production access, no `/system/*` calls, no secrets, local test data only, never push to master, stop after delivering.

**Headline: GREEN.** origin/master moved from `c5da8aa06f192ec6ec3f90534b6c9264e4088da1` to `6560fb021f6ea2cadefcd6e60d67ee274d871e73` by one CI-only commit (#459, no application code); I found one LOW secret-exposure observation about when the new token is visible.

**What I did (evidence):**
- `git ls-remote origin refs/heads/master` returned `6560fb0…`; `git log c5da8aa..origin/master` lists one commit, #459 "CI: pass EU FSF token to the source checks", merged 2026-11-04. It changes two files: `.github/workflows/source-canary.yml` (+6) and a new `tests/test_workflow_env.py` (+22). No file under `amlkit/` changed, so the full-suite result for `c5da8aa` (2860 passed, 2 skipped) still describes the application code; I did not rerun it.
- Ran the new test on `6560fb0` in a throwaway worktree: `tests/test_workflow_env.py` 2 passed.
- Read the whole diff. The token (`secrets.EU_FSF_TOKEN`, exposed as `AMLKIT_EU_FSF_TOKEN`) is scoped to a single step in each of the `sources` and `heartbeat` jobs, not to the whole job, which is the narrow way to do it. The deploy job already passed it.
- Read the workflow triggers and job conditions to see when those steps run.

**Findings:**
- CR-40 (LOW, CONFIRMED): the workflow triggers on `pull_request` as well as `push`, `schedule` and `workflow_dispatch`, and the `sources` and `heartbeat` jobs have no `if:` condition. They therefore run on every pull request from a branch in this repository, now with `EU_FSF_TOKEN` in the environment. GitHub withholds secrets from fork PRs, but any same-repo branch can change `scripts/heartbeat.py` or the workflow itself and print or send the token (log masking does not stop encoding or exfiltration). This repo is changed by many automated agent sessions that push branches, so the realistic risk is a prompt-injected or mistaken agent branch, not a hostile collaborator. Suggested fix: run these two steps only for `github.event_name != 'pull_request'`, or limit the token to the scheduled and master runs. The token's own blast radius is small (read access to the EU sanctions download), which is why this is LOW.
- Carried, unchanged: CR-4 (MEDIUM, unmerged #417; not re-checked), CR-13 and CR-18 (LOW; not re-checked), CR-2/3/5/17, CR-19 to CR-23, CR-28, CR-29, CR-33 to CR-39 (INFO).

**BLOCKED / not checked:**
- Nothing blocked.
- CI status for `6560fb0` was not looked up (standing rule: no CI re-checks), so I cannot say whether the new token makes the EU source check pass in CI.
- I did not run the `sources` or `heartbeat` scripts (they call external sites) and did not rerun the full suite for this CI-only change.
- I did not re-measure the `alert_queue` slowdown (CR-13).

**Files / commits:** `reports/daily/2026-11-05/code-reviewer.md`; commit SHA in the final reply.
