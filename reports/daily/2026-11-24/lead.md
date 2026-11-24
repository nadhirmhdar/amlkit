# Lead consolidated report: 2026-11-24

## 1. Headline: AMBER (one PR merged, #468 `/system/grant-trial`, clean apart from a Low input-type 500; compliance's F-1 disposition race is now reproduced by the lead; every open screening/delisting item is unchanged)
Master `f3c8227121fbec1d4c3860c63b4a383a4656f975` (`git ls-remote`, today). Previous lead report: `c42c77c`. `git log c42c77c..origin/master` = one commit, `f3c8227 Add /system/grant-trial (owner-granted N-day trial, no card) (#468)` (5 files, +220/-1: `routers/system.py`, `cases/operators.py`, `tests/test_grant_trial.py`, `tests/data/routes_master.json`, `CLAUDE.md`). No screening, freeze, review, retention or reporting code changed. Run date 2026-11-24 UTC. All six role branches were present on the first fetch.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | GREEN: #468 gated, atomic, audited; CR-52 (non-string JSON → 500), CR-53 (trial not enforced while billing off), CR-54 (doc gap); suite 2999/2 with `test_entrypoint.py` excluded | in-process TestClient probes, suite count | High (CR-52 confirmed by my code read). Note: its probes hit `/system/grant-trial` in-process with a dummy secret; local only, but outside the "no /system/* calls" rule other roles applied |
| qa-regression | done | GREEN: full suite **3023 passed, 2 skipped, 0 failed** (clean PATH); tenant sweeps identical, 0 leaks | pasted pytest summary, sweep diffs | High |
| red-team | done | GREEN for #468: `grant_trial` called as a function, `days`/dupes/injection REFUTED; 1 MB password accepted (pre-existing, info) | script + evidence on branch | High |
| compliance-specialist | done | AMBER: CS-31 info; **F-1** (disposition UPDATE has no status guard) MEDIUM PLAUSIBLE; F-2 from draft #411; CS-27 look-back still open | code reads, CI run ids (not re-checked by me) | High on F-1 (I reproduced it) |
| mlro-user | done | AMBER: 41 walks still pass; SL1 (per-process sanctions cache) PLAUSIBLE medium; SL2 low | driver logs | Medium: SL1 premise does not hold in the deployed topology |
| skeptic | done | RED carried; SL1 REFUTED for production; F-1 Low-Med; CR-52/CR-53 agree | file:line refs, own regression scripts | High (SL1 refutation matches my read) |

Suite counts agree once the environment is accounted for: QA 3023 passed (clean PATH); compliance 3001 passed + 22 failed, all in `tests/test_entrypoint.py` with `rm: command not found` (rm guard shim on PATH); code-reviewer 2999 with that file excluded. 3010 + 13 new = 3023. Not a regression.

