# Lead consolidated report: 2026-11-18

## 1. Headline: AMBER (code unchanged eleven days; new MEDIUM found by the lead: an exact-name sanctions match whose DOB is one day off, or day/month swapped, raises no alert, while a DOB six years off does)
Master is `9219e2623b3a3ba7e73a20e44c703ab80df7e900` (`git ls-remote` today), unchanged since 11-07; newest PR #462. Run date 2026-11-18 UTC. All six role branches present at first fetch. New: L-158 DOB1 (lead, while verifying mlro-user's "no alert for mismatched DOB" good-practice note), L-159 EX1/EX3 (mlro-user, skeptic), L-160 EX2, L-161 GV1 (red-team). All 31 carried checks still reproduce; 4/4 new checks reproduce.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | GREEN, no change; CR-41/CR-42 carried | ls-remote SHA, PR ref | High (its branch diff vs master is large/stale, report file only matters) |
| qa-regression | done | GREEN, no change; suite not re-run (2945 passed, 2 skipped on `9219e26`) | ls-remote, empty `git log` | High |
| red-team | done | GREEN for area: Graphviz missing/failing handled; GV1 hung `dot` has no timeout (Low) | probe + evidence file; lead re-ran an equivalent | High |
| compliance-specialist | done | AMBER, no change; CS-13, CS-14 stand; corpus BLOCKED | ls-remote, PR list | High |
| mlro-user | done | AMBER: EX1 (no customer DOB/nationality beside listed), EX2 (engine jargon), EX3 (panel shows less than row) | driver + JSON/text evidence | Medium-high: findings hold, but filed "no alert for mismatched DOB and nationality" as good practice without varying DOB alone, which hid L-158 |
| skeptic | done | AMBER: EX1 CONFIRMED (raised to Medium), EX2/EX3/GV1 Low, agreed DOB/nationality suppression is not a defect | file:line | High on code reads; its "AGREE, REFUTED as defects" on the DOB rule is partly wrong (see L-158) |

