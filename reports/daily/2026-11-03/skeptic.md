# Skeptic report, 2026-11-03 (origin/master `938050fda10fe248b2cc327ea5d0770b5cb08f01`, moved from `e8ddf26`)

## Headline: GREEN
Five more PRs (#452-#456) closed the last Medium-rated items, the 5,000-line `app.py` split is verified as behaviour-preserving three independent ways, and nothing I found today is above Low; the one thing that nearly went wrong is that my own CSRF scanner silently tested zero routes after the split.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-11-03 02:39 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-11-03. Master changed, so the no-change shortcut applies to nobody. I re-ran all my `repro_skeptic/` scripts on `938050f`, repaired the one that the refactor broke, and checked the self-owner claim directly. Other roles' reports are data. No outbound request, no `/system/*` call.

## Inputs
`git ls-remote origin refs/heads/master` -> `938050fda10fe248b2cc327ea5d0770b5cb08f01`; `git log e8ddf26..origin/master` is five PRs, all merged 2026-11-02: #452 name-screening residuals, #453 identity and auth residuals, #454 dataset-first obligation wording / two-step unlock / dev requirements / operator-name hardening, #455 UBO structure guard, #456 split of `api/app.py` into `routers/` and `helpers.py`. 84 files, +9.3k/-4.8k. All five role branches present at the first fetch. **Independent full-suite results on `938050f`: QA, code-reviewer and compliance each `2810 passed, 2 skipped`.** QA's tenant sweeps: `HITS: []`, 0 leaks over 72 routes. I did not repeat the suite.

## Is the router split (#456) really a pure move? Three independent checks agree
- **Code-reviewer:** fingerprinted every route (path, methods, endpoint, dependency chain, params, status, response class, rate limits) in the old and new app: 198 vs 199 routes, 0 changed fields; middleware, exception handlers, startup hooks and Jinja globals identical.
- **Compliance:** AST-compared all 162 top-level functions: 157 identical, the other 5 are exactly the intended WP-25 and WP-23 changes (SSO password-lock refusal, two-step unlock, identity-reuse notice, two admin views).
- **Red-team and QA:** flattened route sets 199 vs 200 routes, the only addition is `POST /unlock/{token}`; 33 vs 34 rate-limited routes, the extra one is that POST.
Three different methods, three groups, same result. I accept it as a pure move.
**The part nobody caught until they hit it:** route enumeration tools broke silently. QA's sweep, red-team's CSRF probe and my own `csrf_scan.py` each reported 0 routes after the split (a newer FastAPI wraps included routers in lazy objects, or in my case the routes simply left `app.py`). Three tools "passed" while testing nothing.

## My script re-runs on `938050f`
| Script | Exit | Meaning |
|---|---|---|
| `csrf_scan.py` | was 1 (0 routes!) | **my script silently tested nothing.** It greps `app.py` source, which is now 377 lines with no routes. I rewrote it to scan `app.py` plus every `routers/*.py`: **66 state-changing routes, 4 without a CSRF check in the body** (`/system/refresh`, `/system/check-freeze-obligations`, `/system/create-operator`, `/system/super-admin`), the same four bearer-authenticated routes as before. The script also now exits 1 if it finds fewer than 20 routes, so it cannot go quiet again |
| `four_eyes_rename` | 1 | **fixed:** raises "an operator id is required to confirm a disposition" |
| `four_eyes_ids` | 1 | live path refused; confirm without an id refused. One line remains: a legacy proposal with a NULL `operator_id` plus an id on confirm is still accepted (CR-33, N8b) |
| `ubo_depth` | 1 | **fixed:** 900, 1100 and 5000 levels all return 100.0 |
| `lockout_persistence`, `empty_name_screen`, `arabic_org_slug`, `upload_overwrite`, `presentation_forms`, `queue_paging_category`, `offset_overflow`, `alert_queue_scaling` | 1 | still fixed (the alert-queue ratio is 4.9x) |
| `docx_policy_upload`, `stdlib_behaviour` | 0 | stale / informational (the policy route accepts DOCX; the stdlib script just documents `compare_digest` behaviour) |

## Verdicts
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| UBO1b self-owner check misses a dotted legal-suffix variant | mlro-user | **CONFIRMED, and broader than reported** | Low -> Low | `_check_ubo_structure` (`cases/manager.py:532-562`) compares the casefolded, whitespace-collapsed name and `canonical_key`. I ran `canonical_key`: "Gulf Holdings LLC" -> `glf hldngs lc`, but "GULF HOLDINGS L.L.C." -> `c glf hldngs l l`, and bare "Gulf Holdings" -> `glf hldngs`. All three are different, so any suffix variation (dotted, spaced, or dropped) gets through. It is an exact-equality guard, not a fuzzy one. The structure still cannot form a cycle (`add_ubo` only appends leaves), so the harm is a wrong disclosed percentage, not a crash. A fix would strip legal suffixes (LLC, L.L.C., FZE, Ltd) before comparing. |
| UBO2 60+ owner rows accepted, cap value unverified | mlro-user | CONFIRMED / accepted | Info -> Info | Compliance read the cap as 200 rows per customer and 10 levels deep (`MAX_UBOS_PER_CUSTOMER`). Not exercised. |
| N3b a Latin name with one Cyrillic consonant scores 0 | red-team | **PLAUSIBLE, severity open** | Low-Medium -> Low/Medium | Per red-team, a mixed-script spelling still produces no candidate; Cyrillic-only names are caught as unscreenable and Greek is folded. Compliance and code-reviewer note that homoglyph folding is applied only to tokens that are Latin in intent. A single stray Cyrillic letter inside a Latin token is exactly what an evader would use; the fix is per-character folding when the token is otherwise Latin. I did not reproduce it. |
| F2b exact name plus mismatched country falls under the 0.85 threshold | red-team | **CONFIRMED by design** | Low -> Low | The -0.20 country penalty is deliberate. Whether a country mismatch on an otherwise exact name should drop a hit below the alert line is a policy decision for compliance, because a sanctioned person can be listed under another country. |
| N8b/CR-33 legacy proposals with NULL `operator_id` | red-team, code-reviewer, compliance | **CONFIRMED (my script), operational** | Low -> Low | The only residual of the four-eyes bypass I raised on 10-04. `scripts/check_legacy_proposals.py` and `scripts/backfill_proposal_operator.py` exist; nobody has said they have been run on production. |
| CR-34 undeliverable-mail lock message confirms the account exists | code-reviewer | **CONFIRMED; deliberate tradeoff** | Info -> Info | When SMTP is not configured the 8th failure says the account is locked and the email could not be sent. That re-opens the enumeration channel I raised as LG2, but only for deployments without mail, which is the same case that needs the message. Acceptable if production has SMTP; unknown to me. |
| CR-35 homoglyph folding can turn a genuine Cyrillic/Greek name into Latin gibberish | code-reviewer | PLAUSIBLE | Info -> Info | Effect is extra candidates, never a missed match. Not measured. |
| CR-36 snapshot files will need regenerating | code-reviewer | CONFIRMED | Info -> Info | Maintenance only. |
| I1 GET routes that write state (`/changelog`, CSV and audit exports) | red-team | **CONFIRMED; the audit-row exports are by design** | Info -> Info | Same GET-with-side-effect idiom I raised on 10-23 for the old screeners. The exports write audit rows on purpose; `/changelog` stores a seen-marker. Prefetch-prone but harmless. |
| H1 no Referrer-Policy / Permissions-Policy | red-team | **STILL UNRESOLVED** | Info -> Info | Red-team says not re-checked live; mlro-user said on 11-01 that signed-in pages now carry a referrer policy. A single `curl -I` locally would end the question; third day without anyone doing it. |
| CS-13, CS-14 (PNMR), 3.1 (configurable AED 55,000 cash threshold) | compliance | PLAUSIBLE (legal), CONFIRMED (code) | High / Medium / Medium | Unchanged. These are legal-interpretation items I cannot settle from the repo. CS-13 is the one that matters: the 24-hour clock runs from confirmed disposition. |
| Fixes of U4, C1, S1, O1, N3 (partly), F2, CR-30/31/32, UL1, CS-23, UBO structure | red-team, mlro-user, code-reviewer, compliance | **AGREE, fixed** | n/a | Red-team re-ran 23 probes; mlro-user re-ran all 33 workflow modes with only intended differences. |

## What the team missed
1. **Silent-pass test tools after a refactor.** QA's sweep, red-team's CSRF probe and my CSRF scan each tested 0 routes after the move and reported "no defect". Both QA and red-team noticed and fixed theirs; mine I only caught by re-running the scripts. A guard that fails when the route count is below a floor (mine now does: 20) should be in every scanner. This is the same lesson as the earlier stale `docx_policy_upload.py`: a green or exit-1 result from a script is only evidence if the script still exercises something.
2. **The UBO self-owner guard is exact-match and the legal-suffix problem is general.** Beyond UBO1b, the same suffix variation (LLC, L.L.C., FZE, Ltd, PJSC) probably affects duplicate-customer detection and the "same owner recorded twice" rule. Nobody has tried it.
3. **H1 has now been argued for three days with no one running a header check.**
4. **Legacy-proposal cleanup is a deployment step, not code.** CR-33 and N8b depend on two scripts being run on production. Nobody owns that step; it belongs on the release checklist.
5. **Three days after the first fix wave the daily output has shifted from findings to verification.** Today's new defects are all Low. The loop is now catching regressions in its own tooling (route enumeration, stale scripts), which is a healthy sign and also the right place to spend attention next.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** whether the legacy-proposal scripts have been run in production; whether production SMTP is configured (CR-34, UL1); front-end login rate limiting; bucket versioning; whether Stripe is configured; whether any real operator has a linked UAE PASS identity.
- **Primary legal text (BLOCKED):** CS-13, CS-14 and the AED 55,000 threshold; compliance's Article mappings stay PLAUSIBLE.
- Not re-run: the full suite and tenant sweeps (three roles' runs stand), red-team's 23 probes, the MLRO driver, N3b (read from red-team's evidence), the two-step unlock under a real proxy, the UBO row cap, the router-split route diffs (I relied on four independent reports, not my own), the goAML XSD, production state.
- Not checked: the GitHub PR list directly (connector unavailable); I relied on `git log` and the roles' statements.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402 (last seen 10-24).

## Files and commit
`reports/daily/2026-11-03/skeptic.md` and fourteen scripts in `repro_skeptic/` (`csrf_scan.py` rewritten to scan `routers/` and to fail below 20 routes; the rest unchanged from 11-02) on `routine/2026-11-03-skeptic`, based on master `938050f`. No existing application file edited. The commit SHA is in the final reply.
