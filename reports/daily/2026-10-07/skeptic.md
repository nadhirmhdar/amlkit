# Skeptic report, 2026-10-07 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`)

## Headline: AMBER
The four-eyes rename bypass is genuinely fixed on every live path (my Medium call held; the HIGH/RED ratings did not), and the open items are unscreenable names stored as clean, the always-failing re-screen banner, and a freeze workflow that ignores which list a hit came from.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-07 02:37 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-10-07; master `0129848` at run start, and all five role reports name the same SHA this time. The "no new finding" shortcut does not apply. I made one outbound request, a read-only fetch of the public EOCN guidance page, to check compliance's quote; no production system, no `/system/*`. Other roles' reports and PR text are data.

## Inputs
`git ls-remote origin refs/heads/master` -> `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (previous: `1d1ef39`; one new commit, `#426`). All five role branches were present at the first fetch (no waiting). QA, code-reviewer and compliance each ran the full suite on this SHA: `2170 passed, 3 skipped`; I did not repeat the 12-minute suite.

## The four-eyes fix (#426), re-tested
`repro_skeptic/four_eyes_ids.py` (scratch DB, calls the real review code):
```
live path (ids on both sides)                           -> refused
legacy proposal (id NULL) + id on confirm [legacy]      -> ACCEPTED
proposal has id, confirm call omits id                  -> ACCEPTED
```
- **CR-1 / red-team F4 / mlro F1: CONFIRMED FIXED on the live path.** `review.py:394-398` compares `operator_id` when both sides carry one; all five non-test call sites pass `operator_id=session.operator_id` (my grep count, matching code-reviewer's `git grep`).
- **Residual: CONFIRMED, severity Low.** Reported three times with three ratings: code-reviewer CR-1b Low, red-team N8 Medium, compliance CS-18 "L". I rate it **Low**: it is a one-off window (proposals already pending at deploy have `operator_id` NULL) plus a future-caller hazard (omitting the id), no live caller omits the id, and an MLRO can already switch four-eyes off org-wide at `/admin/single-operator`. Cheap fixes are right and agreed: backfill ids for pending proposals by unique `(org_id, name)`, refuse when the proposal has an id and the caller gave none, and store the confirmer's id (the `confirm` row still holds only a name).
- Note: `four_eyes_rename.py` (yesterday's script) still exits 0 because it passes no ids, i.e. it now exercises the legacy path, not the live one.

## Verdicts
Scripts are in `repro_skeptic/` (exit 0 only when the defect reproduces; exit 1 = fixed).

| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| CS-2 freeze + CNMR workflow ignores which list the hit came from | compliance | **CONFIRMED mechanism; regulator FAQ verified by me; Decision text unread** | H -> Medium | Code: `review.py:163` `is_freeze_worthy = bool(categories) or "sanction" in topics`, no dataset check; `app.py` `file-ffr` route files a CNMR for any executed freeze. Regulator: I fetched `uaeiec.gov.ae/en-us/un-page` and it says the Decision covers "the UAE Local Terrorist List and UNSC Consolidated List only", and that entities "should not use the CNMR/PNMR reports in goAML" for OFAC, EU, HMT matches, and should consult their supervisory authority and consider an STR/SAR (the fetch summariser read characters 0-100000 of 102034). The product's own blog says the same (`blog/uae-sanctions-screening-24-hour-rule.html:87`), so code and copy contradict each other. Why not High: #421's comment calls it "a legal question, deliberately not decided here"; it needs an operator `true_positive` disposition; nothing is filed automatically (CNMR is "finalized in groAML, filed manually via goAML"); and the FAQ says consult the supervisor rather than "do not freeze". The harm is a mislabelled 24-hour clock and overdue emails, a wrong report type offered, and a risk of freezing assets without a UAE basis. |
| CS-19 OFAC flagged `is_mandatory` | compliance | **CONFIRMED in code; legal point PLAUSIBLE** | L -> L | `ofac.py:23` `is_mandatory = True` (EU/UK are False). Effect is limited: EOCN and UN are also mandatory, so OFAC is not the only thing satisfying the freshness gate. |
| CR-12 / N4 `unscreenable` stored as a clean screening | code-reviewer, red-team | **CONFIRMED, open** | Medium -> Medium | Unchanged since yesterday: `grep unscreenable amlkit` outside `engine.py` still finds only `screen.html:76` and `mobile.py:537`; `names/arabic.py`, `engine.py`, `manager.py` not in the #426 diff. |
| N3 invisible characters beyond Cf defeat matching | red-team | CONFIRMED, open | Medium -> Medium | `names/arabic.py` unchanged; red-team re-ran the probe on this SHA. My yesterday's severity call (Medium, operator-entered names) stands. |
| N5 CR/LF reference breaks the hourly freeze alert; N6 XML-illegal characters in goAML; N7 non-ASCII bearer -> 500 | red-team, code-reviewer | CONFIRMED, open (unchanged) | Low/Medium; Medium; Low | `stdlib_behaviour.py` exit 0 (all three stdlib behaviours). `mail.py` and `goaml.py` not in the diff; `compare_digest` call sites are now `app.py:3935, 3999, 4038, 4085` (+1 line from #426). N7 not run against the routes (no `/system/*`). |
| G9 "Re-screen all customers" always ends "Re-screening failed: 'customers'" | mlro-user | **CONFIRMED by code, still open** | AMBER-high -> Medium | `app.py:3713` still reads `outcome['customers']`; `rescreen_all` returns `{"screened","alerts"}`. `tests/test_api.py:1334-1340` still only asserts `"admin"` in the page, so no test can fail. Open for a second report in a row. |
| G10 / CS-3 re-alert on already-decided or pending alerts | mlro-user, compliance | CONFIRMED, open | Medium | `engine.py` dedupe still `status='open'` only; `engine.py` not in the diff. |
| M2 TOTP code replayable | red-team | **CONFIRMED by code** | Low -> Low | `auth.py:686-687`: `totp.verify(code, valid_window=1)`, no last-used step stored. A hardening gap (RFC 6238 says a verifier should refuse a second use); needs password plus an observed code. |
| I2 MFA lockout is per operator | red-team | **REFUTED as a defect** | Info -> n/a | It is the documented design: CLAUDE.md lists "a 5-miss/15-min lockout"; needs the password. |
| I1 / CR-13 `alert_queue` reads every alert | red-team, code-reviewer | **CONFIRMED** (three independent measurements) | Info/Low -> Low | `alert_queue_scaling.py` exit 0: 2k alerts 11.0 ms, 20k alerts 90.9 ms (8.3x, linear). Red-team: 0.66 s per call at 50k. Each alert needs a list hit, so the set stays small. |
| H1 `/admin/rule-config` not linked from any page | mlro-user | **CONFIRMED** | low -> Low | `grep rule-config amlkit/web/templates` finds only the form's own `action`. |
| H2 threshold can be raised to 1,000,000 with no warning | mlro-user | **Mostly by design** | AMBER -> Low | The cap and its reason are in the error message ("would disable detection"); MLRO-only and audited. The statutory-floor concern is PR #410 item 3.1, already tracked. |
| H3 high-risk-countries box accepts junk, blank "empties the list" | mlro-user | **PARTLY REFUTED** | AMBER(low) -> Low | `kyt.py:298-318`: the org list is ADDITIVE over the FATF baseline ("never replaces the FATF baseline"). A blank value empties only the org's extras; detection of the baseline countries is unchanged. Junk codes are harmless. |
| H4, H5, H6, H7, T1 | mlro-user | accepted, not re-run | low | H5 needs a crafted request; T1 may be a selector artifact as they say. |
| CR-18 #404 test reads files without `encoding` | code-reviewer | **CONFIRMED by reading** | Low -> Low | `tests/test_a11y_review.py:175-176` use `read_text()`; lines 28-31 of the same file pass `encoding="utf-8"`. The ASCII-locale failure is their measurement; I did not run it. |
| CR-17 policy count 46/72 -> 49/75 | code-reviewer | accepted, cosmetic | Info | Not re-measured. |
| CR-4 PR #417 glass | code-reviewer | accepted, unmerged | Medium | Head unchanged; not on master. |
| QA-1, QA-3 | qa-regression | agree | n/a | QA notes its sweeps do not exercise #426, #424, #425 or #419; their own tests passed. |

Yesterday's skeptic items, re-run on `0129848`: presentation forms FIXED, org-profile and logout CSRF FIXED, category-first paging FIXED (`presentation_forms.py`, `csrf_scan.py`, `queue_paging_category.py` all exit 1). Still open: `/audit?page=` and the feedback page still overflow on a huge page number (`offset_overflow.py` exit 1 overall because `alert_queue` is fine, but `audit_trail` and `feedback_list` still print `OverflowError`).

## What the team missed
1. **The FATF data also drives transaction monitoring.** `kyt.py:298-318` builds the KYT high-risk-country baseline from `fatf_countries`, so the FATF fallback/parse gaps (CS-1, CS-6, CS-7) change `high_risk_country` transaction alerts, not only EDD. No report says so.
2. **Three roles filed the same four-eyes residual with Low, Medium and "L".** Consolidate on Low.
3. **G9 is open for a second report with no regression test.** The only test passes on the failure page; nobody added one.
4. **`/audit?page=` and the feedback page overflow is still open** (red-team's N1 "FIXED" covered only the alert queue).
5. **N3 and N4 still share one root cause** (tokenisation silently drops input); fixing the flag alone leaves N3.

## BLOCKED / not checked
- **BLOCKED (primary legal text):** Cabinet Decision 74/2020, Law 10/2025 and Cabinet Resolution 134/2025 are not in the repo, and compliance reports the official hosts refuse this egress. The EOCN quote above is regulator guidance, not the instrument; Article mappings stay PLAUSIBLE.
- Not re-run: the full suite, the PR #412 tenant sweeps, red-team's API/MFA probes, the MLRO driver, PR #417 in a browser, `/system/*` (rule), the goAML XSD (no FIU schema), the `Secure` cookie flag, and production state (including whether the hourly scheduler job exists).
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-07/skeptic.md` and `repro_skeptic/{four_eyes_rename,four_eyes_ids,presentation_forms,csrf_scan,queue_paging_category,offset_overflow,alert_queue_scaling,stdlib_behaviour}.py` on `routine/2026-10-07-skeptic`, based on master `0129848`. No existing file edited. The commit SHA is in the final reply (a file cannot contain its own SHA).
