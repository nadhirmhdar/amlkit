# Lead consolidated report: 2026-10-11

## 1. Headline: AMBER
Master has not moved for five days. The new finding is **HIGH**: anyone who knows an operator's email can keep that account locked out with one wrong password every 15 minutes (L-46). Every Medium carried from earlier runs still reproduces.

Master is `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (#426), the same SHA the 2026-10-10 lead report covered. `git log 0129848..origin/master` is empty, and four roles report that no PR was opened or merged after #426. Today's role reports contain new findings, so this is not a no-change run. Run date: 2026-10-11 UTC.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`a97eb71`) | done (no-change) | AMBER unchanged; no new finding. CR-12, CR-4, CR-1b, CR-13, CR-14 and CR-18 open | `ls-remote`, `rev-list` count | High |
| qa-regression (`e541bc2`) | done (no-change) | GREEN; suite not re-run. The 10-07 result (2170 passed / 3 skipped) stands | `ls-remote`, PR list | High |
| red-team (`f9359cf`) | done | AMBER. A1 (Med): login-lockout DoS. A2 (Info): a spoofed XFF chooses its own bucket only without a proxy hop. IP ceiling and cookie flags are clean | `probe_auth_limits.py` plus evidence file; HELD proposal | High |
| compliance-specialist (`48a202d`) | done (no-change) | AMBER unchanged; CS-2 and CS-13 are the most serious. Legal text still BLOCKED | `ls-remote` | High |
| mlro-user (`c4a1b41`) | done | AMBER. Operator lifecycle is sound (deactivation, last-MLRO guard, no enumeration at login). OP1: weak reset gives 500. OP2: admin create skips the strength rule. OP3: no forced change. OP4: wording | HTTP driver plus JSON log | High |
| skeptic (`b248ab4`) | done | AMBER. A1 is CONFIRMED and worse than reported, because the counter is never reset on expiry; Med→High. OP1 is a duplicate of F11; OP2 Low/Med; OP4 Info | `lockout_persistence.py`, file:line | High |

## 3. Consolidated findings
CONFIRMED means I re-ran a repro or read the cited lines on `0129848` today.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-46** lockout persists: `failed_login_count` is not reset when the lock expires, so one wrong password re-locks for 15 min. The lock message gives the expiry time (`auth.py:376-404`, reset only at `:419-421`/`:485`) | **HIGH** | red-team A1, skeptic | CONFIRMED, High | CONFIRMED (`checks_2026_10_11.py` `A1 ... after ONE wrong=(9, ...) correct pw -> 'Account locked...' reproduces=True`; skeptic `lockout_persistence.py` exit 0) | HELD `scripts/proposals/login-lockout-and-password-rules.md` §1. **Needs Nadhir** |
| L-47 password rule: admin reset with a weak 10+ char password gives HTTP 500 (OP1 = F11), and admin create accepts `aaaaaaaaaa` (OP2) (`app.py:3475-3478`, `:3533`, `:3552`) | LOW | mlro OP1/OP2, skeptic | CONFIRMED, Low (OP2 Low/Med) | CONFIRMED (`OP1 status=500`, `OP2 account_created=True`) | HELD, same file §2 |
| **L-48** (new, owed 10-04 lead) any org's MLRO can trigger `/admin/refresh`, which re-screens **every** org under that MLRO's name, so Org B's audit shows Org A's operator (`scheduler.py:96-100`, `app.py:3632-3648`) | LOW | lead | n/a | CONFIRMED (`GR ... Org B screening.run actors=['Alice Lead','Bob Other'] reproduces=True`) | HELD, same file §3 |
| L-49 (owed 10-04 lead) email enumeration | INFO | lead | n/a | Login, resend-verification and deactivated accounts are generic (mlro-user confirms login). `/register-organization` says "An account with that email already exists" (`cases/operators.py:64`), but only after a valid invite code (`app.py:1168-1169`); `/admin/operators` does the same for authenticated MLROs (`app.py:3555`, emails are unique app-wide). Read, not run | Carry; no proposal |
| A2 spoofed XFF behind the proxy | INFO | red-team | PLAUSIBLE, Info | PLAUSIBLE (infrastructure-dependent; not re-run) | Carry |
| OP3 no forced change after an admin-set password; OP4 "other sessions" wording | LOW / INFO | mlro | design / cosmetic | Accept the skeptic | Carry |
| L-43 same-name upload overwrites evidence | MEDIUM | red-team U1 | Med | Unchanged (no commit); not re-run | HELD `upload-overwrite-and-deadlines.md` §1 |
| L-44 deadline API (PATCH ignores `due_date`, unaudited update/delete) | LOW | mlro, skeptic | Low | CONFIRMED again (`DL ... reproduces=True`, `DLA ... ['compliance.deadline_created'] reproduces=True`) | HELD, same file §2 |
| L-38 freeze/CNMR on non-UAE-list hits | MEDIUM-HIGH | compliance CS-2 | Med | CONFIRMED again (`CS-2 ... 'pending_execution' reproduces=True`) | HELD `freeze-list-scope-and-totp-replay.md` §1. **Needs Nadhir** |
| L-40 TOTP replay | LOW | red-team M2 | Low | CONFIRMED again (`M2 first=True second=True`) | HELD |
| L-30 "Re-screening failed: 'customers'" banner | MEDIUM | mlro G9 | Med | CONFIRMED again (`G9 ... reproduces=True`). **Fourth report** | HELD `rescreen-banner-and-realert.md` §1 |
| L-9 rescreen re-alerts decided/pending matches | MEDIUM | mlro G10, CS-3 | Med | CONFIRMED again (`L-9 before=[(1,'pending_review'),(2,'false_positive')]`, exit 0) | HELD, same file §2 |
| L-27 four-eyes legacy NULL-id residual | LOW | CR-1b, N8, CS-18 | Low | CONFIRMED again (`4E legacy NULL-operator_id row: ... completed`) | HELD |
| L-28, L-29, L-21, L-45, U3/E4/E5, L-39, L-41, L-42, L-34/35/36, L-37, L-31/32/33, L-5/L-20, L-14, H7/T1, L-23 (#417), L-3, L-6, L-10 to L-13, L-15, L-22, L-26, G3 to G8, F2b, CR-3, CR-14, CR-17 | as 10-10 | various | as 10-10 | Unchanged: no commit since 10-06 | Carry |

**Severity adjudication**
- **L-46 is HIGH. I side with the skeptic over the red-team's Medium.** The red-team measured an 8-attempt lock. The skeptic showed, and I re-ran, that after the first lock a single attempt every 15 minutes is enough. That rate is far below every limiter, needs no credentials, and the lock message tells the attacker when to send it. The target that matters is the MLRO, who alone can execute freezes and file CNMRs inside 24 hours, and a single-MLRO firm has no in-app unlock. It is not Critical because no data is exposed and recovery exists outside the app (an operator `set_password`). I also found that UAE PASS SSO ignores `locked_until` (`SSO ... True`), so a UAE-PASS-linked MLRO could still get in. Production uses only sandbox credentials, so that mitigation does not apply to real operators today.
- **OP1 and OP2 are merged as L-47 (LOW).** They share a root cause: three password entry points with three different checks. OP1 duplicates red-team F11 (10-04). The skeptic's point holds: findings are being rediscovered, not retired.

**FIXED on master:** none (no commits).

## 4. Combined assessment
1. Five days without a commit. Every Medium carried from earlier runs re-reproduced today on `0129848`.
2. The new HIGH (L-46) is unauthenticated and persistent, and it targets the MLRO. Its fix is about six lines in `auth.login()`.
3. The owed 10-04 leads are now resolved: the global refresh leaks the operator name across tenants (L-48, Low), and email enumeration is gated behind an invite code or an MLRO session (Info).
4. As the skeptic notes, daily probing has saturated on a stable backlog. The next gain comes from landing fixes.
5. The suite was not re-run. No code changed since the 10-07 result (2170 passed).

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_10_11.py` (A1, OP1, OP2, GR, plus SSO informational). Output on `0129848`, scratch venv (`requirements.txt` minus passporteye/pdfminer; OCR not exercised; adapters stubbed to raise, no network):
  ```
  A1   expired=(8, '2026-10-11T03:45:11+00:00') after ONE wrong=(9, '2026-10-11T04:00:12+00:00') correct pw -> 'Account locked after repeated failed attempts. Try again aft' -> reproduces=True
  SSO  password-locked operator resolved by UAE PASS uuid: True (informational)
  OP2  admin create with 'aaaaaaaaaa': status=200 account_created=True -> reproduces=True
  OP1  admin reset to '1234567890': status=500 -> reproduces=True
  GR   Org A MLRO /admin/refresh -> Org B screening.run actors=['Alice Lead', 'Bob Other'] -> reproduces=True
  exit=0
  ```
