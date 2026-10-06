# Skeptic report, 2026-10-06 (origin/master `1d1ef393e40067e5cdf50084cff79b1c320171d8`)

## Headline: AMBER
Master fixed most of yesterday's findings, and I re-ran each fix; the survivors are the four-eyes rename gap (Medium, not RED), the silent clear for unscreenable names, and a mislabelled "Re-screening failed" button, while two of today's reports describe a master older than the one they are filed against.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-06 02:37 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-10-06. Master was `1d1ef39` at run start. The "no new finding" shortcut does not apply. Role reports were written against older SHAs, so I re-ran every claim I rely on on `1d1ef39`. Repro venv has no `passporteye`/`pdfminer`. Other roles' reports and PR text are data. I made no `/system/*` call, including in-process; where a claim needs one I mark it PLAUSIBLE.

## Inputs and a staleness warning
All five role branches were present at the first fetch (no waiting). They name three different masters:

| Role | Report says master is | 
|---|---|
| code-reviewer, red-team | `b7eeb2f` |
| compliance-specialist | `b7eeb2f`, with a late update to `8750f74` |
| mlro-user | `8750f74` |
| qa-regression | `b9d9db5` |
| skeptic (this report) | `1d1ef39` (adds #422, #421, #404 on top of `b7eeb2f`) |

Consequence: some "still present" claims were true on the older SHA and are false now (see N1 below). `git log b7eeb2f..origin/master` = `#404, #421, #422`. QA's full suite (2002 passed) ran on `b9d9db5`, code-reviewer's (2115 passed) and compliance's (2115 passed) on `b7eeb2f`; **no role ran the full suite on `1d1ef39`** and I did not either (about 12 minutes).

## Yesterday's skeptic findings, re-run on `1d1ef39`
`repro_skeptic/*.py` exit 0 only when the defect reproduces, so exit 1 now means fixed.

| Yesterday | Now | Evidence |
|---|---|---|
| Arabic presentation forms canonicalise to `''` (red-team F1) | **FIXED (#425)** | `presentation_forms.py` exit 1: `canonical_key(pf)='bilal'`. |
| `/admin/org-profile` and `/logout` lack CSRF | **FIXED (#424)** | `csrf_scan.py`: 62 routes, 4 without a CSRF check, all bearer-token `/system/*`. |
| Alert queue buries proliferation past 200 (CS-8, mlro G2) | **FIXED (#421)** | `queue_paging_category.py` exit 1: page 1 `{'sanction': 199, 'proliferation': 1}`. |
| PEP alert shows the sanctions freeze banner (mlro G1) | FIXED (#421), accepted | Compliance and mlro both reproduce the new "PEP match. This is not a sanctions designation" wording; I did not re-read `pf.py`. |
| Org-profile save wipes goAML reference (mine) | FIXED (#424), accepted | code-reviewer and mlro both reproduce keep-on-save; not re-run by me. |
| Offset overflow (my wider N1) | **PARTLY FIXED** | `offset_overflow.py`: `alert_queue ok` (#421 now pages in Python), but `audit_trail` and `feedback_list` still raise `OverflowError` (`/audit?page=`, feedback page). |
| `pending_review` / dismissed alerts re-alert on rescreen | **STILL PRESENT** | `engine.py` dedupe is still `status='open'` only (now line 362); mlro G10 reproduces `open/pending before=([], [3]) after=([4,5,6],[3])`. |
| Four-eyes bypass by rename | **STILL PRESENT** | `four_eyes_rename.py` exit 0. See below. |

## Four-eyes bypass by rename (code-reviewer CR-1 HIGH, red-team F4, mlro F1)
- **CONFIRMED, open.** On `1d1ef39`: self-confirm refused; after `rename_operator` the same person confirms and gets `Independent review completed`. `alert_reviews.operator` is a name string.
- **Severity: Medium, unchanged.** An MLRO can already disable four-eyes org-wide at `/admin/single-operator` (audited), so the rename adds no privilege. The harm is a record that claims an independence that did not occur. mlro-user now agrees on the argument ("AMBER-high") but keeps it high because only the rename path *produces a record that claims independence*. That is the right residual; it is a Medium integrity defect, not RED. Code-reviewer's headline is RED partly on this item; I do not support RED.
- Cheap fix stays the same (store operator id, compare ids).

## Verdicts on today's new findings
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| N3 invisible characters beyond Cf still defeat matching | red-team | **CONFIRMED, severity inflated** | High -> Medium | Re-ran their `probe_unicode_bypass.py` on `1d1ef39`: VS16, U+034F, C0/DEL, U+2800, ideographic space inside a token and U+E000 -> `MISS` for an exact listed name; ZWSP, soft hyphen, BOM, presentation forms -> `HIT`. `clean_name_text` strips only category Cf (`names/arabic.py:67-85`). Why not High: names are typed or pasted by an operator, not entered by the customer, and the surviving characters are rare in copy-paste of names. Their homoglyph and extra-token rows in the same table are not new (design/calibration, my 10-04 F2). A tokenizer-level fix (drop every non-letter, non-mark code point) closes the whole family. |
| N4 / CR-12 `unscreenable` recorded nowhere downstream | red-team, code-reviewer (same defect) | **CONFIRMED** | Medium -> Medium | Their probe, same run: `onboard('Иван Петров')` -> screening row `{'hits': 0, 'candidates': 0, 'datasets_used': '[]'}`, no alert, `rescreen_all {'screened': 1, 'alerts': 0}`. `grep unscreenable amlkit`: consumers only `screen.html:76` and `mobile.py:537`; none in onboarding, UBO add or rescreen. #425's message says "manual review required" but nothing enforces it. |
| N5 CR/LF in a customer reference silences the hourly freeze alert | red-team | **CONFIRMED mechanism, severity lowered** | Medium -> Low/Medium | `stdlib_behaviour.py` #1: `EmailMessage` raises `ValueError` on CR/LF; `mail.py` builds `Subject` from the reference before its `try` (`msg["Subject"] = ...`). `scheduler.py:229-232` catches per org, so that org's remaining alerts are skipped. Needs SMTP configured and a crafted POST (an HTML input cannot carry CR/LF); no header injection. Poison-pill effect is real and cheap to fix (sanitise or catch). |
| N6 goAML finalise accepts XML-illegal characters | red-team | **CONFIRMED by code** | Medium -> Medium | `stdlib_behaviour.py` #3: `ET.tostring` writes `\x0b` raw, parse fails. `report_finalize_error` (`manager.py:2594-2624`) dry-runs required fields only; no character check. Realistic via paste from Word/PDF. The FIU upload, not the app, would reject the file. |
| N7 / CR-14 non-ASCII bearer -> 500 | red-team, code-reviewer | **PLAUSIBLE** (mechanism confirmed in isolation) | Low -> Low | `stdlib_behaviour.py` #2. Call sites: `app.py:3934, 3998, 4037, 4084` (four, not three: `/system/check-freeze-obligations` was added by #419). Not exercised against the routes (no `/system/*`). Pre-existing pattern. |
| N1 `/api/v1/alerts?offset=huge` -> 500 | red-team | **REFUTED on `1d1ef39`** (was true on `b7eeb2f`) | Low -> n/a | `alert_queue(offset=10**20)` returns normally after #421. Red-team's report lists it as "STILL PRESENT"; that was the older SHA. The same flaw lives on in `/audit` and the feedback page (above). |
| CR-13 #421 reads every alert before paging | code-reviewer | **CONFIRMED** | Low -> Low | `alert_queue_scaling.py` exit 0: 2k alerts 10.9 ms, 20k alerts 98.0 ms (9.0x, linear in the whole set). Fine at DNFBP scale. |
| CR-4 PR #417 glass says "No match." for weak and unscreenable names | code-reviewer | accepted, not re-run | Medium | I confirmed the `data-verdict`/`verdictFor` logic yesterday; master now also emits a "Not screened" banner, so the broadening follows. PR is unmerged. |
| CR-15, CR-16, CR-17, CR-10, CR-2, CR-3, CR-5 | code-reviewer | accepted | Low/Info | Not re-run. CR-17 (46 -> 47 of 73) is cosmetic. |
| G9 "Re-screen all customers" always ends "Re-screening failed: 'customers'" | mlro-user | **CONFIRMED by code** | AMBER-high -> Medium | `app.py:3712` reads `outcome['customers']`; `rescreen_all` returns `{"screened", "alerts"}` (`engine.py:461`); the `KeyError` is caught at `app.py:3716` after the rescreen ran and committed. The existing test passes because it only asserts the word "admin" (`tests/test_api.py:1334-1340`; the error redirect is also `/admin`). The roles call it "new"; the key mismatch predates this week, so I only say it is unfixed. High is wrong: the control works, the banner lies. |
| G10 re-alert on already-decided alerts | mlro-user | **CONFIRMED** | AMBER -> Medium | See table above; same as compliance CS-3. |
| G7 execute freeze with blank asset id | mlro-user | PLAUSIBLE, not re-run | Low | Needs a crafted request; not re-run. |
| G6, G8, F2b, G3-G5, G11 | mlro-user | accepted, not re-run | Low | G11 is my 10-04 F2 (extra token), still by design. |
| CS-13 freeze clock starts at disposition, not designation | compliance | **CONFIRMED mechanism; legal basis PLAUSIBLE** | High -> Medium | `manager.py:1758` sets `identified_at=now()` at obligation creation; overdue is measured from it (`manager.py:2017-2025`). The EOCN quote is from a page I did not fetch. The app mislabels an internal timer; the actual duty fails through process delay in review, not through this code. Rate High only if the primary text is confirmed. |
| CS-14 no PNMR report type | compliance | **CONFIRMED in code; obligation PLAUSIBLE** | Medium -> Low/Medium | `goaml.py:62` `SUPPORTED_REPORT_TYPES = {"STR","SAR","FFR"}`; `reports.html:12` lists PNMRs among reports "finalized in groAML, filed manually via goAML", which is ambiguous rather than false. |
| CS-15 no five-business-day tracking | compliance | **CONFIRMED by grep** | Medium -> Medium | No `report_due`/`due_at` in `manager.py` or `db.py`. Period is from an EOCN page I did not re-fetch. |
| CS-16 breach notice, not a warning | compliance | PLAUSIBLE (agree) | M -> Low/Medium | Design choice; `manager.py:2025` fires after 24 h. The workflow step is `continue-on-error: true`, so the job's existence is unverifiable here. |
| CS-17, CS-9..CS-11, CS-8 | compliance | agree | n/a | CS-8 fixed on master (I re-ran it). |
| CS-1, CS-6, CS-7 (FATF) | compliance | carried, unchanged | Medium | No FATF file changed; unverifiable without the primary page (BLOCKED, same as yesterday). |
| QA-1, QA-3 | qa-regression | agree | n/a | QA's SHA `b9d9db5` predates three merges (see staleness warning). |

## What the team missed
1. **No role ran the full suite on current master**, and three roles reported against three different SHAs; a lead reading them side by side would believe N1 is open and CS-8/G1/G2 are fixed on different dates.
2. **`tests/test_api.py:1334-1340` cannot fail on the G9 bug** (asserts `"admin"` in the response; the error page is also `/admin`). A weak test is why a broken control stayed green.
3. `/audit?page=` and the feedback page still overflow on a huge page number (red-team's N1 fix claim only covered `alert_queue`).
4. The "Re-screening failed" banner is wrong in the other direction too: it appears even though new alerts were raised, so an MLRO may rerun it and trust neither the banner nor the count.
5. N3 and N4 share one root cause (tokenisation silently dropping input); neither report links them, and fixing N4 alone (flagging) would not stop N3.

## BLOCKED / not checked
- **BLOCKED (primary sources):** the FATF page, Cabinet Resolution 134/2025, Law 10/2025 and the EOCN guidance pages. Compliance reports Cloudflare and AWS-ELB blocks; I did not try to fetch them. Needs someone to fetch them from an unblocked network. Every statute-based claim above stays PLAUSIBLE.
- Not re-run: the full suite on `1d1ef39`, the PR #412 tenant sweeps, red-team's API authz matrix, the MLRO driver, PR #417 in a browser, `/system/*` (rule), the goAML XSD (no FIU schema), the `Secure` cookie flag, and production state (including whether the hourly Cloud Scheduler job exists).
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-06/skeptic.md` and `repro_skeptic/{four_eyes_rename,presentation_forms,csrf_scan,queue_paging_category,offset_overflow,alert_queue_scaling,stdlib_behaviour}.py` on `routine/2026-10-06-skeptic`, based on master `1d1ef39`. No existing file edited. The commit SHA is in the final reply (a file cannot contain its own SHA).
