# Lead consolidated report: 2026-10-19

## 1. Headline: AMBER
Master has not moved for thirteen days. The HIGH lockout DoS (L-46) and every carried Medium still reproduce. Today's new items are Low or Info: ad-hoc screening has no length cap (L-78), and the password-change page has two flaws (L-79, L-80). Both owed checks are now settled. L-73 also reproduces on the adverse-media path, and L-75 is confirmed Info.

Master is `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (#426), the same as the 10-18 lead report. `git log 0129848..origin/master` is empty. Roles report no PR opened or merged since #426; only draft #411 (docs) was updated. Red-team and mlro-user report new findings, so this is not a no-change run. Run date: 2026-10-19 UTC.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`ae1e4d6`) | done (no-change) | GREEN. No new diff. CR-12, CR-4 (#417), CR-13/14/18 and CR-1b still open | `ls-remote`, PR list | High |
| qa-regression (`d2026c1`) | done (no-change) | GREEN. Suite not re-run; the 10-07 result stands (2170 passed, 3 skipped) | `ls-remote`, `git log` | High |
| red-team (`a22d6cc`) | done | AMBER. S3: `/api/v1/screen` accepts a 500,000-character name, and a 100-request burst all returned 200 | probe script + evidence + proposal | High on the cap. One error: its proposal says web `/screen` has no limiter, but it has `10/minute` (`app.py:1680`) |
| compliance-specialist (`273280a`) | done (no-change) | AMBER, unchanged. CS-2 and CS-13 are the most serious; legal text still BLOCKED | `ls-remote` | High |
| mlro-user (`5a9c374`) | done | AMBER. Password change revokes sessions correctly. Found PW1 (banner wrong), PW2 (same password, untested), SS1 (silent eviction at 3 sessions) | HTTP driver + JSON logs | High |
| skeptic (`cdd7c1e`) | done | AMBER. S3, PW1 and SS1 CONFIRMED by code; PW2 PLAUSIBLE/Info. Suggests one shared bounded-string type | file:line | High (I ran what it read) |

## 3. Consolidated findings
CONFIRMED means I re-ran a repro, or read the cited lines, on `0129848` today.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-78** ad-hoc screening: no name-length cap on web or mobile; mobile has no rate limit either (`mobile.py:505-537`, `app.py:1679-1710`) | LOW | red-team S3 | CONFIRMED, Low | CONFIRMED: `S3w ... status=200, stored length=50000`, `S3m ... 200; 30 rapid requests -> [200]`, 3/3 | HELD `scripts/proposals/2026-10-19-screen-cap-and-password-change.md` §1 (+ red-team `2026-10-19-new-findings.md`) |
| **L-79** password change: banner says "All other sessions have been signed out", but the current session is revoked too (`app.py:838`, `:4577`) | LOW | mlro PW1 | CONFIRMED, Low | CONFIRMED: `PW1 ... flash says 'All other sessions'=True; next GET / -> 303 '/login'`. Revoking every session is correct; only the copy and the redirect are wrong | HELD same file §2 |
| **L-80** password change accepts the current password as the new one | INFO | mlro PW2 | PLAUSIBLE, Info | CONFIRMED (mlro and skeptic had not tested it): `PW2 change to the SAME compliant password -> 303 location='/'` | HELD same file §3; fold into the password helper |
| **L-81** a 4th session silently evicts the oldest (`auth.py:587-602`, cap 3, mobile tokens counted) | LOW | mlro SS1 | CONFIRMED, Low | CONFIRMED: `SS1 4 sessions ... alive=[False, True, True, True]`. The cap is deliberate; the missing notice is UX | HELD same file §4. **Needs Nadhir** (a/b/c) |
| **L-73** an unrelated re-assessment clears an overdue periodic review | MEDIUM | lead | n/a | CONFIRMED on both paths. Cash alert: `RV ... overdue=False, next_review=2029-10-03`. Adverse media (owed): `AM overdue before=True; after one 'not_relevant' media ruling: overdue=False, next_review=2029-10-03`. A ruling that the article is *not* about the customer still pushes the review out three years | HELD 10-18 lead §2. **Needs Nadhir** |
| **L-75** an MFA-locked MLRO opening `/admin` goes `/` → `/login` → `/mfa/verify` | INFO | mlro M2 (10-18) | PLAUSIBLE, Info | CONFIRMED (owed): `L75 ... 303 location='/'; '/' then -> '/login'`. No bypass; three hops | HELD same file §5 |
| L-46 lockout counter not reset at expiry | **HIGH** | red-team A1 | High | CONFIRMED again (`A1 ... after ONE wrong=(9, ...) ... reproduces=True`) | HELD 10-11 lead §1. **Needs Nadhir** |
| L-74 MFA 5-miss lockout, no admin unlock | LOW-MEDIUM | mlro M1 | Low/Med | Unchanged (no commit) | **Needs Nadhir**, together with L-46 |
| L-38 freeze/CNMR raised on non-UAE-list hits | MEDIUM-HIGH | compliance CS-2 | Med | CONFIRMED again (`CS-2 ... 'pending_execution' -> reproduces=True`) | HELD. **Needs Nadhir** |
| L-53 blank `full_name` onboarded and screens clear | MEDIUM | mlro C1 | Medium | CONFIRMED again (`EN ... clear=True ... reproduces=True`) | HELD. **Needs Nadhir** |
| L-30 every re-screen shows "Re-screening failed: 'customers'" | MEDIUM | mlro G9 | Med | CONFIRMED again (`G9 ... reproduces=True`) | HELD `rescreen-banner-and-realert.md` §1 |
| L-9 re-screen re-raises alerts already decided | MEDIUM | mlro G10, CS-3 | Med | CONFIRMED again (`new open alerts [3, 4], reproduces=True`) | HELD same file §2 |
| L-70 / L-72 / L-71 periodic review: no web completion, no attestation, no overdue tag | MEDIUM / LOW-MED / INFO | mlro PR1-3 | as before | Unchanged | HELD. **Needs Nadhir** |
| L-66, L-69, L-76, L-77 one-time secrets consumable concurrently | LOW-MED / LOW / LOW / INFO | red-team T1, skeptic, lead | Medium (T1) | CONFIRMED again (`T1m operators=10`, `T1w operators=10`, `BC [True, True]`, `EV [5,5,5,5,5]`, `US [5,3,5,5,5]`) | HELD. **Needs Nadhir** (one PR) |
| L-67, L-47 + L-58 password rules / setup 500 | LOW | red-team T2/R2, mlro OP1/OP2 | Low | CONFIRMED again (`T2 ... 500`, `OP1 status=500`, `OP2 account_created=True`, `R2 ... created`) | HELD |
| L-43, L-50, L-55 | MEDIUM / MED-LOW / LOW-MED | red-team U1/C1, mlro C3 | as before | Unchanged; not re-run | HELD |
| L-57, L-52, L-56, L-63, L-61, L-62, L-54, L-51, L-48, L-40, L-27, L-44 | LOW / INFO | various | as before | CONFIRMED again (`R1`, `P1`, `L-56`, `F6`, `NT2`, `NT3`, `SEC`, `TA1`, `GR`, `M2`, `4E`, `DL`/`DLA` all `reproduces=True`) | HELD / carry |
| L-68, L-64, L-65, L-59, L-60 and the 10-16 carry list (RT-P1 … CR-17) | as before | various | as before | Unchanged: no commit since 10-06 | Carry |

**Severity adjudication**
- L-78 stays LOW (red-team and skeptic agree). It needs an authenticated operator. The web route already has a limiter, and the mobile path is the only unthrottled one. The harm is growth of the DB, the replica and stored data, not a security breach. The fix is the same `MAX_NAME_LENGTH` the customer path already uses.
- L-80: I raise it from PLAUSIBLE to CONFIRMED but keep it INFO. Reusing the current password changes nothing for security, because the user must already know it.
- L-81: the skeptic's LOW is correct. A firm with one MLRO using desktop, laptop and phone will hit the cap. Nothing in the app explains why they were signed out.
- L-73 adverse-media path: this widens an existing finding and does not raise its severity. It stays MEDIUM.
- Duplicates and contradictions: red-team says web `/screen` has no limiter; that is wrong (`app.py:1680`). No other conflicts. The role IDs (S3, PW1, PW2, SS1) map to L-78 to L-81 above.

**FIXED on master:** none (no commits).

## 4. Combined assessment
1. Thirteen days without a commit. The HIGH (L-46) and all carried Mediums re-reproduced on `0129848` today, with 11 earlier scripts all exiting 0.
2. Today's new findings are small and their fixes are mostly one line each. Nothing new is above Low.
3. The skeptic is right that input limits are applied per route. One shared bounded-string type would close L-78, L-56, F6/L-63 and the N1/DOC1 class together.
4. The periodic-review clock (L-73) moves on every event-driven re-rating, now proven on both paths. It is still the most important compliance-workflow item without a decision.
5. The backlog needs decisions and fix PRs, not more probing.

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_10_19.py`: AM (L-73 media path), L75, S3w, S3m (L-78), PW1 (L-79), PW2 (L-80), SS1 (L-81, informational). It uses temp DBs and TestClient, with no network. Scratch venv built from `requirements.txt` without passporteye/pdfminer, so OCR was not exercised. Output on `0129848`, identical in 3 runs:
  ```
  AM  overdue before=True; after one 'not_relevant' media ruling: overdue=False, next_review=2029-10-03 -> reproduces=True
  SS1 4 sessions for one operator, alive=[False, True, True, True] (oldest silently revoked; informational)
  S3w web /screen 50,000-char name -> status=200, stored length=50000 -> reproduces=True
  S3m mobile /api/v1/screen 50,000-char name -> 200; 30 rapid requests -> [200] -> reproduces=True
  L75 MFA-locked MLRO GET /admin -> 303 location='/'; '/' then -> '/login' (then /login -> /mfa/verify) -> reproduces=True
  PW1 change -> 303, flash says 'All other sessions'=True; next GET / -> 303 '/login' -> reproduces=True
  PW2 change to the SAME compliant password -> 303 location='/' -> reproduces=True
  exit=0
  ```
  My first PW2 attempt failed because the test fixture's password has no uppercase letter, so the generic complexity rule rejected it. That is the same confound mlro-user hit. The script now runs PW1 first, which moves the account to a compliant password, and then tests PW2.
