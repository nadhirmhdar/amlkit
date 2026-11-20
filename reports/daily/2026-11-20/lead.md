# Lead consolidated report: 2026-11-20

## 1. Headline: AMBER (two safe-direction screening fixes landed; the DOB inversion still silences exact-name hits, and the CS-27 look-back is still unconfirmed)
Master `bfb0253ee88acabb4d8561f6e9cac2021fa3e12d` (`git ls-remote` today), moved from `cdf3801` (11-19 lead) by #465 (PEP de-dup across lists) and #466 (DOB near-miss -0.10 for same-month / dd-mm swap). Run date 2026-11-20 UTC. All six role branches present at first fetch. Suite on `bfb0253`: 3010 passed, 2 skipped (qa-regression, code-reviewer, compliance each ran it; I did not).

Not RED: no new defect is worse than what was open yesterday, and #466 removed the commonest DOB-typo miss. Not GREEN: DB1 (exact name + month typo on the UN/UAE list = no alert, no trace) is confirmed by five roles and me, and L-164 / CS-27 look-back stay open.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | AMBER: #465/#466 correct; CR-47 PEP fold w/o identity (LOW), CR-48 month typo (INFO), CR-49 one DOB per list entry (MED, pre-existing) | full suite 3010/2, probes, adapter reads | High (CR-49 reproduced by me) |
| qa-regression | done | GREEN: 3010 passed / 2 skipped; tenant sweeps identical, 0 leaks; 30/30 flaky check | pasted counts, ls-remote | High |
| red-team | done | AMBER: PC1 PEP fold (LOW), DB1 DOB edges incl. 01-01 placeholder and month 13 (LOW); sanction-absorbed, different-country merge, XSS REFUTED | two probe scripts + evidence files | High (re-ran `probe_dob_tolerance`, same output) |
| compliance-specialist | done | AMBER: CS-28 = DB1 (MED), CS-29 = PC1 (LOW), CS-30 dismissed PEP re-alerts on other folded entity (LOW, PLAUSIBLE); CS-27 look-back open | probe table, code read; Articles unverified (no corpus) | High on code, PLAUSIBLE on law |
| mlro-user | done | AMBER: 10-customer onboarding through the UI: month typo is the only silent DOB case; PEP de-dup works (1 alert); DB2 no trace of suppressed candidates | driver JSON `log_dob20.json` | High |
| skeptic | done | RED: DB1 CONFIRMED, raised to High; PEP fold Low/Med; DB2 raised to Med; proposes an exact-name floor and a must-alert corpus | own script `dob_penalty_matrix.py` (I re-ran: exit 0) | High |

