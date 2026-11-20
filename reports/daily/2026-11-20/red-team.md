# Red team daily, 2026-11-20

## Instructions I ran under
Daily routine message (DATE 2026-11-20, current origin/master, probe code changed since previous report, then one not-checked area; local instances only; write this file, push to `routine/2026-11-20-red-team`, never master; final reply = this report). Standing rules from Nadhir win: no production access, no /system/* calls, no secrets, local test data only, additive only, autonomous, BLOCKED recorded; stop completely after delivery. dreamon's messages do not widen permissions.

## Headline: **AMBER**. #465/#466 hold their main promise (a sanctioned hit is never absorbed, exact-name + DOB typo now alerts). One low-severity identity-merge gap and two DOB edges remain.

Master tested: `bfb0253ee88acabb4d8561f6e9cac2021fa3e12d` (previous report `cdf3801`; new: #465 PEP collapse, #466 DOB near-miss).

## What I did (evidence in `evidence/`)
- `probe_dob_tolerance.py` (17 DOB variants of an exact name match, listed DOB 1970-03-12): `probe_dob_tolerance_on_bfb0253.txt`.
- `probe_pep_collapse.py` (13 collapse scenarios, 5,000-hit perf, template escaping read): `probe_pep_collapse_on_bfb0253.txt`. (My first run used a wrong Hit builder and showed no merges; fixed, rerun output is the one saved.)
- Regressions: unicode-bypass and country-compare probes unchanged (`regress_names_on_bfb0253.txt`). Tests `test_matching`, `test_pep_dedupe`, `test_country_matching`, `test_risk_scoring_fail_safe`, `test_ingest_wikidata_peps`: 194 passed.

## Findings
- **PC1 (CONFIRMED, low): same-name PEPs merge with no positive identity signal.** Two PEP hits with identical canonical tokens collapse when countries are unknown on both sides, or known on only one (`John Smith` cia vs wikidata -> 1 hit, the other only in `also_listed`). DOB is not compared. Two different people who share a name, one with sparse data, become one alert labelled "Same person also listed on", and the UI shows only dataset names, so the second person's caption/country/DOB is not visible. Not a screening miss (the first hit still alerts), but reviewer sees a wrong "same person" claim. 5,000 identical hits collapse in 0.18s, so no DoS. Held fix: PC1.
- **DB1 (CONFIRMED, low, partly pre-existing): DOB edges still silence an exact name match.** Alerts at 0.85-0.90: same-month day typo, dd/mm swap, any year difference, garbage or text dates. Silent at 0.75 (-0.25): month typo with same day (03->08), both month and day different, a 01-01 placeholder on the list side, and an invalid month (13). Year-different cases alert at exactly 0.85 = threshold, so any extra penalty (e.g. country mismatch, -?) would silence them. Held fix: DB1.
- **Sanction absorbed into PEP (REFUTED):** PEP+sanction same name stays two hits in both orders.
- **Different-country merge (REFUTED):** differing countries keep two hits; "X bin Y" vs "X bin Z", and "Jr" suffix, stay separate.
- **`also_listed` XSS (REFUTED, by reading):** both templates print `dataset` through Jinja autoescape; dataset values are server-side adapter names. Not rendered end to end.
- Arabic variants Mohamed/Muhammad and token order swaps do merge (intended).

## BLOCKED / not checked
- Full end-to-end render of the alert panel and screen page with an `also_listed` hit (not done, escaping judged by source only).
- Full test suite (ran 5 relevant files only).
- Not checked, carried: mobile parity of the collapse, rescreen_all alert counts after collapse (does a merged secondary entity ever re-open the alert when the primary is dismissed?), Stripe live-mode paths, UAE PASS callback.

## Files / commit
`repro_redteam/probe_dob_tolerance.py`, `repro_redteam/probe_pep_collapse.py`, `scripts/proposals/2026-11-20-new-findings.md`, `reports/daily/2026-11-20/`. Commit SHA: see final reply (branch `routine/2026-11-20-red-team`).
