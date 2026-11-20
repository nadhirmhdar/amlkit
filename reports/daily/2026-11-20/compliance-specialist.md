# Compliance specialist — daily report 2026-11-20

**Instructions I ran under.** Standing role from Nadhir: Regulatory Compliance Specialist for Law 10/2025, Cabinet Resolution 134/2025, Cabinet Decision 109/2023 and Cabinet Resolution 74/2020, citation-grounded, additive only, no production access, no `/system/*` calls, no secrets. This run's routine prompt: review changes since the previous report against UAE AML/CFT obligations, then one previously not-checked item; push the report to `routine/<DATE>-compliance-specialist`, never master. The no-change shortcut did not apply because master moved. No message from dreamon arrived. `corpus/` and `citation_register.json` do not exist in the repo, so every Article is unverified (PLAUSIBLE). Not legal advice.

**Headline: AMBER.** Two further screening changes (#465, #466) reduce missed matches and noise without touching sanctions logic, but the scorer still has a gap I reproduced: an exact-name match with the right birth year but the wrong month is dropped, while the same match with the wrong birth year alerts. The RED look-back from CS-27 (2026-11-19) remains open pending confirmation of the deployment.

## What I did, with evidence

- `git ls-remote origin refs/heads/master` at 01:16 UTC on 2026-11-20: `bfb0253ee88acabb4d8561f6e9cac2021fa3e12d` (`bfb0253`). Previous report SHA was `cdf38011da60cb8eadf5c5fc7290e92bf96f124a`.
- `git log cdf3801..origin/master`: two commits merged 2026-11-19: `a524fba` #465 "one hit and one alert per politically exposed person across lists" and `bfb0253` #466 "a DOB typo or dd/mm swap no longer silences an exact name match". 6 files, +229/-4; source: `amlkit/match/scorer.py`, `amlkit/match/engine.py`, and two template lines that show "Also listed on".
- I read the whole non-test diff and ran the new scorer against exact-name cases with different birth dates (probe script in my scratchpad, not committed; results below).
- **Full test suite on `bfb0253`:** **3010 passed, 2 skipped in 967 s, exit 0.** Supersedes `2998 passed, 2 skipped` on `cdf3801`.
- PR list: #465 and #466 are the only PRs merged since #464. Draft #411 was updated at 01:00 UTC today; not reviewed.

## Review of the two commits

**#466 DOB near-miss (`scorer.py`).** A new `P_DOB_NEAR_MISS = -0.10` applies when two birth dates share the year and either share the month or have day and month swapped (03-12 versus 12-03); it replaces the harsher `P_DOB_DAY_MISMATCH = -0.25` in that case. With the alert threshold at 0.85, an exact name match with such a DOB now scores 0.90 and alerts, where it scored 0.75 and was dropped. The adjustment is recorded in the alert's score detail as `dob_near_miss`. This moves in the safe direction (more matches surfaced) and the evidence stays in the record.

**#465 PEP de-duplication (`engine.py`, `collapse_pep_duplicates`).** Hits for the same politically exposed person on several lists (CIA World Leaders, Wikidata) are folded into one alert, kept as the highest score (ties: dataset, then entity id), with the others stored under `detail["also_listed"]` and shown in the alert panel and screen page. The fold applies only when both hits are PEP-only (`is_pep and not is_sanction`), have identical canonical name tokens, and their countries do not contradict. **Sanctions hits are never merged**, so each list keeps its own alert and its own freeze obligation; `onboard()`'s `sanctions_hit` and the freeze scope gate (`sanctions_scope.py`) are untouched. I found no way for this change to hide a sanctions match.

## Probe: exact name, different birth dates (`bfb0253`, threshold 0.85)

| Customer DOB vs listed DOB | Score | Result | Adjustment |
|---|---|---|---|
| identical | 1.00 | alert | none |
| day and month swapped (1980-03-12 vs 1980-12-03) | 0.90 | alert | `dob_near_miss` -0.10 |
| same year and month, different day (03-12 vs 03-28) | 0.90 | alert | `dob_near_miss` -0.10 |
| **same year, different month, same day (03-12 vs 08-12)** | **0.75** | **dropped** | `dob_day_mismatch` -0.25 |
| different year, same month and day (1980 vs 1981) | 0.85 | alert | `dob_year_mismatch` -0.15 |
| **completely different DOB (1980-03-12 vs 1955-09-30)** | **0.85** | **alert** | `dob_year_mismatch` -0.15 |

## Findings

| ID | Severity | Status | Finding |
|---|---|---|---|
| CS-28 | MEDIUM | CONFIRMED (reproduced by execution) | The DOB penalties are inverted. A same-year, different-month-or-day mismatch (-0.25) is penalised harder than a wrong year (-0.15), so an exact-name candidate whose birth year is right but month is off (a one-digit typo) is dropped without an alert, while the same candidate with a completely different birth date raises one. #466 repaired only the swapped-day/month and same-month cases; the rest of the same-year family remains silent. For UN-list and UAE-list entries this is a missed-match path in the freeze regime (Law 10/2025 Art 17, Res 74/2020 Art 15, Res 134/2025 Art 32, unverified), and EOCN's own matching guidance treats a partial match, where an identifier differs but cannot be ruled out, as a case to suspend and report rather than to ignore. Suggested fix: make the same-year, different-month-or-day penalty no harsher than the year penalty (for example -0.10 to -0.15), or never let a DOB difference alone take an exact canonical name match below the threshold for the UN and UAE lists. |
| CS-27 | HIGH | **Open (look-back)** | The country-comparison defect fixed by #464 (reports 2026-11-19): exact-name matches on UN, OFAC, EU and UK entries were dropped for customers with an ISO nationality code. Deployment of #464 to production and a completed post-deploy re-screen are still unconfirmed from the repo. |
| N-13 | none | positive | #466 reduces missed matches for the most common DOB error shapes (swap, same-month typo), at the cost of alerts that an operator must dismiss; the reason is visible in the alert detail. |
| N-14 | none | positive | #465 cuts duplicate PEP alerts without touching sanctions lists. |
| CS-29 | LOW | PLAUSIBLE | PEP fold can hide a second person. Two different people with identical canonical name tokens, no contradicting country (including a missing country on either side) and both PEP-only are shown as one alert; `also_listed` records dataset, caption, entity id and score but not date of birth or position, so an operator may not see that they differ. Common names in the same country are the realistic case. Suggest adding birth date and position to `also_listed` and not folding when the DOBs both exist and differ. |
| CS-30 | LOW | PLAUSIBLE | Possible re-alert of a dismissed PEP. Standing-record suppression (`_coverage`) is keyed on the kept entity id. If a list update changes which of the folded entities scores highest, a PEP dismissed as a false positive on entity X can raise a new alert on entity Y. Low volume, but it can bring back a resolved case; keying suppression on the folded identity would avoid it. |
| CS-13 | HIGH | PLAUSIBLE (legal), CONFIRMED (code) — **open** | Unchanged: the 24-hour freeze clock still runs from `identified_at`, set at confirmed disposition. |
| CS-14 (PNMR) | MEDIUM | CONFIRMED (code) — **open** | `SUPPORTED_REPORT_TYPES` is still `{"STR","SAR","FFR"}`. |
| 3.1 | MEDIUM | PLAUSIBLE — **open** | The AED 55,000 cash threshold (Res 134/2025 Art 21) is still organisation-configurable. |

The remaining findings from earlier reports stand as written (FATF handling, CS-4 Interpol, CS-5 deployment check, CS-18, CS-24 UAE PASS sandbox evidence, the 5-versus-8-year retention question).

## Not-checked item taken this run

"How do the scorer's other contradicting-feature penalties (DOB, gender) behave against exact name matches?" had not been checked after the country defect surfaced. Result: CS-28 above. Gender mismatch (-0.20) and country mismatch (-0.20) on an exact name still take it to 0.80 and drop it; I did not test gender in this run, so I treat that as open rather than verified.

## BLOCKED / not checked

- **Primary legal text: BLOCKED**, unchanged. Three official hosts (`rulebook.centralbank.ae`, `uaelegislation.gov.ae`, `fatf-gafi.org`) refused this environment's egress on 2026-10-06; not retried or bypassed. To unblock: provide the official PDFs of the four instruments as `corpus/` plus `citation_register.json`.
- **Production deployment of #464, #465 and #466, and the 4-hour refresh and re-screen:** not checkable from the repo.
- **Gender-mismatch penalty against exact name matches:** not tested this run (see above).
- **Whether any real customer was affected by CS-27 or CS-28:** not checked; no production data was touched.
- Not re-verified individually: CS-15, CS-16.
- Draft #411: not reviewed.
- Production: not checked.

## Files and commit

`reports/daily/2026-11-20/compliance-specialist.md` on `routine/2026-11-20-compliance-specialist`, created from `origin/master` `bfb0253`. The commit SHA is in the final reply (a commit cannot name its own SHA).
