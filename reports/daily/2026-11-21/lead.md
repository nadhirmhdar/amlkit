# Lead consolidated report: 2026-11-21

## 1. Headline: AMBER (master unchanged; two new suppression defects confirmed end to end: a dismissed PEP hides a second same-name PEP, and a gender mismatch silences an exact sanctions name)
Master `bfb0253ee88acabb4d8561f6e9cac2021fa3e12d` (`git ls-remote` today), same as the 11-20 lead report; no PR opened or merged since #466 (roles' ls-remote of `refs/pull/*`; compliance notes draft #411 docs-only touched today, not reviewed). Run date 2026-11-21 UTC. All six role branches present at first fetch. Not a "no change" day: red-team (PC1b) and mlro-user (ED1-ED3) raised new findings.

Not RED: no new item is worse than the open DB1 / CS-27 look-back, and PC1b is PEP-only (EDD, not a freeze). Not GREEN: L-166 DB1 is still open and today adds a second same-class case (GEN1).

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done (no-change shortcut) | GREEN no change; carries CR-47/48/49 etc. | ls-remote only, by design | High |
| qa-regression | done (no-change shortcut) | GREEN no change; last suite on `bfb0253` 3010 passed / 2 skipped | ls-remote, git log | High |
| red-team | done (short) | AMBER: PC1b absorbed PEP never alerts after primary dismissed; primary flip = noise | code read only, no probe | High (I reproduced PC1b end to end) |
| compliance-specialist | done (no-change) | AMBER unchanged; CS-27 look-back, CS-28, CS-13, CS-14 stand; corpus still BLOCKED | ls-remote; law PLAUSIBLE | High on status |
| mlro-user | done | AMBER: ED1 high-risk PEP onboarded with SoW/SoF/purpose empty; ED2 EDD is a label; ED3 no EDD-outstanding reminder | driver JSON `log_edd21.json` | High (code read confirms, with a refinement) |
| skeptic | done | RED carried; PC1b raised to Medium; ED1/ED2 Medium; names the "suppression without positive evidence" principle | code reads with line refs, no new script | High |

