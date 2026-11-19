# mlro-user daily report — 2026-11-19

**Headline: AMBER** — master moved to cdf3801 and its fix (#464) closes a real screening miss I could not see before (exact-name, same-DOB, same-nationality hits on lists that spell countries as names were being dropped); everything I re-ran still passes, and my earlier open items stand.

## Instructions I ran under
- MLRO persona (Agent 5): judge groAML from outside. LOCAL seeded instance only; no production, no /system/*, no secrets; additive only. Source read only to see what #464 changed (the country table and scorer).
- Report to branch `routine/2026-11-19-mlro-user` (never master) and as final reply. No dreamon messages today.
- Master changed: `git ls-remote origin refs/heads/master` = `cdf38011da60cb8eadf5c5fc7290e92bf96f124a` (previous report: 9219e26). Highest PR ref now 464. Commits: #464 screening: compare countries as ISO codes, and #463 billing switched off by default (master switch). Not the shortcut.

## What I did (evidence: `mlro-user-evidence/log_ctry19.json`; driver `mlro_user_drive.py`, mode `ctry19`, plus all earlier modes)
1. **Regression:** re-ran all 38 earlier driver modes on cdf3801. All exit 0, no tracebacks. `/billing` is still 404 for visitors (billing off).
2. **Before and after for #464.** My seeded list entries carry ISO codes, which is why this never showed up in my runs. The real reference lists (CIA, Wikidata, UN, OFAC, UK, EU) spell countries as names ("Russian Federation", "Iran, Islamic Republic of"). I re-seeded the list entries with names and onboarded customers with the same name, date of birth and ISO nationality as the listed person:
   - On the previous master (9219e26): 1 alert for 5 customers; the Russian, Iranian (UN) and Iranian (PEP) customers with exact name and matching date of birth raised nothing.
   - On the new master (cdf3801): 5 alerts for 5 customers. The Russian customer raised an OFAC alert ("no UAE freeze obligation arises"), the Iranian UN match raised "freeze without delay and do not tip off", and the PEP and UAE-list customers alerted as before.
3. A French customer with the same name and date of birth as the listed Russian also alerts; matching is still driven by name and date of birth, with the country as a comparison rather than a gate.
4. Ad-hoc screening of an exact listed name finds the person on both builds.

## Findings
- **SC1 (high, CONFIRMED, FIXED in cdf3801):** Before #464, customer-to-list country comparisons treated an ISO code and a country name as different countries, so many exact-name, same-DOB, same-nationality hits fell under the alert threshold and were never shown. My earlier seeded tests missed this because they stored codes. After the fix the same cases alert.
- **SC2 (info, CONFIRMED):** The driver seed was unrealistic. I now keep a country-name seed in `ctry19` and will run it each time screening code changes.
- **SC3 (PLAUSIBLE, not tested):** Country names and aliases not in the new table (spelling variants, historical names) will still compare as "can't tell" rather than match. The table is large, but I cannot enumerate every list spelling.
- Billing switched off by default (#463): visitors see no billing pages (`/billing` returns 404) and nothing in the MLRO screens changed.
- Earlier open items unchanged: QU1, QU2, EX1, EX2, EX3, CL1, CL2, TX1, SO1, RL1, RL2, RP1, MA1, RT1, CR1, CR2, UBO1b, F4 and the other lows.

## BLOCKED / not checked
- A one-off re-screen of existing customers after the fix: customers screened before #464 whose hits were dropped may need a re-run of "Re-screen all"; I did not walk that on a populated database.
- Real list spellings beyond the ones I seeded; rate limiting (my driver disables the limiter); HSTS; payment sign-up; goAML XSD validation; adverse media (GDELT); tesseract OCR success path; SMTP delivery.

## Files and commit
- `reports/daily/2026-11-19/mlro-user.md`, `mlro_user_drive.py`, `mlro-user-evidence/*.json`
- Branch `routine/2026-11-19-mlro-user`; commit SHA in the final reply.
