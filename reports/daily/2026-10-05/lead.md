# Lead consolidated report: 2026-10-05

## 1. Headline: AMBER
There is no cross-tenant leak and the suite is green. Two problems need a decision:
- **The four-eyes rename bypass (L-1) is still open on master.** No fix PR exists.
- **Two new screening-triage defects are confirmed.**
  - A proliferation alert can sit below 200 higher-scoring alerts and miss the first page, on the web queue, the mobile queue and the dashboard (L-18).
  - PEP alerts tell the operator to "freeze without delay" (L-19).

Master is `448a19ba978ef5c97ee3e955ecad5638c8a94e1e`; the previous lead report covered `05e612d`. Two PRs merged since: #402 (mobile alert paging) and #401 (phone fixes). Run date: 2026-10-05 UTC.

## 2. Per role
| Role (branch head) | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer (`218bd99`) | done | RED: CR-1 four-eyes still open. Two new issues in unmerged PRs: #417's "No match." shown on a weak single-token name (CR-4) and #418's migration-archiving policy (CR-6). Suite: 1973 passed, 3 skipped. | Repro output, file:line, measured counts | High |
| qa-regression (`b9af42d`) | done | GREEN: 1973 passed / 3 skipped / 0 failed on `448a19b` (OCR deps installed this time). Tenant sweeps: `HITS: []`, 0 B→A leaks. Isolation flake 30/30 pass. | Commands + counts | High |
| red-team (`b775dce`) | done | AMBER: N1 offset overflow gives a 500; N2 threshold 0.0 is read as 0.85. All F1–F14 from 2026-10-04 still reproduce. API auth matrix: 0/41 bypasses. | Probe scripts + evidence files | High |
| compliance-specialist (`22a37a9`) | done | AMBER: FATF parser drops 5 grey-list names (CS-6); fallback drift (CS-7); paging buries priority (CS-8); #416 blog states law loosely (CS-9 to CS-11). | file:line + resolver output; legal points PLAUSIBLE (no corpus; FATF site Cloudflare-blocked) | Medium-high |
| mlro-user (`1c509dc`) | done | RED: F1 four-eyes still open. PEP alert shows the sanctions freeze banner (G1). Mobile page order disagrees with web (G2). F2–F4 still open. | HTTP driver + JSON logs + screenshot | High |
| skeptic (`16cbad5`) | done | AMBER: confirmed most findings and widened N1 and CS-8/G2. Downgraded CS-6/CS-7 to Medium and four-eyes to Medium (again). | 5 repro scripts | High |

