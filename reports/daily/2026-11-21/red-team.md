# Red team daily, 2026-11-21 (short: master unchanged)

## Instructions I ran under
Daily routine message (DATE 2026-11-21, current origin/master; shortcut applies when master is unchanged: probe one not-checked area, keep short; local only; push to `routine/2026-11-21-red-team`, never master; final reply = this report). Standing rules win: no production, no /system/*, no secrets, additive only, stop after delivery.

## Headline: **AMBER (unchanged)**. Master is the same as yesterday; reading the alert-coverage path shows the PC1 merge gap is worse than reported: dismissing one same-name PEP alert also hides the other person.

Master: `bfb0253ee88acabb4d8561f6e9cac2021fa3e12d` (same as the 2026-11-20 report). Newest PR still #466; no PR opened or merged since.

## What I did
Read `engine.screen` (hits, alert creation) and `_coverage` (lines ~330-540 of `amlkit/match/engine.py`) for the not-checked item "does a merged secondary entity re-open or stay hidden once the primary alert is dismissed". Code reading only; no new probe run, no new evidence file.

## Findings
- **PC1b (CONFIRMED by code reading, low-medium; extends PC1):** alerts and coverage are keyed by `(org, entity_id, customer)`, and only entities that survive `collapse_pep_duplicates` become hits. A same-name PEP absorbed into `also_listed` never gets its own alert or `_coverage` row. If the reviewer dismisses the primary as a false positive for person A, person B (different person, same name, no country or DOB data to tell them apart) is never alerted on later runs either, because B keeps being absorbed. Before #465 B alerted separately. Not run end to end. Held fix: the PC1 proposal in `scripts/proposals/2026-11-20-new-findings.md` (merge only with a corroborating signal) also closes this.
- **Primary flip (PLAUSIBLE, noise only):** the primary is chosen by `(-score, dataset, entity_id)`. If scores change between runs the primary can switch to another entity, which would raise a new alert for a customer already dismissed on the old primary. That is extra alerts, not a miss. Not run.

## BLOCKED / not checked
- End-to-end run of PC1b with a seeded DB (needs the PR #412 seed; skipped for the shortcut).
- Mobile parity of the collapse; full test suite; rendering of `also_listed`; Stripe live-mode paths; UAE PASS callback.

## Files / commit
`reports/daily/2026-11-21/red-team.md` on branch `routine/2026-11-21-red-team` (built on the 2026-11-20 branch). Commit SHA: see final reply.
