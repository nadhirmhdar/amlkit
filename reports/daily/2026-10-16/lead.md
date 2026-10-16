# Lead consolidated report: 2026-10-16

## 1. Headline: AMBER
Master has not moved for ten days. Every carried finding, including the HIGH login-lockout DoS (L-46), still reproduces. Today's three new findings are all Low (feedback widget and identity-document scan input validation).

Master is `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (#426), the same SHA as the 10-15 lead report. `git log --oneline origin/master --since=2026-10-14` is empty. Roles report no PR opened or merged since #426; only draft #411 (docs) was touched. Red-team and mlro-user report new findings, so this is not a no-change run. Run date: 2026-10-16 UTC.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`99b467c`) | done (no-change) | GREEN. No new diff; CR-12, CR-4 (#417), CR-13/14/18, CR-1b still open | `ls-remote`, PR list | High |
| qa-regression (`92bfe76`) | done (no-change) | GREEN. Suite not re-run; the 10-07 result stands (2170 passed, 3 skipped) | `ls-remote`, `git log` | High |
| red-team (`4f635c9`) | done | AMBER. New area `/feedback`: output escaped and CSRF enforced, but no size or rate limit (F6) | probe script, evidence file, proposal | High (I reproduced F6) |
| compliance-specialist (`f48303c`) | done (no-change) | AMBER, unchanged. CS-2 and CS-13 most serious. Legal text still BLOCKED | `ls-remote` | High |
| mlro-user (`84670af`) | done | AMBER. New area document scan: auth/CSRF fine; S1 misleading "Scan complete", S2 no file check | HTTP driver plus JSON log | Medium-High (I confirmed by code; could not run the OCR path) |
| skeptic (`31dd5c3`) | done | AMBER. Confirmed F6, S1, S2 by code at Low; flagged the input-path pattern and reused IDs | file:line | High (I read the same lines) |

## 3. Consolidated findings
CONFIRMED means I re-ran a repro or read the cited lines on `0129848` today.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-63** `/feedback` has no length cap or rate limit (`app.py:2942-2978`) | LOW | red-team F6 (10-16), skeptic | CONFIRMED, Low | CONFIRMED: `F6 900 KB post status=200 stored message=900000 page=50000 rows=61; 60 rapid posts non-200=[] -> reproduces=True` | HELD `scripts/proposals/2026-10-16-new-findings.md` (red-team branch) |
| **L-64** scan endpoints accept any file type and size (`app.py:1898-1905`, `1935-1942`; no `validate_file_mime`) | LOW | mlro S2 (10-16), skeptic | CONFIRMED, Low | CONFIRMED by code. Not run: OCR stack absent here | HELD `scripts/proposals/2026-10-16-scan-upload-validation.md` (this branch) |
| **L-65** an unreadable scan shows "Scan complete (... fields extracted ...)" (`app.js:358-362`) | LOW | mlro S1 (10-16), skeptic | CONFIRMED, Low | CONFIRMED by code. The form stays empty, so the user can see nothing was filled | HELD, same file |
| L-61 "Open one to go straight to the alert" lands on the customer page | INFO | mlro NT2 | Info | **CONFIRMED (owed item):** `notifications.html:11` vs `notifications.py:62` (`/customers/{id}#alerts`); repro `NT2 ... reproduces=True` | Carry (copy fix) |
| L-62 unknown alert-queue filters are dropped without a message | INFO | mlro NT3 | Info | **CONFIRMED (owed item):** `app.py:2568-2570` coerces `sort`/`category`; repro `NT3 ... -> 200, mentions the bad value=False -> reproduces=True` | Carry |
| L-46 lockout counter not reset at expiry (`auth.py:376-404`) | **HIGH** | red-team A1 | High | CONFIRMED again (`A1 expired=(8, ...) after ONE wrong=(9, ...) ... reproduces=True`) | HELD `login-lockout-and-password-rules.md` §1 (10-11 lead branch). **Needs Nadhir** |
| L-53 blank `full_name` onboarded, screens clear | MEDIUM | mlro C1 | Medium | CONFIRMED again (`EN ... clear=True unscreenable=False ... reproduces=True`) | HELD `blank-name-and-sector-validation.md` (10-14 lead). **Needs Nadhir** |
| L-38 freeze/CNMR raised on non-UAE-list hits | MEDIUM-HIGH | compliance CS-2 | Med | CONFIRMED again (`CS-2 ... 'pending_execution' -> reproduces=True`) | HELD `freeze-list-scope-and-totp-replay.md` §1. **Needs Nadhir** |
| L-30 every re-screen shows "Re-screening failed: 'customers'" | MEDIUM | mlro G9 | Med | CONFIRMED again (`G9 ... reproduces=True`). **Ninth report** | HELD `rescreen-banner-and-realert.md` §1 |
| L-9 re-screen re-raises decided/pending alerts | MEDIUM | mlro G10, CS-3 | Med | CONFIRMED again (`new open alerts [3, 4], reproduces=True`) | HELD, same file §2 |
| L-43 same-name upload overwrites evidence | MEDIUM | red-team U1 | Med | Unchanged (no commit); not re-run | HELD `upload-overwrite-and-deadlines.md` §1 |
| L-50 UAE PASS CDD not tied to customer identity | MEDIUM-LOW | red-team C1 | Low/Med | Unchanged | HELD. **Needs Nadhir** |
| L-57 all non-Latin org names slug to `org` | LOW-MEDIUM | red-team R1 | Low/Med | CONFIRMED again (`R1 ... #2 ValueError ... reproduces=True`) | HELD (10-15 red-team proposal). **Needs Nadhir** |
| L-52 policy library advertises DOCX, rejects it | LOW-MEDIUM | mlro P1 | Low/Med | CONFIRMED again (`P1 real DOCX ... reproduces=True`) | HELD `policy-upload-docx.md`. **Needs Nadhir** |
| L-55 mobile PATCH downgrades risk without reason | LOW-MEDIUM | mlro C3 | Low/Med | Unchanged | **Needs Nadhir** (policy) |
| L-47 + L-58 weak passwords: admin reset 500, admin-create and register skip complexity | LOW | mlro OP1/OP2, red-team R2 | Low | CONFIRMED again (`OP1 status=500`, `OP2 account_created=True`, `R2 ... created`) | HELD, lockout file §2; one shared helper |
| L-56 one-letter canonical tokens make search return unrelated customers | LOW | mlro C4 | PLAUSIBLE→(lead CONFIRMED 10-15) | CONFIRMED again (`L-56 ... ['Q-001', 'Q-002'] ... reproduces=True`) | HELD `customer-search-canonical-substring.md` (10-15 lead) |
| L-54, L-51, L-48, L-40, L-27, L-44 | LOW | as 10-15 | Low | CONFIRMED again (`SEC`, `TA1`, `GR`, `M2`, `4E` via `_06` exit 0, `DL`/`DLA`, all `reproduces=True`) | HELD |
| L-59, L-60 | INFO | red-team R3, mlro NT1 | Info | PLAUSIBLE, unchanged | Carry |
| RT-P1, G1, P2, S1(UAE PASS, 10-12), S2(10-12), TA2, TA3, N1, U3, L-49, A2, OP3/OP4, L-28, L-29, L-21, L-45, E4/E5, L-39, L-41, L-42, L-34/35/36, L-37, L-31/32/33, L-5/L-20, L-14, H7/T1, L-23 (#417), L-3, L-6, L-10 to L-13, L-15, L-22, L-26, G3 to G8, F2b, CR-3, CR-14, CR-17 | as 10-15 | various | as 10-15 | Unchanged: no commit since 10-06 | Carry |

**Severity adjudication**
- L-63 (F6) is LOW. All roles agree. It needs a logged-in operator and the server's own form limit stops a single body over about 1 MB; the cost is DB, replica and audit-trail growth.
- L-64 (S2) is LOW, not Medium. The endpoints are authenticated and CSRF-guarded and store nothing; the risk is CPU/memory on the OCR path (decompression bomb not tested).
- L-65 (S1) is LOW. mlro-user's "AMBER (low)" and the skeptic's Low agree. Nothing is recorded as screened or verified from an empty scan, unlike L-53.
- ID collision: red-team's 10-16 `F6` and mlro-user's 10-16 `S1`/`S2` reuse earlier IDs. The lead L-numbers above are the canonical ones (L-63, L-64, L-65). No contradictions between roles today.

**FIXED on master:** none (no commits).

## 4. Combined assessment
1. Ten days without a commit; the HIGH (L-46) and every carried Medium re-reproduced today on `0129848`.
2. Today's new findings are Low input-validation gaps in two newly probed areas; both areas held up on auth, CSRF and output escaping.
3. The skeptic's table is right: only policy upload caps size. One upload helper (type, size, safe name) closes L-64, U3/DOC1 and L-43; one password helper closes L-47/L-58; one name/field validator closes L-53/L-54/L-59.
4. The HELD backlog (now about 21 proposals) needs decisions, not more probing.
5. Probing new areas keeps yielding only Lows; the value now is in landing fixes.

## 5. Corrections I made
- C-1 **Owed optional item done (L-61, L-62):** settled by file:line (§3) and added to the repro.
- C-2 Created `repro_lead/checks_2026_10_16.py` (F6, NT2, NT3). Temp DB, no network. Scratch venv from `requirements.txt` without passporteye and pdfminer, so S1/S2 (OCR) were not exercised and are confirmed by code only. Output on `0129848`:
  ```
  F6   900 KB post status=200 stored message=900000 page=50000 rows=61; 60 rapid posts non-200=[] -> reproduces=True
  NT2  copy says 'straight to the alert'=True; link is /customers/{id}#alerts=True -> reproduces=True
  NT3  /alerts?sort=bogus&category=bogus -> 200, mentions the bad value=False -> reproduces=True
  exit=0
  ```
- C-3 Created `scripts/proposals/2026-10-16-scan-upload-validation.md` (HELD): size cap plus `validate_file_mime` on both scan routes and an "nothing could be read" message. Notes that `validation.py:13` lists only three JPEG signatures. Not applied (route logic).
- C-4 Owed re-runs, all exit 0, nothing fixed. Copied from their lead branches into `repro_lead/`, run with `PYTHONPATH=.:tests`, copies removed before commit:
  `_06` (G9, L-9, 4E), `_07` (CS-2, M2), `_10` (DL, DLA), `_11` (A1, OP1, OP2, GR), `_12` (TA1), `_13` (P1), `_14` (EN, SEC), `_15` (L-56, R1, R2). Note: `_06` must be run from `repro_lead/` because it resolves the repo root from its own path.
- Not re-run: red-team `probe_feedback.py` (my repro covers F6), mlro-user driver (needs tesseract for the scan success path), skeptic scripts.
- No tests added: each would fail on master (rule 5). No existing file edited.
- Commit: see the final reply.

## 6. Decisions needed from Nadhir
1. **L-46 (HIGH): approve the lockout fix** (10-11 proposal §1).
2. **L-53 (MEDIUM): approve the blank-name fix** (10-14 proposal).
3. L-38/L-39 freeze scope: option (a), (b) or (c).
4. Approve the shared helpers: password (L-47, L-58), upload (L-64, U3, L-43), field validation (L-53, L-54, L-59).
5. L-57 slug fix choice; check whether a production org already holds slug `org`.
6. L-55 risk-downgrade reason/second review; L-50 identity matching; L-52 DOCX (a) or (b).
7. L-30 one-line banner fix (ninth request); L-9, L-56, L-63, L-65, L-51, L-28/L-29, L-27, L-48.
8. Carried: E4, L-44, L-40, L-42, L-31/32/33 adviser confirmation, FATF snapshot, #417 (L-23), `github-advanced-security` 402 quota, role-prefixed finding IDs (third day of collisions).

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_10_16.py` (this branch) and `_15`, `_14`, `_13`, `_12`, `_11`, `_10`, `_07`, `_06` from their lead branches, placed in `repro_lead/`, with `PYTHONPATH=.:tests`. Exit 1 means something was fixed; read the lines.
- Owed by the lead: none new. Optional: if a venv with tesseract is available, run the scan routes with an HTML file to confirm L-64 at runtime.
- Track landing in this order: L-46, L-53, L-38, L-50, L-43, L-30, L-9, L-57, L-47+L-58, L-52, L-55, L-56, L-64, L-65, L-63, L-54, L-28, L-29, L-51, L-48, L-27, L-40, L-44, L-21.
