# Lead consolidated report: 2026-10-13

## 1. Headline: AMBER
Master has not moved for seven days. Today's only new defect is **LOW-MEDIUM**: the policy library says it accepts DOCX, but it rejects every real DOCX (L-52). Every carried finding still reproduces, including the HIGH login-lockout DoS (L-46).

Master is `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (#426), the same SHA as the 10-12 lead report. `git log 0129848..origin/master` is empty. Code-reviewer, QA and compliance report no PR opened or merged since #426 (only draft #411, docs, was touched). Red-team and mlro-user report new findings, so this is not a no-change run. Run date: 2026-10-13 UTC.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`3692c45`) | done (no-change) | GREEN. No new diff. CR-12, CR-4 (#417), CR-13/14/18 and CR-1b still open | `ls-remote`, PR list | High |
| qa-regression (`fe8e184`) | done (no-change) | GREEN. Suite not re-run by QA; the 10-07 result stands | `ls-remote`, `git log` | High |
| red-team (`61708ac`) | done | AMBER. Full suite on `0129848`: **2170 passed, 3 skipped, 0 failed** (19m35s). New: G1 (Info), GCS download/delete trust `stored_path` | pytest log in an evidence file; code reading; HELD proposal | High (I read `storage.py:77-100`) |
| compliance-specialist (`259be2b`) | done (no-change) | AMBER unchanged; CS-2 and CS-13 are the most serious. Legal text still BLOCKED | `ls-remote` | High |
| mlro-user (`c2dff84`) | done | AMBER. Policy library, notifications, feedback and e-signature work and respect tenancy. New: P1 (DOCX refused) and P2 (raw 422) | HTTP driver plus JSON log | High |
| skeptic (`be729a8`) | done | AMBER. P1 CONFIRMED and stronger than reported (a real DOCX can never pass). G1 Info. P2 Info. The suite is green but tests none of the open findings | file:line plus `docx_policy_upload.py` | High (I re-ran it) |

## 3. Consolidated findings
CONFIRMED means I re-ran a repro or read the cited lines on `0129848` today.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-52 (P1)** the policy form and `upload_policy` accept DOCX (`policies.html:42-43`, `manager.py:2347`), but the route's `validate_file_mime` (`app.py:3848-3850`) allows only PDF, PNG and JPEG (`validation.py:11-15`) | **LOW-MEDIUM** | mlro P1, skeptic | CONFIRMED, Low/Med | CONFIRMED (`repro_lead/checks_2026_10_13.py`: `P1 real DOCX (magic b'PK\x03\x04') rejected by route validator ... reproduces=True`, exit 0; the skeptic's script also exits 0) | HELD `scripts/proposals/policy-upload-docx.md`. **Needs Nadhir:** support DOCX (a) or drop it (b) |
| G1 the GCS download/delete paths take the bucket and object name from `stored_path` without pinning them to `GCS_BUCKET` or a prefix (`storage.py:77-100`) | INFO | red-team, skeptic | Info | CONFIRMED by reading. Exploiting it needs write access to the database | HELD in red-team branch `scripts/proposals/2026-10-13-new-findings.md` |
| P2 raw 422 JSON for empty feedback or signature fields | INFO | mlro, skeptic | Info | PLAUSIBLE (HTTP log only). Needs a crafted request | Carry |
| L-46 the lockout counter is not reset at expiry (`auth.py:376-404`) | **HIGH** | red-team A1, skeptic | High | CONFIRMED again (`A1 expired=(8, ...) after ONE wrong=(9, ...) ... reproduces=True`) | HELD `login-lockout-and-password-rules.md` §1 (10-11 lead branch). **Needs Nadhir** |
| L-38 freeze and CNMR obligations raised on non-UAE-list hits | MEDIUM-HIGH | compliance CS-2 | Med | CONFIRMED again (`CS-2 ... 'pending_execution' -> reproduces=True`) | HELD `freeze-list-scope-and-totp-replay.md` §1. **Needs Nadhir** |
| L-50 UAE PASS customer verification is not tied to the customer's identity | MEDIUM-LOW | red-team C1 | Low/Med | Unchanged (no commit). Re-run not owed | HELD (10-12 red-team branch §C1). **Needs Nadhir** |
| L-30 every re-screen shows "Re-screening failed: 'customers'" | MEDIUM | mlro G9 | Med | CONFIRMED again (`G9 ... reproduces=True`). **Sixth report** | HELD `rescreen-banner-and-realert.md` §1 |
| L-9 a re-screen re-raises alerts that were already decided or are pending | MEDIUM | mlro G10, CS-3 | Med | CONFIRMED again (`new open alerts [3, 4], reproduces=True`) | HELD, same file §2 |
| L-43 an upload with the same file name overwrites earlier evidence | MEDIUM | red-team U1 | Med | Unchanged; not re-run | HELD `upload-overwrite-and-deadlines.md` §1 |
| L-51 a transaction alert can be closed with a blank note | LOW | mlro TA1 | Low | CONFIRMED again (`TA1 ... disposition=None -> reproduces=True`) | HELD `transaction-alert-disposition-note.md` |
| L-47 a weak admin password reset returns 500; admin-created accounts skip the strength rule | LOW | mlro OP1/OP2 | Low | CONFIRMED again (`OP1 status=500`, `OP2 account_created=True`) | HELD, lockout file §2 |
| L-48 one org's `/admin/refresh` writes its MLRO's name into every org's audit | LOW | lead | n/a | CONFIRMED again (`GR ... actors=['Alice Lead', 'Bob Other']`) | HELD, lockout file §3 |
| L-40 a TOTP code can be replayed | LOW | red-team M2 | Low | CONFIRMED again (`M2 first=True second=True`) | HELD |
| L-27 residual four-eyes gap on legacy rows with a NULL operator id | LOW | CR-1b, N8, CS-18 | Low | CONFIRMED again (`legacy NULL-operator_id row ... completed`) | HELD |
| L-44 deadline API: PATCH ignores `due_date`; updates and deletes are not audited | LOW | mlro | Low | CONFIRMED again (`DL ... reproduces=True`, `DLA ... ['compliance.deadline_created']`) | HELD `upload-overwrite-and-deadlines.md` §2 |
| S1, S2, TA2, TA3, N1, U3 (DOC1/DOC2), L-49, A2, OP3/OP4, L-28, L-29, L-21, L-45, E4/E5, L-39, L-41, L-42, L-34/35/36, L-37, L-31/32/33, L-5/L-20, L-14, H7/T1, L-23 (#417), L-3, L-6, L-10 to L-13, L-15, L-22, L-26, G3 to G8, F2b, CR-3, CR-14, CR-17 | as 10-12 | various | as 10-12 | Unchanged: no commit since 10-06 | Carry |

**Severity adjudication**
- **L-52 is LOW-MEDIUM; I agree with the skeptic and raise mlro-user's "low".** The skeptic showed that a real DOCX can never pass, which is more than a misleading error message. Firms usually keep AML policies in Word, so half of an advertised feature does not work. No data is lost or exposed, because the upload fails loudly. That is why it is not Medium. The fix must not add the zip signature to the shared allow-list: customer documents use the same validator, so the proposal scopes the change to policies.
- **G1 is INFO**, as both roles say. It is defence in depth behind database compromise.
- **No contradictions between roles today.** The skeptic notes that the 10 MB cap on policies contrasts with the uncapped customer document route. That strengthens U3 (already HELD); it is not a new item.

**FIXED on master:** none (no commits).

## 4. Combined assessment
1. Seven days without a commit. The HIGH (L-46) and every carried Medium re-reproduced today on `0129848`.
2. Red-team's full run (2170 passed, 0 failed) is the fourth independent green on this SHA. As the skeptic says, the suite tests none of the open findings, so green does not mean safe.
3. Today's new items are small: one broken feature (L-52) and two Info items.
4. More probing now has low yield. The backlog of about 16 HELD proposals needs decisions and fix PRs.
5. Policy library, notifications, feedback and e-signature respect roles and tenancy (mlro-user HTTP log).

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_10_13.py` (L-52). It builds a real DOCX with the stdlib; no network, no database. Output on `0129848` in a scratch venv (`requirements.txt` minus passporteye/pdfminer, so OCR was not exercised):
  ```
  P1   real DOCX (magic b'PK\x03\x04') rejected by route validator: File type not allowed or unrecognized. Allowed types: PDF, PNG, JPEG.  -> reproduces=True
  exit=0
  ```