## 3. Consolidated findings
"CONFIRMED (lead)" = reproduced by me today on `f3c8227`; output in `reports/daily/2026-11-24/evidence/lead_checks_2026_11_24_on_f3c8227.txt`.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-166 DB1 / CS-28 / CR-48** exact name, same-year different-month DOB → 0.75, no alert | **MEDIUM-HIGH** | 5 roles | CONFIRMED High | **CONFIRMED** (`checks_20` DB1; `probe_dob_onboard_18`: `1975-12-31 LY NO ALERT`) | HELD 11-20 proposal §1; **Nadhir's decision** |
| **L-163 CS-27 look-back** | HIGH (operational) | compliance, skeptic | carried | Fix deployed 11-18; post-deploy re-screen **unconfirmed** | **Nadhir's decision** |
| **L-176 F-1 (new)** concurrent dispositions: op B's confirmed `true_positive` (freeze created) is overwritten by op A's staged dismissal, then confirmed as `false_positive`; freeze stays `pending_execution` | **LOW-MEDIUM** | compliance (from draft #411) | PLAUSIBLE Low-Med | **CONFIRMED (lead)** (`f1_disposition_race_2026_11_24.py` exit 0) | HELD `scripts/proposals/2026-11-24-lead-disposition-status-guard.md` |
| L-174 DL1d delisted UN freeze can only be closed as `false_positive` | MEDIUM | lead | — | **CONFIRMED** (`dl1c` exit 0) | HELD 11-23 proposal |
| L-175 DL1c delisted freeze still overdue; legacy OFAC flips into scope | LOW-MEDIUM | lead | — | **CONFIRMED** (`dl1c`) | HELD 11-23 proposal |
| L-172 / L-171 DL1b/DL1 alert cascade-deleted on delisting | MEDIUM | lead | — | **CONFIRMED** (`dl1b` exit 0) | HELD 11-22 §2 |
| L-170 GEN1 gender mismatch silences exact name | MEDIUM | lead | — | **CONFIRMED** (`checks_21`) | HELD 11-21 §5 |
| L-168 PC1b absorbed PEP never alerts | MEDIUM | red-team, lead | CONFIRMED | **CONFIRMED** (`checks_21`) | HELD 11-21 §1 |
| L-167 CR-49 multi-DOB; PC1 | MEDIUM / LOW | code-reviewer, 3 roles | — | **CONFIRMED** (`checks_20` 3/3) | HELD 11-20 §2/§3 |
| CS-30 primary flip re-alerts | LOW | compliance, red-team | noise | **CONFIRMED** (`checks_21`) | HELD 11-21 §2 |
| L-164 rescreen uses `nationality` only; CT1/CT2 | MEDIUM / LOW | lead | — | **CONFIRMED** (`probe_dual_nat` True; `checks_19` 2/3, L158 stays fixed) | HELD 11-19 |
| L-162 caps | MEDIUM | lead | — | **CONFIRMED** 4/4 | HELD 11-19 |
| L-159 EX1+EX3, L-161 GV1 | MED / LOW | lead | — | **CONFIRMED** (`checks_18` 3/4; DOB1 stays fixed) | HELD 11-18 |
| L-156 QU1, TD2 | MED / LOW | lead | — | **CONFIRMED** 4/4 (`checks_17`) | HELD 11-17 |
| L-173 EV1 (+EV4) disclaimer over evidence PDF | LOW | mlro-user | Low/Med | **CONFIRMED, scoped** (`ev1` exit 0) | HELD 11-22 §1 |
| L-169 ED1-ED3 EDD gate | MED / LOW | mlro-user | CONFIRMED | not re-run (no change) | HELD 11-21 §4 |
| **CR-52 (new)** non-string JSON field → 500 on `/system/grant-trial` | LOW | code-reviewer | agree Low | **CONFIRMED** by code: `routers/system.py:224-227` call `.strip()` / `.lower()` on `body.get(...) or ""`, outside `except ValueError` | Fix with `/system/create-operator` (same pattern); not held as a proposal (admin-secret only, nothing written) |
| **CR-53 (new)** dated trial unenforced while billing is off | INFO / commercial | code-reviewer, skeptic | agree | CONFIRMED (documented in CLAUDE.md) | **Nadhir's decision** |
| CR-54 CLAUDE.md omits `days` default 14 | INFO | code-reviewer | — | CONFIRMED (`body.get("days", 14)`, system.py:228) | Doc follow-up |
| CS-31 trial audit actor is literal `"system"` | LOW | compliance | agree | PLAUSIBLE (not read line-by-line by me) | Note; same for create-operator |
| **SL1** per-process sanctions cache misses new listings in other workers | LOW (latent) | mlro-user (Med) | REFUTED for prod | **REFUTED for production**: `source-canary.yml:553-554` `--min-instances 1 --max-instances 1`; `scripts/serve.py:78` `uvicorn.run` with no `workers` | Note: comment the coupling next to `--max-instances 1` |
| SL2 re-screen-all message shows no list date | LOW | mlro-user | agree | CONFIRMED (role evidence) | Carry |
| F-2 onboard commits before screening; no token expiry sweep | LOW | compliance (from #411) | — | PLAUSIBLE (not verified) | Carry |
| Red-team: no password length cap; unthrottled admin-secret guess | INFO | red-team | agree | PLAUSIBLE / by code | Carry |
| CR-50, CR-51, EV2, CL1, CL2, TD1, TX1, TX2, N3c, SO1, RL1-RL3, RP1, MA1, SS5, RT1, RT2, SS1b, SS3b, CS24, CS5d, BL1, CR1-CR3, UBO1b, N8b, CS-13, CS-14, 3.1 | as before | | | Not re-run (no app code change in their areas) | HELD earlier / carry |
| L-158 DOB1 | — | | | FIXED by #466 (still False today) | Closed |

**Adjudication**
- **F-1 LOW-MEDIUM**, between compliance (Medium) and skeptic (Low-Med). The interleaving is real, not theoretical: the window spans two DB reads, and sync routes run on a thread pool. The outcome is the same class as DL1d (a confirmed UN match ends recorded as a false positive with a live freeze). Not Medium because it needs two operators on one alert in a millisecond window, and `alert_reviews` keeps all three decisions.
- **SL1 LOW (latent)**: I side with the skeptic. One instance, one uvicorn process. The mlro-user's own write-to-DB method was the cause of the missed alert, as they said.
- **CR-53** is not a defect but a commercial gap: a "14-day trial" granted today is unlimited until billing is switched on.
- Duplicates: CS-28 = DB1 = CR-48; F-1 = draft #411 finding 1. Contradictions: only SL1 severity (above). No role contradicts another's facts.

## 4. Combined assessment
1. #468 is sound: gated by the admin secret, atomic (orphan org REFUTED), audited, 13 tests; one Low input-type 500.
2. Full suite green on `f3c8227` (3023/2/0); the 22 `test_entrypoint` failures seen by two roles are the sandbox rm shim, not code.
3. All 11 carried lead checks reproduce exactly as on 11-23; nothing has moved on screening or delisting.
4. New confirmed item F-1 adds a second path (after DL1d) to "confirmed sanctions match recorded as false positive with a live freeze".
5. The constraint is still decisions: ≥17 Medium-or-above items HELD; the only app change in six days was a provisioning endpoint.

## 5. Corrections I made
Scratch venv (Python 3.11.18, `requirements.txt` + `requirements-dev.txt`), repo root, `PYTHONPATH=.`, detached at `f3c8227`; WeasyPrint rendered; OCR not exercised. No existing file edited; I did not call any `/system/*` route (CR-52 is a code read).
- **New repro `repro_lead/f1_disposition_race_2026_11_24.py`**, exit 0:
  ```
  F1  op B in the gap: true_positive; freeze rows=[(1, 1, 'pending_execution')]
  F1  op A after B: pending_review (no error raised)
  F1  op C confirms: false_positive; final alert status=false_positive; freeze rows=[(1, 1, 'pending_execution')]
  F1  alert_reviews trail=[('opB', 'propose', 'true_positive'), ('opA', 'propose', 'false_positive'), ('opC', 'confirm', 'false_positive')]
  F1  confirmed true_positive overwritten to false_positive with live freeze obligation=True
  ```
  Proposal with diff (status guard + rowcount in both UPDATEs, test to add): `scripts/proposals/2026-11-24-lead-disposition-status-guard.md` (HELD).
- **Owed (11-23, optional): does the web freeze-obligations page mark a delisted `pending_execution` row?** Template read: `freeze_obligations.html` and `freeze_obligation_detail.html` show no alert, entity or list reference at all, so a row whose alert was cascade-deleted looks identical to any other. And the detail page offers `delisted` as a resolve reason (`freeze_obligation_detail.html:151`) that the backend refuses for an unexecuted obligation (DL1d), so the MLRO is shown an option that fails. Added to L-174; closed as an owed item.
- **Carried checks re-run on `f3c8227`** (master moved): `checks_21` 3/3, `checks_20` 3/3, `dl1b_22` exit 0, `ev1_22` exit 0, `dl1c_23` exit 0, `checks_19` 2/3, `checks_l162_caps_19` 4/4, `probe_dual_nat_19` True, `checks_18` 3/4, `probe_dob_onboard_18` exit 1 by design (`1975-03-12 IN` and `1975-12-31 LY` NO ALERT), `checks_17` 4/4. Identical to 11-23. Harness note: `ev1`, `checks_18`, `checks_17` import `tests/test_api.py` relative to their own path and fail with `ModuleNotFoundError` when run from outside `repro_lead/`; re-run from `repro_lead/` (temporary copies, removed, not recommitted). Both passes are in the evidence file.
- Files created: `repro_lead/f1_disposition_race_2026_11_24.py`, `scripts/proposals/2026-11-24-lead-disposition-status-guard.md`, `reports/daily/2026-11-24/evidence/lead_checks_2026_11_24_on_f3c8227.txt`, this report. Commit SHA: in the final reply.

## 6. Decisions needed from Nadhir
1. **CS-27 look-back (urgent, carried):** confirm a refresh + `rescreen_all` ran after 2026-11-18 14:36 UTC, review its alerts (UN first), record the window (from at least 2026-10-04).
2. **Exact-name floor (L-166 + L-170):** Option B recommended, DB2 in the same PR.
3. **Delisting (L-171/172/174/175):** soft-delist (recommended); whether "delisted before execution" may close a freeze obligation; and drop or fix the `delisted` option the UI offers today.
4. **F-1 guard (new):** approve the two-line status guard in `2026-11-24-lead-disposition-status-guard.md` (low risk, could land with the delisting set).
5. **Granted trials (CR-53):** accept that a trial granted while billing is off never expires, or ask for an expiry check independent of the billing switch.
6. Carried: PEP fold (L-168 + PC1 + CS-30), EDD (L-169), EV1+EV4, CR-45, L-156 + L-162 caps, L-159, L-149, L-152, L-154, L-145/L-146, runbook, correct-and-refile, L-135, L-132/L-131, corpus, goAML XSD (+EV2), `github-advanced-security` 402.

## 7. Next run: carried over
- Re-run the 11 carried lead scripts plus `f1_disposition_race_2026_11_24.py` if master moves in screening/review/freeze code; otherwise only on a role report in their area. Run `ev1`, `checks_18`, `checks_17` from inside `repro_lead/`.
- **Owed by the lead:** none. Optional: verify compliance F-2 (onboard commits customer before screening/risk; can an exception leave an unscreened, unrated customer?) with a scratch repro.
- Landing order: CS-27 follow-ups (L-164 + CT1 + CT2) with L-166/L-170 + DB2; then L-168 + CR-49; then the delisting set (L-171/172/174/175) with F-1; then L-169; then EV1+EV4, CR-52 and the rest.
