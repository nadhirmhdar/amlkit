# mlro-user report, 2026-11-27

**Headline: AMBER.** master is unchanged. Overdue periodic reviews are visible to the MLRO, which clears HP3. One new gap: ad-hoc `/screen` runs and returns a result on lists 5 days old with no staleness warning, while onboarding refuses in the same state.

## Instructions I ran under
Routine "groAML daily: mlro-user". Local seeded instance only. No production access, no /system/* calls, no secrets, additive-only. The report goes to branch `routine/2026-11-27-mlro-user`, never master. After delivery I stop completely: no polling, CI re-checks or self-scheduled reminders.

## Base
origin/master = `f3c8227121fbec1d4c3860c63b4a383a4656f975`, unchanged since 11-25. The highest PR ref is still 468. Shortcut applied.

## What I did (driver modes `review27`, `review27b`; evidence in `mlro-user-evidence/review_*.txt`, `log_review27*.json`)
1. Onboarded a customer and backdated `risk_assessments.next_review` to 2026-01-15 (direct DB update).
2. Looked for the overdue marker in the customers list, the customer page, the dashboard and the JSON feed.
3. Ran ad-hoc `/screen` for a listed name (UAE Local Terrorist List) with fresh lists, then with lists aged to 5 days.

| Surface | Result |
|---|---|
| /customers | row shows "overdue" in the Review due column |
| /customers/1 | "next review 2026-01-15 Overdue" |
| /api/alerts-summary | `overdue_reviews:[{id:1, "Fatima Khan", "2026-01-15"}]` |
| /dashboard | mentions the customer and review (my first regex missed it; the second run confirmed it) |
| /screen, fresh lists | 1 match, "SANCTIONS match. Freeze without delay and without prior notice… Do not tip off." |
| /screen, stale lists | the same match and wording; I found no staleness warning anywhere in the response |

## Findings
- **HP3, REFUTED.** Overdue reviews are visible in four places. My 11-25 and 11-26 notes were wrong because I read only the Ops queues and a truncated dashboard excerpt.
- **SS2, CONFIRMED, low-medium.** `/screen` gives a definitive answer on stale lists, while onboarding fails closed with a clear message. An MLRO who screens a counterparty ad hoc during a refresh outage gets "no match" or "match" with no freshness stamp. A negative result on 5-day-old lists could be read as clear. Suggest showing the lists' age on the result, or a banner when any mandatory list is past its window. The dashboard banner exists, but nothing on `/screen` points to it.
- **HP2, still low, probably a seed artefact.** "No successful load recorded yet" on Ops.
- **HP5, still low.** The onboarding refusal says "Refresh sources" while the dashboard banner says "Refresh sanctions lists now".
- Both of my earlier misses (HP3 on 11-25, HP4 on 11-26) came from reading too little of the response. I now check the full page text before reporting a gap.

## Open from earlier reports (not re-verified today)
UBO1b, QU1/QU2, EX1–EX3, CL1/CL2, TX1–TX3, SO1, RL1–RL3, RP1/RP2, MA1/MA2, RT1/RT2, CR1–CR3, SU1, ED1/ED2, DB1–DB3, EV1/EV2/EV4, SL1 (PLAUSIBLE), SL2, F4, TA2, TA3, E2–E5, LN1, SE2, PR5.

## BLOCKED / not checked
- goAML XSD validation, adverse media (GDELT network), tesseract OCR success path, SMTP delivery, HSTS and payment sign-up.
- Rate limiting: my driver disables the limiter (`/screen` is limited to 10/minute).
- Mobile screening on stale lists: not tested.
- `/system/*` endpoints, including `/system/grant-trial` from #468: not called, per the rules.

## Files
`reports/daily/2026-11-27/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/`.