## 3. Consolidated findings
CONFIRMED (lead) = reproduced by me today; output in `reports/daily/2026-11-21/evidence/lead_checks_2026_11_21_on_bfb0253.txt`.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-166 DB1 / CS-28 / CR-48**: exact name, same year, month differs → 0.75 silent; wrong year 0.85 alerts | **MEDIUM-HIGH** | 5 roles (11-20) | CONFIRMED High | **CONFIRMED** (`checks_20` DB1 0.75 vs 0.85; `probe_dob_onboard_18`: `1975-12-31 LY NO ALERT`) | HELD `2026-11-20-lead-dob-floor-and-multi-dob.md` §1; **Nadhir's decision** |
| **L-170 GEN1 (new, owed from 11-20)**: exact sanctions name, customer gender female vs listed male, no DOB/country → 0.80, no alert, via `cases.manager.onboard` (`scorer.py:36,316-318`) | **MEDIUM** (same class as L-166) | lead | — | **CONFIRMED** (`checks_21` GEN1: G-1 female 0 alerts, G-2 male 1 alert) | HELD `2026-11-21-lead-pep-fold-coverage-and-edd-gate.md` §5; closed by L-166 Option B |
| **L-168 PC1b**: same-name PEP absorbed into `also_listed` never gets an alert or `_coverage` row; dismissing the primary hides it on every later run (`engine.py:332` collapse before `:419` coverage) | **MEDIUM** | red-team | CONFIRMED by code, Low-Med → Med | **CONFIRMED** end to end (`checks_21` PC1b: dismissed A, `rescreen_all` alerts 0, alerts ever on B = 0) | HELD new proposal §1 (fold needs identity signal + per-member coverage) |
| **L-169 ED1/ED2**: high computed risk (PEP + FATF = 115, "EDD required") onboards with SoW/SoF/purpose empty; no EDD approval record | **MEDIUM** | mlro-user | CONFIRMED Med/Med | **CONFIRMED, refined**: web guard exists but keys on the optional *declared* `risk_level` form field (`routers/customers.py:150-155`), not the computed rating; `manager.onboard` and `api/mobile.py` have no check (mobile has no SoW/SoF inputs, grep) | HELD new proposal §4; **Nadhir's decision** (warn vs block) |
| ED3: no EDD-outstanding reminder | LOW | mlro-user | CONFIRMED Low | CONFIRMED (follows from ED2) | Part of proposal §4 |
| CS-30 / primary flip: absorbed entity re-alerts when the kept one leaves | LOW | compliance (11-20), red-team | PLAUSIBLE, noise | **CONFIRMED** (owed; `checks_21` CS30: A delisted → B alert opened). Extra alert, not a miss | HELD new proposal §2 |
| **L-171 DL1 (new, side observation)**: delisting deletes the dismissed alert row (`db.py:366` ON DELETE CASCADE, `loader.py:158-168`); only the audit row remains | LOW (decision) | lead | — | **CONFIRMED** (`DL1 false_positive alert rows left: 0; alert.* audit rows: 1`). Documented in code as intended; true_positive/freeze case not checked | **Nadhir's decision** (proposal §3) |
| L-167 CR-49 multi-DOB (first/last only) | MEDIUM | code-reviewer | — | **CONFIRMED** still (`checks_20` CR49) | HELD 11-20 §2 |
| PC1 / CR-47 / CS-29 fold w/o identity | LOW (now the root of L-168) | 3 roles | CONFIRMED | **CONFIRMED** (`checks_20` PC1) | HELD 11-20 §3 |
| L-164 rescreen uses `nationality` only | MEDIUM | lead | — | **CONFIRMED** (`probe_dual_nat_rescreen_19`: L164 True) | HELD 11-19 |
| L-163a CT1, L-163b CT2 | LOW / INFO | lead | | **CONFIRMED** (`checks_19` 2/3) | HELD 11-19 |
| L-162 caps | MEDIUM | lead | | **CONFIRMED** 4/4 | HELD 11-19 |
| L-156 QU1, TD2 | MED / LOW | lead | | **CONFIRMED** 4/4 (`checks_17`) | HELD 11-17 |
| L-159 EX1+EX3, L-161 GV1 | MED / LOW | lead | | **CONFIRMED** (`checks_18` 3/4) | HELD 11-18 |
| CL1, CL2, TD1, TX1, TX2, N3c | as before | | | **CONFIRMED** 6/6 (`checks_16`) | HELD earlier |
| SO1, RL1, RL2, RL2d, RL3 | as before | | | **CONFIRMED** 5/5 (`checks_13`) | HELD earlier |
| RP1, RP1g; MA1; SS5, RT1, RT2 | as before | | | **CONFIRMED** (`checks_11` 2/2, `_10` 1/1, `_09` 3/3) | HELD earlier |
| SS1b, SS3b, CS24, CS5d; BL1, CR1-CR3 (billing on) | as before | | | **CONFIRMED** (`checks_08` 4/4, `_07` 4/4, `AMLKIT_BILLING_ENABLED=1`) | HELD earlier |
| UBO1b, N8b | as before | | | **CONFIRMED** (`checks_03` 2/2) | HELD earlier |
| L-163 CS-27 look-back | HIGH (operational) | compliance, skeptic | open | Code fixed by #464; deployment + re-screen **unconfirmed** (no production access) | **Nadhir's decision** |
| DB2, L-165, CR-45, L-160, L-154, L-149..L-153, L-145..L-148, older list | as before | | | Not re-run (no code change; no script for them) | Carry |
| L-158 DOB1 | — | | | FIXED by #466 (`checks_18` DOB1 False, `checks_19` L158 False) | Closed (re-confirmed) |

**Severity adjudication**
- **L-168 PC1b: MEDIUM**, with the skeptic over red-team's Low-Medium: it converts a labelling error (PC1) into a permanent miss after one correct dismissal, and my run shows it through the real `rescreen_all` path. Not higher: PEP-only, no freeze obligation, and the first PEP hit still alerts.
- **L-170 GEN1: MEDIUM**, not MEDIUM-HIGH like DB1, because it needs a gender on the list record (EU, UK, UN, OFAC carry it; CIA, EOCN do not) and no DOB or country on the customer; a matching DOB would offset it. Same fix as L-166.
- **L-169 ED1/ED2: MEDIUM** (all agree). Skeptic's "no check refuses" is slightly overstated: a web check exists but is keyed on the wrong input.
- Duplicates: PC1b = red-team "absorbed entity stays hidden"; CS-30 = red-team "primary flip". ED1-ED3 join the lifecycle-precondition cluster (CL1, SO1, MA1). No contradictions; the no-change GREENs are scoped to "no code moved".

## 4. Combined assessment
1. Master is unchanged for two days; every carried lead check still reproduces (13 scripts, outputs in evidence), and #466's fix holds.
2. Today's two new screening items (PC1b, GEN1) and DB1/CS-27 share one root, as the skeptic says: suppression on missing or weak evidence. One exact-name floor plus "fold only with an identity signal" closes four items.
3. EDD (ED1/ED2) is a real gap for a PEP/high-risk tool: the existing guard checks a declared field nobody has to fill.
4. Delisting silently removes decided alert rows (DL1); intended per code comment, but it should be an owner decision given record-keeping.
5. The constraint is landing, not finding: nothing has merged since 11-19.

