# code-reviewer daily report, 2026-11-20

**Instructions I ran under:** scheduled routine "groAML daily: code-reviewer" (fired 2026-11-20 00:46 UTC). Review current origin/master, the changes since the SHA in my previous report, and PRs opened or updated since. Standing rules: no production access, no `/system/*` calls, no secrets, local test data only, never push to master, stop after delivering.

**Headline: AMBER.** origin/master moved from `cdf38011da60cb8eadf5c5fc7290e92bf96f124a` to `bfb0253ee88acabb4d8561f6e9cac2021fa3e12d` (2 screening PRs, #465 and #466); the suite is green and both changes do what they say, but #465 can fold two different politically exposed people into one alert, and I found a pre-existing gap that stores only one date of birth per list entry.

**What I did (evidence):**
- `git ls-remote origin refs/heads/master` returned `bfb0253…`; `git log cdf3801..origin/master` lists #465 "one hit and one alert per politically exposed person across lists" and #466 "a DOB typo or dd/mm swap no longer silences an exact name match". Both merged 2026-11-19; 6 files, +229/-4.
- Full suite on `bfb0253` in a throwaway worktree (Linux, scratchpad venv, Python 3.13): **3010 passed, 2 skipped**, 12 min 49 s (previous baseline 2998 passed, 2 skipped).
- Read the full `amlkit/` diff.
- **Probe of `collapse_pep_duplicates`** with constructed hits (no network): sanctions hits are never merged (a PEP plus a UN-sanctioned entry with the same name stays 2 hits; a PEP that also carries the sanction topic stays 2 hits); three entries for one person on two lists collapse to 1; same name and different countries (Egypt vs India) stay 2; same name and same country merge to 1; same name with no country on one side merges to 1; swapped token order merges to 1.
- **Probe of the DOB rule** with exact name "Amit Shah" and customer DOB 1970-03-05, threshold 0.85: same month other day 0.90 (alert); day/month swapped 0.90 (alert); other month same day 0.75 (dropped); other month other day 0.75 (dropped); year off by one 0.85 (alert, exactly at the threshold); year-only or day-missing candidate 1.00.
- Read the ingest adapters to see which dates of birth reach the scorer.

**Findings:**
- CR-47 (LOW, CONFIRMED at function level): `collapse_pep_duplicates` keys on the sorted name tokens plus "countries do not contradict", and `_countries_contradict` returns False when either side has no country or an unresolved one. Two different people with the same name tokens in the same country, or where one entry lacks a country, are therefore folded into one hit, and the survivor is the higher-scoring one. Date of birth is not part of the key. If an MLRO dismisses that one alert as a false positive, the other person is never raised, because the dismissed alert also covers later re-screens of that entity pair. The screen page text "Same person also listed on" asserts an identity the code did not establish. Impact is limited to PEP-only hits (enhanced due diligence), never sanctions or freeze obligations.
- CR-48 (INFO, CONFIRMED): the new near-miss rule covers a different day in the same month and a day/month swap, but not a one-digit month typo: an exact-name hit with DOB 1970-04-05 against 1970-03-05 still scores 0.75 and is dropped. Judgement call, not a defect.
- CR-49 (MEDIUM, CONFIRMED in code, pre-existing): the scorer receives one `birth_date` per list entry (`cand_birth_date=row["birth_date"]`), and the UN, OFAC and EU adapters take only the first date of birth element they find (the UK adapter keeps one). Sanctions lists commonly give several or approximate dates of birth per person. A customer whose date of birth equals a listed alternate date takes the -0.25 mismatch penalty with an exact name (1.00 to 0.75) and is dropped. Magnitude is unknown without production data and the real list files; fix by storing all dates of birth and using the best-matching one.
- Carried, unchanged: CR-41 (LOW) and CR-42 (PLAUSIBLE) from 2026-11-08 are still open; CR-44 was fixed by #464 and its look-back advice from 2026-11-19 still stands; CR-4 (MEDIUM, unmerged #417; not re-checked), CR-13 and CR-18 (LOW; not re-checked), CR-2/3/5/17, CR-19 to CR-23, CR-28, CR-29, CR-33 to CR-37, CR-39, CR-43, CR-45, CR-46 (INFO).

**BLOCKED / not checked:**
- Nothing blocked.
- I did not load the real UN/OFAC/EU/UK files, so I cannot say how many entries carry several dates of birth (CR-49) or how often CR-47 would trigger.
- I did not re-measure `alert_queue` performance (CR-13) or the effect of the collapse on alert volume.
- CI status for `bfb0253` was not looked up (standing rule: no CI re-checks).

**Files / commits:** `reports/daily/2026-11-20/code-reviewer.md`; commit SHA in the final reply.
