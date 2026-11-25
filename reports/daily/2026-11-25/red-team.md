# Red team daily, 2026-11-25 (short: master unchanged)

## Instructions I ran under
Daily routine message (DATE 2026-11-25; shortcut applies when master is unchanged: probe one not-checked area, keep short; local only; push to `routine/2026-11-25-red-team`, never master; final reply = this report). Standing rules win: no production, no /system/*, no secrets, additive only, stop after delivery.

## Headline: **GREEN for this area, overall AMBER carried (PC1/PC1b open)**. Trial expiry is enforced exactly at the 7-day grace for owner-granted trials; only unparseable or NULL dates fail open, by design.

Master: `f3c8227121fbec1d4c3860c63b4a383a4656f975` (same as 2026-11-24). Newest PR still #468; none opened or merged since.

## What I did
Picked "expired-trial enforcement past grace, billing on" from yesterday's not-checked list. `repro_redteam/probe_trial_expiry.py` (function level, scratch DB, billing switched on with a dummy key; run against a worktree of origin/master because this branch carries no application code): create a trial via `grant_trial`, then set `trial_ends_at` to 11 values and call `check_limit` for operators and customers. Evidence: `evidence/probe_trial_expiry_on_f3c8227.txt`.

## Findings
- **Expiry enforcement (REFUTED as a problem):** allowed while the trial runs, 1 day after, and at 6d23h after; refused (BillingLimitError) at 7d1h and 400 days after. Same for operators and customers.
- **Date formats (REFUTED):** naive timestamp, date-only and `Z`-suffixed past dates are all parsed and refused correctly.
- **Fail-open on bad data (CONFIRMED, informational):** `trial_ends_at` of `'tomorrow'`, empty string or NULL is allowed, i.e. unlimited. This matches the documented rule (unknown period end fails open; NULL is the legacy-org case). It is only reachable by direct SQL or a future writer; `grant_trial` always writes a valid timestamp. A stricter alternative would be to treat unparseable non-empty values as expired. Not a new bug.

## BLOCKED / not checked
- The `/system/grant-trial` route over HTTP (standing rule: no /system/* calls).
- PC1/PC1b still open (see 2026-11-23). Mobile parity of the merge, the full test suite, `also_listed` rendering, Stripe live-mode paths, UAE PASS callback.

## Files / commit
`repro_redteam/probe_trial_expiry.py`, `reports/daily/2026-11-25/`. Branch `routine/2026-11-25-red-team` (built on the 2026-11-24 branch; no application code touched). Commit SHA: see final reply.