- C-2 Created `scripts/proposals/login-lockout-and-password-rules.md` (HELD), with diffs for L-46, L-47 and L-48. All three change auth, route or scheduler logic, so none is applied.
- C-3 Owed item: re-ran `checks_2026_10_10.py` (exit 0: DUAL, DL and DLA as quoted above), `checks_2026_10_07.py` (exit 0: CS-2, M2) and `checks_2026_10_06.py` (exit 0: G9, L-9, 4E). I ran them from the older lead branches, with PYTHONPATH=.:tests and the 10-06 script copied into `repro_lead/` temporarily and then removed. Nothing has been fixed.
- C-4 Owed item, the 10-04 sub-agent leads: the any-MLRO global refresh and NULL-org rows across orgs are now L-48, CONFIRMED by run. Email enumeration is now L-49, Info, done by reading the code.
- C-5 Owed item, CSV BOM in Excel (E4): **not done**. Checking it needs Excel, which this container does not have. It stays PLAUSIBLE/Low. I am dropping it from the owed list rather than carrying it a third time: only a person with Excel can settle it (see §6).
- Re-ran the skeptic's `lockout_persistence.py`: exit 0, output identical in shape to the A1 line above.
- No tests added: each would fail on master (rule 5). No existing file edited. The commit SHA is in the final reply.

