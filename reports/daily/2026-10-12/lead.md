# Lead consolidated report: 2026-10-12

## 1. Headline: AMBER
Master has not moved for six days. Today's new finding is **MEDIUM-LOW**: one UAE PASS login can be used to "verify" any customer, and its Emirates ID is then copied onto that customer's record (C1). Every carried finding, including the HIGH login-lockout DoS (L-46), still reproduces.

Master is `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (#426), the same SHA as the 10-11 lead report. `git log 0129848..origin/master` is empty. Code-reviewer, QA and compliance report no PR opened or merged since #426 (only draft #411, docs, was updated). Red-team and mlro-user report new findings, so this is not a no-change run. Run date: 2026-10-12 UTC.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`190dbd4`) | done (no-change) | GREEN. No new diff. CR-12, CR-4 (in #417), CR-13, CR-14, CR-18 and CR-1b still open | `ls-remote`, PR list | High |
| qa-regression (`7f3eff1`) | done (no-change) | GREEN. Suite not re-run; the 10-07 result (2170 passed / 3 skipped) stands | `ls-remote`, `git log` | High |
| red-team (`b30ab55`) | done | AMBER. C1 (Med): UAE PASS verification is not tied to the customer's identity. S1 (Info): SSO ignores the password lockout. S2 (Info): the SOP2 email claim is trusted. State, cookie, org and customer binding are clean | `probe_uaepass.py` plus an evidence file; HELD proposal | High (I re-ran it) |
| compliance-specialist (`7f0f4f9`) | done (no-change) | AMBER unchanged; CS-2 and CS-13 are the most serious. Legal text still BLOCKED | `ls-remote` | High |
| mlro-user (`5026978`) | done | AMBER. Documents and cross-org isolation hold. TA1: a transaction alert can be closed with no note. TA2, TA3, DOC1, DOC2 and N1 are Low or Info | HTTP driver plus JSON log | High |
| skeptic (`3dd8f8c`) | done | AMBER. C1 CONFIRMED, partly mitigated (Med→Low/Med). TA1 partly by design (Low). DOC1/DOC2 duplicate U3. Calls for one lockout policy across password, MFA and SSO | file:line reads, no new script | Medium-High (read only, no run) |

## 3. Consolidated findings
CONFIRMED means I re-ran a repro or read the cited lines on `0129848` today.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-50 (C1)** UAE PASS customer verification is not tied to the customer's identity. There is no name, nationality or ID comparison and no duplicate-IDN check, and `id_number`/`id_type` are backfilled from whichever login completes the flow (`cases/manager.py:948-1008`) | **MEDIUM-LOW** | red-team C1, skeptic | CONFIRMED, Low/Med | CONFIRMED (re-ran `probe_uaepass.py`, exit 0: `verifications: [(4, 'OPERATOR-OWN-UUID', 'Zed Unrelated'), (5, 'OPERATOR-OWN-UUID', 'Zed Unrelated')]`; both customers now have `'784199012345678', 'emirates_id'`) | HELD in red-team branch `scripts/proposals/2026-10-12-new-findings.md` §C1. **Needs Nadhir** |
| L-51 (TA1) a transaction alert can be closed as false positive with a blank note; stored `disposition=NULL` (`manager.py:822-846`) | LOW | mlro TA1, skeptic | partly by design, Low | CONFIRMED (`repro_lead/checks_2026_10_12.py`: `TA1 large_cash alert closed with blank note -> status=false_positive disposition=None -> reproduces=True`). The missing four-eyes is documented as deliberate (`:825-827`). The blank note is not | HELD `scripts/proposals/transaction-alert-disposition-note.md` |
| S1 SSO ignores `locked_until` | INFO | red-team S1, skeptic | Info | CONFIRMED (probe: `password-LOCKED ... SSO login -> 303 / | session issued: True`; my `checks_2026_10_11.py` `SSO ... True`). It does not mitigate L-46 for real operators while only sandbox credentials exist | Fold into L-46 decision |
| S2 SOP2 email claim trusted for linking | INFO | red-team S2 | PLAUSIBLE | PLAUSIBLE (policy documented in CLAUDE.md; whether UAE PASS verifies the claim is external) | Carry |
| TA2 no next step after a true positive; TA3 raw error text | INFO | mlro | Info | Accept the skeptic | Carry |
| DOC1 27 MB upload accepted; DOC2 free-text `doc_type` | LOW | mlro | duplicate | **Duplicate of red-team U3 (10-10)**; not a new item | Merged into U3 |
| N1 20,000-char case note | LOW | mlro | Low | PLAUSIBLE (HTTP log only, not re-run) | Carry |
| **L-46** lockout counter not reset at expiry: one wrong password every 15 min keeps an account locked (`auth.py:376-404`) | **HIGH** | red-team A1, skeptic (10-11) | High | CONFIRMED again (`A1 expired=(8, ...) after ONE wrong=(9, ...) ... reproduces=True`) | HELD `login-lockout-and-password-rules.md` §1 (10-11 lead branch). **Needs Nadhir** |
| L-47 weak admin reset → 500; admin create skips strength rule | LOW | mlro, skeptic | Low | CONFIRMED again (`OP1 status=500`, `OP2 account_created=True`) | HELD, same file §2 |
| L-48 any org's MLRO `/admin/refresh` writes their name into every org's audit | LOW | lead | n/a | CONFIRMED again (`GR ... actors=['Alice Lead', 'Bob Other'] reproduces=True`) | HELD, same file §3 |
| L-38 freeze/CNMR on non-UAE-list hits | MEDIUM-HIGH | compliance CS-2 | Med | CONFIRMED again (`CS-2 ... 'pending_execution' -> reproduces=True`) | HELD `freeze-list-scope-and-totp-replay.md` §1. **Needs Nadhir** |
| L-40 TOTP replay | LOW | red-team M2 | Low | CONFIRMED again (`M2 first=True second=True`) | HELD |
| L-30 "Re-screening failed: 'customers'" banner | MEDIUM | mlro G9 | Med | CONFIRMED again (`G9 ... reproduces=True`). **Fifth report** | HELD `rescreen-banner-and-realert.md` §1 |
| L-9 rescreen re-alerts decided/pending matches | MEDIUM | mlro G10, CS-3 | Med | CONFIRMED again (`new open alerts [3, 4], reproduces=True`) | HELD, same file §2 |
| L-27 four-eyes legacy NULL-id residual | LOW | CR-1b, N8, CS-18 | Low | CONFIRMED again (`legacy NULL-operator_id row ... completed`) | HELD |
| L-44 deadline API (PATCH ignores `due_date`; update/delete unaudited) | LOW | mlro, skeptic | Low | CONFIRMED again (`DL ... reproduces=True`, `DLA ... ['compliance.deadline_created'] reproduces=True`) | HELD `upload-overwrite-and-deadlines.md` §2 |
| L-43 same-name upload overwrites evidence | MEDIUM | red-team U1 | Med | Unchanged (no commit); not re-run | HELD, same file §1 |
| L-49, A2, OP3/OP4, L-28, L-29, L-21, L-45, U3/E4/E5, L-39, L-41, L-42, L-34/35/36, L-37, L-31/32/33, L-5/L-20, L-14, H7/T1, L-23 (#417), L-3, L-6, L-10 to L-13, L-15, L-22, L-26, G3 to G8, F2b, CR-3, CR-14, CR-17 | as 10-11 | various | as 10-11 | Unchanged: no commit since 10-06 | Carry |

**Severity adjudication**
- **C1 (L-50) is MEDIUM-LOW, between red-team's Medium and the skeptic's Low/Med.** The skeptic is right that the case-file page shows the UAE PASS identity's own name, so a careful reader can spot a mismatch, and that it needs an insider. But the backfill writes a wrong Emirates ID into the customer's `id_number`, and later screening, exports and goAML reports use that field. Nothing marks it as coming from a mismatched identity. A wrong ID on an STR is worse than a cosmetic mismatch. It is not Medium because the flow is only reachable with sandbox credentials today (CLAUDE.md, #378), so no real customer record can be affected yet. It must be fixed before real UAE PASS credentials go live.
- **TA1 (L-51) is LOW.** I agree with the skeptic: four-eyes is a documented scope decision. A required note is a one-line fix that an examiner would expect.
- **DOC1/DOC2 are not new.** They are red-team U3 (10-10), as the skeptic said. They do not add to the count.

**FIXED on master:** none (no commits).

## 4. Combined assessment
1. Six days without a commit. Every carried Medium and the HIGH (L-46) re-reproduced today on `0129848`.
2. The new UAE PASS defect (L-50) is a gate for going live: identity matching and a duplicate-IDN check must land before real credentials replace the sandbox ones.
3. The UAE PASS state, cookie, org and customer binding held under every replay and cross-binding attempt. Documents and cross-org isolation also held.
4. The roles are rediscovering each other's findings (DOC1/DOC2 = U3; OP1 = F11). The backlog is stable at about 15 HELD proposals waiting on decisions.
5. The suite was not re-run. No code changed since the 10-07 result (2170 passed).

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_10_12.py` (TA1). Output on `0129848`, scratch venv (`requirements.txt` minus passporteye/pdfminer; OCR not exercised; no network):
  ```
  TA1  large_cash alert closed with blank note -> status=false_positive disposition=None -> reproduces=True
  exit=0
  ```
