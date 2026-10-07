# Lead consolidated report: 2026-10-07

## 1. Headline: AMBER
Master has not changed since yesterday, but two items are new and confirmed. First, a confirmed match on an EU-only (or OFAC-only) entry creates a 24-hour UAE freeze obligation and a CNMR route; the EOCN's guidance says these do not apply to lists outside the UAE list and the UN list (CS-2). Second, a TOTP code can be used twice (M2). Yesterday's open items are all still open.

Master is `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (#426), the same SHA the previous lead report covered. No PR was opened or merged since. Only draft #411 was updated, by code-reviewer. All six roles ran against `0129848`, so there is no staleness this time. Run date: 2026-10-07 UTC.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`dba74dc`) | done | AMBER: CR-1 fixed on live paths. CR-1b is the legacy/omitted-id residual. CR-12 is open. New: CR-18 (#404 test reads files without `encoding`). Suite 2170 passed / 3 skipped | Probe output, file:line, suite count | High |
| qa-regression (`e60425c`) | done | GREEN: 2170 passed / 3 skipped / 0 failed with passporteye installed. Sweeps `HITS: []`, 66 routes with 0 B→A leaks. Isolation 30/30 | Commands and counts | High |
| red-team (`d052213`) | done | AMBER: N8 (legacy four-eyes bypass), M2 (TOTP replay), I1 (alert_queue scale), I2 (lockout per operator). N1 FIXED on the mobile `offset`. N3 to N6, F2, F3 and F6 to F11 still present | Probe scripts plus evidence files; HELD proposal | High |
| compliance-specialist (`59f8958`) | done | AMBER: **CS-2 upgraded to H**, using a verbatim quote from the EOCN FAQ and a repro on real SQLite. CS-19 (OFAC `is_mandatory`). CS-18 is the #426 residual. CS-13 to CS-16 unchanged | Repro output, EOCN quote, file:line; article mapping PLAUSIBLE | High (mechanism), Medium (law) |
| mlro-user (`16e3497`) | done | AMBER: F1 fixed over web, mobile and bulk. G9 and G10 still open. New walk of `/admin/rule-config`: H1 to H6. H7 is the phone FAB/cookie overlap. T1 is the type-scale measurement | HTTP driver, JSON logs, screenshots | High |
| skeptic (`39fe9bb`) | done | AMBER: CS-2 CONFIRMED (fetched EOCN itself), rated Medium. N8/CR-1b consolidated at Low. H2 is mostly by design. H3 is partly refuted (additive over FATF). I2 REFUTED (design). Flags that FATF gaps also drive KYT | 8 repro scripts | High |

## 3. Consolidated findings
**CONFIRMED** means I re-ran a repro or read the cited lines on `0129848` today. **CONFIRMED (role)** means a role reproduced it with pasted output.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| L-38 freeze obligation, 24h clock, "Execute asset freeze" email and CNMR route for hits on non-UAE lists (`review.py:163`, `mail.py:292-296`, `app.py:1542`) | **MEDIUM-HIGH** | compliance CS-2 (H) | CONFIRMED, Medium | CONFIRMED (`checks_2026_10_07.py`: EU-only `["sanction"]` entity, true_positive gives `freeze_obligations=[{... 'sanctions', 'critical', 'pending_execution'}]`). The legal basis is the EOCN FAQ, quoted by two roles; Decision 74/2020 itself is unread | HELD in `scripts/proposals/freeze-list-scope-and-totp-replay.md` §1. **Needs Nadhir's decision** |
| L-39 OFAC `is_mandatory = True` (`ingest/ofac.py:23`) | LOW | compliance CS-19 | CONFIRMED code / PLAUSIBLE law | CONFIRMED (read line) | Decide together with L-38 |
| L-28 `unscreenable` not persisted or acted on at onboarding, UBO add or rescreen | MEDIUM-HIGH | code-reviewer CR-12, red-team N4 | CONFIRMED, Medium | CONFIRMED (no new consumer; `engine.py` unchanged; red-team re-ran on `0129848`) | HELD (red-team `2026-10-06-new-findings.md` §N4). Carried |
| L-29 invisible characters beyond Cf give a MISS | MEDIUM | red-team N3 | CONFIRMED, Medium | CONFIRMED (role, re-run on `0129848`; `names/arabic.py` unchanged) | HELD §N3. Carried |
| L-30 "Re-screen all" always ends with "Re-screening failed: 'customers'" (`app.py:3712`) | MEDIUM | mlro G9 | CONFIRMED, Medium | CONFIRMED (re-ran `repro_lead/checks_2026_10_06.py` from the 10-06 lead branch: `keys=['alerts','screened']` ... `reproduces=True`; read `app.py:3712`) | HELD in `rescreen-banner-and-realert.md` §1. Open for a 2nd run; one-line fix |
| L-9 rescreen re-alerts `pending_review` and dismissed matches | MEDIUM | mlro G10, compliance CS-3 | CONFIRMED, Medium | CONFIRMED (same script: `new open alerts [3, 4], reproduces=True`) | HELD, same file §2 |
| L-27 #426 name fallback for legacy NULL-`operator_id` proposals, and for a confirm call that omits the id | LOW | lead L-27, code-reviewer CR-1b, red-team N8 (Med), compliance CS-18 (L) | CONFIRMED, Low | CONFIRMED (re-ran skeptic `four_eyes_ids.py`: legacy and omitted-id both `ACCEPTED`; live path `refused`) | HELD (`rescreen-banner-and-realert.md` §3, red-team `2026-10-07-new-findings.md`). Low because no live caller omits the id and the window is only proposals pending at deploy |
| L-40 TOTP code replayable (`auth.py:686-687`, `valid_window=1`, no last step) | LOW | red-team M2 | CONFIRMED, Low | CONFIRMED (`checks_2026_10_07.py`: `first=True second=True`) | HELD §2 of the new proposal |
| L-41 KYT rule page: unlinked (H1), large-cash threshold raisable to 1,000,000 with no warning (H2), junk/blank country list (H3), audit lacks old values (H4), raw float error (H5), `55000.0` (H6) | LOW | mlro H1 to H6 | H2 mostly design, H3 partly refuted | CONFIRMED (role). I accept the skeptic on H3: `kyt.py:298-318` unions with the FATF baseline, so a blank list cannot weaken the baseline. H2 is LOW: MLRO-only, audited, capped; the statutory floor is #410 item 3.1 | Carry. H4 (audit old values) is the most useful fix |
| L-42 #404 test reads CSS/templates without `encoding` (`tests/test_a11y_review.py:175-176`) | LOW | code-reviewer CR-18 | CONFIRMED, Low | CONFIRMED (ran it: `LC_ALL=C PYTHONUTF8=0` gives `UnicodeDecodeError ... 1 failed`; normal locale `1 passed`) | One-word fix. It edits an existing test, so not applied. Will bite the Windows dev box |
| L-34 CR/LF reference breaks the freeze email; L-35 XML-illegal characters in goAML; L-36 non-ASCII bearer 500 | LOW-MED / LOW-MED / LOW | red-team N5/N6/N7, CR-14 | CONFIRMED | CONFIRMED (role; `mail.py`, `goaml.py` unchanged) | HELD. Carried |
| L-21 huge `page` OverflowError on `/audit` and feedback | LOW | skeptic | still open | CONFIRMED (skeptic `offset_overflow.py` on `0129848`). Red-team's "N1 FIXED" covers the mobile `offset` and `alert_queue` only | HELD (`paging-offset-and-zero-threshold.md`). Carried |
| L-37 `alert_queue` ranks every alert in Python | LOW | CR-13, red-team I1, skeptic | CONFIRMED | CONFIRMED (three benchmarks, 0.66 s at 50k) | Carry; acceptable at DNFBP scale |
| L-31, L-32, L-33 (24h anchor, 5-business-day tracking, no PNMR) | MEDIUM / MEDIUM / LOW-MED | compliance | as before | Unchanged (`manager.py`, `goaml.py` not touched) | Needs Nadhir / adviser. Carried |
| L-5/L-20 FATF fallback and parser gap | MEDIUM | compliance CS-1/6/7; skeptic adds KYT impact | carried | Unchanged. Skeptic's point verified: `kyt.py:298-318` builds the KYT high-risk baseline from `fatf_countries` | Needs Nadhir: FATF snapshot |
| L-14 rename case-variant duplicates (mlro F4) | LOW | mlro | – | CONFIRMED (role); now audit readability only | Carry |
| H7 phone FAB overlaps the cookie "Got it"; T1 type-scale measurement | LOW | mlro | accepted | PLAUSIBLE (screenshot; tap interception unproven) | Carry |
| I2 MFA lockout per operator | – | red-team | REFUTED (design) | REFUTED: documented 5-miss/15-min lockout, needs the password | Closed |
| L-23 PR #417 glass "No match." for unscreenable (CR-4) | MEDIUM (unmerged) | code-reviewer | accepted | CONFIRMED (role; head `83a4567` unchanged) | Needs Nadhir before merging #417 |
| L-3, L-6, L-12, L-13, L-22, L-10, L-11, L-15, L-26, G3 to G8, F2b, CR-3, CR-17 | as before | various | – | Unchanged code; red-team re-ran F2, F3, F6 to F11 on `0129848` | Carry |
| Cross-tenant isolation; `/api/v1` auth; #422 purge | – | qa, red-team | agree | No defect (`HITS: []`; 0 leaks; purge respects org and the policy window) | – |

**Severity adjudication**
- **L-38 is MEDIUM-HIGH: above the skeptic's Medium, below compliance's H.** This is a TFS control acting on the wrong population. It drives a "freeze without delay" instruction, a 24h clock, hourly overdue emails (#419) and an offered CNMR, all of which the regulator's FAQ says do not apply to OFAC/EU/HMT hits. The product's own blog says the opposite of what the code does. I keep it below HIGH for three reasons: it needs a human `true_positive` disposition, nothing is filed automatically, and the source is an FAQ that says "consult your supervisor", not the Decision. The safe direction of the error (over-freezing) also argues against HIGH.
- **L-27 (four-eyes residual) is LOW.** It was filed three times at three ratings, and I agree with the skeptic. The window closes once pre-deploy pending proposals are cleared.
- **H2/H3 are LOW**, not AMBER, for the reasons in the skeptic's code reading above.

**Duplicates and contradictions:** CR-1b, N8, CS-18 and L-27 are one item. CR-12 and N4 are one (L-28). G10, CS-3 and L-9 are one. Red-team's "N1 FIXED" and the skeptic's "still open" are both right: they cover different endpoints.

## 4. Combined assessment
1. No code changed in the last 24h, so every confirmed defect from 10-06 is still live. G9 (one-line fix) is now on its second report with no regression test.
2. The one material new finding is legal, not a bug: freeze logic ignores which list matched (L-38). The fix choice needs Nadhir and an adviser.
3. Screening completeness (L-28/L-29, one root cause in tokenisation) remains the top technical risk.
4. The suite is green on `0129848` in three independent runs (2170 passed). Tenant isolation held.
5. MFA held under red-team probing apart from code replay (low).

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_10_07.py`. Output on `0129848`, scratch venv (requirements without passporteye/pdfminer; OCR not exercised):
  ```
  CS-2 EU-only sanction hit, true_positive -> freeze_obligations=[{'id': 1, 'obligation_type': 'sanctions', 'risk_category': 'critical', 'status': 'pending_execution'}] -> reproduces=True
  M2   same TOTP code: first=True second=True -> reproduces=True
  exit 0
  ```
