# mlro-user report, 2026-11-28

**Headline: AMBER.** master is unchanged. The mobile API fails closed on customer creation with stale lists, like the web. Mobile `/screen` still answers on stale lists with no staleness field, so SS2 from 11-27 reaches mobile too.

## Instructions I ran under
Routine "groAML daily: mlro-user". Local seeded instance only. No production access, no /system/* calls, no secrets, additive-only. The report goes to branch `routine/2026-11-28-mlro-user`, never master. After delivery I stop completely: no polling, CI re-checks or self-scheduled reminders.

## Base
origin/master = `f3c8227121fbec1d4c3860c63b4a383a4656f975`, unchanged since 11-25. The highest PR ref is still 468. Shortcut applied.

## What I did (driver mode `mobstale28`; evidence in `mlro-user-evidence/log_mobstale28.json`)
I logged in over the mobile API as the MLRO (bearer token plus TOTP verify). Then I made the same calls with fresh lists and with every mandatory list backdated to 2026-11-20 (about 194 h old).

| Call | Fresh lists | Stale lists |
|---|---|---|
| POST /api/v1/customers (listed name) | 200, `blocked:true`, risk high, EDD required | **503** "Cannot onboard: no fresh mandatory sanctions dataset available. Ask an MLRO to run Admin → Refresh sources" |
| POST /api/v1/screen (listed name) | not run | 200, `clear:false`, 1 hit, no staleness field (keys: candidates, clear, hits, low_confidence, query, threshold, unscreenable) |
| GET /api/v1/datasets | not run | 200, shows `last_refresh` 2026-11-20 for each source, no breach flag |
| GET /api/v1/dashboard | not run | `staleness[]` per source: `hours_since_refresh` 193.7, `max_age_hours` 24, `breach:true`; also `oldest_list_age`, `compliant`, `breaches` |

## Findings
- **MS1, REFUTED as a defect.** Mobile onboarding fails closed, with the same message as the web. The 503 is the right class of status (service state, not a client error).
- **SS2, CONFIRMED on mobile, low-medium.** `/screen` returns a verdict without saying how old the lists are. The data is available in the same API: `/dashboard` already carries `staleness` and `breach`. Suggested fix: include `lists_stale: true` and the oldest age in the `/screen` response, and show it on the web result page. A mobile client could otherwise display "clear" from lists 8 days old.
- **MS2, CONFIRMED, low.** The mobile refusal text says "Refresh sources" (HP5, same wording as the web). The mobile app has no refresh action in this API, so the instruction cannot be followed from the device. An MLRO on a phone is told to go to the Admin page.
- **MS3, CONFIRMED, informational.** `/datasets` exposes `last_refresh` but no staleness verdict. Clients must compute it, or call `/dashboard`.

## Open from earlier reports (not re-verified today)
UBO1b, QU1/QU2, EX1–EX3, CL1/CL2, TX1–TX3, SO1, RL1–RL3, RP1/RP2, MA1/MA2, RT1/RT2, CR1–CR3, SU1, ED1/ED2, DB1–DB3, EV1/EV2/EV4, SL1 (PLAUSIBLE), SL2, F4, TA2, TA3, E2–E5, LN1, SE2, PR5, HP2, HP5, SS2 (web).

## BLOCKED / not checked
- goAML XSD validation, adverse media (GDELT network), tesseract OCR success path, SMTP delivery, HSTS and payment sign-up.
- Rate limiting: my driver disables the limiter (mobile `/screen` is limited to 10/minute).
- Mobile alert rescreen on stale lists: not tested.
- `/system/*` endpoints, including `/system/grant-trial` from #468: not called, per the rules.

## Files
`reports/daily/2026-11-28/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/`.
