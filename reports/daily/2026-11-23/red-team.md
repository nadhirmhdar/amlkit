# Red team daily, 2026-11-23 (short: master unchanged)

## Instructions I ran under
Daily routine message (DATE 2026-11-23, current origin/master; shortcut applies when master is unchanged: probe one not-checked area, keep short; local only; push to `routine/2026-11-23-red-team`, never master; final reply = this report). Standing rules win: no production, no /system/*, no secrets, additive only, stop after delivery.

## Headline: **AMBER (unchanged)**. Master is unchanged; the customer-scoped dismissal check now confirms PC1b end to end: after the first same-name PEP alert is marked false positive, the second person stays hidden.

Master: `c42c77ce59179c86b3ed5107b78e65e227326c0d` (same as 2026-11-22). Newest PR still #467; none opened or merged since.

## What I did
Re-ran the 2026-11-22 e2e probe as `repro_redteam/probe_pep_collapse_e2e_v2.py` with the real decided status. Evidence: `evidence/probe_pep_collapse_e2e_v2_on_c42c77c.txt`.

**Correction to my 2026-11-22 report:** its probe set alerts to status `dismissed`, which is not a status the engine treats as decided (`_coverage` knows `false_positive`, `true_positive`, `escalated`), so its run 2 re-alert was a probe artefact. The PC1/PC1b conclusion stands; the "re-alerted entity 1" line there should be ignored.

## Findings
- **PC1b (CONFIRMED end to end, low-medium):** two different people named "John Smith" (cia: no country; wikidata: Ghana). Run 1: one hit, one alert (entity 1); entity 2 only under `also_listed`. Run 2 after marking that alert `false_positive`: 0 new alerts, entity 2 still absorbed, so person B never gets reviewed. Run 3 after person A is removed from the list: B alerts. So B is hidden only because of the merge. Held fix: PC1 in `scripts/proposals/2026-11-20-new-findings.md`.
- **Dismissal persistence (REFUTED as a problem):** a decided alert does stop re-alerting on re-screen, as designed.

## BLOCKED / not checked
- Customer-scoped (onboarded customer) variant: probe used an ad-hoc screen (customer none), same coverage key rules; not run through `onboard`.
- Mobile parity of the collapse (mobile `/screen` and `rescreen` call the same `engine.screen`; not run), full test suite, `also_listed` rendering, Stripe live-mode paths, UAE PASS callback.

## Files / commit
`repro_redteam/probe_pep_collapse_e2e_v2.py`, `reports/daily/2026-11-23/`. Branch `routine/2026-11-23-red-team` (built on the 2026-11-22 branch). Commit SHA: see final reply.
