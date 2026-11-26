# Red team daily, 2026-11-26 (short: master unchanged)

## Instructions I ran under
Daily routine message (DATE 2026-11-26; shortcut applies when master is unchanged: probe one not-checked area, keep short; local only; push to `routine/2026-11-26-red-team`, never master; final reply = this report). Standing rules win: no production, no /system/*, no secrets, additive only, stop after delivery.

## Headline: **GREEN for test health, overall AMBER carried (PC1/PC1b open)**. The full suite passes on master except one entrypoint test that fails only because this sandbox lacks `rm` on the test's restricted PATH.

Master: `f3c8227121fbec1d4c3860c63b4a383a4656f975` (same as 2026-11-24/25). Newest PR still #468; none opened or merged since.

## What I did
Ran the full test suite (a not-checked item since 2026-11-21) on a detached worktree of origin/master, with the venv Python. Evidence: `evidence/full_suite_on_f3c8227.txt` (first pass, stopped at first failure), `evidence/full_suite_rest_on_f3c8227.txt` (rest, `tests/test_entrypoint.py` ignored). I also read that mobile `/screen` and the second mobile screen call both go through `engine.screen`, so the PC1 collapse behaves the same on mobile (reading only).

## Findings
- **Suite (CONFIRMED green):** 2,999 passed, 2 skipped, 0 failed with `test_entrypoint.py` ignored (14 min). The first pass also had 738 passed before its one failure.
- **`tests/test_entrypoint.py::test_verified_database_starts[ok-ok]` fails here (environment, PLAUSIBLE not a product bug):** the entrypoint script exits 127 with `rm: command not found` while the test runs it with a restricted PATH in this sandbox. Not the application. I did not run the other cases in that file or check CI, so I cannot say it passes in CI.
- **Mobile parity of PC1 (CONFIRMED by reading):** both mobile screening paths call `engine.screen`, so same-name PEPs merge the same way there. PC1/PC1b is unchanged and open; held fix in `scripts/proposals/2026-11-20-new-findings.md`.

## BLOCKED / not checked
- `tests/test_entrypoint.py` beyond that one failure (sandbox PATH).
- The `/system/grant-trial` route over HTTP (standing rule); `also_listed` rendering; Stripe live-mode paths; UAE PASS callback.

## Files / commit
`reports/daily/2026-11-26/` only (no probe script, no application code). Branch `routine/2026-11-26-red-team`. Commit SHA: see final reply.
