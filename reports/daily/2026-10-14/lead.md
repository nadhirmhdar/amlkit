# Lead consolidated report: 2026-10-14

## 1. Headline: AMBER
Master has not moved for eight days. Today's most important new finding is **MEDIUM (L-53)**: a customer with a blank name is onboarded and recorded as "screened clear". This happens through both the mobile API and the web form. Every carried finding still reproduces, including the HIGH login-lockout DoS (L-46).

Master is `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (#426), the same SHA as the 10-13 lead report. `git log 0129848..origin/master` is empty, and roles report no PR opened or merged since #426. Only draft #411 (docs) was touched. Mlro-user and red-team report new findings, so this is not a no-change run. Run date: 2026-10-14 UTC.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`6c4ffd6`) | done (no-change) | GREEN. No new diff. CR-12, CR-4 (#417), CR-13/14/18 and CR-1b are still open | `ls-remote`, PR list | High |
| qa-regression (`4af591f`) | done (no-change) | GREEN. The suite was not re-run; the 10-07 result stands (2170 passed, 3 skipped) | `ls-remote`, `git log` | High |
| red-team (`ce2257e`) | done | AMBER. A new probe of the public `/apply` form held against header injection, CSRF, spam and the rate limit. New item: P1 (Info) | probe script plus evidence file | Medium-High (I did not re-run it, but the skeptic agrees) |
| compliance-specialist (`7351c6f`) | done (no-change) | AMBER, unchanged. CS-2 and CS-13 are the most serious. Legal text is still BLOCKED | `ls-remote` | High |
| mlro-user (`fa861b7`) | done | AMBER. Customer search (Arabic, wildcards, tenancy) and mobile create-customer validation work. New: C1 to C4 | HTTP driver plus JSON log | High |
| skeptic (`a21c615`) | done | AMBER. Raised C1 to Medium (the customer screens clear) and corrected C2's wording. The finding IDs collide across roles | file:line plus `empty_name_screen.py` | High (I re-ran it: `empty -> clear=True unscreenable=False`, exit 0) |

## 3. Consolidated findings
CONFIRMED means I re-ran a repro or read the cited lines on `0129848` today. Role IDs collide (mlro C1 vs red-team C1, mlro P1 vs red-team P1), so the lead `L-` IDs below are the canonical ones.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-53** a blank `full_name` is onboarded and screens clear, not unscreenable (`datamodel.py:163-165`, `manager.py:258`, `engine.py:291`) | **MEDIUM** | mlro C1, skeptic | CONFIRMED, Medium | CONFIRMED and **wider than reported**: the web form also reaches it, because `"   "` passes `Form()` and `app.py:1843` strips it to `""`. Output: `EN blank full_name onboarded id=3 stored='' clear=True unscreenable=False rating=low -> reproduces=True` | HELD `scripts/proposals/blank-name-and-sector-validation.md` §L-53 |
| **L-54** an unknown `sector` is accepted and scores the default 5 points; `validate_risk_inputs` has no sector entry (`risk/model.py:85-91, 169-170`) | LOW | mlro C2, skeptic | CONFIRMED, Low | CONFIRMED: `real_estate score=25.0 vs 'realestate' score=5.0 ... validator_checks_sector=False` | HELD, same file §L-54 |
| L-55 one mobile PATCH downgrades a customer from high to low with no reason, no prior values and no second review | LOW-MEDIUM | mlro C3, skeptic | Low/Med, partly by design | PLAUSIBLE→CONFIRMED by reading (`mobile.py:795-850`: the audit records only the new values). Whether a reason or review is needed is a policy question | **Needs Nadhir** (policy); same shape as H4 |
| L-56 a 2,000-character search returns unrelated customers | LOW | mlro C4 | PLAUSIBLE | PLAUSIBLE (not read) | Carry; next run reads the search truncation |
| RT-P1 the `/apply` notice email carries the submitter's message and display name as typed | INFO | red-team, skeptic | Info | PLAUSIBLE (evidence file, not re-run). Social-engineering only | No action |
| L-46 the lockout counter is not reset at expiry (`auth.py:376-404`) | **HIGH** | red-team A1 | High | CONFIRMED again (`A1 expired=(8, ...) after ONE wrong=(9, ...) ... reproduces=True`) | HELD `login-lockout-and-password-rules.md` §1 (10-11 lead branch). **Needs Nadhir** |
| L-38 freeze and CNMR obligations are raised on non-UAE-list hits | MEDIUM-HIGH | compliance CS-2 | Med | CONFIRMED again (`CS-2 ... 'pending_execution' -> reproduces=True`) | HELD `freeze-list-scope-and-totp-replay.md` §1. **Needs Nadhir** |
| L-30 every re-screen shows "Re-screening failed: 'customers'" | MEDIUM | mlro G9 | Med | CONFIRMED again (`G9 ... reproduces=True`). **Seventh report** | HELD `rescreen-banner-and-realert.md` §1 |
| L-9 a re-screen re-raises alerts that were already decided or are pending | MEDIUM | mlro G10, CS-3 | Med | CONFIRMED again (`new open alerts [3, 4], reproduces=True`) | HELD, same file §2 |
| L-52 the policy library advertises DOCX but rejects it | LOW-MEDIUM | mlro P1 (10-13) | Low/Med | CONFIRMED again (`P1 real DOCX ... reproduces=True`) | HELD `policy-upload-docx.md`. **Needs Nadhir** (a/b) |
| L-50 UAE PASS customer verification is not tied to the customer's identity | MEDIUM-LOW | red-team C1 | Low/Med | Unchanged (no commit) | HELD (10-12 red-team branch). **Needs Nadhir** |
| L-43 an upload with the same file name overwrites earlier evidence | MEDIUM | red-team U1 | Med | Unchanged; not re-run | HELD `upload-overwrite-and-deadlines.md` §1 |
| L-51 a transaction alert can be closed with a blank note | LOW | mlro TA1 | Low | CONFIRMED again (`TA1 ... disposition=None -> reproduces=True`) | HELD |
| L-47 a weak admin password reset returns 500; admin-created accounts skip the strength rule | LOW | mlro OP1/OP2 | Low | CONFIRMED again (`OP1 status=500`, `OP2 account_created=True`) | HELD, lockout file §2 |
| L-48 one org's `/admin/refresh` writes its MLRO's name into every org's audit | LOW | lead | n/a | CONFIRMED again (`actors=['Alice Lead', 'Bob Other']`) | HELD, lockout file §3 |
| L-40 a TOTP code can be replayed | LOW | red-team M2 | Low | CONFIRMED again (`M2 first=True second=True`) | HELD |
| L-27 residual four-eyes gap on legacy rows with a NULL operator id | LOW | CR-1b, N8, CS-18 | Low | CONFIRMED again (`legacy NULL-operator_id row ... completed`) | HELD |
| L-44 deadline API: PATCH ignores `due_date`; updates and deletes are not audited | LOW | mlro | Low | CONFIRMED again (`DL ... reproduces=True`, `DLA ... ['compliance.deadline_created']`) | HELD |
| G1, P2, S1, S2, TA2, TA3, N1, U3, L-49, A2, OP3/OP4, L-28, L-29, L-21, L-45, E4/E5, L-39, L-41, L-42, L-34/35/36, L-37, L-31/32/33, L-5/L-20, L-14, H7/T1, L-23 (#417), L-3, L-6, L-10 to L-13, L-15, L-22, L-26, G3 to G8, F2b, CR-3, CR-14, CR-17 | as 10-13 | various | as 10-13 | Unchanged: no commit since 10-06 | Carry |

**Severity adjudication**
- **L-53 is MEDIUM.** I agree with the skeptic and raise mlro-user's "AMBER (low)". The defect is not that the name is blank. The defect is that the record is stored as *screened clear*, which is the same silent-clear result as CR-12/N4 and N3. It is not High because it needs an operator to submit a blank name. It is wider than reported: the web form's HTML `required` does not stop a whitespace-only name, so the gap is not limited to the mobile API.
- **L-54 is LOW.** The skeptic is right that the score is 5, not zero. The real harm is that a typo downgrades a 25–35-point sector.
- **L-55 is LOW-MEDIUM**, pending a policy decision. Recomputing the rating from the factors is by design. A downgrade with no reason and no record of the previous values is an examination gap.
- **No contradictions between roles today.** One process issue: the skeptic is right that role IDs collide, so this report maps them to `L-` IDs.

**FIXED on master:** none (no commits).

## 4. Combined assessment
1. Eight days without a commit. The HIGH (L-46) and every carried Medium re-reproduced today on `0129848`.
2. The new Medium (L-53) is the third member of the "screened clear without anything being searched" family. One engine rule (`unscreenable` whenever there are no blocking keys) would close L-53 and narrow CR-12/N4.
3. The mobile API is the common weak entry point, as the skeptic says: L-53, L-54, L-55, N1 and DOC1/2. Shared validation would retire several Low items at once.
4. Customer search (Arabic variants, wildcard escaping, tenancy) and the public `/apply` form held up under probing.
5. The backlog of HELD proposals (now about 17) needs decisions, not more probing.

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_10_14.py` (L-53, L-54). It uses a scratch `:memory:` DB and has no network access. I ran it in a scratch venv built from `requirements.txt` without passporteye and pdfminer, so OCR was not exercised. Output on `0129848`:
  ```
  EN   blank full_name onboarded id=3 stored='' clear=True unscreenable=False rating=low -> reproduces=True
  SEC  sector real_estate score=25.0 vs 'realestate' score=5.0 stored='realestate' validator_checks_sector=False -> reproduces=True
  exit=0
  ```
