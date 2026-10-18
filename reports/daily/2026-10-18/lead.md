# Lead consolidated report: 2026-10-18

## 1. Headline: AMBER
Master has not moved for twelve days; the HIGH lockout DoS (L-46) and every carried Medium still reproduce. Today's lead checks turn the L-70 "review clock silently resets" suspicion into a confirmed Medium (L-73), and add two more single-use tokens that can be used more than once (L-76, L-77; Low/Info).

Master is `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (#426), the same SHA as the 10-17 lead report. `git log 0129848..origin/master` is empty; roles report no PR opened or merged since #426 (only draft #411, docs, updated). Red-team and mlro-user report findings, so this is not a no-change run. Run date: 2026-10-18 UTC.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`6af1d77`) | done (no-change) | GREEN. No new diff; CR-12, CR-4 (#417), CR-13/14/18, CR-1b open | `ls-remote`, PR list | High |
| qa-regression (`80073cd`) | done (no-change) | GREEN. Suite not re-run; 10-07 result stands (2170 passed, 3 skipped) | `ls-remote`, `git log` | High |
| red-team (`4e0b41e`) | done | AMBER. Re-confirms setup-token race (T1) and 500 on duplicate email (T2) on the web path, 20/20 threads | probe script + evidence file + proposal | High, but a duplicate: the 10-17 lead already confirmed both on web (L-66, L-67) |
| compliance-specialist (`2426df6`) | done (no-change) | AMBER, unchanged. CS-2, CS-13 most serious; legal text BLOCKED | `ls-remote` | High |
| mlro-user (`4e7c30d`) | done | AMBER. MFA gate, lockout, backup codes, trusted device all work as designed; M1 lockout has no unlock path, M2 odd `/admin` redirect, M3 cookie not Secure locally | HTTP driver + JSON logs | High |
| skeptic (`2dd61b2`) | done | AMBER. T1/T2 web CONFIRMED by code; M1 Low/Med, M2 Info, M3 REFUTED; repeats the token-race family point | file:line, no new script | High (I ran what it read) |

## 3. Consolidated findings
CONFIRMED means I re-ran a repro or read the cited lines on `0129848` today.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-73** an unrelated re-assessment clears an overdue periodic review (`risk/model.py:196`, `cases/manager.py:817-818`, `1337`) | MEDIUM | lead (owed from 10-17, L-70 part 2) | n/a | CONFIRMED: `RV overdue before=True; after one cash txn alert: overdue=False, next_review=2029-10-02, review recorded=False`, 3/3. Adverse-media path by code only | HELD `scripts/proposals/2026-10-18-token-consume-and-review-clock.md` §2. **Needs Nadhir** |
| **L-74** five wrong TOTP codes lock an MLRO out of web+mobile for 15 min; no admin unlock route | LOW-MEDIUM | mlro M1 | CONFIRMED, Low/Med | CONFIRMED: by design (`auth.py:737-749`), counter does reset; MLRO/admin banner exists (`queries.py:189`) but `grep` finds no unlock route. Needs the password, so weaker than L-46 | **Needs Nadhir** (add admin unlock with L-46 fix?) |
| **L-76** email-verify token redeemable concurrently (`auth.py:558-569`) | LOW | lead (owed) | n/a | CONFIRMED: `EV ... successes per round=[5, 5, 5, 5, 5]`, 3/3. Holder is the legitimate owner; extra sessions only | HELD same file §1 |
| **L-77** UAE PASS state consumable concurrently (`auth.py:985-1015`) | INFO | lead (owed) | n/a | CONFIRMED: `US ... successes per round=[5, 5, 5, 5, 5]`, 3/3. Cookie binding makes cross-browser replay impossible | HELD same file §1 |
| L-75 `/admin` for MFA-locked session redirects to `/` | INFO | mlro M2 | PLAUSIBLE, Info | PLAUSIBLE (not run) | Carry |
| mlro M3 trusted-device cookie not Secure without proxy | — | mlro M3 | REFUTED | REFUTED: `app.py:912-915` uses the same `AMLKIT_BEHIND_PROXY` switch as every other cookie (`:317-322`, `:373-395`) | Closed |
| L-66 setup token claimable concurrently (web + mobile) | LOW-MEDIUM | red-team T1 (10-17, again 10-18) | Medium | CONFIRMED again (`T1m ... operators=10`, `T1w ... operators=10`) | HELD red-team `2026-10-17-new-findings.md` §T1 (+ `2026-10-18-new-findings.md`). **Needs Nadhir** |
| L-67 setup: duplicate email → 500, no email/name/complexity checks (web + mobile) | LOW | red-team T2 | Low | CONFIRMED again (`T2 existing email -> 500 ...`) | HELD; fold into password helper |
| L-69 MFA backup code usable twice concurrently | LOW | skeptic 10-17 | — | CONFIRMED again (`BC ... results=[True, True]`) | HELD 10-17 lead proposal §1 |
| L-70 / L-72 / L-71 no web periodic-review completion, no attestation, no overdue tag | MEDIUM / LOW-MED / INFO | mlro PR1-3 | Med / Low-Med / Info | Unchanged (no commit) | HELD 10-17 lead proposal §2-3. **Needs Nadhir** |
| L-46 lockout counter not reset at expiry (`auth.py:376-404`) | **HIGH** | red-team A1 | High | CONFIRMED again (`A1 expired=(8,...) after ONE wrong=(9,...) ... reproduces=True`) | HELD 10-11 lead `login-lockout-and-password-rules.md` §1. **Needs Nadhir** |
| L-53 blank `full_name` onboarded, screens clear | MEDIUM | mlro C1 | Medium | CONFIRMED again (`EN ... clear=True ... reproduces=True`) | HELD 10-14 lead. **Needs Nadhir** |
| L-38 freeze/CNMR on non-UAE-list hits | MEDIUM-HIGH | compliance CS-2 | Med | CONFIRMED again (`CS-2 ... 'pending_execution' -> reproduces=True`) | HELD `freeze-list-scope-and-totp-replay.md` §1. **Needs Nadhir** |
| L-30 every re-screen shows "Re-screening failed: 'customers'" | MEDIUM | mlro G9 | Med | CONFIRMED again (`_06` exit 0) | HELD `rescreen-banner-and-realert.md` §1 |
| L-9 re-screen re-raises decided alerts | MEDIUM | mlro G10, CS-3 | Med | CONFIRMED again (`new open alerts [3, 4], reproduces=True`) | HELD same file §2 |
| L-43 same-name upload overwrites evidence | MEDIUM | red-team U1 | Med | Unchanged; not re-run | HELD |
| L-50 UAE PASS CDD not tied to customer identity | MEDIUM-LOW | red-team C1 | Low/Med | Unchanged | HELD. **Needs Nadhir** |
| L-57, L-52, L-55 | LOW-MEDIUM | red-team R1, mlro P1/C3 | Low/Med | CONFIRMED again (`R1 ... ValueError`, `P1 ... reproduces=True`); L-55 unchanged | HELD. **Needs Nadhir** |
| L-47 + L-58 weak passwords / admin reset 500 | LOW | mlro OP1/OP2, red-team R2 | Low | CONFIRMED again (`OP1 status=500`, `OP2 account_created=True`, `R2 ... created`) | HELD lockout file §2 |
| L-56, L-63, L-61, L-62 | LOW / INFO | mlro C4, red-team F6, mlro NT2/NT3 | Low/Info | CONFIRMED again (`L-56`, `F6`, `NT2`, `NT3 ... reproduces=True`) | HELD / carry |
| L-54, L-51, L-48, L-40, L-27, L-44 | LOW | as 10-16 | Low | CONFIRMED again (`SEC`, `TA1`, `GR`, `M2` TOTP replay, `4E`, `DL`/`DLA`) | HELD |
| L-68, L-64, L-65, L-59, L-60, and the 10-16 carry list (RT-P1 … CR-17) | as before | various | as before | Unchanged: no commit since 10-06 | Carry |

**Severity adjudication**
- L-73 is MEDIUM on its own, not a footnote to L-70: one cash alert on a low-risk customer pushed an overdue review out by 36 months. Event-driven re-ratings are common, so in practice the overdue list under-reports; the case where risk rises (an alert) is exactly when the review is most needed.
- L-74 (mlro M1): I take the skeptic's LOW-MEDIUM. It needs the password, and the lock expires (unlike L-46), but there is no way to clear it early, which matters to a one-MLRO firm during a freeze deadline. The missing admin unlock is shared with L-46 and should land in the same fix.
- Red-team T1/T2 (web) are duplicates of L-66/L-67, which the 10-17 lead already confirmed on web; red-team's Medium vs my LOW-MEDIUM stays as adjudicated yesterday (no privilege gain for a token holder).
- L-76 LOW, L-77 INFO: same idiom as L-66/L-69 but low impact, see proposal §1.
- No contradictions. ID collision again (mlro M1-M3 vs red-team M2, T-series); the L-numbers above are canonical.

**FIXED on master:** none (no commits).

## 4. Combined assessment
1. Twelve days without a commit; the HIGH (L-46) and all carried Mediums re-reproduced on `0129848` today.
2. The check-then-act family now has four confirmed members (setup token, backup code, email-verify token, UAE PASS state); one `UPDATE ... WHERE used_at IS NULL` + rowcount idiom closes all four.
3. Periodic review is the weakest compliance workflow: no web completion (L-70), no attestation (L-72), and the due date silently moves on unrelated events (L-73).
4. The new MFA surface (lockout, backup codes, trusted device) tested correct apart from the missing unlock path (L-74).
5. The HELD backlog (~25 proposals) needs decisions more than new probing.

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_10_18.py` (RV = L-73, EV = L-76, US = L-77). Temp DB, no network. Scratch venv from `requirements.txt` without passporteye/pdfminer (OCR not exercised). Output on `0129848`, identical in 3 runs:
  ```
  RV  overdue before=True; after one cash txn alert: overdue=False, next_review=2029-10-02, review recorded=False -> reproduces=True
  EV  one email-verify token, 5 concurrent redeems x5 rounds: successes per round=[5, 5, 5, 5, 5] -> reproduces=True
  US  one UAE PASS state, 5 concurrent consumes x5 rounds: successes per round=[5, 5, 5, 5, 5] -> reproduces=True
  exit=0
  ```
