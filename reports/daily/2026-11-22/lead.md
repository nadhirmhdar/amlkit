# Lead consolidated report: 2026-11-22

## 1. Headline: AMBER (no app code changed; CI confirms the CS-27 fix deployed 11-18; new: delisting deletes a confirmed UN match and its four-eyes record, leaving the freeze orphaned)
Master `c42c77ce59179c86b3ed5107b78e65e227326c0d` (`git ls-remote`, today). It moved from `bfb0253` (11-21 lead report) by one commit, #467 "Deploy with --no-cpu-throttling" (`.github/workflows/source-canary.yml` +19, `CLAUDE.md` 1 line, no `amlkit/` or `tests/` change). Run date 2026-11-22 UTC. All six role branches were there on the first fetch.

Not RED: nothing new is worse than the open DB1 or the CS-27 look-back. Not GREEN: DB1, GEN1, PC1b and ED1 are still open, and today adds DL1b (MEDIUM) and EV1 (LOW).

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | GREEN: #467 correct (flag in the only deploy command, YAML parses); CR-50 stale "CPU throttled" comments; CR-51 revision overlap (plausible) | diff read + PyYAML parse | High (CR-50 lines checked) |
| qa-regression | done | GREEN: 2988 pass + 22 `test_entrypoint` fails caused by the session's `rm-guard` PATH wrapper (24/24 with a clean PATH on both SHAs) = 3010 / 2 skipped; tenant sweeps unchanged | commands + counts, same failure shown on the old SHA | High (total built from two runs, as QA says) |
| red-team | done (short) | AMBER: PC1/PC1b reproduced end to end via ad-hoc screen; #467 no security impact | script + evidence txt on branch | High (agrees with my `checks_21`) |
| compliance-specialist | done | AMBER: CI shows #464 (CS-27 fix) deployed 2026-11-18 ~14:36 UTC; look-back still open; N-15/N-16 positive | Actions run metadata; law PLAUSIBLE (corpus BLOCKED) | High: I checked the CI run list myself |
| mlro-user | done | RED: EV1 "Important Notice" dialog + grey overlay printed on page 1 of the evidence PDF; EV2 no XML declaration; EV3 Arabic intact | rendered PNGs, PDFs, driver JSON | High on the mechanism; severity overstated |
| skeptic | done | RED carried; EV1 real but limited to unacknowledged sessions (High → Low/Med); PC1b Med; "nobody tests print/PDF" | code reads with line refs, no new script | High |

