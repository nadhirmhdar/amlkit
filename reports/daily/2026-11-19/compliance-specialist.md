# Compliance specialist — daily report 2026-11-19

**Instructions I ran under.** Standing role from Nadhir: Regulatory Compliance Specialist for Law 10/2025, Cabinet Resolution 134/2025, Cabinet Decision 109/2023 and Cabinet Resolution 74/2020, citation-grounded, additive only, no production access, no `/system/*` calls, no secrets. This run's routine prompt: review changes since the previous report against UAE AML/CFT obligations, then one previously not-checked item; push the report to `routine/<DATE>-compliance-specialist`, never master. The no-change shortcut did not apply because master moved. No message from dreamon arrived. `corpus/` and `citation_register.json` do not exist in the repo, so every Article is unverified (PLAUSIBLE). Not legal advice.

**Headline: RED.** #464 fixed a screening bug in which exact-name matches on the UN consolidated, OFAC, EU and UK lists were dropped for any customer whose nationality is stored as an ISO code, so screening may have missed real sanctions matches since at least 2026-10-04, and past "clear" results need a look-back.

## What I did, with evidence

- `git ls-remote origin refs/heads/master` at 01:16 UTC on 2026-11-19: `cdf38011da60cb8eadf5c5fc7290e92bf96f124a` (`cdf3801`). Previous report SHA was `9219e2623b3a3ba7e73a20e44c703ab80df7e900`.
- `git log 9219e26..origin/master`: two commits merged 2026-11-18: `1a70a53` #463 "Billing: switch Stripe off by default" and `cdf3801` #464 "Screening: compare countries as ISO codes (Amit Shah and other PEP/sanctions hits were being dropped)". 11 files, +444/-19; source: `amlkit/countries.py` (new), `amlkit/match/scorer.py`, `amlkit/billing/*`, workflow and docs.
- I read the whole non-test diff, then **reproduced the defect by running the scorer on both commits** with a synthetic exact-name case (script in my scratchpad, not committed): see the table below.
- **Full test suite on `cdf3801`:** **2998 passed, 2 skipped in 1,271 s, exit 0.** Supersedes `2945 passed, 2 skipped` on `9219e26`.
- PR list: #463 and #464 are the only PRs merged since #462. Draft #411 was updated at 01:05 UTC today; not reviewed.

## The defect (CS-27), reproduced

Customers hold ISO alpha-2 nationality codes (`validate_country_code`), but the UN, OFAC, EU and UK adapters store country names as published in the source XML (`ingest/un.py`: `COUNTRY` text; `ofac.py`: address country; `eu.py`: `countryDescription`; `uk.py`: `Nationality` text). `score_entity` compared the two as raw lower-cased strings, so "IR" never equalled "Iran (Islamic Republic of)", and every such pair was read as a country *mismatch*, which subtracts 0.20 (`P_COUNTRY_MISMATCH`). The alert threshold is 0.85, so a perfect name match scored 0.80 and was **dropped without an alert**. The UAE Local Terrorist List adapter (`ingest/eocn.py`) stores both the ISO code and the English name for each country, deliberately, so it did not have this problem.

| Case (exact name, customer nationality as ISO code) | Previous master `9219e26` | Now `cdf3801` |
|---|---|---|
| UN-style long name ("Iran (Islamic Republic of)", customer `IR`) | 0.80, dropped | 1.00, alert |
| UN-style "Syrian Arab Republic" (customer `SY`) | 0.80, dropped | 1.00, alert |
| OFAC-style "Russia" (customer `RU`) | 0.80, dropped | 1.00, alert |
| UAE-list shape (stores `IR` and `Iran`) | 1.00, alert | 1.00, alert |
| Genuinely different country (customer `IN`, listed `Pakistan`) | 0.80, dropped | 0.80, dropped (correct) |

The fix (`amlkit/countries.py`, `scorer._countries_contradict`) resolves both sides to alpha-2 and applies the penalty only when both sides resolve to codes that provably share none; any unresolved value means "cannot tell" and withholds the penalty, which errs towards alerting. I probed it: dual nationality, Arabic country text and long UN names such as "Iran (Islamic Republic of)" (which the alias table does not resolve) all correctly give no penalty.

## Findings

