# Lead consolidated report: 2026-10-06

## 1. Headline: AMBER
Twelve PRs merged since the last lead run. They closed the four-eyes bypass (L-1) and five other carried items. Two issues now lead: names in a non-Latin, non-Arabic script are saved as a clean screening at onboarding and rescreen (N4/CR-12), and the admin "Re-screen all" control reports failure on every run (G9).

Master is `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (#426, merged 2026-10-06 03:30 UTC). The previous lead report covered `448a19b`. Run date: 2026-10-06 UTC.

**Staleness warning.** The roles reported against four different masters: QA `b9d9db5`, code-reviewer and red-team `b7eeb2f`, mlro `8750f74`, skeptic `1d1ef39`. #426 landed after every role had run. I re-checked every item below that #426 or #421 could change on `0129848`.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`dc9d272`) | done | RED (on `b7eeb2f`): CR-1 four-eyes still open, now FIXED by #426. New: CR-12 `unscreenable` not persisted. Also CR-13 (#421 perf), CR-14 (bearer compare) and CR-4 (#417). Suite 2115 passed / 3 skipped. | Repro output, file:line, benchmarks | High |
| qa-regression (`f828570`) | done | GREEN on `b9d9db5`: 2002 passed / 3 skipped / 0 failed. Tenant sweeps `HITS: []`, 0 B→A leaks over 66 routes. Isolation flake 30/30. | Commands and counts; oldest SHA of the six | High (for that SHA) |
| red-team (`e28d811`) | done | AMBER: N3 (invisible characters beyond Cf), N4 (unscreenable not enforced), N5 (CR/LF reference breaks the freeze email), N6 (XML-illegal characters in goAML), N7 (bearer 500). F5 CSRF FIXED. | Probe scripts plus evidence files; HELD diffs | High |
| compliance-specialist (`b0e3a7a`) | done | AMBER: CS-13 (24h clock starts at disposition, not designation), CS-14 (no PNMR), CS-15 (no 5-business-day tracking), CS-16 (breach notice only). CS-8 and the PEP wording FIXED by #421. | Code citations plus an EOCN page quote; article mapping PLAUSIBLE | Medium-high |
| mlro-user (`3745b73`) | done | AMBER on `8750f74`: G9 rescreen banner always fails, G10 re-alert on decided alerts. F1 still open (now FIXED by #426). F2, F3, G1, G2 FIXED. G6 to G8 freeze friction. | HTTP driver plus JSON logs | High |
| skeptic (`c8c08a1`) | done | AMBER on `1d1ef39`: confirmed N3 (lowered to Medium), N4, G9 (Medium), G10. Refuted N1 on `alert_queue` but kept it alive on `/audit` and feedback. Flagged the SHA staleness and the weak G9 test. | 7 repro scripts | High |

## 3. Consolidated findings
Verdict key: **CONFIRMED** means I re-ran a repro or read the cited lines on `0129848` today. **CONFIRMED (role)** means a role reproduced it with pasted output and I did not re-run it.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| L-1 four-eyes bypass via self-rename | closed | CR-1, mlro F1, red-team F4 | CONFIRMED, Medium (on `1d1ef39`) | **FIXED on master by PR #426**. `tests/test_foureyes_rename_bypass.py`: 4 passed. My id-path check: "self-confirm after rename refused" | Closed |
| L-27 #426 falls back to a name comparison for proposals staged before deploy (`operator_id IS NULL`) | LOW | lead (new) | – | CONFIRMED (`repro_lead/checks_2026_10_06.py`: "legacy NULL-operator_id row: same person confirmed after rename -> completed") | HELD in `scripts/proposals/rescreen-banner-and-realert.md` §3. Only affects alerts pending at deploy time |
| L-28 `unscreenable` not persisted or acted on at onboarding, UBO add or rescreen (`engine.py:292`; consumers only `screen.html:76`, `mobile.py:537`) | **MEDIUM-HIGH** | red-team N4, code-reviewer CR-12 (duplicates) | CONFIRMED, Medium | CONFIRMED (re-ran red-team probe: `onboard('Иван Петров')` gives screening row `hits 0, candidates 0, datasets_used []`, `rescreen_all {'screened': 1, 'alerts': 0}`) | HELD in red-team `scripts/proposals/2026-10-06-new-findings.md` §N4 |
| L-29 invisible or non-letter characters still give a MISS: VS16, U+034F, C0/DEL, U+2800, ideographic space, U+E000 (`names/arabic.py` `clean_name_text` strips Cf only) | MEDIUM | red-team N3 (High) | CONFIRMED, Medium | CONFIRMED (re-ran probe on `0129848`: 6 MISS rows for the exact listed name; ZWSP, BOM, soft hyphen and presentation forms HIT) | HELD in red-team proposal §N3 |
| L-30 "Re-screen all" always shows "Re-screening failed: 'customers'" (`app.py:3712` vs `engine.py:461`) | MEDIUM | mlro G9 (high) | CONFIRMED, Medium | CONFIRMED (`checks_2026_10_06.py`: `keys=['alerts','screened']`, route reads `outcome['customers']`). The test cannot catch it (`tests/test_api.py:1334-1340`) | HELD in `scripts/proposals/rescreen-banner-and-realert.md` §1 (one-line fix) |
| L-9 rescreen re-alerts `pending_review` and dismissed matches (`engine.py:369-375`, `status='open'` only) | MEDIUM | mlro G10, compliance CS-3, skeptic (carried) | CONFIRMED, Medium | CONFIRMED (`checks_2026_10_06.py`: before `[(1,'pending_review'),(2,'false_positive')]`, after adds open alerts 3 and 4) | HELD, same file §2. The dismissed half needs Nadhir's decision |
| L-31 freeze 24h clock starts at disposition, not detection/designation (`manager.py:1758`, `:2017-2025`) | MEDIUM | compliance CS-13 (H), code-reviewer CR-16 | mechanism CONFIRMED, legal PLAUSIBLE, Medium | CONFIRMED mechanism (read `manager.py:1758` "Sets identified_at=now()"); legal basis PLAUSIBLE (EOCN page quote, not the instrument) | Needs Nadhir / adviser |
| L-32 no 5-business-day CNMR/PNMR due date or overdue check | MEDIUM | compliance CS-15, mlro G8 | CONFIRMED, Medium | CONFIRMED (role, grep) | Needs Nadhir: proposal in CS report |
| L-33 no PNMR report type (`goaml.py:62`), while `reports.html:12` lists PNMRs | LOW-MED | compliance CS-14 | Low/Medium | CONFIRMED (read both lines) | Needs Nadhir: build it, or fix the copy |
| L-34 CR/LF in a customer reference stops the org's hourly freeze email (`mail.py:284`, outside the try) | LOW-MED | red-team N5 | CONFIRMED, Low/Medium | CONFIRMED (`stdlib_behaviour.py` #1 re-run; read `mail.py:284`) | HELD in red-team proposal §N5 |
| L-35 goAML finalise accepts XML-illegal characters, giving an export that is not well-formed | LOW-MED | red-team N6 | CONFIRMED, Medium | CONFIRMED (role probe; `stdlib_behaviour.py` #3 re-run: `ParseError`) | HELD in red-team proposal §N6 |
| L-21 huge `page` gives OverflowError 500 | LOW | red-team N1, skeptic | `alert_queue` REFUTED; `/audit` and feedback still overflow | CONFIRMED (re-ran `offset_overflow.py`: `alert_queue ok`, `audit_trail` and `feedback_list` OverflowError) | HELD in `scripts/proposals/paging-offset-and-zero-threshold.md` (10-05) |
| L-36 non-ASCII bearer gives 500 instead of 401 on 4 `/system/*` routes | LOW | red-team N7, code-reviewer CR-14 | PLAUSIBLE | PLAUSIBLE (stdlib behaviour confirmed; routes not called, by rule) | HELD in red-team proposal §N7 |
| L-37 #421 ranks every alert in Python before paging | LOW | code-reviewer CR-13 | CONFIRMED | CONFIRMED (role and skeptic benchmarks: 20k alerts take about 100-250 ms) | Carry; known limit, acceptable at DNFBP scale |
| L-23 PR #417 glass says "No match." for weak and unscreenable names | MEDIUM (unmerged) | code-reviewer CR-4 | accepted | CONFIRMED (role) | Needs Nadhir: fix before merging #417 |
| L-18 category priority lost past page 1 | closed | – | FIXED | **FIXED on master by PR #421** (compliance and skeptic repros now pass) | Closed |
| L-19 PEP alert told to freeze | closed | – | FIXED | **FIXED on master by PR #421** (mlro `log_pep.json`) | Closed. L-10 (EU/UK-only hits keep freeze wording) stays a legal question |
| L-2 Arabic presentation forms give an empty key | closed | – | FIXED | **FIXED on master by PR #425** (probe: presentation forms HIT 1.0). The remainder is L-29 | Closed |
| L-4 goAML reference blanked; L-8 CSRF on org-profile/logout; L-7 STR finalised without account | closed | – | FIXED | **FIXED on master by PR #424** (mlro F2, F3; red-team 0/48 POST routes without CSRF; skeptic `csrf_scan`) | Closed. F2b (raw JSON 400 on draft export) is LOW, carried |
| L-24 #418 policy, L-25 #416 blog | closed | – | resolved | Merged in revised form (#418, #420). CR-17 stale count "46 of 72", now 47 of 73, is cosmetic | Closed |
| L-17a `sync_replica` in a failing refresh's `finally` (`app.py:3962`) | closed | code-reviewer CR-2 | PLAUSIBLE | REFUTED as a defect: the comment says it is deliberate, and the call is best-effort and never raises | Closed |
| L-14 rename accepts case-variant duplicates | LOW | mlro F4 | – | CONFIRMED (role). Since #426 this is a display-confusion issue only | Carry |
| L-3, L-6, L-12, L-13, L-22 (extra-token miss, rescreen skips <25%/nominee owners, KYT hardening, reset-password 500, threshold 0.0) | as before | red-team (re-ran on `b7eeb2f`), mlro G11 | CONFIRMED | CONFIRMED (role); code unchanged since | HELD / carried |
| L-5, L-20 FATF fallback stale; live parser drops 5 names | MEDIUM | compliance CS-1/6/7 | carried | Unchanged (no FATF file changed) | Needs Nadhir: FATF snapshot from an unblocked network |
| L-10, L-11, L-15, L-26 (EU/UK freeze wording, #410 items, goAML XSD, G3-G5 risk labels), G4, G6, G7, G8, CS-16, CR-3 | LOW to MED | compliance, mlro, code-reviewer | PLAUSIBLE / accepted | PLAUSIBLE or CONFIRMED (role) | Carry |
| Cross-tenant isolation; `/api/v1` auth | – | qa, red-team | agree | No defect (`HITS: []`, 66 routes 0 leaks, on `b9d9db5` and `b7eeb2f`) | – |

**Severity adjudication**
- **L-28 is MEDIUM-HIGH, above the skeptic's Medium.** In Dubai DNFBP sectors, Russian and Chinese clients are common. Onboarding them by native-script name writes a screening row that looks clean, with no marker in the screening, audit or risk record, and rescreen counts it as screened. The ad-hoc page says "not screened" but the case file does not. I am not rating it HIGH because passport and MRZ names are Latin, which an operator would normally enter.
- **L-29 is MEDIUM (skeptic) not High (red-team).** The characters need an operator to type or paste them, and the same tokenizer fix closes both L-29 and L-28's root cause.
- **L-30 is MEDIUM, not mlro's high.** The rescreen runs and commits; only the banner is wrong. It ranks above Low because the banner hides the "N new alerts" count on the list-change control.
- **L-31 is MEDIUM until the primary text is read.** It would be HIGH if the instrument confirms that the clock starts at designation.

**Duplicates and contradictions**
- N4 and CR-12 are one defect (L-28). G10, CS-3 and L-9 are one defect.
- Red-team's "N1 still present" was true on `b7eeb2f` and false on `alert_queue` after #421. It is still true on `/audit` and the feedback page.
- Code-reviewer's RED headline rested on CR-1, which #426 has since fixed.

## 4. Combined assessment
1. The fix rate has caught up: L-1, L-2, L-4, L-7, L-8, L-18 and L-19 all closed in one day, each with tests. The full suite on `0129848` is in §5.
2. #425 added an `unscreenable` signal but wired it to the ad-hoc page only. The case-file path still records a silent clear (L-28), and the cleaner strips too little (L-29).
3. The rescreen control has two defects: a false failure banner (L-30) and duplicate alerts on decided matches (L-9). It runs after every list refresh, so both recur daily.
4. The TFS timing gaps (L-31, L-32) are design gaps that need legal confirmation, not bugs.
5. Tenant isolation held across all sweeps. No exposure to outsiders was found.

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_10_06.py`. It covers the owed L-9 repro, G9 and the #426 behaviour. Output on `0129848`: `G9 ... reproduces=True` / `L-9 ... new open alerts [3, 4], reproduces=True` / `4E id path: self-confirm after rename refused` / `4E legacy NULL-operator_id row: ... -> completed` / `exit 0`.
- C-2 Created `scripts/proposals/rescreen-banner-and-realert.md` (HELD), covering G9, L-9 and the #426 legacy fallback. Each changes route or engine logic, so none was applied.
- C-3 The owed L-7 repro and proposal are no longer needed: PR #424 fixed L-7 (mlro `log11.json`: "Cannot finalize report: the goAML export requires source account number ...", then draft edit and export 200).
- C-4 Re-ran on a `0129848` checkout in a scratch venv (requirements without passporteye/pdfminer; OCR not exercised): red-team `probe_unicode_bypass.py`, skeptic `offset_overflow.py`, `four_eyes_rename.py` and `stdlib_behaviour.py`, and `tests/test_foureyes_rename_bypass.py` (4 passed). The skeptic's `four_eyes_rename.py` still exits 0 because it passes no `operator_id`, which takes the legacy name path. It no longer models the routes.
- C-5 Verified the owed L-17. CR-2 is REFUTED (deliberate, commented at `app.py:3956-3962`). CR-3 is on PR #412, which is unchanged, so it is carried. L-26 is unchanged (`ruleset.yaml:76 domestic_pep: 30`; whether nationality drives it is not re-run).
- C-6 Full suite on `0129848` (OCR tests excluded, `-x`): running when this commit was pushed; the result is added in a follow-up commit on this branch.
- No test added for the open defects, because each would fail on master (rule 5). No existing file edited. The commit SHA is in the final reply.

## 6. Decisions needed from Nadhir
1. L-28 / L-29: persist `unscreenable` and route it to manual review at onboarding, UBO add and rescreen. Also widen `clean_name_text` to drop every non-letter, non-mark code point (red-team proposal §N3/§N4).
2. L-30: approve the one-line fix plus a test that asserts no "Re-screening failed".
3. L-9: approve suppressing re-alerts for `pending_review`. Decide whether a dismissed match re-alerts on every refresh or only when the list entry changes.
4. L-27: run a one-off check for `pending_review` alerts proposed before #426 (NULL `operator_id`), or backfill.
5. L-31 / L-32 / L-33: have an adviser confirm the 24h anchor and the 5-business-day CNMR/PNMR deadline from the instrument. Choose to build PNMR or to fix the `reports.html` copy.
6. Carried: L-5/L-20 FATF snapshot, L-10 EU/UK freeze wording, L-15 goAML XSD, #417 (L-23) before merge, a `corpus/` of primary legal texts fetched from an unblocked network, and the `github-advanced-security` 402 quota.

## 7. Next run: carried over
- Track whether these land on master: L-28, L-29, L-30, L-9, L-21, L-34, L-35, L-36.
- Re-run `repro_lead/checks_2026_10_06.py`. Exit 1 means G9 and L-9 are both fixed. Print-check the legacy line.
- The skeptic's `four_eyes_rename.py` should pass `operator_id`, or be retired now that #426 is in (a suggestion for the skeptic, not an instruction).
- Not yet driven end to end over HTTP: mobile `/api/v1/alerts/{id}/confirm` after a rename (#426 passes the id in code, at `mobile.py:1327`).
- L-14, L-26, CR-3, G6 to G8, F2b: low items to re-check if their code changes.