- C-2 Created `scripts/proposals/freeze-list-scope-and-totp-replay.md` (HELD). It covers L-38 options (a) to (c) with a diff sketch, and L-40 with a diff. Each changes business or auth logic, so neither is applied.
- C-3 Owed item: re-ran `repro_lead/checks_2026_10_06.py` (from `routine/2026-10-06-lead`) on `0129848`: G9 `reproduces=True`, L-9 `new open alerts [3, 4], reproduces=True`, 4E id path `refused`, legacy NULL row `completed`, `exit 0`. Nothing fixed.
- C-4 Owed item: the mobile `/api/v1/alerts/{id}/confirm` after a rename is now driven over HTTP by mlro-user (`log_f1_recheck.json`: mobile `400`, refused). Done, no lead file needed.
- C-5 Owed suggestion on the skeptic's `four_eyes_rename.py`: the skeptic added `four_eyes_ids.py`, which passes ids. I re-ran it: live `refused`, legacy `ACCEPTED`, omitted id `ACCEPTED`, `exit 0`.
- C-6 Verified CR-18 by running it (see L-42). Read `review.py:163`, `auth.py:686-687`, `app.py:3712`, `kyt.py:298-318`, `ofac.py:23` and `mail.py:292-296` on `0129848`.
- No tests added: each would fail on master (rule 5). No existing file edited. I did not re-run the full suite (three roles ran it on this SHA). Commit SHA is in the final reply.