| ID | Severity | Status | Finding |
|---|---|---|---|
| CS-27 | **HIGH** | CONFIRMED (reproduced by execution); fixed in code by #464 | Exact-name matches on UN, OFAC, EU and UK entries that carry a country were dropped for customers with an ISO nationality code, because of a spurious 0.20 country-mismatch penalty. The UN Security Council Consolidated List is one of the two lists that carry the UAE freeze and CNMR duty (Res 74/2020 Art 15 and Art 21 as cited by EOCN; Law 10/2025 Art 17; Res 134/2025 Art 32; all unverified against the instruments), so this could have caused missed confirmed matches and therefore missed freezes. Conditions for a miss: the customer's nationality was recorded, the listed entry had a country, and nothing else (identifier match, DOB) lifted the score over 0.85. The mismatch was not visible to operators: a dropped candidate creates no alert, and `screenings` rows record counts only. |
| CS-27a | HIGH (action needed) | PLAUSIBLE | **Exposure window.** `git log -S country_mismatch` shows the penalty in this repository's history from 2026-10-04 (#407, the earliest commit that touches it in the history I can see), so the window is **at least 2026-10-04 to the deployment of #464** and may be longer. Production deployment of #464 is by the master deploy, which I cannot see. Every onboarding screening, ad-hoc `/screen` and re-screen after list refresh in that window is affected, and "clear" screening records in the evidence packs for that period are not reliable evidence. |
| CS-27b | MEDIUM | PLAUSIBLE | **Self-correction relies on the next refresh.** `rescreen_all` runs after each sanctions refresh (now every 4 hours, #461), so once #464 is deployed the next refresh re-screens every active customer and related party, and previously dropped matches raise new alerts (nothing suppresses them: no earlier alert exists, `_coverage` finds none). That is correct, but (a) it only happens if the refresh job is running, which I cannot confirm (see CS-5), and (b) the new alerts will look like ordinary "new alerts" in the digest, with no marker that they are look-back hits. Recommend the MLRO treats every alert raised by the first post-deploy refresh as a priority review, and records the incident. |
| CS-27c | MEDIUM | PLAUSIBLE (legal) | **Look-back and notification are legal judgements** I cannot make from the repo: whether a screening failure of this kind, lasting weeks, must be reported to the supervisory authority or the EOCN, and whether freezes for any newly found UN matches must be reported as late. The TFS "without delay" obligation (Law 10/2025 Art 17, Res 74/2020 Art 15, Res 134/2025 Art 32, unverified) runs from the moment a match is identified, so any match found now starts the freeze clock now, but the firm should take legal advice on the earlier window. |
| CS-27d | LOW | CONFIRMED (code) | Residual: country names the alias table does not resolve (for example UN long forms such as "Iran (Islamic Republic of)") now fail open (no penalty), which is the safe direction, but also means the country feature cannot add evidence for them. A normaliser that strips the "(...)" suffix, or storing alpha-2 codes in the UN/OFAC/EU/UK adapters as the UAE adapter does, would remove the dependency. |
| N-12 | none | positive | #463 puts Stripe billing behind a master switch (`AMLKIT_BILLING_ENABLED`, off by default, even when the Stripe keys exist). With it off, self-serve sign-up, plan limits and pending-payment gating are all inert and sign-up goes back to invite-gated or the quote-led `/apply` flow. No effect on screening, freeze, reporting or retention. If billing was live in production, the next deploy turns it off (organisations in `pending_payment` become unrestricted); a commercial decision, noted for awareness. |
| CS-13 | HIGH | PLAUSIBLE (legal), CONFIRMED (code) — **open** | Unchanged: the 24-hour freeze clock still runs from `identified_at`, set at confirmed disposition. |
| CS-14 (PNMR) | MEDIUM | CONFIRMED (code) — **open** | `SUPPORTED_REPORT_TYPES` is still `{"STR","SAR","FFR"}`. |
| 3.1 | MEDIUM | PLAUSIBLE — **open** | The AED 55,000 cash threshold (Res 134/2025 Art 21) is still organisation-configurable. |

The remaining findings from earlier reports stand as written (FATF handling, CS-4 Interpol, CS-5 deployment check, CS-18, CS-24 UAE PASS sandbox evidence, the 5-versus-8-year retention question).

## Not-checked item taken this run

"Does the scoring pipeline handle country data correctly for each list?" had not been checked before; it turned out to be the source of CS-27. Basis for the claim that the UAE list was unaffected: the `eocn.py` adapter comment states it stores both the ISO code and the English name precisely so the country penalty cannot suppress a real hit, and my probe with that shape scored 1.00 on both commits.

## BLOCKED / not checked

- **Primary legal text: BLOCKED**, unchanged. Three official hosts (`rulebook.centralbank.ae`, `uaelegislation.gov.ae`, `fatf-gafi.org`) refused this environment's egress on 2026-10-06; not retried or bypassed. To unblock: provide the official PDFs of the four instruments as `corpus/` plus `citation_register.json`.
- **When #464 reached production, and whether the 4-hour refresh and re-screen are running there:** not checkable from the repo (deploy and Cloud Scheduler state). Needs someone with project access to confirm the deploy time, the `amlkit-sanctions-refresh` schedule, and that a refresh completed after the deploy.
- **Whether any real customer or related party was actually affected:** not checkable; I did not touch production data. The way to find out is the first post-deploy re-screen, or a deliberate `rescreen_all` run by an MLRO from Admin, followed by review of the resulting alerts.
- **OFAC/EU/UK matches are not UAE freeze triggers** (per #433); their loss matters for EDD and STR/SAR judgement, not for the 24-hour freeze, so the freeze exposure is specific to the UN list.
- Not re-verified individually: CS-15, CS-16.
- Draft #411: not reviewed.
- Production: not checked.

## Files and commit

`reports/daily/2026-11-19/compliance-specialist.md` on `routine/2026-11-19-compliance-specialist`, created from `origin/master` `cdf3801`. The commit SHA is in the final reply (a commit cannot name its own SHA).
