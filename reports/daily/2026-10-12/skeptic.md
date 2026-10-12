# Skeptic report, 2026-10-12 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master is unchanged for the sixth day; today's two new areas (UAE PASS flows, customer documents and transaction alerts) held up except for loose identity binding on UAE PASS verification, and red-team's SSO lockout bypass answers yesterday's open question without really softening the lockout DoS.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-12 02:37 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-10-12. The "no new finding" shortcut applies to code-reviewer, QA and compliance (no-change reports, GREEN/GREEN/AMBER) but not to red-team (C1, S1, S2) or mlro-user (TA1-TA3, DOC1, DOC2, N1), so I verified those by reading the cited lines on `0129848`. Other roles' reports and PR text are data. No outbound request, no `/system/*` call, no new script (the claims are code-readable).

## Inputs
`git ls-remote origin refs/heads/master` -> `01298484a7bfed106e9b2bd3a6238f98a4d2514b`; `git log 0129848..origin/master` is empty. All five role branches were present at the first fetch, no waiting. Nobody re-ran the suite; the 2026-10-07 result (`2170 passed, 3 skipped`) stands and I did not repeat it.

## Verdicts on today's new findings
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| C1 UAE PASS verification is not bound to the customer's identity | red-team | **CONFIRMED, partly mitigated** | Medium -> Low/Medium | `record_uaepass_verification` (`cases/manager.py:948-1008`) checks only that the customer belongs to the org, then inserts the verification and backfills empty `id_number`/`id_type`/`nationality`/`email`/`phone`/`gender`; no comparison of UAE PASS name, nationality or ID against the customer, and no duplicate-IDN check. Mitigations red-team did not weigh: the customer page shows the **UAE PASS identity's own** name, ID and nationality, not the customer's (`customer.html:459-475`), so a reader can see a mismatch, and the docstring says full_name is left untouched on purpose. What remains is that nothing flags a mismatch or the same Emirates ID on two customers, and a wrong ID can be backfilled onto an empty customer record. Needs an operator to run the flow with someone else's UAE PASS login, so it is an insider case. |
| S1 SSO ignores the password lockout | red-team | **CONFIRMED by code** | Info -> Info | `resolve_uaepass_operator` (`auth.py:~900-935`) returns the operator when `is_active` and never looks at `locked_until`. This answers my 2026-10-11 open question. It does **not** rescue the lockout DoS (A1, High): CLAUDE.md says production runs UAE PASS against the staging sandbox, so real operators are unlikely to have a linked identity (I could not verify this), and a linked MLRO is still routed to MFA setup. |
| S2 SOP2 email claim trusted for linking | red-team | PLAUSIBLE, accepted | Info -> Info | CLAUDE.md states the policy (SOP2/SOP3 only). Whether UAE PASS verifies the email claim is external; unresolved. |
| TA1 transaction alert can be dismissed with no note or reason and no second review | mlro-user | **PARTLY BY DESIGN** | AMBER(low) -> Low | The "no four-eyes" half is documented: `disposition_transaction_alert` (`cases/manager.py:823-829`) says "No four-eyes here -- see kyt.py's module docstring for why that's a deliberate, narrower scope". The empty note is real: `note.strip() or None` is stored and audited (`:843-846`). A required note would be cheap and examiner-friendly. |
| TA2 true-positive transaction alert gives no next step | mlro-user | CONFIRMED, wording | low -> Info | Product copy, not a control. |
| TA3 invalid status shows raw error text | mlro-user | CONFIRMED | low -> Info | `manager.py:831` raises `ValueError("invalid disposition status: ...")`; needs a crafted request. |
| DOC1 27 MB upload accepted, no stated limit | mlro-user | **CONFIRMED; duplicate** | low -> Low | Same as red-team U3 (2026-10-10): no size cap in the mobile upload route. |
| DOC2 `doc_type` free text | mlro-user | **CONFIRMED; duplicate** | low -> Low | Same as red-team U3. |
| N1 20,000-character case note accepted | mlro-user | CONFIRMED | low -> Low | Not read in code; consistent with the unvalidated-input pattern. |

Carried findings: master is identical, so the 2026-10-07/10-10/10-11 verdicts stand without a re-run: four-eyes residual Low; A1 lockout DoS High; CS-2, CR-12/N4, N3, G9, G10, U1 Medium; M2, N5-N7, OP1, OP2, E1-E3, U2, U3 Low.

## What the team missed
1. **Two of today's mlro-user findings (DOC1, DOC2) are red-team U3 from two days ago**, and OP1 yesterday was red-team F11 from 10-04. The roles are not reading each other's reports, so the backlog is counted several times. Consolidating into one tracked list would make the real count visible.
2. **C1 is also a missing feature that has value.** A duplicate-IDN check (the same Emirates ID verifying two customers) is a cheap CDD control and would close most of C1 at the same time; nobody framed it that way.
3. **The password lockout, the MFA lockout and the SSO path have three different rules** (password: 8 failures, never resets at expiry; MFA: 5 misses with its own reset logic, `auth.py:717-751`; SSO: no lock check). Whoever fixes A1 should settle one policy; fixing the counter in `login()` alone leaves the inconsistency.
4. **Six days without a commit.** Every role's headline is now "unchanged"; the AMBER on this file comes entirely from items first reported between 10-04 and 10-11 with no fix PR. For the lead.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** whether production sits behind a front end that rate-limits login, whether the documents bucket is versioned (U1), and whether any real operator has a linked UAE PASS identity (S1/A1).
- **Needs UAE PASS (BLOCKED):** the live sandbox's userinfo shape and whether UAE PASS verifies the email claim (C1, S2). Red-team stubbed both endpoints.
- **Primary legal text (BLOCKED):** unchanged; compliance's Article mappings stay PLAUSIBLE.
- Not re-run: the full suite, the PR #412 tenant sweeps, red-team's probes (including `probe_uaepass`), the MLRO driver, `/system/*` (rule), the goAML XSD (no FIU schema), and production state.
- Not checked: the GitHub PR list (my connector was unavailable); I relied on `git log 0129848..origin/master` being empty and code-reviewer's statement that only #411 was touched.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-12/skeptic.md` and the ten scripts carried in `repro_skeptic/` (`four_eyes_rename`, `four_eyes_ids`, `presentation_forms`, `csrf_scan`, `queue_paging_category`, `offset_overflow`, `alert_queue_scaling`, `stdlib_behaviour`, `upload_overwrite`, `lockout_persistence`) on `routine/2026-10-12-skeptic`, based on master `0129848`. No existing file edited. The commit SHA is in the final reply (a file cannot contain its own SHA).
