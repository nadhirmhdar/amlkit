# Lead consolidated report: 2026-10-21

## 1. Headline: AMBER
Master has not moved for fifteen days. No new defect raises the overall risk. Red-team showed the image-bomb (L-82) also hits the mobile Emirates ID route. mlro-user re-found the HIGH lockout DoS (L-46) and turned up a Low account-enumeration leak (L-86). Every carried item still reproduces.

Master is `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (#426), the same as the 10-20 lead report. `git log 0129848..origin/master` is empty. Roles report no PR opened or merged since #426; only draft #411 (docs) was updated. Red-team and mlro-user report findings, so this is not a no-change run. Run date: 2026-10-21 UTC.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`70d9f56`) | done (no-change) | GREEN. No new diff. CR-12, CR-4 (#417), CR-13/14/18, CR-1b open | `ls-remote`, PR list | High |
| qa-regression (`ca2f8f0`) | done (no-change) | GREEN. Suite not re-run; the 10-07 result stands (2170 passed, 3 skipped) | `ls-remote`, `git log` | High |
| red-team (`3d7701a`) | done | AMBER. B1 extended: mobile Emirates ID scan peaks at 1.2 GB and web passport at 1.6 GB on a 97 KB PNG. B2: the web passport route accepts an `MZ` blob. A PDF with a 14400 pt page peaks at only 732 MB | probe script + evidence file + HELD proposal | High |
| compliance-specialist (`ea75d41`) | done (no-change) | AMBER, unchanged. CS-2 and CS-13 are the most serious; legal text still BLOCKED | `ls-remote` | High |
| mlro-user (`ed44eb9`) | done | AMBER. LG1 lock any account by email, LG2 enumeration, LG3 empty-password 422, LG4 no 429 seen | HTTP driver + JSON logs | High for LG1 to LG3. LG4 is an artefact of its own driver (see §3) |
| skeptic (`ff577b6`) | done | AMBER. B1/B2 CONFIRMED by code. LG1 is a duplicate of A1 (High). LG2 CONFIRMED Low. LG3 Info. LG4 PLAUSIBLE | file:line, no re-runs | High, except its claim that no test asserts 429 on `/login`, which is wrong (§3) |

## 3. Consolidated findings
CONFIRMED means I re-ran a repro or read the cited lines on `0129848` today.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-46** lockout counter not reset at expiry; anyone who knows an email can keep that account locked (now also mlro LG1) | **HIGH** | red-team A1, skeptic, mlro LG1 | High (dup) | CONFIRMED by code (`auth.py:71-72`, `:376-383`) and by mlro's log (lock from attempt 9, correct password refused). Last lead re-run of `lockout_persistence` was 10-20 | HELD `login-lockout-and-password-rules.md` (10-11) §1. **Needs Nadhir** |
| **L-86** (new) the lock message reveals that an email exists and names the retry time. The `login()` docstring promises the opposite (`auth.py:347-351` vs `:380-383`) | LOW | mlro LG2 | Low | CONFIRMED: `LG2 9 bad logins: real email -> 'Account locked after repeated failed att'...; unknown email -> 'Incorrect email or password.'` | HELD `2026-10-21-lockout-message-and-empty-password.md`. Ship with L-46 |
| **L-87** (new) an empty password gives a raw 422 JSON (`app.py:608`, required `Form()`) | INFO | mlro LG3 | Info | CONFIRMED: `LG3 empty password -> 422 application/json` | HELD same file |
| LG4 "declared rate limits never return 429" | n/a | mlro LG4 | PLAUSIBLE | **REFUTED**. `mlro_user_drive.py:20` sets `app.state.limiter.enabled = False`. With the limiter on: `[200 x10, 429, 429]`. `tests/test_p23_login_rate_limit_10_per_min.py` and `tests/test_rate_limiting.py` already assert 429 on `/login` | Closed |
| **L-82** scan uploads: no byte cap, no pixel cap, no limiter; web passport skips MIME (now includes red-team B1-ext and B2) | **MEDIUM** | red-team B1/B2, skeptic | Medium; B2 Low/Med | CONFIRMED again: `B1w ... peak RSS +1452 MB`, `B1m ... 30 MB junk -> 200`. Red-team adds mobile `scan-emirates-id` at 1.2 GB | HELD `2026-10-20-upload-image-guard-and-audit-paging.md` §1 (covers B2 already). **Needs Nadhir** |
| L-83, L-84, L-85 (audit paging, 403 copy, privacy cookies) | LOW / INFO / LOW | mlro, skeptic | as 10-20 | CONFIRMED again (`AU1 500`, `AU2 200`, `AU3`, `PV1` all `reproduces=True`) | HELD same file §2-§4 |
| L-73 unrelated re-assessment clears an overdue review | MEDIUM | lead | n/a | CONFIRMED again (`RV ... next_review=2029-10-05`) | HELD. **Needs Nadhir** |
| L-38 freeze/CNMR raised on non-UAE-list hits | MEDIUM-HIGH | compliance CS-2 | Med | CONFIRMED again (`CS-2 ... 'pending_execution'`) | HELD. **Needs Nadhir** |
| L-53 blank `full_name` screens clear | MEDIUM | mlro C1 | Medium | CONFIRMED again (`EN ... clear=True`) | HELD. **Needs Nadhir** |
| L-30 / L-9 rescreen banner, re-raised alerts | MEDIUM | mlro, compliance | Med | CONFIRMED again (`new open alerts [3, 4]`) | HELD |
| L-66, L-69, L-76, L-77 one-time secrets consumed concurrently | LOW-MED … INFO | red-team, skeptic, lead | Medium | CONFIRMED again (`T1m operators=10`, `T1w operators=10`, `BC [True, True]`, `EV [5,5,5,5,5]`, `US [5,5,5,5,5]`) | HELD. **Needs Nadhir** |
| L-78, L-79, L-80, L-81, L-75 | LOW / LOW / INFO / LOW / INFO | red-team, mlro | as before | CONFIRMED again (`S3w`, `S3m`, `PW1`, `PW2`, `L75`) | HELD |
| L-67, L-47+L-58, L-57, L-52, L-56, L-63, L-61, L-62, L-54, L-51, L-48, L-40, L-27, L-44 | LOW / INFO | various | as before | CONFIRMED again (`T2`, `OP1 500`, `R1`, `R2`, `P1`, `F6`, `NT2`, `NT3`, `SEC`, `TA1`, `GR`, `M2`, `4E`, `DL`, `DLA`) | HELD / carry |
| L-74, L-70/L-72/L-71, L-43, L-50, L-55, L-68, L-64, L-65, L-59, L-60 and the 10-16 carry list | as before | various | as before | Unchanged: no commit | Carry |

**Severity adjudication**
- LG1 / L-46: mlro-user says Medium and the skeptic says High. I keep **HIGH**. mlro-user waited out no expiry. The 10-11 repro shows that after expiry one wrong attempt re-locks the account, so the lock lasts indefinitely, not 15 minutes, and the locked account can be the only MLRO. The per-account limit (3/min) slows the first lock but does not stop the re-lock.
- L-86 LOW. It only confirms that an email exists, and it needs 8 or more attempts that themselves lock the account. Fix it with L-46.
- B2 stays inside L-82, as on 10-20 (the lead already logged the missing MIME check there). Red-team rates it Low, the skeptic Low/Med. It has no impact of its own beyond letting more junk reach the decoder, so there is no separate id.
- Duplicates: LG1 = A1 = L-46. B1-ext and B2 = L-82. Contradiction: the skeptic says "no test asserts a 429 on `/login`". Refuted by the two test files above.

**FIXED on master:** none (no commits). Closed today: LG4 (refuted). Also partly closed: the "PDF variant of L-82" from 10-20 §7. Red-team measured 732 MB / 6.7 s for one PDF shape, so PDFs are not a comparable amplifier. That result stays PLAUSIBLE for other shapes.

## 4. Combined assessment
1. Fifteen days without a commit. All 13 carried lead scripts exit 0 on `0129848`, so nothing has been fixed.
2. Today's new items are both on the login path and both fold into the L-46 fix: one PR for the counter reset, the neutral message and the admin unlock.
3. The rate limiter does work. Its existence does not reduce L-46.
4. L-82 now covers every scan route. The 10-20 shared-helper proposal already covers all of them.
5. The backlog needs decisions, not more probing.

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_10_21.py`: LG2 (L-86), LG3 (L-87), plus an LG4 refutation check that does not count towards the exit code. It uses a temp DB and TestClient, with no network. Output on `0129848`:
  ```
  LG2 9 bad logins: real email -> 'Account locked after repeated failed att'...; unknown email -> 'Incorrect email or password.' -> reproduces=True
  LG3 empty password -> 422 application/json -> reproduces=True
  LG4 limiter ON, 12 POST /login one client, distinct emails -> [200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 429, 429] -> 429 seen=True (finding refuted if True)
  2/2 reproduce
  exit=0
  ```
