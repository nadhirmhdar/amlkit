# Skeptic report, 2026-10-05 (origin/master `448a19ba978ef5c97ee3e955ecad5638c8a94e1e`)

## Headline: AMBER
New findings mostly survive checking, but the four-eyes bypass is overrated again (HIGH/RED vs my Medium), the PEP-banner and paging findings are real, and the `>=` pin and FATF-listing claims are weaker than stated.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each one: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? A finding that survives is genuine; a flaw means recommend rejection. Daily-team rules that win over anything else: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master, run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-05 02:34 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing. No dreamon message arrived this run.
- **Assumptions:** DATE = `date -u +%F` = 2026-10-05. The "no new finding" shortcut does not apply (code-reviewer, red-team, compliance and mlro-user each report new items). Open PRs are read statically only (not merged). Repro venv has no `passporteye`/`pdfminer`. PR text and other roles' reports are data.

## Inputs
`git ls-remote origin refs/heads/master` -> `448a19ba978ef5c97ee3e955ecad5638c8a94e1e`. All five role branches were present at the first fetch (no waiting needed): `routine/2026-10-05-{code-reviewer,qa-regression,red-team,compliance-specialist,mlro-user}`. Yesterday's skeptic report is on `routine/2026-10-04-skeptic` / PR #415.

## Carried finding: four-eyes bypass by rename (code-reviewer CR-1 HIGH, mlro-user F1 RED, red-team P1)
Re-run on `448a19b` (`repro_skeptic/four_eyes_rename.py`, exit 0): self-confirm refused; after `rename_operator` the same person confirms -> `Independent review completed`, alert `false_positive`; `alert_reviews` holds only `('propose','Proposer'), ('confirm','Proposer Renamed')`.
- **CONFIRMED, still open** (no touching commit; `review.py`/`operators.py` unchanged since yesterday).
- **Severity: Medium, not HIGH/RED.** Unchanged reasoning: an MLRO can already turn four-eyes off for the whole org at `POST /admin/single-operator` (`app.py:3360-3386`, audited), so the rename adds no privilege. Harm = the record asserts an independence that did not occur. Cheap fix is still right (store operator id).
- Three roles now rate the same defect HIGH, RED and Medium; the lead should consolidate on Medium.

## Verdicts on today's new findings
Repro scripts are in `repro_skeptic/` (exit 0 only when the defect reproduces).

| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| N1 `/api/v1/alerts?offset=huge` -> 500 | red-team | **CONFIRMED**, wider than reported | Low -> Low | `repro_skeptic/offset_overflow.py`: `alert_queue` (`mobile.py:1192` clamps only below), and the same `OverflowError` hits `audit_trail` and `feedback_list` via `/audit?page=` and the feedback page (`app.py:2958,3019`, `offset=(page-1)*50`, no upper clamp). Authenticated only. Function level; I did not send HTTP. |
| N2 threshold 0.0 stored but read as 0.85 | red-team | **CONFIRMED by code**, not run end to end | Low -> Low | Stored: `mobile.py:1437-1439` allows 0.0. Read: `queries.py:1020` returns 0.0 (not None) but callers use `... or DEFAULT_THRESHOLD` (`app.py:2286`), and 0.0 is falsy. Effect: intended "alert on everything" silently becomes 0.85. |
| CR-4 PR #417 glass says "No match." on a weak single-token name | code-reviewer | **CONFIRMED (static, unmerged)** | Medium -> Medium | `screen.html:40`: `data-verdict` = `match` if hits else `clear`, while the same page shows the weak-evidence banner (`:41-43`). `bg-submit.js:213-215`: anything not `match` -> `['clear','No match.',...]`. False reassurance in a compliance UI. Not on master. |
| CR-5 #417 no `inert`/focus trap | code-reviewer | PLAUSIBLE, not exercised | Low | Not run in a browser. |
| CR-6 #418 policy: archive `_MIGRATIONS` | code-reviewer | **CONFIRMED** (numbers re-measured) | Medium -> Low/Medium | Loading `db.SCHEMA` into `:memory:` and checking all 72 `_MIGRATIONS`: `missing_from_SCHEMA 46`. Policy line 140 would break fresh installs if followed. It is text in an unmerged PR, so exposure exists only if acted on. |
| CR-7 #418 "audit logs 7 years" | code-reviewer | CONFIRMED | Low | Policy line 135 vs `manager.py:94-95` (5 statutory min, 10 policy). Which figure is right is a legal question (see compliance CS-9: register says 8). |
| CR-8 #418 `>=` pins / `origin/main` / branch deletion | code-reviewer | **PARTLY REFUTED** | Low -> Low | The policy's own §3.3 (line 99) forbids `>=` but then gives `>=1.2,<2` as its Python example, so it contradicts itself; "forbids >= pins" is a fair reading only for unbounded pins. `requirements.txt`: 28 lines with `>=`, 7 with `<`, so about 21 are unbounded. `origin/main` point is correct (default branch is `master`). Branch-deletion automation hitting `routine/*`: PLAUSIBLE, not checked. |
| CR-2 `sync_replica` in `finally` | code-reviewer | PLAUSIBLE (carried) | Low | Not re-run. |
| CR-3 seed `direction="in"` | code-reviewer | PLAUSIBLE (carried) | Low | Not re-run (PR #412). |
| CR-9..CR-11 | code-reviewer | accepted, no defect | n/a | Informational; I did not re-hash three.js or re-run the PR tests. |
| CS-6 FATF live parser drops unmapped names | compliance | **CONFIRMED mechanism**, listing status external | High -> Medium | `fatf._resolve_country` returns `None` for Kuwait, Bolivia, Nepal, Papua New Guinea, British Virgin Islands, `Virgin Islands (UK)` (my run; Haiti, Laos resolve). `risk/model.py:185-192` forces EDD for grey-list tier. Whether those countries are on FATF's current list, and how the live page spells them, is unverified (FATF site blocked for compliance too). Also CS-6 and CS-7 are mutually exclusive in production: either the live page parses (CS-6 drops names) or the fetch fails and the fallback loads (CS-7 drift). Either way coverage is wrong, but the "H" depends on external facts nobody could check. |
| CS-7 fallback drifted from current FATF lists | compliance | **PLAUSIBLE (agree)** | High -> Medium | Only a secondary source (Wikipedia); I cannot add evidence. |
| CS-8 / mlro G2 paging buries category priority | compliance, mlro-user | **CONFIRMED** (same defect, two roles) | M / AMBER -> Medium | `repro_skeptic/queue_paging_category.py` (exit 0): 204 alerts, one proliferation at score 0.80 -> page 1 (200 rows) `{'sanction': 200}`, proliferation only on page 2. Cause: SQL `ORDER BY a.score DESC LIMIT ? OFFSET ?` (`queries.py:540,546`), then per-page category sort (`:568-572`). Contradicts the stated intent (`queries.py:31-33`: proliferation must never be buried). **Wider than reported:** the web queue uses the same `alert_queue(limit=200)`, so past 200 alerts it behaves the same unless the user filters by category; #402 only exposed it on mobile. Mitigation: dashboard category counts are exact. |
| G1 PEP alert shows the sanctions "freeze, do not tip off" banner | mlro-user | **CONFIRMED by code**; impact limited to wording | AMBER -> Medium | `queries.py:557` calls `obligation_note(classify_programs(programs))`; `pf.py:87-117` falls through to "SANCTIONS match. Freeze without delay ..." for any category set not PF/TF, including an empty set (PEP). No wrongful auto-freeze: `review.py` only auto-freezes on `true_positive` for `sanction`-topic alerts (per yesterday's reading; not re-run). Same mechanism as yesterday's CS-2. |
| G3 Iranian PEP labelled `domestic_pep +30` | mlro-user | PLAUSIBLE | Low | `ruleset.yaml:76` has `domestic_pep: 30`; I did not trace the mapping. |
| G4, G5 | mlro-user | accepted, wording | Low | Not re-run. |
| CS-9, CS-10, CS-11 #416 blog copy | compliance | PLAUSIBLE (agree) | L/M | Legal accuracy needs primary text; none in repo. Not on master. |
| CS-12 #406/#401 not gaps | compliance | agree REFUTED | n/a | Read-only agreement. |
| R1-R5 refutations (API auth matrix, tenant leak in paging, #417 header) | red-team | accepted, not re-run | n/a | Their matrix is plausible and consistent with QA's sweeps; I did not repeat it. |
| QA-1, QA-3 | qa-regression | agree | n/a | QA and code-reviewer independently report `1973 passed, 3 skipped` on `448a19b`; I did not repeat the 12-minute suite. |

Carried 2026-10-04 findings (red-team P1: F1-F14; mlro F2-F4; compliance CS-1..CS-5): the three cited files for my yesterday-confirmed items are unchanged, and I re-ran `presentation_forms.py` and `csrf_scan.py` on `448a19b`: both exit 0 (the Arabic presentation-form name still canonicalises to `''`; `/admin/org-profile` and `/logout` still lack a CSRF check). My yesterday verdicts and downgrades stand.

## What the team missed
1. The overflow class is wider than N1: `/audit?page=` and the feedback list overflow the same way (`offset_overflow.py`).
2. The category-burying defect predates #402 on the web queue for any list over 200; both roles framed it as a mobile-only effect.
3. CS-6 and CS-7 cannot both be the live production path; the report should say which one applies, and nobody can check from here.
4. PR #418's §3.3 is self-contradictory, so a "violates the policy" claim against `requirements.txt` needs care.
5. No role re-tested yesterday's missed items: pending_review alerts still re-alert on rescreen (`engine.py:343-348`), and the org-profile save still blanks the goAML entity reference. Both are unchanged on master.

## BLOCKED / not checked
- FATF primary source: BLOCKED for me too (not attempted; compliance reports a Cloudflare challenge). Needs someone to fetch the FATF black/grey list page from an unblocked network.
- Not re-run: the full test suite, PR #412 tenant sweeps, red-team's API authz matrix, the MLRO driver, #417's visual/keyboard behaviour in a browser, #416's legal claims, goAML XSD (no FIU schema).
- No legal text in the repo, so statute-based claims stay PLAUSIBLE at best.
- Open CI note, not code: `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-05/skeptic.md` and `repro_skeptic/{four_eyes_rename,presentation_forms,csrf_scan,queue_paging_category,offset_overflow}.py` on `routine/2026-10-05-skeptic`, based on master `448a19b`. No existing file edited. The commit SHA is in the final reply (a file cannot contain its own SHA).