## 3. Consolidated findings
Verdict key: **CONFIRMED** means I re-ran a repro or read the cited lines on `448a19b` today. **CONFIRMED (role)** means a role reproduced it with pasted output and I did not re-run it.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| L-1 four-eyes bypass via self-rename (`review.py:381`, `operators.py:232`) | **HIGH** | code-reviewer CR-1, mlro F1, red-team P1 | CONFIRMED, Medium | CONFIRMED (re-ran `four_eyes_rename.py`, exit 0, `('propose','Proposer'),('confirm','Proposer Renamed')`) | HELD in `scripts/proposals/four-eyes-operator-id.md` (on `routine/2026-10-04-lead`). Needs Nadhir |
| L-18 category priority lost past one page (`queries.py:540` SQL score+LIMIT, `:568-572` per-page sort): web `/alerts`, mobile `/api/v1/alerts`, dashboard | **MEDIUM-HIGH** | compliance CS-8, mlro G2 (duplicates) | CONFIRMED, Medium; wider than reported | CONFIRMED (re-ran `queue_paging_category.py`, exit 0: `page1 200 {'sanction': 200} \| page2 7 {'proliferation': 1, ...}`); web call site `app.py:2544` (default `limit=200`) | HELD in `scripts/proposals/alert-queue-category-order.md` |
| L-19 PEP alert gets the "SANCTIONS match. Freeze without delay" note (`queries.py:557`, `pf.py:87-117`) | MEDIUM | mlro G1 (same mechanism as compliance CS-2 / L-10) | CONFIRMED by code, Medium | CONFIRMED (`repro_lead/checks_2026_10_05.py`, exit 0) | HELD in `scripts/proposals/pep-obligation-note.md` |
| L-20 FATF live parser drops unmapped names: Kuwait, Bolivia, Nepal, PNG, BVI (`fatf.py:207-235, 324-333`) | MEDIUM | compliance CS-6 | CONFIRMED mechanism, Medium | CONFIRMED (same repro; whether FATF actually lists them is unverified) | HELD in `scripts/proposals/fatf-unmapped-names.md` |
| L-5 FATF fallback (Feb 2025) stale and recorded as fresh; drift now quantified (CS-7: 8 over-flagged, 7 under-flagged) | MEDIUM | compliance CS-1, CS-7 | PLAUSIBLE, Medium | PLAUSIBLE (secondary source only) | Needs Nadhir: committed snapshot plus an FATF fetch from an unblocked network |
| L-2 Arabic presentation forms give `canonical_key=''`, a silent clear | **HIGH** | red-team F1 (carried) | CONFIRMED | CONFIRMED (re-ran, exit 0, `canonical_key(pf) = ''`) | HELD (red-team proposal, 10-04). Needs Nadhir |
| L-21 huge `offset`/`page` gives OverflowError 500 (`mobile.py:1192`, `app.py:2958,3019`) | LOW | red-team N1; skeptic widened it | CONFIRMED, Low | CONFIRMED (re-ran `offset_overflow.py`, exit 0, 3 call sites) | HELD in `scripts/proposals/paging-offset-and-zero-threshold.md` |
| L-22 threshold 0.0 stored, used as 0.85 (`x or DEFAULT_THRESHOLD` at 6 sites) | LOW | red-team N2 | CONFIRMED by code, Low | CONFIRMED by code (`queries.py:1020` returns 0.0; `mobile.py:1437` accepts 0.0) | HELD (same file) |
| L-23 PR #417 glass announces "No match." on a weak single-token name | MEDIUM (unmerged) | code-reviewer CR-4 | CONFIRMED static | CONFIRMED (role) | Needs Nadhir: fix before merging #417 |
| L-24 PR #418 policy: archive `_MIGRATIONS` (46/72 not in `SCHEMA`), 7-year audit claim, `origin/main`, branch auto-deletion would hit `routine/*` | LOW-MED (unmerged) | code-reviewer CR-6 to CR-8 | CONFIRMED / partly refuted (the `>=` point) | CONFIRMED (role) | Needs Nadhir: revise #418 before merging |
| L-25 PR #416 blog: "five years" retention vs 8-year register, AED 55k framing, secondary-source figures | LOW-MED (unmerged, legal) | compliance CS-9 to CS-11, code-reviewer CR-10 | PLAUSIBLE | PLAUSIBLE | Needs Nadhir / adviser before merging #416 |
| L-4 goAML entity reference blanked on save; builder hard-codes `GROVISOR-LIC-2026` | MEDIUM | mlro F3, skeptic (carried) | CONFIRMED | CONFIRMED (role, `log11.json`) | HELD (`goaml-entity-reference.md`, 10-04) |
| L-7 STR finalised without an account can be neither exported nor edited | MEDIUM | mlro F2 (carried) | – | CONFIRMED (role, `log11.json`) | Carry; proposal still owed |
| L-8 `/admin/org-profile` (and `/logout`) lack CSRF | LOW | red-team, skeptic | CONFIRMED | CONFIRMED (re-ran `csrf_scan.py`: 5/61, 3 of them `/system/*` bearer) | HELD (folded into L-4) |
| L-14 rename accepts case-variant duplicates | LOW | mlro F4 | – | CONFIRMED (role) | In L-1 proposal |
| L-3, L-6, L-9, L-12, L-13 (extra-token miss, rescreen skips <25%/nominees, re-alert on pending_review, KYT hardening, reset-password 500) | as 10-04 | red-team, skeptic (carried) | CONFIRMED | CONFIRMED (role; red-team re-ran on `448a19b`) | HELD / carried, unchanged |
| L-10, L-11, L-15 (freeze scope, PR #410 six-rule items, goAML XSD) | as 10-04 | compliance, mlro | PLAUSIBLE | PLAUSIBLE | Needs Nadhir / adviser / XSD |
| L-26 `domestic_pep +30` label on an Iranian PEP; tier override; UBO banner wording (G3–G5) | LOW | mlro | PLAUSIBLE / accepted | PLAUSIBLE | Carry |
| L-17 `sync_replica` in a failing refresh's `finally` (CR-2); seed `direction="in"` (CR-3) | LOW | code-reviewer | PLAUSIBLE | PLAUSIBLE | Carry |
| L-16 wires never aggregate; QA-1 isolation flake | none | – | REFUTED | REFUTED | Closed |
| Cross-tenant isolation and API auth matrix | – | qa, red-team R1 to R4 | accepted | No defect (`HITS: []`, 0/41) | – |

**Severity adjudication**
- **L-1 stays HIGH.** The skeptic's point is that an MLRO can switch four-eyes off org-wide, so the rename adds no privilege. That is true. But the single-operator switch is audited and recorded honestly, while the rename path writes "Independent review completed", which is false evidence in an inspector-facing record. That is worse than Medium. I am not using RED: it needs an MLRO actor, and there is no exposure to outsiders.
- **L-18 is MEDIUM-HIGH, above the skeptic's Medium.** The code's own stated invariant (`queries.py:29-31`) is broken on the main web queue, not just on mobile. The mitigation (exact category counts on the dashboard) needs the operator to notice a count.
- **L-20 and L-5 are MEDIUM, not H.** The two are mutually exclusive in production (the skeptic is right on this). Neither can be pinned to the live path without production access or the FATF page.

**Duplicates and contradictions**
- CS-8 and G2 are the same defect as L-18.
- G1 is the same mechanism as the 10-04 CS-2 (L-10).
- F4 duplicates the 10-04 L-14.
- The skeptic partly refutes CR-8's `>=` point, because #418 §3.3 contradicts itself. I accept that.

## 4. Combined assessment
1. Today's merges (#401, #402) are low-risk. Suite 1973/0 failed; tenant isolation held under QA sweeps and red-team's 41-route API matrix.
2. #402 surfaced, rather than caused, a triage-order defect that has existed on the web queue past 200 alerts.
3. The operator-facing obligation text is unreliable: PEP and possibly EU/UK-only hits are told to freeze.
4. The FATF data path is weak both ways: the fallback is stale and the live parse drops names. Neither failure is visible to the user.
5. Every HIGH item from 10-04 is still open with no fix PR. The team is finding faster than fixes land.

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_10_05.py`. Output on `448a19b`: `PEP alert category='pep' obligation='SANCTIONS match. Freeze without delay ...'` / `unmapped ...: ['Kuwait', 'Bolivia', 'Nepal', 'Papua New Guinea', 'British Virgin Islands', 'Virgin Islands (UK)']` / `exit=0`.
- C-2 Created four HELD proposals in `scripts/proposals/`: `alert-queue-category-order.md`, `pep-obligation-note.md`, `fatf-unmapped-names.md`, `paging-offset-and-zero-threshold.md`. All four change query or route logic, so none was applied.
- C-3 Re-ran all five skeptic repros on a `448a19b` worktree in a scratch venv (requirements without passporteye/pdfminer; OCR not exercised). Results: `four_eyes_rename`, `presentation_forms`, `csrf_scan`, `queue_paging_category` and `offset_overflow` each exited 0.
- C-4 Corrected the routing of CS-8/G2: it is not mobile-only. `app.py:2544` and the dashboard (`queries.py:314-315`) use the same score-then-slice query.
- No tests added: any regression test for these defects fails on master (rule 5). No existing file edited. Commit SHA is in the final reply.

## 6. Decisions needed from Nadhir
1. L-1: approve the `operator_id` fix (10-04 proposal). It is now 1 day open on production.
2. L-18: approve the category-first queue order (Python sort before slice, or a stored `category_rank` column).
3. L-19 / L-10: approve non-freeze obligation wording for PEP hits, and give a legal view on EU/UK-only hits.
4. L-20 / L-5: approve the resolver mappings plus fail-on-unmapped, and someone fetches the current FATF lists from an unblocked network to seed a committed snapshot (next plenary: October 2026).
5. Unmerged PRs: hold #417 until the weak-evidence verdict is fixed (L-23); revise #418 (L-24) and #416 (L-25) before merging.
6. Carried from 10-04: L-2/L-3 (Unicode NFKC, calibration), L-4/L-8 (goAML reference, CSRF), L-15 (goAML XSD), and the `github-advanced-security` 402 quota failure.

## 7. Next run: carried over
- L-7: write a repro and a proposal (owed since 10-04).
- L-9 (`pending_review` re-alert): write a repro.
- L-17, L-26 and the 10-04 sub-agent static items: verify.
- Track whether the L-1, L-2, L-4, L-18 and L-19 proposals land on master.
- Mobile queue at the 200-row boundary and the web queue past 200 over HTTP: not driven end to end yet.