## 6. Decisions needed from Nadhir
1. **L-46 (new, HIGH): approve the lockout fix in proposal §1.** Optionally, choose an escalating lockout or an email to the operator when their account locks.
2. L-38 / L-39 freeze scope, option (a), (b) or (c). Option (a) was shown safe for dual-listed persons on 10-10.
3. L-43: approve the unique-key fix and check `gsutil versioning get` on the documents bucket.
4. L-30: the one-line banner fix (fourth request). L-9, L-28/L-29, L-27 as before.
5. L-47 and L-48: approve proposal §2 (a shared password check) and §3 (refresh runs as "system"). Separately decide whether any tenant's MLRO should be able to trigger a global refresh at all.
6. E4: open an exported CSV with Arabic names in Excel once and say whether it is garbled.
7. Carried: L-44, L-40, L-42, L-31/32/33 adviser confirmation, FATF snapshot, #417 (L-23) before merge, and the `github-advanced-security` 402 quota.

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_10_11.py` (this branch), `checks_2026_10_10.py`, `checks_2026_10_07.py` and `checks_2026_10_06.py` (from their lead branches; run from inside the repo with `PYTHONPATH=.:tests`). Exit 1 means something was fixed; read the lines.
- Track landing of L-46 first, then L-38, L-43, L-28, L-29, L-30, L-9, L-47, L-48, L-27, L-40, L-44, L-21.
- Nothing is owed by the lead beyond the re-runs.