- C-2 Created `scripts/proposals/2026-10-18-token-consume-and-review-clock.md` (HELD): guarded-UPDATE diff for L-76/L-77 (same idiom for L-66/L-69), and a "never extend the review clock on event re-ratings" rule for L-73. Not applied: auth and business logic.
- C-3 Both owed items from the 10-17 "Next run" are done (L-70 incidental-reset path → L-73; email-verify and UAE PASS consumers → L-76/L-77).
- C-4 Owed re-runs, all exit 0, nothing fixed: `_06` (G9, L-9, 4E; run from `repro_lead/`), `_07` (CS-2, M2), `_10` (DL, DLA), `_11` (A1, OP2, OP1, GR), `_12` (TA1), `_13` (P1), `_14` (EN, SEC), `_15` (L-56, R1, R2), `_16` (F6, NT2, NT3), `_17` (T1m, T1w, T2, BC). Copied from their lead branches into `repro_lead/`, run with `PYTHONPATH=.:tests`, copies removed before commit.
- Not re-run: red-team `probe_web_setup_race.py` (my `_17` T1w covers it), mlro driver (M1 confirmed by code), skeptic scripts. Adverse-media path of L-73 by code only.
- No tests added: each would fail on master (rule 5). No existing file edited.

## 6. Decisions needed from Nadhir
1. **L-46 (HIGH): approve the lockout fix** (10-11 proposal §1), and decide whether it adds an admin unlock that also covers the MFA lock (L-74).
2. **Atomic consume for all one-time secrets** (L-66, L-69, L-76, L-77): one small PR, proposals 10-17 red-team §T1, 10-17 lead §1, 10-18 lead §1.
3. **Periodic review (L-70/L-72/L-73):** choose the review record (outcome list, mandatory note) and confirm the rule that event re-ratings may bring the review date forward but never push it back.
4. L-53 blank-name fix; L-38/L-39 freeze scope (a)/(b)/(c).
5. Shared helpers: password (L-47, L-58, L-67), upload (L-64, U3, L-43), field validation (L-53, L-54, L-59).
6. L-57 slug; L-55; L-50; L-52 DOCX.
7. L-30 one-line banner fix (eleventh request); L-9, L-56, L-63, L-65, L-51, L-28/L-29, L-27, L-48, L-68.
8. Carried: E4, L-44, L-40, L-42, L-31/32/33 adviser confirmation, FATF snapshot, #417 (L-23), `github-advanced-security` 402 quota, role-prefixed finding IDs.

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_10_18.py` (this branch) and `_17`, `_16`, `_15`, `_14`, `_13`, `_12`, `_11`, `_10`, `_07`, `_06` from their lead branches, placed in `repro_lead/`, `PYTHONPATH=.:tests` (`_06` from inside `repro_lead/`). Exit 1 means something was fixed; read the lines.
- Owed by the lead: run the adverse-media disposition path of L-73 (by code only today), and exercise L-75 (`/admin` redirect while MFA-locked) to settle PLAUSIBLE.
- Track landing in this order: L-46 (+L-74), L-53, L-38, L-70/L-72/L-73, L-66/L-69/L-76/L-77, L-50, L-43, L-30, L-9, L-57, L-47+L-58+L-67, L-52, L-55, L-56, L-64, L-65, L-63, L-54, L-28, L-29, L-51, L-48, L-27, L-40, L-44, L-21.
