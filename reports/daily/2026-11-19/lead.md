# Lead consolidated report: 2026-11-19

## 1. Headline: RED (code is fixed, but a HIGH sanctions-screening miss was live until #464 and needs an owner decision on look-back; one new MEDIUM in the same control)
Master is `cdf38011da60cb8eadf5c5fc7290e92bf96f124a` (`git ls-remote` today), moved from `9219e26` (11-18 lead) by #463 (billing master switch, off by default) and #464 (compare countries as ISO codes). Run date 2026-11-19 UTC. All six role branches present at first fetch. Suite on `cdf3801`: 2998 passed, 2 skipped (qa-regression, code-reviewer and compliance ran it independently; I did not re-run it).

The miss (CS-27): before #464, an exact-name hit on a UN, OFAC, EU or UK entry was dropped (0.80 < 0.85) whenever the customer had an ISO nationality and the entry had a country name, even the same country. I reproduced it end to end: onboarding on `9219e26` raised **no alert**; `rescreen_all` on `cdf3801` over the same DB raised it (1.0). Whether and when production deployed #464 cannot be seen from the repo.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | AMBER: #464 correct; CR-44 (the miss, HIGH, fixed), CR-45 pending-payment orgs un-gated when billing is off, CR-46 bare "Korea" | full suite, alias-collision probe, scores | High |
| qa-regression | done | GREEN: 2998 passed / 2 skipped; tenant sweeps unchanged, 0 leaks | pasted counts, ls-remote | High |
| red-team | done | GREEN for area: CT1 bare "Korea" (Low), CT2 non-string country crashes (Info); billing switch holds over 13 spellings | probe scripts + evidence files | High (CT1/CT2 reproduced by me) |
| compliance-specialist | done | RED: CS-27 HIGH (UN list = freeze trigger), CS-27a window ≥ 2026-10-04, CS-27b look-back relies on refresh, CS-27c legal call, CS-27d UN long names unresolved | before/after scorer table, code reads; Articles unverified (no corpus) | High on code, PLAUSIBLE on law |
| mlro-user | done | AMBER: SC1 before/after through the UI seed (1 vs 5 alerts for 5 customers), 38 driver modes still pass | driver JSON evidence | High |
| skeptic | done | RED: CS-27 CONFIRMED High/Critical; adds bare "Congo"; withdraws its own F2b "by design" verdict; asks for scorer version on screenings and a volume estimate | own script exits 0 old / 1 new | High |