## 3. Consolidated findings
"CONFIRMED (lead)" = reproduced by me today on `c42c77c`; output in `reports/daily/2026-11-22/evidence/lead_checks_2026_11_22_on_c42c77c.txt`.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-166 DB1 / CS-28 / CR-48**: exact name, same-year different-month DOB → 0.75, no alert | **MEDIUM-HIGH** | 5 roles | CONFIRMED High | **CONFIRMED** (`checks_20` DB1; `probe_dob_onboard_18`: `1975-12-31 LY NO ALERT`) | HELD `2026-11-20-lead-dob-floor-and-multi-dob.md` §1; **Nadhir's decision** |
| **L-163 CS-27 look-back** | HIGH (operational) | compliance, skeptic | PLAUSIBLE | **Deploy CONFIRMED** in CI: Source canary #1238, `cdf3801`, push, success, 14:17:45 to 14:36:37 UTC 11-18 (my `actions_list`); the deploy-step times are from compliance. Re-screen after deploy: **unconfirmed** | **Nadhir's decision** (look-back) |
| **L-172 DL1b (new, owed)**: a refresh that delists a UN entity cascade-deletes the **true_positive** alert and its `alert_reviews`; the freeze obligation stays `pending_execution` with `alert_id=NULL` | **MEDIUM** | lead | — | **CONFIRMED** (`dl1b`: `alert row left=0; alert_reviews left=0; freeze_obligations=[(1, None, 'pending_execution', 'sanctions')]`) | HELD `2026-11-22-lead-evidence-pdf-overlay-and-delisted-decisions.md` §2; **Nadhir's decision** |
| L-171 DL1 (false_positive case) | LOW → merged into L-172 | lead | — | CONFIRMED (`checks_21` DL1: 0 rows left) | same as L-172 |
| **L-170 GEN1**: gender mismatch silences an exact sanctions name | MEDIUM | lead | — | **CONFIRMED** (`checks_21` 3/3) | HELD 11-21 §5 (closed by L-166 Option B) |
| **L-168 PC1b**: an absorbed same-name PEP never alerts | **MEDIUM** | red-team (again today), lead | CONFIRMED Med | **CONFIRMED** (`checks_21`; red-team's e2e matches) | HELD 11-21 §1 |
| **L-173 EV1 (new)**: first-login disclaimer dialog printed over page 1 of the evidence PDF | **LOW** | mlro-user | CONFIRMED, Low/Med | **CONFIRMED, scoped**: `ev1`: unacked PDF contains "Important Notice" = True; after `POST /acknowledge-disclaimer` = False | HELD new proposal §1 (2-line CSS/template fix) |
| L-169 ED1/ED2/ED3 EDD gate | MEDIUM / LOW | mlro-user | CONFIRMED | CONFIRMED 11-21 (no code change) | HELD 11-21 §4; **Nadhir's decision** |
| CS-30 primary flip re-alerts | LOW | compliance, red-team | noise | **CONFIRMED** (`checks_21`) | HELD 11-21 §2 |
| L-167 CR-49 multi-DOB | MEDIUM | code-reviewer | — | **CONFIRMED** (`checks_20`) | HELD 11-20 §2; interaction with PC1 analysed, new proposal §3 |
| PC1 / CR-47 / CS-29 fold w/o identity | LOW (root of L-168) | 3 roles | CONFIRMED | **CONFIRMED** (`checks_20`) | HELD 11-20 §3 |
| CR-50 stale "Cloud Run throttles CPU" comments (`replication.py:5`, `litestream.yml:42`) | INFO | code-reviewer | — | CONFIRMED (lines read; `--no-cpu-throttling` at `source-canary.yml:556`) | Doc-only follow-up, no proposal needed |
| CR-51 old/new revision overlap during deploy | INFO | code-reviewer | — | PLAUSIBLE (not testable here) | Note |
| EV2 goAML XML has no declaration | INFO | mlro-user | PLAUSIBLE, Info | PLAUSIBLE (no XSD) | Carry with goAML XSD item |
| QA-env: `test_entrypoint.py` links `shutil.which("rm")`, so a wrapper on PATH breaks it | INFO (test hygiene) | qa-regression | — | PLAUSIBLE (QA's evidence; not re-run, my session has no such wrapper) | Note; not a master regression (REFUTED as one) |
| L-164 rescreen uses `nationality` only | MEDIUM | lead | — | **CONFIRMED** (`probe_dual_nat`: True) | HELD 11-19 |
| L-163a CT1, L-163b CT2 | LOW / INFO | lead | | **CONFIRMED** (`checks_19` 2/3) | HELD 11-19 |
| L-162 caps | MEDIUM | lead | | **CONFIRMED** 4/4 | HELD 11-19 |
| L-159 EX1+EX3, L-161 GV1 | MED / LOW | lead | | **CONFIRMED** (`checks_18` 3/4) | HELD 11-18 |
| L-156 QU1, TD2 | MED / LOW | lead | | **CONFIRMED** 4/4 (`checks_17`) | HELD 11-17 |
| CL1, CL2, TD1, TX1, TX2, N3c; SO1, RL1-RL3; RP1, MA1, SS5, RT1, RT2; SS1b, SS3b, CS24, CS5d; BL1, CR1-CR3; UBO1b, N8b; CS-13, CS-14, 3.1 | as before | | | Not re-run today (no app code change since they were last CONFIRMED) | HELD earlier / carry |
| L-158 DOB1 | — | | | FIXED by #466 (`checks_18` DOB1 False, `checks_19` L158 False again today) | Closed |
| CS-5 4-hourly refresh | — | compliance | PLAUSIBLE | Closed in repo; live schedule not visible | Closed (repo) |

**Severity adjudication**
- **EV1: LOW**, against mlro-user's High and below the skeptic's Low/Medium. Acknowledgement is per operator, and `web/static/js/app.js:639-645` opens the dialog with `showModal()` and blocks Escape. A browser user with JS on therefore cannot click the PDF link before acknowledging. The PDF only comes out unacknowledged from a typed URL, no-JS browsing or a script, which is how mlro-user's driver got it. The defect is real, it lands on a regulator-facing document, and the fix is trivial. It is not "every evidence pack".
- **DL1b: MEDIUM** (up from DL1 LOW). A confirmed UN match and the record of who decided it vanish from the case file. A freeze stays pending and is no longer linked to the match that created it. The loader comment (`loader.py:158-161`) assumes a disposition protects the record, and for `true_positive` it does not. Not higher: the audit row survives and the freeze row is not lost.
- **PC1b: MEDIUM** stands. Red-team still says low-medium; the skeptic and I agree on Medium for the reason given 11-21.
- Duplicates: red-team PC1/PC1b = L-168; EV1 is the skeptic's "print path untested" class. No contradictions. QA's 22 failures are an environment artefact (shown on the old SHA too), not a contradiction of code-reviewer's GREEN.

## 4. Combined assessment
1. #467 is a sound infra change with no app impact. The suite stays at 3010/2 and every carried lead check reproduces exactly as on 11-21 (8 scripts).
2. CS-27 now has an independently confirmed deploy time (11-18 14:36 UTC). The remaining risk is the look-back, which DB1 would force to be repeated (skeptic point 3).
3. The new MEDIUM is record-keeping, not screening: delisting deletes confirmed decisions. It belongs with DL1 in one soft-delist change.
4. EV1 is real but narrow, and nobody had looked at PDF output as a rendered page before today.
5. Same constraint as before: nothing app-side has merged since 11-19, and the Medium-or-above list keeps growing.

## 5. Corrections I made
Scratch venv (Python 3.11.18, `requirements.txt` + `requirements-dev.txt`), repo root, `PYTHONPATH=.`; WeasyPrint rendered fine; OCR not exercised. No existing file edited.
- **Owed (11-21): DL1 high-impact case (true_positive + freeze)** → done, new `repro_lead/dl1b_delist_true_positive_2026_11_22.py`, exit 0:
  ```
  DL1b  before delisting: alert 1 status=true_positive; alert_reviews=1; freeze_obligations=[(1, 1, 'pending_execution')]
  DL1b  after delisting: alert row left=0; alert_reviews left=0; freeze_obligations=[(1, None, 'pending_execution', 'sanctions')]; alert.* audit rows=1
  DL1b  true_positive alert cascade-deleted=True; freeze row kept but alert_id NULL=True
  ```
- **Owed (11-21): CR-49 × PC1b DOB-corroboration interaction** → analysed, no conflict if `_dobs_contradict` compares DOB *sets* (contradict only when both sides have dates and no pair agrees). Written up in proposal §3.
- **New verification of EV1**: `repro_lead/ev1_evidence_pdf_disclaimer_overlay_2026_11_22.py` (real route through `TestClient`, pypdfium2 text of page 1), exit 0:
  ```
  EV1  unacknowledged PDF page 1 contains 'Important Notice': True
  EV1  POST /acknowledge-disclaimer -> 303
  EV1  acknowledged PDF page 1 contains 'Important Notice': False
  ```
- **Carried checks re-run on `c42c77c`**: `checks_21` 3/3, `checks_20` 3/3, `checks_19` 2/3 (L158 fixed), `checks_l162_caps_19` 4/4, `probe_dual_nat_rescreen_19` L164 True, `checks_18` 3/4 (DOB1 fixed), `probe_dob_onboard_18` exit 1 by design (`1975-03-12 IN` and `1975-12-31 LY` still NO ALERT), `checks_17` 4/4. These scripts were copied in from their lead branches for the run and are not recommitted.
- **CS-27 deploy check**: GitHub Actions `list_workflow_runs` (read-only CI metadata): run #1238 `cdf3801` success, ended 2026-11-18T14:36:37Z.
- **Created `scripts/proposals/2026-11-22-lead-evidence-pdf-overlay-and-delisted-decisions.md`** (HELD): EV1 diff + test, DL1b soft-delist vs archive options, CR-49×PC1 rule.
- Evidence: `reports/daily/2026-11-22/evidence/lead_checks_2026_11_22_on_c42c77c.txt`, with console-mail noise and dev tokens stripped.
- Commit SHA: in the final reply (a commit cannot contain its own SHA).

## 6. Decisions needed from Nadhir
1. **CS-27 look-back (urgent, narrowed):** the fix has been deployed since 2026-11-18 14:36 UTC. Confirm that a refresh + `rescreen_all` ran after that, review its alerts (UN first) and record the incident window (from at least 2026-10-04). Plan to repeat the look-back after the DB1/GEN1/L-164 fixes.
2. **Exact-name floor (L-166 + L-170):** Option B is still recommended, with DB2 in the same PR.
3. **Delisting (L-171 + L-172):** soft-delist (recommended) or archive-before-delete, plus an MLRO notice when a pending freeze's entity is delisted.
4. **PEP fold (L-168 + PC1 + CS-30), EDD (L-169):** as 11-21.
5. **EV1:** approve the 2-line print fix, or bundle it into the next UI PR.
6. Carried: CR-45, L-156 + L-162 caps, L-159, L-149, L-152, L-154, L-145/L-146, runbook, correct-and-refile, L-135, L-132/L-131, corpus, goAML XSD (now with EV2), `github-advanced-security` 402.

## 7. Next run: carried over
- Re-run `checks_2026_11_21.py`, `checks_2026_11_20.py`, `ev1_…_2026_11_22.py`, `dl1b_…_2026_11_22.py`, plus `checks_19`, `checks_l162_caps_19`, `probe_dual_nat_rescreen_19`, `checks_18`, `checks_17` (copy them into `repro_lead/` first). Older checks only if master moves in their areas.
- **Owed by the lead:** check whether the other print views (UBO diagram export, report print/PDF, if any) inherit the EV1 overlay, as the skeptic suggests; check whether a delisted entity's pending freeze is still counted by `/system/check-freeze-obligations`'s query (code read only, no endpoint call).
- Suggestions for the roles: mlro-user could re-run its walks with an acknowledged operator (skeptic point 2).
- Landing order: CS-27 follow-ups (L-164 + CT1 + CT2) with L-166/L-170 + DB2, then L-168 + CR-49, then L-171/L-172, then L-169, then EV1 + the rest.
