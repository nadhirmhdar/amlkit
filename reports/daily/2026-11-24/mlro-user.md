# mlro-user daily report — 2026-11-24

**Headline: AMBER** — master moved to f3c8227 (one owner-only trial-grant endpoint, which I did not call), all 41 of my earlier walks still pass, and today's check of new list entries found that the sanctions search index is cached per server process, so a refresh seen by one process may not reach the others.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to see what the new commit touched and to read the cache module and where it is cleared.
- Report to branch `routine/2026-11-24-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master changed: `git ls-remote origin refs/heads/master` = `f3c8227121fbec1d4c3860c63b4a383a4656f975` (previous report: c42c77c). Highest PR ref now 468. The one new commit, #468, adds `/system/grant-trial` (an owner-granted N-day trial with no card) behind the system bearer token. `/system/*` is out of bounds for me by standing rule, so I did not call it, and nothing in the MLRO screens changed.

## What I did (evidence: `mlro-user-evidence/log_newlist24.json`; driver `mlro_user_drive.py`, mode `newlist24`)
1. **Regression:** re-ran all 41 earlier driver modes on f3c8227. All exit 0, no tracebacks.
2. **New list entry after onboarding:** onboarded two customers, then added a person (same name, date of birth and country as one customer) to the UAE Local Terrorist List by writing to the local database, then pressed "Re-screen all". It reported "Re-screened 2 name(s)" and raised no alert; an ad-hoc screen of the new name and a freshly onboarded customer with that name also found nothing.
3. Read why: the matching engine keeps an in-memory token cache (including "no match" answers), which is cleared only when the refresh job running in that same process finishes (`scheduler.py` clears it after a refresh). My direct database write bypassed that, so this result is an artefact of my method, not a defect. It does show the dependency, which is why I checked how the clear happens.

## Findings
- **SL1 (medium, PLAUSIBLE):** The sanctions search cache is per process. After a list refresh, only the process that ran the refresh clears its cache. If the service runs more than one worker or instance, the others keep the old index, including remembered "no match" answers, until they restart. A person newly added to a list could then be missed by screening and re-screening in those processes. The code already acknowledges the same problem for the transaction-rule settings cache (`kyt.py`: "every other worker"). I cannot see the production worker or instance count, so I cannot confirm exposure.
- **SL2 (low, CONFIRMED):** "Re-screen all" reports "Re-screened N name(s)" without saying which list version or when the lists were last refreshed, so an MLRO cannot tell from that message whether the screen was against current data. (The dashboard and Ops page do show freshness separately.)
- Earlier open items unchanged: EV1 (low-medium, corrected), ED1, ED2, DB1, DB2, EX1, QU1, CL1, TX1, SO1, RL1, RP1, MA1, RT1, CR1 and the other lows.

## BLOCKED / not checked
- `/system/grant-trial` (out of bounds by rule) and any billing or trial screen that it feeds.
- Multi-worker cache behaviour (needs a deployed multi-process run).
- Rate limiting (my driver disables the limiter), HSTS, payment sign-up, goAML XSD validation, adverse media (GDELT), tesseract OCR success path, SMTP delivery.

## Files and commit
- `reports/daily/2026-11-24/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-24-mlro-user`; commit SHA in the final reply.