## 5. Corrections I made
Scratch venv (Python 3.11.18, `requirements.txt` + `requirements-dev.txt`), repo root, `PYTHONPATH=.`. OCR not exercised. No existing file edited.
- **Owed (11-20): CS-30 two-refresh DB probe** → done, CONFIRMED (re-alert). **Owed (11-20): gender mismatch via onboarding** → done, CONFIRMED (GEN1). Both in new `repro_lead/checks_2026_11_21.py`:
  ```
  PC1b  onboarding alerts: [(1, 1)]  (A=1, B=2)
  PC1b  alert 1 disposed -> false_positive
  PC1b  re-screen: hits=[(1, 'us_cia_world_leaders')] also_listed=[2] rescreen_all={'screened': 1, 'alerts': 0, 'unscreenable': 0}; alerts ever on B=0
  CS30  after A delisted: hits=[(2, 'wikidata_ministers')] rescreen_all={'screened': 1, 'alerts': 1, 'unscreenable': 0}; alerts on B=[(1, 'open')]
  DL1   false_positive alert rows left after delisting A: 0; alert.* audit rows: 1
  GEN1  G-1 gender=female hits=0 alerts=0
  GEN1  G-2 gender=male hits=1 alerts=1
  3/3 reproduce   exit=0
  ```
- **Owed (11-20): carried checks re-run on `bfb0253`**, all exit 0 except the two noted: `checks_20` 3/3, `checks_19` 2/3 (L158 fixed), `checks_l162_caps_19` 4/4, `probe_dual_nat_rescreen_19` L164 True, `checks_18` 3/4 (DOB1 fixed), `probe_dob_onboard_18` exit 1 by design (primary case fixed; `1975-03-12 IN` and `1975-12-31 LY` still NO ALERT), `checks_17` 4/4, `checks_16` 6/6, `checks_13` 5/5, `checks_11` 2/2, `checks_10` 1/1, `checks_09` 3/3, `checks_08` 4/4 and `checks_07` 4/4 (billing on), `checks_03` 2/2. `probe_lookback_rescreen_19` needs CLI args (mode, dir) and was not run; it is a look-back helper, not a defect check. Scripts were copied into `repro_lead/` for the run and removed afterwards (not committed; they live on their own lead branches).
- **Created `scripts/proposals/2026-11-21-lead-pep-fold-coverage-and-edd-gate.md`** (HELD): PC1b per-member coverage diff, CS-30, DL1 options, ED1/ED2 warn-vs-block design, GEN1 → L-166 Option B.
- Evidence: `reports/daily/2026-11-21/evidence/lead_checks_2026_11_21_on_bfb0253.txt`.
- Commit SHA: in the final reply (a commit cannot name its own SHA).

## 6. Decisions needed from Nadhir
1. **CS-27 look-back (unchanged, urgent):** confirm `bfb0253` is deployed and a refresh + `rescreen_all` has run; plan a second look-back after the DB1/GEN1/L-164 fixes.
2. **Exact-name floor (L-166 + L-170):** Option B (exact canonical name never drops below threshold on DOB/gender/country penalties alone) closes DB1, GEN1 and the true-country-mismatch case. Lead recommends B with DB2 in the same PR.
3. **PEP fold (L-168 + PC1 + CS-30):** fold only with a corroborating identity signal, and scope a dismissal to the entities shown in it.
4. **EDD (L-169):** warn (`edd_outstanding` flag) or block (`pending_edd` until an MLRO records approval, date and evidence), keyed on the computed `requires_edd`, in web and mobile.
5. **Delisting (L-171):** keep the cascade-delete of decided alerts, or soft-delist entities so case-file decisions survive.
6. Carried: CR-45, L-156 + L-162 caps, L-159, L-149, L-152, L-154, L-145/L-146, runbook, correct-and-refile, L-135, L-132/L-131, corpus, goAML XSD, `github-advanced-security` 402.

## 7. Next run: carried over
- Re-run `checks_2026_11_21.py` and `checks_2026_11_20.py` (this branch and the 11-20 lead branch), plus `checks_19`, `checks_l162_caps_19`, `probe_dual_nat_rescreen_19`, `checks_18`, `checks_17` (copy into `repro_lead/` first). Older checks only if master moves in their areas.
- **Owed by the lead:** check whether a delisted `true_positive` alert with a `freeze_obligations` row is also cascade-deleted (DL1 high-impact case); check whether the 11-20 proposal's multi-DOB change (CR-49) interacts with PC1b's DOB-corroboration rule.
- For the roles (suggestions only): mlro-user's `edd21` driver against mobile onboarding; skeptic's lifecycle-precondition table.
- Landing order: CS-27 follow-ups (L-164 + CT1 + CT2) with L-166/L-170 + DB2, then L-168 + CR-49, then L-169, then L-151 + L-154 + L-156/L-162 + L-159, then the rest.