## 3. Consolidated findings
CONFIRMED (lead) = reproduced by me today; output in §5 and `reports/daily/2026-11-19/evidence/lead_checks_2026_11_19_on_cdf3801.txt`.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-163 CS-27 / CR-44 / SC1**: ISO code vs country name counted as mismatch (-0.20), exact-name UN/OFAC/EU/UK hits dropped | **HIGH** | compliance, code-reviewer, mlro-user, skeptic | CONFIRMED High/Critical | **CONFIRMED**, scorer (`IN/India` 0.80 → 1.00) and end to end (onboard on `9219e26`: 0 alerts; `rescreen_all` on `cdf3801`: alert 1.0) | **FIXED on master by PR #464**. Exposure/look-back: **needs Nadhir's decision** (§6.1) |
| **L-164** (new, lead): `rescreen_all` screens customers with `nationality` only, not `nationalities` (`match/engine.py:522-535`); onboarding uses all (`cases/manager.py` `screen(countries=all_nats)`). Dual national IN+PK vs listed `Pakistan`: onboarding 1.0, list-update re-screen 0.80, **no alert**; PK-only control alerts | **MED** | lead | — | **CONFIRMED** | HELD `scripts/proposals/2026-11-19-lead-country-compare-followups.md` |
| L-163a CT1 / CR-46: bare "Korea"→KR, "Congo"→CG, "Virgin Islands"→VI (`countries.py:60,36,96`); KP/CD/VG customer exact name 0.80 | LOW | red-team, code-reviewer, skeptic (Congo) | CONFIRMED Low | **CONFIRMED** (+ Virgin Islands, lead) | HELD same proposal |
| L-163b CT2: non-string country raises `AttributeError` | INFO | red-team | CONFIRMED Info | **CONFIRMED** | HELD same proposal |
| L-163c CS-27d: "Iran (Islamic Republic of)", "Venezuela (Bolivarian Republic of)", "Bolivia (Plurinational State of)" → None (no penalty, safe side) | LOW | compliance | CONFIRMED Low | **CONFIRMED** (`to_alpha2` run) | HELD same proposal |
| L-165: no scorer version on `screenings` rows, so the exposure window can't be listed from data | LOW-MED | skeptic | (own point) | PLAUSIBLE (design gap, code read) | Needs Nadhir's decision (schema); sketch in same proposal |
| CS-27b: first post-deploy refresh re-screens all; look-back alerts look like ordinary alerts | MED | compliance, skeptic | CONFIRMED Med | **CONFIRMED** that re-screen raises them (probe); "no marker" by code read | Operational: §6.1 |
| CR-45: switching billing off un-gates `pending_payment` orgs | INFO | code-reviewer, compliance (N-12), skeptic | AGREE | CONFIRMED by read (`load_config()` None ⇒ `check_limit` no-op) | Needs Nadhir's awareness only |
| **L-162** (owed): 200-row caps outside the screening queue | **MED** (was LOW-MED) | lead | — | **CONFIRMED** 4/4: txn-alert queue 200/250, adverse-media 200/250, customer transactions 200/250, and **dashboard "oldest 5" open transaction alerts shows 2026-02-23..27 instead of 2026-01-01..05** (wrong output) | HELD `scripts/proposals/2026-11-19-lead-capped-helpers.md` |
| L-158 DOB1 (+1 day 0.75 < +6 years 0.85) | MED | lead (11-18) | — | **CONFIRMED** still; now applies to name-country lists too (same-country IN/India: 0.75 vs 0.85). Before #464 both were masked at 0.55/0.65 | HELD 11-18 |
| L-159 EX1+EX3, L-160 EX2, L-161 GV1 | MED / LOW / LOW | as 11-18 | | CONFIRMED (`checks_18` 4/4) | HELD 11-18 |
| L-156 QU1, L-155, L-154, L-149..L-153 | as 11-17 | carried | | CONFIRMED (`checks_17` 4/4, `checks_16` 6/6) | HELD |
| L-145..L-148; L-138; L-140/141; L-134..L-136; L-129..L-132; L-124..L-127; L-112/113 | as 11-17 | carried | | CONFIRMED (`checks_13/11/10/09/03` all reproduce; `checks_08` 4/4 and `checks_07` 4/4 **only with `AMLKIT_BILLING_ENABLED=1`**) | HELD; self-serve items (SS1b, SS3b, and the rest of the pre-Stripe batch) now **DORMANT** while billing is off, not fixed |
| **F2b** (red-team 11-03, "exact name, mismatched country under threshold") | LOW policy (true mismatch only) | red-team, skeptic | **withdrawn "by design"** | Its symptom was largely CS-27; the residual (genuinely different country → 0.80) is the policy question in L-158 Option B | Carry as policy, folded into §6.2 |
| L-143, L-144, L-142, L-139, L-137, L-133, SS4, K2, SU1, CR-41..CR-43, L-128, L-116, CS-13, CS-14, 3.1, rest of 11-13 list | as before | various | as stated | No relevant code change | Carry |
| N3b, H1, L-157 QU2 | — | | | REFUTED earlier | Closed |

**Severity adjudication**
- **CS-27: HIGH, not Critical.** Skeptic says High/Critical. It is the worst defect in the series (silent loss of exact-name hits on the UN list, which carries the freeze duty), but it is fixed in code, and the automatic re-screen surfaces the dropped hits (proved). Note a matching DOB adds no score (`scorer.py` applies DOB only as a penalty), so only an exact identifier match could have rescued a dropped hit. What remains open is the operational/legal look-back, which is the owner's call, not a code severity.
- **L-164: MEDIUM.** Same control (list-update re-screen), silent, and #464 made it reachable: before, a dual national's name-format hit was dropped anyway. Narrower than CS-27 (dual nationals whose *second* nationality is the listed one, and only for listings that appear after onboarding).
- **CT1: LOW** (all agree): the real UN/OFAC strings for North Korea and DRC resolve correctly.
- **L-162 raised to MEDIUM** because T2 is wrong output on the dashboard (an MLRO is told the wrong items have waited longest), not just truncation; still needs > 200 open transaction alerts.