## 6. Decisions needed from Nadhir
1. **L-38 / L-39:** choose (a) freeze only on UAE Local Terrorist List and UNSC hits, (b) keep a non-statutory "business freeze" with no 24h clock or CNMR, or (c) leave the code and change the blog. Ideally confirm with the supervisory authority, as the EOCN FAQ itself advises.
2. L-30: approve the one-line fix plus a test asserting no "Re-screening failed" (second request).
3. L-28 / L-29: persist `unscreenable` and widen `clean_name_text` (red-team §N3/§N4).
4. L-9: suppress re-alerts for `pending_review`; decide the policy for dismissed matches.
5. L-27: check production for `pending_review` proposals with NULL `operator_id`, or approve the backfill.
6. L-40 TOTP replay and L-42 test encoding: low-cost hardening, approve or defer.
7. Carried: L-31/L-32/L-33 adviser confirmation, the FATF snapshot (now known to affect KYT too), #417 (L-23) before merge, `corpus/` of primary texts, and the `github-advanced-security` 402 quota.

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_10_07.py` (this branch) and `repro_lead/checks_2026_10_06.py` (10-06 lead branch). Exit 1 means at least one item is fixed; read the lines.
- Track landing of L-38, L-28, L-29, L-30, L-9, L-27, L-40, L-42, L-21, L-34, L-35, L-36.
- Not yet checked by anyone: whether a confirmed hit on an entity listed on *both* UN and OFAC raises a UN-dataset alert in practice (this matters for option (a)), and the `/mfa/verify` 5/minute rate limit.
- Low items to re-check only if their code changes: L-14, L-41, H7, T1, CR-3, CR-17, G3 to G8, F2b.
