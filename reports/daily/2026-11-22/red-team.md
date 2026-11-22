# Red team daily, 2026-11-22

## Instructions I ran under
Daily routine message (DATE 2026-11-22, current origin/master, probe code changed since previous report, then one not-checked area; local only; push to `routine/2026-11-22-red-team`, never master; final reply = this report). Standing rules win: no production, no /system/*, no secrets, local test data only, additive only, stop after delivery.

## Headline: **AMBER (unchanged)**. The only new code on master is a deploy-flag change with no app impact; the PC1 same-name PEP merge is now reproduced end to end (the second person never gets an alert).

Master tested: `c42c77ce59179c86b3ed5107b78e65e227326c0d` (previous report `bfb0253`). New: #467 only.

## What I did
- Read #467 (`.github/workflows/source-canary.yml` +19, `CLAUDE.md` 1 line): adds `--no-cpu-throttling` to the Cloud Run deploy so litestream gets CPU. No application code, no secrets, no routes touched.
- New `repro_redteam/probe_pep_collapse_e2e.py` (scratch DB, reuses `tests/test_pep_dedupe.py::_load`): two different people named "John Smith" (cia: no country; wikidata: Ghana), ad-hoc screen of "John Smith", then dismiss the alert, screen again. Evidence: `evidence/probe_pep_collapse_e2e_on_c42c77c.txt`.

## Findings
- **PC1 / PC1b (CONFIRMED end to end, low-medium):** both runs return 1 hit; entity 2 is listed only as "absorbed" under entity 1. Alert rows exist only for entity 1 (run 2 raised a new open alert for entity 1; none for entity 2). So the second PEP can never alert on its own, whatever the reviewer does with the first. Held fix: `scripts/proposals/2026-11-20-new-findings.md` (PC1).
- **#467 (no finding, informational):** instance-based billing roughly triples the idle cost the PR itself quotes (about USD 58-63 vs 19-21 a month). Not a security issue. A durable-replica gain with no code risk. I did not check the live deploy.

## BLOCKED / not checked
- Whether dismissal persists across runs for a real customer: my probe was an ad-hoc screen with no customer, so run 2 re-alerted entity 1 (expected for ad-hoc). Customer-scoped coverage not exercised.
- Mobile parity of the collapse, full test suite, `also_listed` rendering, Stripe live-mode paths, UAE PASS callback.
- Production/deploy behaviour of #467 (no production access).

## Files / commit
`repro_redteam/probe_pep_collapse_e2e.py`, `reports/daily/2026-11-22/` (+ carried files from the 2026-11-21 branch). Commit SHA: see final reply (branch `routine/2026-11-22-red-team`).