## 3. Consolidated findings
CONFIRMED (lead) = reproduced today on `9219e26` (output in §5).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-158 DOB1** (new): `match/scorer.py:29-30` `P_DOB_DAY_MISMATCH=-0.25` > `P_DOB_YEAR_MISMATCH=-0.15`, year checked first (`:272-277`). Exact name, same nationality: DOB +1 day / DD-MM swap / same-year -> 0.75, **no alert**; +1 or +6 years -> 0.85, alert | **MED** | lead (from mlro-user's "good practice" note) | AGREE (as not a defect) | **CONFIRMED** (scorer + end-to-end `onboard()`) | HELD `scripts/proposals/2026-11-18-lead-dob-penalty-and-alert-facts.md` |
| **L-159 EX1+EX3**: `/alerts` row and `/alerts/{id}/panel` show the listed DOB/countries (`alerts.html:80-81,140-141`) but never the customer's (`queries.py:504-508` selects no customer DOB/nationality); panel shows neither side's DOB nor the reason text (`_alert_panel.html:17-32`) | **MED** (EX1), LOW (EX3), merged | mlro-user, skeptic | CONFIRMED, Med / Low | **CONFIRMED** (customer DOB 1981-01-02 absent from page and panel; listed DOB on page, not panel; reason on page, not panel) | HELD same proposal |
| L-160 EX2: "recall/precision", phonetic keys in reason text (`_macros.html:21-25`) | LOW | mlro-user | CONFIRMED, Low | PLAUSIBLE-to-CONFIRMED: code at `_macros.html:21-22`; not shown for an exact match in lead run (shown only on fuzzy matches, per mlro-user evidence) | Carry; template wording, fold into L-159 |
| L-161 GV1: `cases/diagram.py:110,156` `dot.pipe()` no timeout | LOW | red-team | CONFIRMED, Low | **CONFIRMED** (stub `dot` sleeping 6 s: helper blocked 6.0 s). Correction to the obvious fix: graphviz 0.21 `pipe()` has no `timeout` arg; use `subprocess.run(..., timeout=)` | HELD (red-team proposal; lead correction in its own proposal) |
| L-162 (new, lead sweep, code-read only): other 200-capped helpers with no paging/notice: mobile `/api/v1/transaction-alerts` (`mobile.py:1413`), mobile `/api/v1/adverse-media` (`mobile.py:1404`), dashboard oldest-5 transaction alerts taken from a capped, priority-ordered list (`queries.py:344-345`), per-customer transactions (`queries.py:842`, `mobile.py:1090`, cap 200) | LOW-MED (same class as L-156) | lead | — | **PLAUSIBLE** (not run) | Owed next run: add to a checks script; extend L-156 proposal |
| L-156 QU1 silent 200 alert cap (web, CSV, mobile CSV) | MED | carried | CONFIRMED | CONFIRMED (`checks_17`) | HELD 11-17 |
| L-155 TD2, L-154 N3c, L-149..L-153 | LOW / MED / as 11-17 | carried | | CONFIRMED (`checks_17`, `checks_16`) | HELD 11-16/11-17 |
| L-145..L-148; L-138; L-140, L-141; L-134..L-136; L-129..L-132; L-124..L-127; L-112, L-113 | as 11-17 | carried | | CONFIRMED (`checks_13/11/10/09/08/07/03`, 21/21) | HELD as before |
| L-143, L-144, L-142, L-139, L-137, L-133, SS4, K2, SU1, CR-41..CR-43, L-128, L-116, CS-13, CS-14, F2b, rest of 11-13 list | as 11-13 | various | as stated | No code change | Carry |
| N3b, H1; L-157 QU2 | — | roles still list | | REFUTED earlier | Closed |
| FIXED on master since 11-17 | — | | | None (master unchanged) | — |

**Severity adjudication**
- **L-158 DOB1: MEDIUM, and the skeptic/mlro-user "no alert for mismatched DOB is good practice" is overturned for DOB.** Suppressing a match where DOB *and* nationality both disagree is defensible; suppressing one where only the day differs inside the right year is not, and it is worse than for a wrong year. A DD/MM swap is the commonest date-entry fault. Not HIGH: an exact ID number still overrides, and the evidence is one synthetic entity with threshold 0.85.
- **L-159 EX1: MEDIUM (skeptic) over mlro-user's Low-Medium.** Agreed with the skeptic's reasoning and L-158 strengthens it: the customer's DOB both drives suppression and is hidden from the reviewer. EX3 merged into it (same fix).
- **GV1: LOW (all agree).** Needs a broken install.

## 4. Combined assessment
1. Eleventh day on `9219e26`; no regression; 31/31 carried checks and 4/4 new checks reproduce.
2. New and most important today: a screening false negative (L-158), found by testing the boundary of a behaviour two roles recorded as correct.
3. Open MEDIUMs now 15: L-158, L-159, L-156, L-149, L-151, L-154, L-145, L-138, L-140, L-141, L-135, L-124, L-131 (plus L-146/L-152/L-162 at LOW-MED). Every one has a HELD proposal except L-162 (owed).
4. The fix wave should now lead with L-158 (two constants) alongside L-151 + L-154 + L-156.
5. Unverifiable here: production match volumes / false-positive impact of changing DOB weights, live refresh schedule, legal corpus, goAML XSD.

## 5. Corrections I made
Scratch venv (Python 3.11.18, `requirements.txt` + `requirements-dev.txt`), repo root, `PYTHONPATH=.`; OCR not exercised. No existing file edited.
- **Owed 1 (from 11-17): carried checks re-run** (copied from lead branches into `repro_lead/`, run, removed; not re-committed):
  ```
  checks_2026_11_17 exit=0 4/4   checks_2026_11_16 exit=0 6/6   checks_2026_11_13 exit=0 5/5
  checks_2026_11_11 exit=0 2/2   checks_2026_11_10 exit=0 1/1   checks_2026_11_09 exit=0 3/3
  checks_2026_11_08 exit=0 4/4   checks_2026_11_07 exit=0 4/4   checks_2026_11_03 exit=0 2/2
  ```
- **Owed 2 (optional): capped-helper sweep** done by code read; result is L-162 (PLAUSIBLE, not run).
- **Created `repro_lead/checks_2026_11_18.py`** (exit 0 while any reproduces):
  ```
  setup variant 0: customer DOB=1981-01-02 nat=IN -> alert=None
  setup variant 1: customer DOB=1981-01-02 nat=LY -> alert=1
  setup variant 2: customer DOB=1975-03-13 nat=LY -> alert=None
  EX1   /alerts listed DOB shown=True customer DOB shown=False customer nationality 'IN' token shown=False
  EX1   panel status=200 listed DOB=False customer DOB=False
  EX3   queue row: DOB=True reason=True; panel: DOB=False reason=False
  EX2   queue shows 'precision'=False 'recall'=False (not counted)
  DOB1  scorer: +1 day=(0.75, {'dob_day_mismatch': -0.25})  DD/MM swap=(0.75, {'dob_day_mismatch': -0.25})  6 years=(0.85, {'dob_year_mismatch': -0.15})  threshold=0.85
  GV1   hung dot stub: generate_ubo_diagram returned svg after 6.0s
  4/4 reproduce
  exit=0
  ```
- **Created `repro_lead/probe_dob_onboard_2026_11_18.py`** (end-to-end `onboard()`, fresh DB per row; exit 0 = reproduces):
  ```
  1975-03-13 LY NO ALERT | 1975-03-12 LY alert 1.0 | 1981-01-02 LY alert 0.85 | 1975-03-12 IN NO ALERT
  None LY alert 1.0 | None None alert 1.0 | 1975-12-31 LY NO ALERT | 1976-03-12 LY alert 0.85
  exit=0
  ```
  Evidence file: `reports/daily/2026-11-18/evidence/lead_checks_2026_11_18_on_9219e26.txt`.
- **Created `scripts/proposals/2026-11-18-lead-dob-penalty-and-alert-facts.md`** (HELD: scorer constants, query, templates): L-158 options A/B + 3 tests, L-159 query/template diff + test, GV1 correction (graphviz 0.21 `Digraph.pipe` signature has no `timeout`; checked with `inspect.signature`).
- Code read on `9219e26`: `match/scorer.py:20-60, 222-290`, `queries.py:338-345, 480-515, 840-850, 1140-1190`, `alerts.html:80-81,140-141`, `_alert_panel.html`, `_macros.html:21-25`, `routers/alerts.py:188-207`, `routers/screening.py:178-186`, `mobile.py:1088-1094, 1400-1416`, `cases/diagram.py:95-160`.
- Not re-run: full suite (no code change), red-team's `probe_no_graphviz.py`, mlro-user's `reasons18` driver.

## 6. Decisions needed from Nadhir
1. **DOB weights (L-158):** Option A (day penalty -0.10, swap treated as no contradiction; restores ordering, tiny change) or Option B (A plus a floor so contradictions never drop an exact-name match on a mandatory list below threshold, which also reverses the country-mismatch suppression F2b). Recommend A now, B after a false-positive estimate.
2. **Alert facts side by side (L-159):** add customer DOB/nationality to the queue row and panel. Recommend yes; two query columns and template lines.
3. Carried: alert export completeness (L-156); closure with open TFS work (L-149); FX plausibility (L-152); letter folds (L-154).
4. **Fix wave:** master frozen since 11-07, 15 Mediums open. Suggested order: L-158 + L-151 + L-154 + L-156 + L-159, then L-138 + L-145..L-148, then L-149/L-150, then L-141 + L-140 + L-143.
5. Carried: single-operator rule (L-145), role change (L-146), no-MLRO recovery runbook, correct-and-refile, pre-Stripe batch L-129 + L-130 + L-134, L-135 scope, production scheduler check / L-132, L-131, corpus, goAML XSD, `github-advanced-security` 402 quota.

## 7. Next run: carried over
- Re-run `checks_2026_11_18.py`, `probe_dob_onboard_2026_11_18.py`, and `checks_2026_11_17`, `_16`, `_13`, `_11`, `_10`, `_09`, `_08`, `_07`, `_03` from their lead branches (copy into `repro_lead/`; `PYTHONPATH=.`). Exit 1 means every item in that script is fixed.
- **Owed by the lead:** L-162 — add a checks script that seeds > 200 open transaction alerts and adverse-media findings and > 200 transactions for one customer, and counts rows returned by mobile `/api/v1/transaction-alerts`, `/api/v1/adverse-media`, the customer case file, and the dashboard oldest-5; extend `2026-11-17-lead-alert-queue-cap.md` with any that reproduce.
- For the roles (suggestions only): mlro-user and skeptic, vary one identifier at a time before filing a suppression rule as good practice; red-team, a DOB-format probe (DD/MM swap, Hijri-converted dates, year-only) against `score_entity`.
- Landing order: L-158 + L-151 + L-154 + L-156 + L-159, L-138 + L-145..L-148, L-149/L-150, L-141 + L-140 + L-143, L-152/L-153/L-155/L-161/L-162, then the 11-13 order (L-129 + L-130 + L-134, L-136, L-132, L-131, L-135, L-124, L-127, L-125/L-126, L-113, L-116, L-112, CS-13, L-117, L-111, F2b, INFO-8).
