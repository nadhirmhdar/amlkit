# Lead consolidated report: 2026-10-17

## 1. Headline: AMBER
Master has not moved for eleven days; the HIGH lockout DoS (L-46) and every carried Medium still reproduce, and today adds one race-condition class (one-time setup tokens and MFA backup codes can be consumed more than once) plus a Medium workflow gap (no web way to complete a periodic review).

Master is `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (#426), the same SHA as the 10-16 lead report. `git log 0129848..origin/master` is empty; roles report no PR opened or merged since #426 (only draft #411, docs, touched). Red-team and mlro-user report new findings, so this is not a no-change run. Run date: 2026-10-17 UTC.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`4c9c8e1`) | done (no-change) | GREEN. No new diff; CR-12, CR-4 (#417), CR-13/14/18, CR-1b open | `ls-remote`, PR list | High |
| qa-regression (`44b25a9`) | done (no-change) | GREEN. Suite not re-run; 10-07 result stands (2170 passed, 3 skipped) | `ls-remote`, `git log` | High |
| red-team (`907e286`) | done | AMBER. Mobile unauth routes: setup token claimable many times concurrently (T1), setup input gaps (T2), no rate limit on token routes (T3) | probe script + evidence file + HELD proposal | High (I reproduced T1 mobile and web, and T2) |
| compliance-specialist (`4779b10`) | done (no-change) | AMBER, unchanged. CS-2, CS-13 most serious; legal text BLOCKED | `ls-remote` | High |
| mlro-user (`7ca0aae`) | done | AMBER. Periodic review: no web action completes it (PR1), no reviewer attestation (PR2), case file lacks overdue flag (PR3) | HTTP driver + JSON log; overdue state simulated by DB edit | High (confirmed by code) |
| skeptic (`733b42d`) | done | AMBER. Confirmed T1 for web too by reading; T1 → Low/Med; raised the backup-code race as missed | file:line, no new script | High (I ran what it read) |

## 3. Consolidated findings
CONFIRMED means I re-ran a repro or read the cited lines on `0129848` today.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-66** setup token claimable concurrently; N operators (MLRO) per token, mobile `mobile.py:448-472` and web `cases/operators.py:111-140` | LOW-MEDIUM | red-team T1 | CONFIRMED (both), Low/Med | CONFIRMED: `T1m ... operators=10`, `T1w ... operators=10`, 3/3 runs | HELD red-team `scripts/proposals/2026-10-17-new-findings.md` §T1. **Needs Nadhir** |
| **L-67** mobile `/auth/setup`: duplicate email → 500 (token unused), no email format check, no complexity, blank name | LOW | red-team T2 | CONFIRMED, Low | CONFIRMED: `T2 existing email -> 500, token still unused=True; 'not-an-email' -> 200, created=True` | HELD red-team proposal §T2; fold into the password helper (L-47/L-58) |
| **L-68** no rate limit on `verify-email`, `resend-verification`, `GET /auth/setup` | INFO | red-team T3 | Info | PLAUSIBLE→CONFIRMED by red-team evidence file (120×, no 429); not re-run | HELD red-team proposal §T3 |
| **L-69** one MFA backup code usable twice concurrently (`auth.py:839-859`) | LOW | skeptic (missed-by-team #1) | suggested, not run | CONFIRMED: `BC same backup code used twice concurrently: results=[True, True]`, 3/3 | HELD `scripts/proposals/2026-10-17-backup-code-and-periodic-review.md` §1 (this branch) |
| **L-70** no web action completes a periodic CDD review; only mobile `POST /customers/{id}/risk` (`mobile.py:772`) | MEDIUM | mlro PR1 | CONFIRMED, Medium | CONFIRMED by code (`app.py:2201-2533` route list). Extra, PLAUSIBLE: `model.py:196` resets `next_review` on every re-assess, and web transactions/adverse-media dispositions re-assess (`manager.py:818`, `1337`), so the flag can clear with no review done | HELD same file §2. **Needs Nadhir** (record format) |
| **L-72** completing a review leaves no reviewer/outcome/note, only `risk.assess` | LOW-MEDIUM | mlro PR2 | Low/Med | CONFIRMED (mlro log; same shape as L-55) | HELD same file §2 (one fix with L-70) |
| **L-71** case file shows due date with no overdue marker (`customer.html:142`) | INFO | mlro PR3 | Info | CONFIRMED by code | HELD same file §3 |
| L-46 lockout counter not reset at expiry (`auth.py:376-404`) | **HIGH** | red-team A1 | High | CONFIRMED again (`A1 expired=(8,...) after ONE wrong=(9,...) ... reproduces=True`) | HELD 10-11 lead `login-lockout-and-password-rules.md` §1. **Needs Nadhir** |
| L-53 blank `full_name` onboarded, screens clear | MEDIUM | mlro C1 | Medium | CONFIRMED again (`EN ... clear=True ... reproduces=True`) | HELD 10-14 lead. **Needs Nadhir** |
| L-38 freeze/CNMR on non-UAE-list hits | MEDIUM-HIGH | compliance CS-2 | Med | CONFIRMED again (`CS-2 ... 'pending_execution' -> reproduces=True`) | HELD `freeze-list-scope-and-totp-replay.md` §1. **Needs Nadhir** |
| L-30 every re-screen shows "Re-screening failed: 'customers'" | MEDIUM | mlro G9 | Med | CONFIRMED again (`G9 ... reproduces=True`); tenth report | HELD `rescreen-banner-and-realert.md` §1 |
| L-9 re-screen re-raises decided alerts | MEDIUM | mlro G10, CS-3 | Med | CONFIRMED again (`new open alerts [3, 4], reproduces=True`) | HELD same file §2 |
| L-43 same-name upload overwrites evidence | MEDIUM | red-team U1 | Med | Unchanged (no commit); not re-run | HELD |
| L-50 UAE PASS CDD not tied to customer identity | MEDIUM-LOW | red-team C1 | Low/Med | Unchanged | HELD. **Needs Nadhir** |
| L-57 non-Latin org names slug to `org` | LOW-MEDIUM | red-team R1 | Low/Med | CONFIRMED again (`R1 ... #2 ValueError`) | HELD. **Needs Nadhir** |
| L-52 policy library rejects DOCX | LOW-MEDIUM | mlro P1 | Low/Med | CONFIRMED again (`P1 ... reproduces=True`) | HELD. **Needs Nadhir** |
| L-55 mobile PATCH downgrades risk without reason | LOW-MEDIUM | mlro C3 | Low/Med | Unchanged | **Needs Nadhir** |
| L-47 + L-58 weak passwords / admin reset 500 | LOW | mlro OP1/OP2, red-team R2 | Low | CONFIRMED again (`OP1 status=500`, `OP2 account_created=True`, `R2 ... created`) | HELD lockout file §2 (now also covers L-67) |
| L-56 one-letter tokens in customer search | LOW | mlro C4 | Low | CONFIRMED again (`L-56 ... ['Q-001', 'Q-002']`) | HELD |
| L-63, L-61, L-62 | LOW / INFO | red-team F6, mlro NT2/NT3 | Low/Info | CONFIRMED again (`F6`, `NT2`, `NT3 ... reproduces=True`) | HELD / carry |
| L-54, L-51, L-48, L-40, L-27, L-44 | LOW | as 10-16 | Low | CONFIRMED again (`SEC`, `TA1`, `GR`, `M2`, `4E`, `DL`/`DLA`) | HELD |
| L-64, L-65 | LOW | mlro S2/S1 | Low | Unchanged, by code (OCR stack absent) | HELD 10-16 lead |
| L-59, L-60, and the 10-16 "carry" list (RT-P1 … CR-17) | as 10-16 | various | as 10-16 | Unchanged: no commit since 10-06 | Carry |