## 3. Consolidated findings
CONFIRMED (lead) = reproduced by me today; output in `reports/daily/2026-11-20/evidence/lead_checks_2026_11_20_on_bfb0253.txt`.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-166 DB1 / CS-28 / CR-48** (supersedes L-158): exact name, same birth year, month differs (or month+day, or list-side `01-01` placeholder, or month 13) → -0.25 → 0.75, **silent**; any wrong year → 0.85, alert (`scorer.py:30-35,306-314`) | **MEDIUM-HIGH** | mlro-user, red-team, compliance, code-reviewer, skeptic | CONFIRMED, High | **CONFIRMED** (`checks_2026_11_20` DB1; skeptic matrix; red-team probe; 11-18 onboard probe: `1975-12-31 LY NO ALERT`) | HELD `scripts/proposals/2026-11-20-lead-dob-floor-and-multi-dob.md` §1; **Nadhir's decision** (Option A vs B) |
| **L-167 CR-49**: UN/OFAC/EU adapters keep the first DOB, UK the last (`un.py:71-74`, `ofac.py:84-87`, `eu.py:162-165`, `uk.py:118-125`). Customer born on a listed alternate in the same year → 0.75 silent; in another year → 0.85 (zero margin) | **MEDIUM** | code-reviewer | (not judged) | **CONFIRMED** (UN fixture with two DOBs, `checks_2026_11_20` CR49) | HELD same proposal §2 |
| **L-164** (11-19): `rescreen_all` uses `nationality` only, not `nationalities` | MEDIUM | lead | — | **CONFIRMED** still (`probe_dual_nat_rescreen`: onboard 1.0, re-screen 0 alerts). Owed audit done: it is the **only** affected caller (§5) | HELD `2026-11-19-lead-country-compare-followups.md` |
| PC1 / CR-47 / CS-29: two PEP-only hits with equal name tokens and a missing country on one side fold into one "Same person" alert; DOB not compared (`engine.py:216-246`) | LOW | red-team, code-reviewer, compliance | CONFIRMED Low/Med | **CONFIRMED** (`checks_2026_11_20` PC1). PEP-only; sanctions never fold (verified by 2 roles) | HELD same proposal §3 |
| CS-30: dismissed PEP can re-alert when the kept folded entity changes | LOW | compliance | PLAUSIBLE | PLAUSIBLE (code read of `_coverage` keyed on entity id; not reproduced) | Carry; note in proposal §3 |
| DB2: sub-threshold candidates leave no record | MEDIUM (lead agrees with skeptic) | mlro-user | CONFIRMED, Med | CONFIRMED by read (screenings store counts) | HELD proposal §4; pairs with L-165 |
| Year-different = exactly 0.85 (zero margin) | LOW | red-team, skeptic | CONFIRMED | CONFIRMED (DB1 matrix) | Covered by Option B |
| DB3: alert does not name the other list | INFO | mlro-user | PARTLY REFUTED | PARTLY REFUTED (`also_listed` rendered; caption/country/DOB absent) | Folded into PC1 |
| L-163 CS-27 look-back | HIGH (operational) | compliance, skeptic, code-reviewer | open | Code FIXED by #464 (`checks_19`: IN/India 1.0); **look-back unconfirmed** and, per skeptic, must also cover DB1 | **Nadhir's decision** (§6.1) |
| L-158 DOB1 (+1 day 0.75 < +6 y 0.85) | — | lead 11-18 | | **FIXED on master by PR #466** for same-month/swap (`checks_18` DOB1 False, `checks_19` L158 False); residual moved to L-166 | Closed |
| L-163a CT1, L-163b CT2 | LOW / INFO | 11-19 | CONFIRMED | **CONFIRMED** still (`checks_19`) | HELD 11-19 |
| L-162 caps (txn queue, dashboard oldest-5 wrong, adverse media, transactions) | MEDIUM | lead | — | **CONFIRMED** 4/4 | HELD 11-19 |
| L-156 QU1 (205 open, /alerts + CSVs show 200), TD2 | MED / LOW | lead | | **CONFIRMED** 4/4 (`checks_17`) | HELD 11-17 |
| L-159 EX1+EX3, L-161 GV1 | MED / LOW | lead | | **CONFIRMED** (`checks_18` 3/4; DOB1 now fixed) | HELD 11-18 |
| L-165 scorer version on screenings, CR-45, L-160 EX2, L-154, L-149..L-153, L-145..L-148, L-138, L-140/141, L-134..L-136, L-129..L-132, L-124..L-127, L-112/113, CS-13, CS-14, 3.1, the rest of the 11-19 list | as before | various | as stated | Not re-run today (#465/#466 touch only scorer DOB, PEP fold, two template lines) | Carry |
| N3b, H1, L-157 QU2 | — | | | REFUTED earlier | Closed |

**Severity adjudication**
- **L-166 DB1: MEDIUM-HIGH.** Skeptic says High, others Medium. Same consequence as CS-27 (exact name on a freeze list, silent, no trace) but narrower trigger: needs a DOB on both sides, same year, and a month error. Above Medium because it is reachable by one keystroke and #466 shows the owner already accepts the principle; below High because a wrong-year error (the commoner large error) alerts. Raise to HIGH if DB2 stays unfixed, since then nothing can find these after the fact.
- **L-167 CR-49: MEDIUM.** Code-reviewer's "1.00 to 0.75" holds only when the alternate DOB is in the same year; in another year it scores 0.85 and alerts at zero margin. Fixing L-166 by Option B neutralises it for exact names.
- **PC1: LOW** (all agree apart from skeptic's Low/Med): PEP-only, first hit still alerts; the wrong "same person" label is the harm.
- Duplicates: DB1 = CS-28 = CR-48 = skeptic DB1 (one item, L-166). PC1 = CR-47 = CS-29. No contradictions between roles; qa-regression's GREEN is scoped to regressions/tenancy and does not conflict.

## 4. Combined assessment
1. #465/#466 are correct and move in the safe direction; no regression (3010 passed, sweeps identical).
2. The scorer still lets an additive penalty silence an exact canonical name on the UN/UAE lists (DB1, alternate DOBs, gender, true country mismatch: `1975-03-12 IN` vs listed LY = NO ALERT).
3. One floor rule for exact names (proposal §1 Option B) closes the class; per-weight tuning has now been needed three days running.
4. L-164 is the only `screen()` caller with the nationality-only pattern; the CS-27 look-back should run after the DOB and L-164 fixes or be repeated.
5. DB2 (no sub-threshold record) is why these misses are invisible; it should ship with the scorer fix.

## 5. Corrections I made
Scratch venv (Python 3.11.18, `requirements.txt` + `requirements-dev.txt`), repo root, `PYTHONPATH=.`. OCR not exercised. No existing file edited.
- **Owed (from 11-19): audit of every `screen()` caller that re-screens an existing customer for the L-164 pattern.** Read on `bfb0253`: `cases/manager.py:460-470` (onboarding, `countries=all_nats`), `:483` (UBOs at onboarding, `country=ubo.nationality`; UBOs have one `nationality` column, `db.py:324`), `match/engine.py:569-582` (**rescreen_all customers: `country=row["nationality"]` only = L-164**), `:585-600` (rescreen_all UBOs, single nationality, fine), `api/routers/ubo.py:71` and `api/mobile.py:1028` (UBO add: no country/DOB passed; that removes penalties, safe side), `routers/screening.py:94` and `mobile.py:566` (ad hoc, single country by design). There is no customer-edit or periodic-review path that re-screens (`grep "screen(" amlkit`). Result: **L-164 is the only instance**; no new checks needed beyond `probe_dual_nat_rescreen_2026_11_19.py`.
- **Owed (from 11-19): carried checks re-run on `bfb0253`:**
  ```
  checks_2026_11_19          exit=0 2/3 (CT1, CT2 reproduce; L158 reproduces=False -> fixed by #466)
  checks_l162_caps_2026_11_19 exit=0 4/4
  probe_dual_nat_rescreen    exit=0 onboard (IN+PK): [1.0]; rescreen_all alerts: 0; L164 reproduces=True
  checks_2026_11_18          exit=0 3/4 (EX1, EX3, GV1; DOB1 reproduces=False)
  probe_dob_onboard_2026_11_18 exit=1 (primary case fixed: 1975-03-13 alert 0.9); 1975-12-31 LY and 1975-03-12 IN still NO ALERT
  checks_2026_11_17          exit=0 4/4
  ```
  Not re-run today: `checks_16`, `_13`, `_11`, `_10`, `_09`, `_03`, `_08`, `_07` (no code change in their areas since `cdf3801`; diff is scorer DOB, PEP fold, two template lines). They are owed next run.
- **Role scripts re-run:** skeptic `dob_penalty_matrix.py` exit 0 (month typo 0.75 silent, +20 years 0.85 alert); red-team `probe_dob_tolerance.py` exit 0, identical to its evidence; red-team `probe_pep_collapse.py` scenarios ran (5,000 hits → 1 in 0.17 s) then crashed on a template path (script location assumption, not a product defect).
- **Created `repro_lead/checks_2026_11_20.py`** (exit 0 while any reproduces):
  ```
  DB1   month typo=0.75  wrong year=0.85  threshold=0.85
  CR49  UN entry with DOBs 1961-02-14 + 1961-09-20 stored birth_date='1961-02-14'; customer born on the listed alternate 1961-09-20 scores 0.75
  PC1   two PEP hits 'John Smith' (GB vs no country) -> 1 hit(s); also_listed=['wikidata_peps']
  3/3 reproduce   exit=0
  ```
- **Created `scripts/proposals/2026-11-20-lead-dob-floor-and-multi-dob.md`** (HELD: `scorer.py`, adapters, `engine.py`, schema): DB1 Option A/B diffs + must-alert test corpus, CR-49 multi-DOB storage, PC1 DOB check + richer `also_listed`, DB2 sub-threshold record.
- Evidence: `reports/daily/2026-11-20/evidence/lead_checks_2026_11_20_on_bfb0253.txt`.
- Commit SHA: in the final reply (a commit cannot name its own SHA).

## 6. Decisions needed from Nadhir
1. **CS-27 look-back (still urgent, unchanged from 11-19):** confirm `cdf3801`/`bfb0253` deployed and a refresh + `rescreen_all` has completed; treat those alerts as priority look-back; legal advice on reportability; one-off check of customers closed in the window. Skeptic's point: a re-screen now still misses DB1 and L-164 cases, so plan a second look-back after those fixes.
2. **DOB/exact-name policy (L-166):** Option A (set same-year penalty to -0.15, treat `01-01` as year-only) or Option B (exact canonical name never drops below threshold on penalties alone). Lead recommends **B**, with DB2 in the same PR.
3. **Land together:** L-164 + CT1/CT2 + L-166 + DB2 (+ L-165 scorer version), then CR-49 multi-DOB.
4. **PEP fold (PC1):** accept as Low, or require a non-contradicting DOB before folding and show per-list caption/country/DOB.
5. Carried: billing-off un-gates `pending_payment` orgs (CR-45), L-156 + L-162 caps, L-159, L-149, L-152, L-154, L-145/L-146, runbook, correct-and-refile, L-135, L-132/L-131, corpus, goAML XSD, `github-advanced-security` 402.

## 7. Next run: carried over
- Re-run `checks_2026_11_20.py` (this branch), `checks_2026_11_19.py`, `checks_l162_caps_2026_11_19.py`, `probe_dual_nat_rescreen_2026_11_19.py`, `checks_2026_11_18`, `checks_17`, and the ones skipped today: `checks_16`, `_13`, `_11`, `_10`, `_09`, `_03`; `checks_08`/`_07` with `AMLKIT_BILLING_ENABLED=1`. Copy them into `repro_lead/` before running (they resolve `tests/` relative to their own path).
- **Owed by the lead:** reproduce or refute CS-30 (dismissed PEP re-alert after the kept folded entity changes) with a two-refresh DB probe; check whether gender mismatch on an exact name (−0.20 → 0.80) is reachable through onboarding (QA/compliance left it untested).
- For the roles (suggestions only): a must-alert corpus run on every scorer change (skeptic); red-team's alert-panel render with `also_listed` end to end.
- Landing order: CS-27 follow-ups (L-164 + CT1 + CT2) with L-166 + DB2, then CR-49, then L-151 + L-154 + L-156/L-162 + L-159, then the rest as on 11-19.