- C-2 Created `scripts/proposals/transaction-alert-disposition-note.md` (HELD; a two-line guard in `disposition_transaction_alert`). It changes business logic, so it is not applied. Callers to check: `api/app.py:2377`, `api/mobile.py:982`, and `tests/test_kyt.py:265`.
- C-3 Re-ran red-team `repro_redteam/probe_uaepass.py` with the PR #412 seed (`repro/make_seed.py`). Exit 0; sections 1-4 match the red-team evidence file line for line (output quoted in §3).
- C-4 Owed re-runs, all exit 0 (nothing fixed): `checks_2026_10_11.py` (A1, SSO, OP1, OP2, GR), `checks_2026_10_10.py` (DL, DLA), `checks_2026_10_07.py` (CS-2, M2), `checks_2026_10_06.py` (G9, L-9, 4E). I ran each from a temporary copy with `PYTHONPATH=.:tests` and removed the copies before committing.
- No tests added: each would fail on master (rule 5). No existing file edited. Only the three files above are committed. The commit SHA is in the final reply.

## 6. Decisions needed from Nadhir
1. **L-46 (HIGH, carried): approve the lockout fix** (10-11 proposal §1). Per the skeptic, settle one policy for password, MFA and SSO lockout at the same time, and decide whether SSO staying open during a password lock is a supported break-glass.
2. **L-50 (new): approve identity matching plus a duplicate-IDN check** for UAE PASS customer verification, and confirm that no backfill happens from a mismatched profile. This must happen before real UAE PASS credentials are used.
3. L-51: approve the required-note guard.
4. L-38 / L-39 freeze scope, option (a), (b) or (c).
5. L-43 unique-key fix, plus `gsutil versioning get` on the documents bucket.
6. L-30 one-line banner fix (fifth request); L-9, L-28/L-29, L-27; L-47 and L-48.
7. Carried: E4 (open an exported Arabic CSV in Excel), L-44, L-40, L-42, L-31/32/33 adviser confirmation, FATF snapshot, #417 (L-23) before merge, and the `github-advanced-security` 402 quota.

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_10_12.py` (this branch) and `checks_2026_10_11.py`, `_10_10`, `_10_07`, `_10_06` (from their lead branches; run from the repo root with `PYTHONPATH=.:tests`). Exit 1 means something was fixed; read the lines.
- Re-run red-team `probe_uaepass.py` if UAE PASS code changes (it needs `fixtures/seed.db` from PR #412's `repro/make_seed.py`).
- Track landing in this order: L-46, L-38, L-50, L-43, L-30, L-9, L-28, L-29, L-51, L-47, L-48, L-27, L-40, L-44, L-21.
- Nothing is owed by the lead beyond the re-runs.
