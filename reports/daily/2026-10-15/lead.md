# Lead consolidated report: 2026-10-15

## 1. Headline: AMBER
Master has not moved for nine days. Every carried finding, including the HIGH login-lockout DoS (L-46), still reproduces. Today's new findings are all Low-Medium or below. The most notable is L-57: only one Arabic-named firm can ever self-register.

Master is `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (#426), the same SHA as the 10-14 lead report. `git log 0129848..origin/master` is empty. Roles report no PR opened or merged since #426; only draft #411 (docs) was touched. Red-team and mlro-user report new findings, so this is not a no-change run. Run date: 2026-10-15 UTC.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`5238092`) | done (no-change) | GREEN. No new diff. CR-12, CR-4 (#417), CR-13/14/18 and CR-1b are still open | `ls-remote`, PR list | High |
| qa-regression (`ce275e3`) | done (no-change) | GREEN. The suite was not re-run; the 10-07 result stands (2170 passed, 3 skipped) | `ls-remote`, `git log` | High |
| red-team (`3e46e80`) | done | AMBER. `/register-organization` is invite-gated and rate-limited. New: R1 (slug collision), R2 (password checked for length only), R3 (Info) | probe script, evidence file, proposal | High (I reproduced R1 and R2) |
| compliance-specialist (`382ab56`) | done (no-change) | AMBER, unchanged. CS-2 and CS-13 are the most serious. Legal text is still BLOCKED | `ls-remote` | High |
| mlro-user (`cd47d3f`) | done | AMBER. Match notifications, the dashboard and the alert queue all work. New: NT1 to NT3, all low | HTTP driver plus JSON log | Medium-High (I did not re-run it; the skeptic read it) |
| skeptic (`e6a56b4`) | done | AMBER. Confirmed R1 and R2, downgraded the NT items to Info, and linked R2/OP1/OP2/F11 to one missing helper | file:line plus `arabic_org_slug.py` | High (I re-ran it: `slugs : ['org']`, exit 0) |

## 3. Consolidated findings
CONFIRMED means I re-ran a repro or read the cited lines on `0129848` today.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-57** all non-Latin org names get the slug `org`, so a second Arabic-named firm is refused with "similar name already exists" (`cases/operators.py:38`, `db.py:147` UNIQUE) | **LOW-MEDIUM** | red-team R1, skeptic | CONFIRMED, Low/Med | CONFIRMED: `R1 Arabic org #1 created; #2 ValueError: An organization with a similar name already exists. -> reproduces=True` | HELD `scripts/proposals/2026-10-15-new-findings.md` (red-team branch). **Needs Nadhir** |
| L-58 org self-registration checks password length only (`operators.py:32`), web and mobile | LOW (one family with L-47) | red-team R2, skeptic | CONFIRMED, Low/Med | CONFIRMED: `R2 register with 'xxxxxxxxxx' -> created -> reproduces=True` | HELD, same red-team file; fix together with L-47 (one `check_new_password()` helper) |
| **L-56** a 2,000-character or `aa` search returns unrelated customers | LOW | mlro C4 (10-14) | PLAUSIBLE | **CONFIRMED and root-caused (owed item).** The query is not truncated; `canonical_tokens('a'*2000) == ['a']`, then `LIKE '%a%'` on `canonical_key` (`queries.py:742-748`). Output: `L-56 search 'a'*2000 -> ['Q-001', 'Q-002']; search 'aa' -> ['Q-001', 'Q-002'] -> reproduces=True`. Search only; screening is not affected | HELD `scripts/proposals/customer-search-canonical-substring.md` |
| L-59 blank operator name; 5,000-character and NUL org names accepted | INFO | red-team R3 | Info | PLAUSIBLE (not re-run). Same missing-validation family as L-53 | No action; fold into L-53/L-58 validation |
| L-60 only the MLRO is notified of a new match; officers are not | INFO | mlro NT1 | Info, likely by design | PLAUSIBLE (not read in code) | Policy question, low priority |
| L-61 "Open one to go straight to the alert" lands on the customer's alerts section | INFO | mlro NT2 | Info | PLAUSIBLE (evidence log, not re-run). Copy fix | Carry |
| L-62 unknown alert-queue filters are ignored without a message | INFO | mlro NT3 | Info | PLAUSIBLE (evidence log, not re-run) | Carry |
| L-46 the lockout counter is not reset at expiry (`auth.py:376-404`) | **HIGH** | red-team A1 | High | CONFIRMED again (`A1 expired=(8, ...) after ONE wrong=(9, ...) ... reproduces=True`) | HELD `login-lockout-and-password-rules.md` §1 (10-11 lead branch). **Needs Nadhir** |
| L-53 a blank `full_name` is onboarded and screens clear | MEDIUM | mlro C1, skeptic | Medium | CONFIRMED again (`EN ... clear=True unscreenable=False ... reproduces=True`) | HELD `blank-name-and-sector-validation.md` (10-14 lead branch). **Needs Nadhir** |
| L-38 freeze and CNMR obligations are raised on non-UAE-list hits | MEDIUM-HIGH | compliance CS-2 | Med | CONFIRMED again (`CS-2 ... 'pending_execution' -> reproduces=True`) | HELD `freeze-list-scope-and-totp-replay.md` §1. **Needs Nadhir** |
| L-30 every re-screen shows "Re-screening failed: 'customers'" | MEDIUM | mlro G9 | Med | CONFIRMED again (`G9 ... reproduces=True`). **Eighth report** | HELD `rescreen-banner-and-realert.md` §1 |
| L-9 a re-screen re-raises alerts that were already decided or are pending | MEDIUM | mlro G10, CS-3 | Med | CONFIRMED again (`new open alerts [3, 4], reproduces=True`) | HELD, same file §2 |
| L-43 an upload with the same file name overwrites earlier evidence | MEDIUM | red-team U1 | Med | Unchanged; not re-run | HELD `upload-overwrite-and-deadlines.md` §1 |
| L-50 UAE PASS customer verification is not tied to the customer's identity | MEDIUM-LOW | red-team C1 | Low/Med | Unchanged (no commit) | HELD. **Needs Nadhir** |
| L-52 the policy library advertises DOCX but rejects it | LOW-MEDIUM | mlro P1 | Low/Med | CONFIRMED again (`P1 real DOCX ... reproduces=True`) | HELD `policy-upload-docx.md`. **Needs Nadhir** |
| L-55 one mobile PATCH downgrades risk with no reason or previous values | LOW-MEDIUM | mlro C3 | Low/Med | Unchanged | **Needs Nadhir** (policy) |
| L-54 an unknown `sector` is accepted and scores 5 | LOW | mlro C2 | Low | CONFIRMED again (`SEC ... reproduces=True`) | HELD (10-14 file §L-54) |
| L-47 a weak admin password reset returns 500; admin-created accounts skip the strength rule | LOW | mlro OP1/OP2 | Low | CONFIRMED again (`OP1 status=500`, `OP2 account_created=True`) | HELD, lockout file §2; merge with L-58 |
| L-51, L-48, L-40, L-27, L-44 | LOW | as 10-14 | Low | CONFIRMED again (`TA1`, `GR`, `M2`, `4E legacy ... completed`, `DL`/`DLA` all `reproduces=True`) | HELD |
| RT-P1, G1, P2, S1, S2, TA2, TA3, N1, U3, L-49, A2, OP3/OP4, L-28, L-29, L-21, L-45, E4/E5, L-39, L-41, L-42, L-34/35/36, L-37, L-31/32/33, L-5/L-20, L-14, H7/T1, L-23 (#417), L-3, L-6, L-10 to L-13, L-15, L-22, L-26, G3 to G8, F2b, CR-3, CR-14, CR-17 | as 10-14 | various | as 10-14 | Unchanged: no commit since 10-06 | Carry |

**Severity adjudication**
- **L-57 is LOW-MEDIUM.** Red-team says Medium and the skeptic says Low/Medium. I side with the skeptic. Registration is invite-gated, the firm can register under a Latin name, and the slug is only a lookup key. It is not Low, because a UAE product that cannot register a second Arabic-named firm is a real functional defect, and the "similar name" message misleads.
- **L-58 is LOW** on its own, because the registrant is an MLRO behind mandatory TOTP. I agree with the skeptic that it belongs with L-47 (OP1/OP2) and F11. One shared password check closes all four, so it should be fixed with L-47, not separately.
- **L-56 is LOW.** It affects only search results, not screening, and it does not cross tenants. The skeptic's PLAUSIBLE is now CONFIRMED. The mlro-user's guess that truncation was involved is wrong; the cause is a substring match on one-letter canonical tokens.
- NT1 to NT3: I accept the skeptic's Info. No contradictions between roles today.

**FIXED on master:** none (no commits).

## 4. Combined assessment
1. Nine days without a commit. The HIGH (L-46) and every carried Medium re-reproduced today on `0129848`.
2. Today's new findings are all input-validation gaps (org slug, password, names), none above Low-Medium.
3. Two shared fixes would close about eight items: one password-check helper (L-47, L-58, F11) and one name/field validator plus the `unscreenable` engine rule (L-53, L-54, L-59, CR-12/N4).
4. Notifications, the dashboard, the alert queue and the invite gate on registration held up under probing.
5. The backlog of HELD proposals (now about 19) needs decisions, not more probing.

## 5. Corrections I made
- C-1 **Owed item done (L-56).** I read `queries.search_customers` and root-caused C4 (§3). Created `repro_lead/checks_2026_10_15.py` (L-56, R1, R2). It uses a scratch `:memory:` DB and has no network access. I ran it in a scratch venv built from `requirements.txt` without passporteye and pdfminer, so OCR was not exercised. Output on `0129848`:
  ```
  L-56 search 'a'*2000 -> ['Q-001', 'Q-002']; search 'aa' -> ['Q-001', 'Q-002'] -> reproduces=True
  R1   Arabic org #1 created; #2 ValueError: An organization with a similar name already exists. -> reproduces=True
  R2   register with 'xxxxxxxxxx' -> created -> reproduces=True
  exit=0
  ```
- C-2 Created `scripts/proposals/customer-search-canonical-substring.md` (HELD). It holds a one-line diff that drops canonical tokens shorter than 2 characters and caps the query at 200 characters. I checked this in a Python simulation against the repro keys: the junk queries return nothing, and `jaleel`, `Ahmad Jalil`, the Arabic form and `Fatima` still hit. I also tried a token-boundary (prefix) variant and rejected it, because it loses the `Ahmad Jalil` match. Not applied, because it changes query logic.
- C-3 Owed re-runs, all exit 0, nothing fixed. Each was copied from its lead branch and run with `PYTHONPATH=.:tests`; the copies were removed before committing.
  - `checks_2026_10_06.py`: G9, L-9, 4E
  - `checks_2026_10_07.py`: CS-2, M2
  - `checks_2026_10_10.py`: DL, DLA
  - `checks_2026_10_11.py`: A1, OP1, OP2, GR
  - `checks_2026_10_12.py`: TA1
  - `checks_2026_10_13.py`: P1
  - `checks_2026_10_14.py`: EN, SEC

  The skeptic's `arabic_org_slug.py` also exits 0 (`slugs : ['org']`).
- Red-team's `probe_register_org.py` and the mlro-user driver were not re-run. My own repro covers R1 and R2. NT1 to NT3 are Info.
- No tests added, because each one would fail on master (rule 5). No existing file edited.
- Commit: see the final reply. A file cannot hold its own SHA.

## 6. Decisions needed from Nadhir
1. **L-46 (HIGH, carried): approve the lockout fix** (10-11 proposal §1).
2. **L-53 (MEDIUM, carried): approve the blank-name fix** (10-14 proposal).
3. **L-57 (new):** pick the slug fix: a slug derived from the id, or a suffix on collision (red-team proposal). Check whether any production org already holds the slug `org`.
4. **L-47 + L-58:** approve one shared password-strength check for register (web and mobile), admin-create and admin-reset.
5. L-38/L-39 freeze scope: option (a), (b) or (c).
6. L-55: should a risk downgrade need a reason or a second review?
7. L-50: identity matching before real UAE PASS credentials are used.
8. L-52: support DOCX (a) or drop it (b).
9. L-43 unique-key fix, plus `gsutil versioning get` on the documents bucket.
10. L-30 one-line banner fix (eighth request); L-9, L-56, L-54, L-51, L-28/L-29, L-27, L-48.
11. Carried: E4, L-44, L-40, L-42, L-31/32/33 adviser confirmation, FATF snapshot, #417 (L-23), the `github-advanced-security` 402 quota, and role-prefixed finding IDs.

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_10_15.py` (this branch) and the `_14`, `_13`, `_12`, `_11`, `_10`, `_07` and `_06` checks from their lead branches, from the repo root with `PYTHONPATH=.:tests`. Exit 1 means something was fixed; read the lines.
- Owed by the lead: none new. Optional: read the notification routes and settle NT2 (L-61) and NT3 (L-62) by file:line.
- Track landing in this order: L-46, L-53, L-38, L-50, L-43, L-30, L-9, L-57, L-47+L-58, L-52, L-55, L-56, L-54, L-28, L-29, L-51, L-48, L-27, L-40, L-44, L-21.