## 4. Combined assessment
1. Master moved for the first time in 12 days; #464 fixes a HIGH silent screening miss, verified end to end, and the look-back mechanism (re-screen) works in code.
2. The exposure itself is open: deploy time, refresh status and the count of affected customers are only visible in production (CS-5, CS-27a).
3. New MEDIUM L-164 sits in the same re-screen path and should ship with the CS-27 follow-ups.
4. No regression: 2998 passed; all carried lead checks reproduce (billing-dependent ones only with billing on).
5. Every role's test data used the same notation on both sides for six weeks; the skeptic's fixture rule (one test per adapter in that adapter's real notation) is the process fix.

## 5. Corrections I made
Scratch venv (Python 3.11.18, `requirements.txt` + `requirements-dev.txt`), repo root, `PYTHONPATH=.`; old-code runs used a `git worktree` of `9219e26`. OCR not exercised. No existing file edited.
- **Owed 1 (from 11-18): carried checks re-run on `cdf3801`** (copied from lead branches, run, removed):
  ```
  checks_2026_11_18 exit=0 4/4   checks_2026_11_17 exit=0 4/4   checks_2026_11_16 exit=0 6/6
  checks_2026_11_13 exit=0 5/5   checks_2026_11_11 exit=0 2/2   checks_2026_11_10 exit=0 1/1
  checks_2026_11_09 exit=0 3/3   checks_2026_11_03 exit=0 2/2
  checks_2026_11_08 exit=0 2/4 (billing off) ; AMLKIT_BILLING_ENABLED=1 -> 4/4
  checks_2026_11_07 exit=1 AttributeError 'NoneType'.tier_for_price (billing off) ; AMLKIT_BILLING_ENABLED=1 -> exit=0 4/4
  probe_dob_onboard_2026_11_18 exit=0 (1975-03-13 LY NO ALERT, 1981-01-02 LY alert 0.85)
  ```
- **Owed 2 (from 11-18): L-162 checks script** — created `repro_lead/checks_l162_caps_2026_11_19.py`:
  ```
  T1  transaction_alert_queue open: 200 of 250 (no total/next returned)
  T2  dashboard 'oldest' shown=['2026-02-23', ..., '2026-02-27'] true oldest=['2026-01-01', ..., '2026-01-05']
  A1  adverse_media_queue open: 200 of 250
  X1  transactions_for_customer: 200 of 250
  4/4 reproduce   exit=0
  ```
  and `scripts/proposals/2026-11-19-lead-capped-helpers.md` (HELD; new file rather than editing the 11-17 proposal).
- **Created `repro_lead/checks_2026_11_19.py`** (exit 0 while CT1/CT2/L-158 reproduce; CS-27 printed as info):
  ```
  cdf3801: CS27 IN/India=1.0 IR/'Iran, Islamic Republic of'=1.0 RU=1.0 AE=1.0 IN/Pakistan=0.8
           CT1 KP/'Korea'=0.8 CD/'Congo'=0.8 VG/'Virgin Islands'=0.8 ; CT2 AttributeError ; L158 0.75 vs 0.85 ; 3/3 exit=0
  9219e26: CS27 IN/India=0.8 IR=0.8 RU=0.8 AE=0.8 IN/Pakistan=0.8 ; L158 0.55 vs 0.65 (masked) ; 2/3 exit=0
  ```
- **Created `repro_lead/probe_lookback_rescreen_2026_11_19.py`** (two phases, two code trees, one DB): `onboard` on `9219e26` → `alerts=0` (exit 0); `rescreen` on `cdf3801` → `alerts=[(1.0, 'open')]` (exit 0). Note: `tests/test_api.py:21` re-inserts its own repo root into `sys.path`; the probe loads `tests/` from the tree under test and asserts which tree is loaded (my first run silently used the new code).
- **Created `repro_lead/probe_dual_nat_rescreen_2026_11_19.py`** (L-164): `onboard (IN+PK): [1.0]`, `rescreen_all ... 'alerts': 0`, `L164 reproduces=True exit=0`; control with PK only: `rescreen_all ... 'alerts': 1`.
- **Created `scripts/proposals/2026-11-19-lead-country-compare-followups.md`** (HELD: `countries.py`, `scorer.py`, `engine.py`, schema): CT1 diff + tests, CT2 guard, CS-27d option, L-164 diff + test, L-165 scorer-version sketch.
- Evidence: `reports/daily/2026-11-19/evidence/lead_checks_2026_11_19_on_cdf3801.txt`.
- Code read on `cdf3801`: `match/scorer.py:219-300`, `match/engine.py:225-275, 496-562`, `cases/manager.py:440-475` (old tree), `countries.py:1-131`, `ingest/{un,ofac,eu,uk}.py` country fields, `queries.py:335-350, 900-945, 1184-1215`, `mobile.py:1084-1096, 1400-1416`.
- Not re-run: full suite (three roles ran it on `cdf3801`), role probes other than reproducing CT1/CT2/CS-27 myself.

## 6. Decisions needed from Nadhir
1. **CS-27 look-back (urgent).** (a) Confirm `cdf3801` is deployed and that a sanctions refresh + `rescreen_all` has completed since (Cloud Run revision time, `amlkit-sanctions-refresh` last success). (b) Treat every alert raised by that first post-deploy re-screen as a priority look-back, and record the incident. (c) Take legal advice on whether the window (≥ 2026-10-04 to deploy) is reportable and whether any UN match found now needs a late-freeze note. (d) Customers closed during the window are not re-screened by `rescreen_all` (active only); decide whether they need a one-off check.
2. **Land the follow-ups together:** L-164 (re-screen uses all nationalities) + CT1/CT2 in one small PR; consider L-165 (scorer version on screenings) so the next scorer fix can list what to redo.
3. **DOB weights (L-158)** still open; now more visible, since name-format lists no longer mask it. Recommendation unchanged: Option A now.
4. **Billing off (#463):** any `pending_payment` orgs in production are now un-gated (CR-45); decide whether that is acceptable.
5. Carried: L-156 + L-162 caps (now one fix), L-159 alert facts, L-149, L-152, L-154, L-145/L-146, runbook, correct-and-refile, L-135, L-132/L-131, corpus, goAML XSD, `github-advanced-security` 402.

## 7. Next run: carried over
- Re-run `checks_2026_11_19.py`, `checks_l162_caps_2026_11_19.py`, `probe_dual_nat_rescreen_2026_11_19.py` (this branch) and `checks_2026_11_18`, `probe_dob_onboard_2026_11_18`, `checks_17`, `_16`, `_13`, `_11`, `_10`, `_09`, `_03` from their lead branches; `checks_08` and `checks_07` with `AMLKIT_BILLING_ENABLED=1` (billing items are dormant, not fixed). Exit 1 = every item in that script fixed.
- `probe_lookback_rescreen_2026_11_19.py` only needs re-running if the scorer or `rescreen_all` changes.
- **Owed by the lead:** check every other `screen()` caller that re-screens an existing customer (periodic review, mobile rescreen, customer edit, UBO path) for the same `nationality`-only pattern as L-164, and add any that reproduce to a checks script.
- For the roles (suggestions only): one fixture per adapter in that adapter's real country notation (skeptic's rule); red-team, the DOB-format probe still pending from 11-18.
- Landing order: CS-27 follow-ups (L-164 + CT1 + CT2) and L-158, then L-151 + L-154 + L-156/L-162 + L-159, then L-138 + L-145..L-148, L-149/L-150, L-141 + L-140 + L-143, the rest as on 11-18.
