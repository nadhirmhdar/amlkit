# Lead consolidated report: 2026-10-31

## 1. Headline: AMBER
One new MEDIUM. A freeze raised by a confirmed sanctions match can be closed by one MLRO as "false positive", with no reason, no authority reference and no second approver, and concurrent closes race. The four commits merged since the last lead report (#428-#431) are public-site only and add no defect. All earlier Medium-or-higher items still reproduce.

Master is `401da3298f97bc94710e4b7171ec43a2ce4162b2` (`git ls-remote origin refs/heads/master`). The previous lead report (2026-10-23) named `0d56f72`. `git log 0d56f72..origin/master` lists 4 commits: `48eda02` gzip (#428), `41f7490` public links (#429), `0dbe14f` legal name FZE (#430), `401da32` share image (#431). 11 files, +123/-20, none in screening, freeze, auth, review, DB or reporting code. Run date: 2026-10-31 UTC.

**Gap:** there is no lead report for 2026-10-24 to 2026-10-30. Role reports exist for 10-24 (all roles except skeptic) but were never consolidated. Every role says no firing reached it for 10-25 to 10-30. I folded the new 10-24 items (CR-21, CR-22, CS-18; all INFO) into §3.

## 2. Per role
| Role (branch) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done (no-change) | GREEN; master unchanged since its 10-24 review of `401da32`; carried CR items unchanged | ls-remote + PR list | High |
| qa-regression | done (no-change) | GREEN; the 10-24 full run on `401da32` stands: 2177 passed, 3 skipped, 0 tenant leaks | ls-remote; cites 10-24 commit `8fd3ac0` | High |
| red-team | done | GREEN on new code. H1 (INFO): no `Referrer-Policy`/`Permissions-Policy`. Gzip keeps the security headers; 47 blog/header tests pass | two evidence files | High |
| compliance-specialist | done (no-change) | AMBER unchanged. CS-2/CS-13 stand; legal text BLOCKED | ls-remote | High on code; Articles PLAUSIBLE |
| mlro-user | done | AMBER. FZ1: a confirmed freeze can be resolved `false_positive` with no reason or approval; FZ2: `authority_ref` is optional; FZ3: the error echoes an org id | driver + JSON log | High |
| skeptic | done | AMBER. Confirms FZ1 (Medium) and FZ2 (Low/Med) by code; refutes FZ3 (it is the caller's own org id); H1 stays Info; raises a resolve race; no defect in #428 | file:line, no re-runs | High |

## 3. Consolidated findings
CONFIRMED means I re-ran a repro on `401da32` today (all 17 lead scripts exit 0; output in §5).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-95** (new) a freeze obligation from a true-positive alert can be resolved `false_positive` by one MLRO, unexecuted, with empty `authority_ref` and `notes`; the alert stays `true_positive` (`cases/manager.py:1927-1933`) | **MEDIUM** | mlro FZ1, skeptic | Medium | CONFIRMED: `FZ1 ... status=resolved executed_at=None authority_ref='' notes=''; alert status still='true_positive' -> reproduces=True` | HELD `scripts/proposals/2026-10-31-freeze-resolution.md`. **Needs Nadhir** (option A/B) |
| **L-96** (new) `authority_clearance` accepted with an empty `authority_ref` | LOW | mlro FZ2, skeptic | Low/Med | CONFIRMED: `FZ2 authority_clearance with empty authority_ref -> status=resolved authority_ref='' -> reproduces=True` | HELD, same file |
| **L-97** (new) resolve is check-then-act: two concurrent resolves both succeed, the second overwrites `resolved_by`/`authority_ref`, and 2 audit rows are written (`manager.py:1917` SELECT, `:1944-1953` UPDATE with no status guard) | LOW | skeptic (reading) | not run | CONFIRMED (barrier-forced interleave): `FZR ... results=[('MonaA','ok'),('MonaB','ok')] freeze.resolved audit rows=2 final resolved_by='MonaB' authority_ref='REF-MonaB'` | HELD, same file (one-line `AND status != 'resolved'` + rowcount) |
| FZ3 "not found in org N" leaks a tenant id | REFUTED | mlro FZ3 | Refuted | REFUTED: `manager.py:1923` formats the caller's own `org_id` from the session | Closed |
| **L-98** (new) no `Referrer-Policy` / `Permissions-Policy` header | INFO | red-team H1, skeptic | Info | CONFIRMED: `git grep -i "referrer-policy\|permissions-policy" -- amlkit` returns nothing | Carry. One-line middleware addition when the headers middleware is next touched |
| L-99 (10-24, never consolidated) CR-21 weak `nofollow` assert; CR-22 `twitter:card=summary`; CS-18 needs a regression test that anonymous gzip pages carry no `csrf_token` | INFO | code-reviewer, compliance | n/a | PLAUSIBLE (not re-checked) | Carry. CS-18's test is worth adding with any template change |
| **L-46** lockout not reset at expiry (+L-86 enumeration, L-87 422) | **HIGH** / LOW / INFO | red-team A1, mlro LG1-3, skeptic | High | CONFIRMED: `A1 expired=... after ONE wrong ... correct pw -> 'Account locked...'`; `LG2 ... real email -> 'Account locked...'; unknown email -> 'Incorrect email or password.'`; `LG3 empty password -> 422` | HELD. **Needs Nadhir** |
| **L-82** scan uploads: no byte, pixel, MIME or rate cap (4 routes) | **MEDIUM** | red-team B1/B2 | Medium | CONFIRMED: `B1w ... 9000x9000 PNG (97 KB) -> 200, peak RSS +1453 MB`; `B1m ... 30 MB junk -> 200`; `TL ... MZ .exe blob -> 200` | HELD. **Needs Nadhir** |
| **L-38** freeze/CNMR raised on non-UAE-list hits | MEDIUM-HIGH | compliance CS-2 | Med | CONFIRMED: `CS-2 EU-only sanction hit, true_positive -> ... 'status': 'pending_execution'` | HELD. **Needs Nadhir** |
| L-73 unrelated alert clears an overdue review | MEDIUM | lead | n/a | CONFIRMED: `RV ... overdue=False, next_review=2029-10-15, review recorded=False` | HELD |
| L-53 blank `full_name` screens clear | MEDIUM | mlro C1 | Medium | CONFIRMED: `EN blank full_name onboarded id=3 stored='' clear=True` | HELD |
| L-30 / L-9 rescreen re-raises alerts (+G9) | MEDIUM | mlro, compliance | Med | CONFIRMED: `G9 ... route reads outcome['customers']=True` | HELD |
| L-66, L-69, L-76, L-77 one-time secrets consumed concurrently | LOW-MED to INFO | red-team, lead | Medium | CONFIRMED: `T1m ... operators=10`; `EV ... successes per round=[5, 5, 5, 5, 5]`; `BC ... results=[True, True]` | HELD. **Needs Nadhir** |
| L-91 to L-94 `kg-screen` / `gdelt-bq` | LOW (latent) / INFO | mlro, skeptic, lead | Low/Med | CONFIRMED again (`_23`: 4/4 reproduce) | HELD (10-23 proposal) |
| L-88 / L-89 SEO | LOW / INFO | mlro, cs, cr | Info/Low | CONFIRMED (`_22`: 2/2) | HELD |
| L-83, L-84, L-85, L-90, L-78-L-81, L-75, L-67, L-47+L-58, L-57, L-52, L-56, L-63, L-61, L-62, L-54, L-51, L-48, L-40, L-27, L-44 | LOW / INFO | various | as before | CONFIRMED again (`_06`-`_22` all exit 0; L-90 still PLAUSIBLE) | HELD / carry |
| L-74, L-70/L-72/L-71, L-43, L-50, L-55, L-68, L-64, L-65, L-59, L-60 and the 10-16 carry list | as before | various | as before | Unchanged: no code path touched by #428-#431 | Carry |

**Severity adjudication**
- L-95: mlro-user and the skeptic both say Medium, and I agree. It is not High: only an MLRO can do it, and the action is audited with the reason. It is not Low: the record that results contradicts a four-eyes-confirmed true positive, and nobody has to write why. **Interaction with L-38:** for an EU/OFAC-only hit, which L-38 wrongly turns into a freeze, `false_positive` is today the MLRO's only way to close the freeze without executing it. That makes the record say "false positive" about a real match. Fixing L-95 by option B, before L-38, would remove that escape route and leave such firms forced to freeze. **Land L-38 before or with L-95.**
- L-96: the skeptic proposes Low/Medium. I put it at LOW on its own, because it disappears with L-95's validation.
- L-97: the skeptic did not run it; I did, with a barrier. That proves the guard is absent, not that two MLROs hit it in practice. LOW, the same class as L-66.
- FZ3: I agree with the skeptic: REFUTED.
- H1: red-team says Info and the skeptic agrees. Modern browsers default to `strict-origin-when-cross-origin`. INFO.
- Duplicates: FZ1/FZ2 = the skeptic's rows; the skeptic's "missed #1" (three single-person reversals of four-eyes decisions) links L-95, the single-operator toggle and L-70/L-73. I record it as a theme, not a new id. Contradictions: none.

**FIXED on master:** none. #428-#431 touch none of the cited lines.

## 4. Combined assessment
1. Master moved by 4 public-site commits. QA's full run (2177 passed) and the red-team, code-reviewer and skeptic reads find no regression; the gzip middleware is BREACH-aware and holds.
2. New: freeze resolution lacks the controls that alert disposition has (L-95/L-96/L-97). The fix is small, and its order matters relative to L-38.
3. All 17 lead repro scripts still exit 0, so nothing from the backlog has landed since the 10-23 report.
4. The routine missed 6 days (10-25 to 10-30) across every role, and 10-24 was never consolidated. Check the scheduler.
5. The bottleneck is still decisions, not evidence.

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_10_31.py` (FZ1, FZ2, FZR). It uses a temp-file DB and synthetic UAE-list entities, with no network. Output on `401da32` (mail console noise removed):
  ```
  FZ1  unexecuted freeze resolved false_positive with empty ref/notes: status=resolved executed_at=None authority_ref='' notes=''; alert status still='true_positive' -> reproduces=True
  FZ2  authority_clearance with empty authority_ref -> status=resolved authority_ref='' -> reproduces=True
  FZR  two concurrent resolves: results=[('MonaA', 'ok'), ('MonaB', 'ok')] freeze.resolved audit rows=2 final resolved_by='MonaB' authority_ref='REF-MonaB' -> reproduces=True
  3/3 reproduce
  exit=0
  ```
- C-2 Created `scripts/proposals/2026-10-31-freeze-resolution.md` (HELD). It holds a minimal diff (validation + `AND status != 'resolved'` + rowcount check), options A/B for a second approver, and the tests to add. Not applied, because it changes business logic in `cases/manager.py`.
- C-3 Owed by the 10-23 "Next run": I re-ran `_23`, `_22`, `_21`, `_20`, `_19`, `_18`, `_17`, `_16`, `_15`, `_14`, `_13`, `_12`, `_11`, `_10` and `_07` (with `PYTHONPATH=.:tests`), and `_06` from inside `repro_lead/`. I checked out detached `origin/master` = `401da32` after `git fetch origin master`, in a scratch venv (`requirements.txt` + `passporteye` + pytest; no tesseract, no pdfminer, so no OCR success paths). **All 16 exit 0.** Count of `reproduces=True` lines: `_23:4 _22:2 _21:2 _20:6 _19:6 _18:3 _17:4 _16:3 _15:3 _14:2 _13:1 _12:1 _11:4 _10:2 _07:2 _06:2`. (`_21` LG4 prints `429 seen=True`; that line was already a refutation check.) I copied the scripts from their lead branches and removed them before committing.
- Not re-run: the full suite (QA's 10-24 run is on the same SHA), the MLRO freeze driver (my C-1 covers it), red-team's header probe (I re-checked H1 by `git grep`).
- No tests added, because each would fail on master (rule 5). No existing file edited.

## 6. Decisions needed from Nadhir
1. **L-46 (HIGH) + L-86 + L-74: approve one lockout PR** (10-11 §1, 10-21 proposal).
2. **L-38 then L-95: decide the freeze scope (UAE/UN lists only), then choose option A or B for reversing a confirmed freeze.** I recommend B: block `false_positive` while the alert is `true_positive` and require a re-disposition through four-eyes. Also say whether you want the minimal validation + race guard landed now, which is safe on its own.
3. **L-82 (MEDIUM): approve the shared scan-upload guard** (4 routes); confirm the production memory limit.
4. **Scheduler:** no role or lead firing reached its session from 10-25 to 10-30, and no lead ran on 10-24. Check the routines in Settings → Routines.
5. L-91 to L-94: remove or harden `kg-screen` / `gdelt-bq`.
6. Periodic review (L-70/L-72/L-73); atomic consume for one-time secrets (L-66, L-69, L-76, L-77; L-97 is the same pattern).
7. L-53 blank name; L-81 session cap; L-85 privacy wording.
8. Carried: L-88/L-89 SEO, L-98 headers, L-30 banner fix, L-9, L-79, the Low list, L-31/32/33 adviser confirmation, legal-text `corpus/` (also needed to settle whether UAE law requires dual approval to lift a freeze), FATF snapshot, #417 (L-23), the `github-advanced-security` 402 quota, a single de-duplicated finding register.

## 7. Next run: carried over
- Run `git fetch origin master` and check out the SHA, then re-run `repro_lead/checks_2026_10_31.py` (this branch) plus `_23`, `_22`, `_21`, `_20`, `_19`, `_18`, `_17`, `_16`, `_15`, `_14`, `_13`, `_12`, `_11`, `_10`, `_07` and `_06` from their lead branches. Put them in `repro_lead/` with `PYTHONPATH=.:tests` (run `_06` from inside `repro_lead/`; `_20` needs `passporteye`). Exit 1 means fixed; read the printed lines.
- Owed by the lead: nothing new beyond the re-runs.
- For whichever role picks it up: list every path where one person can reverse a four-eyes decision (freeze resolve, the single-operator toggle, periodic review, anything else); check whether execute/file-CNMR share L-97's check-then-act pattern; CS-18's anonymous-page `csrf_token` regression test; whether Cloud Run injects `GOOGLE_CLOUD_PROJECT`; lock expiry end to end over HTTP.
- Landing order: L-46 (+L-74, L-86), L-38, L-95/L-96/L-97, L-82, L-53, L-70/L-72/L-73, L-66/L-69/L-76/L-77, L-91-L-94, L-50, L-43, L-30, L-9, L-57, L-47+L-58+L-67+L-80, L-78, L-83, L-88, L-52, L-55, L-56, L-64, L-65, L-63, L-79, L-85, L-81, L-54, L-28, L-29, L-51, L-48, L-27, L-40, L-44, L-21, L-75, L-84, L-87, L-89, L-90, L-98, L-99.