- C-2 Created `scripts/proposals/policy-upload-docx.md` (HELD). It has two options: (a) a DOCX check for policies only, with a proposed diff; (b) PDF only. It changes route and business logic, so it is not applied.
- C-3 Owed re-runs, all exit 0, nothing fixed. Each was copied from its lead branch and run with `PYTHONPATH=.:tests`; the copies were removed before committing.
  - `checks_2026_10_06.py`: G9, L-9, 4E
  - `checks_2026_10_07.py`: CS-2, M2
  - `checks_2026_10_10.py`: DL, DLA
  - `checks_2026_10_11.py`: A1, SSO, OP1, OP2, GR
  - `checks_2026_10_12.py`: TA1

  The key lines are quoted in §3. I also re-ran the skeptic's `repro_skeptic/docx_policy_upload.py`: `rejected: File type not allowed ... Allowed types: PDF, PNG, JPEG.`, exit 0.
- Red-team's `probe_uaepass.py` was not re-run because no UAE PASS code changed.
- No tests added, because each one would fail on master (rule 5). No existing file edited.
- Commit `b770209c3114d0452a1ba77207bd79bff9b7aec0` holds C-1 and C-2. This report is in the next commit; its SHA is in the final reply.

## 6. Decisions needed from Nadhir
1. **L-46 (HIGH, carried): approve the lockout fix** (10-11 proposal §1), with one lockout policy for password, MFA and SSO.
2. **L-38 / L-39 freeze scope:** option (a), (b) or (c).
3. **L-50:** identity matching plus a duplicate-IDN check before real UAE PASS credentials are used.
4. **L-52 (new):** support DOCX for policies (option a) or drop it from the form (option b).
5. L-43 unique-key fix, plus `gsutil versioning get` on the documents bucket.
6. L-30 one-line banner fix (sixth request); L-9, L-51, L-28/L-29, L-27, L-47, L-48.
7. Carried: E4 (open an exported Arabic CSV in Excel), L-44, L-40, L-42, L-31/32/33 adviser confirmation, FATF snapshot, #417 (L-23) before merge, and the `github-advanced-security` 402 quota.

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_10_13.py` (this branch) and `checks_2026_10_12.py`, `_11`, `_10`, `_07`, `_06` from their lead branches, from the repo root with `PYTHONPATH=.:tests`. Exit 1 means something was fixed; read the lines.
- Re-run red-team's `probe_uaepass.py` if UAE PASS code changes (it needs `fixtures/seed.db` from PR #412's `repro/make_seed.py`).
- Track landing in this order: L-46, L-38, L-50, L-43, L-30, L-9, L-52, L-28, L-29, L-51, L-47, L-48, L-27, L-40, L-44, L-21.
- Nothing is owed by the lead beyond the re-runs.
