# mlro-user daily report — 2026-11-17

**Headline: AMBER** — master is unchanged (9219e26); the alert queue stays consistent across screens at 120 alerts, but it has no paging or search, so every alert is sent in one page, and bad filter values are silently ignored.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. No source read today.
- Report to branch `routine/2026-11-17-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master: `git ls-remote origin refs/heads/master` = `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, unchanged since my 2026-11-08 report; highest PR ref still 462. Shortcut applied: one new workflow, short report.

## What I did (evidence: `mlro-user-evidence/log_queue17.json`; driver `mlro_user_drive.py`, mode `queue17`)
Created 120 customers who each match the same listed person, giving 120 open sanctions alerts, then compared every place the queue is shown:
1. Database: 120 open alerts. `/alerts`: all 120 rendered. Dashboard: "120 waiting for a decision — Open the queue (120)". `alerts.csv`: 120 rows. The four agree.
2. The queue page is about 465 KB of HTML for 120 alerts (about 3.9 KB each). `?page=2`, `?limit=5` and `?q=Ahmed` return the identical full page.
3. The grouped view (`?group_by=customer`) renders about 574 KB.
4. Malformed filters: `?status=bogus`, `?sort=bogus`, `?group_by=bogus` and `?category=bogus` all return 200 with the default view and no message. `?status=false_positive` and `?status=all` filter as expected.

## Findings
- **QU1 (low-medium, CONFIRMED):** The alert queue has no paging and no search: all open alerts are sent in a single page and the `page`, `limit` and `q` parameters are ignored. At this size the page is 465 KB; a firm with a few thousand alerts after a list refresh would get a multi-megabyte page. An MLRO also cannot find one customer's alert by name from the queue.
- **QU2 (low, CONFIRMED):** An unknown status, sort, category or grouping value is silently replaced by the default, so a mistyped or bookmarked filter shows a different list with no hint.
- **QU3 (info, CONFIRMED):** 120 customers with identical names and dates of birth could be onboarded without any duplicate warning (CR2 from earlier), which is how this volume was created.
- Counts agreeing across database, queue, dashboard and CSV: **REFUTED** as a defect.
- Earlier open items unchanged (no application change since the last report): CL1, CL2, TX1, TX2, TX3, SO1, RL1, RL2, RL3, RP1, RP2, MA1, MA2, RT1, RT2, CR1, CR2, CR3, UBO1b, SU1, F4, TA2, TA3, high-risk-country field, E2-E5, LN1, SE2, PR5 and the other lows.

## BLOCKED / not checked
- Real response time of the queue page in production (local test only; page size is what I can measure).
- Rate limiting (my driver disables the limiter), HSTS, payment sign-up, goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-17/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-17-mlro-user`; commit SHA in the final reply.