**Severity adjudication**
- L-66 (T1) is LOW-MEDIUM, between red-team's Medium and skeptic's Low/Med. The holder of a valid token is already entitled to one MLRO account in that org, so there is no privilege gain; the harm is that a leaked link yields several persistent accounts (deactivating one leaves the rest) and the "one-time" guarantee is false. Red-team's "web: PLAUSIBLE" is upgraded to CONFIRMED by my run.
- L-69 is LOW: needs the password plus a real backup code; it only lets one spent code mint a second session in the race window.
- L-70 is MEDIUM (mlro and skeptic agree): periodic review is an ongoing-monitoring duty and the desktop UI has no way to discharge it. My code reading adds that unrelated web events can silently reset the clock, which makes the gap worse, not better; I mark that part PLAUSIBLE until run.
- L-72 raised from mlro's low to LOW-MEDIUM with the skeptic: it is the audit-evidence half of L-70 and should land with it.
- No contradictions between roles. Duplicates: L-67 is a fifth instance of the missing password helper (L-47/L-58). Red-team T1/T2/T3 and mlro PR1-3 reuse earlier role IDs; L-numbers above are canonical.

**FIXED on master:** none (no commits).

## 4. Combined assessment
1. Eleven days without a commit; the HIGH (L-46) and all carried Mediums re-reproduced on `0129848` today.
2. New class: check-then-act on one-time secrets (setup tokens, backup codes). One idiom, `UPDATE ... WHERE used_at IS NULL` + rowcount check, fixes both; email-verify and UAE PASS state consumers are unchecked.
3. New Medium: periodic CDD review cannot be completed or attested from the web UI (L-70/L-72).
4. Mobile/web duplication keeps producing divergent behaviour (L-66 web+mobile, L-67, L-70): one service function per operation would close the class.
5. The HELD backlog (~23 proposals) needs decisions; probing new areas keeps finding real but mostly Low items.

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_10_17.py` (T1 mobile, T1 web, T2, backup-code race). Temp DB, no network. Scratch venv from `requirements.txt` without passporteye/pdfminer (OCR not exercised). Output on `0129848`, identical in 3 runs:
  ```
  T1m 10 concurrent mobile claims of one token: statuses=[200, 200, 200, 200, 200, 200, 200, 200, 200, 200] operators=10 -> reproduces=True
  T1w 10 concurrent complete_initial_setup calls on one token: results=['ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'ok'] operators=10 -> reproduces=True
  T2  existing email -> 500, token still unused=True; 'not-an-email' -> 200, created=True -> reproduces=True
  BC  same backup code used twice concurrently: results=[True, True] -> reproduces=True
  exit=0
  ```
- C-2 Created `scripts/proposals/2026-10-17-backup-code-and-periodic-review.md` (HELD): atomic backup-code consume diff (L-69), a shared `complete_periodic_review` service + web route with attestation (L-70/L-72), overdue tag on the case file (L-71). Not applied: auth and route logic.
- C-3 Owed re-runs (10-16 "Next run"), all exit 0, nothing fixed: `_06` (G9, L-9, 4E; run from `repro_lead/`), `_07` (CS-2, M2), `_10` (DL, DLA), `_11` (A1, OP2, OP1, GR), `_12` (TA1), `_13` (P1), `_14` (EN, SEC), `_15` (L-56, R1, R2), `_16` (F6, NT2, NT3). Copied from their lead branches into `repro_lead/`, run with `PYTHONPATH=.:tests`, copies removed before commit.
- Optional owed item (L-64 runtime with tesseract): not done; no OCR stack in this environment.
- Not re-run: red-team `probe_mobile_unauth.py` (needs PR #412 fixtures; my C-1 covers T1/T2), mlro driver (L-70 confirmed by code), skeptic scripts.
- No tests added: each would fail on master (rule 5). No existing file edited.

## 6. Decisions needed from Nadhir
1. **L-46 (HIGH): approve the lockout fix** (10-11 proposal §1).
2. **L-66 + L-69: approve the atomic-claim fix** for setup tokens and backup codes (red-team 10-17 proposal §T1, this branch's proposal §1). Small and self-contained.
3. **L-70/L-72: choose the periodic-review record** (outcome list, mandatory note) and whether incidental re-assessments may move `next_review`.
4. L-53 blank-name fix; L-38/L-39 freeze scope (a)/(b)/(c).
5. Shared helpers: password (L-47, L-58, L-67), upload (L-64, U3, L-43), field validation (L-53, L-54, L-59).
6. L-57 slug; L-55; L-50; L-52 DOCX.
7. L-30 one-line banner fix (tenth request); L-9, L-56, L-63, L-65, L-51, L-28/L-29, L-27, L-48, L-68.
8. Carried: E4, L-44, L-40, L-42, L-31/32/33 adviser confirmation, FATF snapshot, #417 (L-23), `github-advanced-security` 402 quota, role-prefixed finding IDs.

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_10_17.py` (this branch) and `_16`, `_15`, `_14`, `_13`, `_12`, `_11`, `_10`, `_07`, `_06` from their lead branches, placed in `repro_lead/`, `PYTHONPATH=.:tests` (`_06` from inside `repro_lead/`). Exit 1 means something was fixed; read the lines.
- Owed by the lead: run the L-70 incidental-reset path (adverse-media disposition or a transaction alert on an overdue customer, check `next_review` moves) to settle the PLAUSIBLE part; check `email_verify_tokens` and `uaepass_states` consumers for the same check-then-act shape as L-66/L-69.
- Track landing in this order: L-46, L-53, L-38, L-70/L-72, L-66/L-69, L-50, L-43, L-30, L-9, L-57, L-47+L-58+L-67, L-52, L-55, L-56, L-64, L-65, L-63, L-54, L-28, L-29, L-51, L-48, L-27, L-40, L-44, L-21.