- C-2 Created `scripts/proposals/2026-10-21-lockout-message-and-empty-password.md` (HELD). It holds the L-86 neutral message (option a or b) and the L-87 `Form()` defaults. Not applied, because both are auth/route changes.
- C-3 Owed by the 10-20 "Next run": re-runs of `_20`, `_19`, `_18`, `_17`, `_16`, `_15`, `_14`, `_13`, `_12`, `_11`, `_10`, `_07` and `_06` (`_06` run from inside `repro_lead/`). Scratch venv from `requirements.txt` plus `passporteye`; no tesseract, no pdfminer. **All exit 0.** The quoted lines are in §3. I copied them from their lead branches and removed them before committing.
- Not re-run: red-team `probe_scan_variants.py` (my `_20` B1w covers the mechanism and keeps this sandbox safe), the mlro driver, the skeptic scripts.
- No tests added, because each would fail on master (rule 5). No existing file edited.

## 6. Decisions needed from Nadhir
1. **L-46 (HIGH) + L-86: approve one lockout PR.** It covers the counter reset at expiry (10-11 §1), the neutral lock message (today's option a, or b if operators should be told they are locked), and an admin unlock that also clears the MFA lock (L-74).
2. **L-82 (MEDIUM): approve the shared scan-upload guard** (10-20 §1). Also confirm the production memory limit and instance count, and say whether roles below MLRO may scan.
3. Periodic review (L-70/L-72/L-73): event re-ratings may bring the review date forward but never push it back.
4. Atomic consume for one-time secrets (L-66, L-69, L-76, L-77): one small PR.
5. L-53 blank name; L-38/L-39 freeze scope (a)/(b)/(c); L-81 session cap.
6. L-85 privacy-page wording.
7. Shared helpers: password (L-47, L-58, L-67, L-80), bounded inputs (L-78, L-83, L-56, L-63, L-53, L-54, L-59), uploads (L-82, L-64, U3, L-43).
8. Carried: L-30 one-line banner fix (fourteenth request), L-9, L-79, the Low list, E4, L-44, L-40, L-42, L-31/32/33 adviser confirmation, FATF snapshot, #417 (L-23), the `github-advanced-security` 402 quota, a single de-duplicated finding register.

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_10_21.py` (this branch) plus `_20`, `_19`, `_18`, `_17`, `_16`, `_15`, `_14`, `_13`, `_12`, `_11`, `_10`, `_07` and `_06` from their lead branches. Place them in `repro_lead/` and use `PYTHONPATH=.:tests` (run `_06` from inside `repro_lead/`). `_20` needs `pip install passporteye`. Exit 1 means something was fixed; read the printed lines.
- Owed by the lead: nothing new beyond the re-runs.
- Not yet checked, for whichever role picks it up: the web trade-licence and legal-person scan routes (same pattern by code, not run); other PDF shapes for L-82; the L-81 mobile-token question; lock expiry plus the admin unlock route, end to end over HTTP.
- Track landing in this order: L-46 (+L-74, L-86), L-82, L-53, L-38, L-70/L-72/L-73, L-66/L-69/L-76/L-77, L-50, L-43, L-30, L-9, L-57, L-47+L-58+L-67+L-80, L-78, L-83, L-52, L-55, L-56, L-64, L-65, L-63, L-79, L-85, L-81, L-54, L-28, L-29, L-51, L-48, L-27, L-40, L-44, L-21, L-75, L-84, L-87.