- C-2 Created `scripts/proposals/blank-name-and-sector-validation.md` (HELD). It holds the proposed diffs for `manager.py`, `engine.py` and `risk/model.py`. I did not apply them because they change business logic.
- C-3 Owed re-runs, all exit 0, nothing fixed. Each was copied from its lead branch and run with `PYTHONPATH=.:tests`; the copies were removed before committing.
  - `checks_2026_10_06.py`: G9, L-9, 4E
  - `checks_2026_10_07.py`: CS-2, M2
  - `checks_2026_10_10.py`: DL, DLA
  - `checks_2026_10_11.py`: A1, SSO, OP1, OP2, GR
  - `checks_2026_10_12.py`: TA1
  - `checks_2026_10_13.py`: P1

  The skeptic's `empty_name_screen.py` also exits 0. The key lines are quoted in §3.
- Red-team's `probe_uaepass.py` and `probe_apply_public.py` were not re-run: no code changed, and the skeptic accepted the `/apply` result.
- No tests added, because each one would fail on master (rule 5). No existing file edited.
- Commit: see the final reply. A file cannot hold its own SHA.

## 6. Decisions needed from Nadhir
1. **L-46 (HIGH, carried): approve the lockout fix** (10-11 proposal §1).
2. **L-53 (new, MEDIUM): approve the blank-name fix.** I recommend both the `onboard()` check and the engine rule, then run the `trim(full_name)=''` query in the proposal against production data.
3. **L-55 (new):** should a risk downgrade need a reason, or a second review, and should the audit record the previous values?
4. L-38/L-39 freeze scope: option (a), (b) or (c).
5. L-50: identity matching before real UAE PASS credentials are used.
6. L-52: support DOCX (option a) or drop it (option b).
7. L-43 unique-key fix, plus `gsutil versioning get` on the documents bucket.
8. L-30 one-line banner fix (seventh request); L-9, L-54, L-51, L-28/L-29, L-27, L-47, L-48.
9. Carried: E4, L-44, L-40, L-42, L-31/32/33 adviser confirmation, FATF snapshot, #417 (L-23), the `github-advanced-security` 402 quota, and role-prefixed finding IDs (skeptic's suggestion; this would be a change to the role prompts, so it is Nadhir's call).

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_10_14.py` (this branch) and the `_13`, `_12`, `_11`, `_10`, `_07` and `_06` checks from their lead branches, from the repo root with `PYTHONPATH=.:tests`. Exit 1 means something was fixed; read the lines.
- Owed by the lead: read the customer search query path and settle L-56 (C4) as CONFIRMED or REFUTED.
- Track landing in this order: L-46, L-53, L-38, L-50, L-43, L-30, L-9, L-52, L-55, L-54, L-28, L-29, L-51, L-47, L-48, L-27, L-40, L-44, L-21.