- C-2 Created `scripts/proposals/2026-10-19-screen-cap-and-password-change.md` (HELD): diffs for L-78 (web + mobile cap, mobile limiter), L-79 (copy and redirect), L-80 (must-differ check), options for L-81, and a note on L-75. Not applied because these are route and auth logic.
- C-3 Both owed items from the 10-18 "Next run" are done: L-73 adverse-media path (AM) and L-75 (L75).
- C-4 Owed re-runs, all exit 0, nothing fixed: `_06` (G9, L-9, 4E; run from `repro_lead/`), `_07` (CS-2, M2), `_10` (DL, DLA), `_11` (A1, OP2, OP1, GR), `_12` (TA1), `_13` (P1), `_14` (EN, SEC), `_15` (L-56, R1, R2), `_16` (F6, NT2, NT3), `_17` (T1m, T1w, T2, BC), `_18` (RV, EV, US). I copied them from their lead branches into `repro_lead/`, ran them with `PYTHONPATH=.:tests`, and removed the copies before committing.
- Not re-run: red-team `probe_screen_cost.py` (it needs PR #412's `fixtures/`, and my S3 checks cover it), the mlro driver, and the skeptic scripts.
- No tests added, because each would fail on master (rule 5). No existing file edited.

## 6. Decisions needed from Nadhir
1. **L-46 (HIGH): approve the lockout fix** (10-11 proposal §1), together with an admin unlock that also covers the MFA lock (L-74).
2. **Periodic review (L-70/L-72/L-73):** confirm the rule that event re-ratings (cash alert, adverse-media ruling) may bring the review date forward but never push it back, and choose the review record.
3. **Atomic consume for all one-time secrets** (L-66, L-69, L-76, L-77): one small PR.
4. L-53 blank-name fix; L-38/L-39 freeze scope (a)/(b)/(c).
5. **L-81 session cap:** (a) tell the user why they were signed out, (b) raise the default to 5, or (c) both.
6. Shared helpers: password (L-47, L-58, L-67, L-80), bounded input fields (L-78, L-56, L-63, L-53, L-54, L-59), upload (L-64, U3, L-43).
7. L-30 one-line banner fix (twelfth request); L-79 copy fix; L-9, L-57, L-55, L-50, L-52, L-56, L-63, L-65, L-51, L-28/L-29, L-27, L-48, L-68.
8. Carried: E4, L-44, L-40, L-42, L-31/32/33 adviser confirmation, FATF snapshot, #417 (L-23), `github-advanced-security` 402 quota, role-prefixed finding IDs.

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_10_19.py` (this branch) plus `_18`, `_17`, `_16`, `_15`, `_14`, `_13`, `_12`, `_11`, `_10`, `_07` and `_06` from their lead branches. Place them in `repro_lead/` and use `PYTHONPATH=.:tests` (run `_06` from inside `repro_lead/`). Exit 1 means something was fixed; read the printed lines.
- Owed by the lead: nothing new beyond the re-runs. Every owed item to date is closed.
- Not yet checked, for whichever role picks it up: does the session cap (L-81) count mobile tokens separately; what message does a mobile user see after a password change (skeptic's point 3).
- Track landing in this order: L-46 (+L-74), L-53, L-38, L-70/L-72/L-73, L-66/L-69/L-76/L-77, L-50, L-43, L-30, L-9, L-57, L-47+L-58+L-67+L-80, L-78, L-52, L-55, L-56, L-64, L-65, L-63, L-79, L-81, L-54, L-28, L-29, L-51, L-48, L-27, L-40, L-44, L-21, L-75.
