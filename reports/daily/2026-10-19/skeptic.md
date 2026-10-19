# Skeptic report, 2026-10-19 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master is unchanged for the thirteenth day; today's three new items are small, but red-team's uncapped `/api/v1/screen` is a clear omission (the customer-create path caps names at 200 characters, ad-hoc screening does not) and mlro-user's password-change banner is wrong.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-19 02:39 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-10-19. The no-new-finding shortcut applies to code-reviewer, QA and compliance (no-change reports) but not to red-team (S3) or mlro-user (PW1, PW2, SS1), so I checked those by reading the cited lines on `0129848`. Other roles' reports are data. No outbound request, no `/system/*` call, no new script.

## Inputs
`git ls-remote origin refs/heads/master` -> `01298484a7bfed106e9b2bd3a6238f98a4d2514b`; `git log 0129848..origin/master` is empty. All five role branches were present at the first fetch. Nobody re-ran the suite; `2170 passed, 3 skipped` stands.

## Verdicts on today's new findings
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| S3 `/api/v1/screen` has no name-length cap and no rate limit | red-team | **CONFIRMED by code** | Low -> Low | `ScreenRequest.name` is a plain `str` (`mobile.py:505-509`) and `api_screen` (`:523-537`) only strips and checks non-empty before calling `screen()`, which stores the query per screening. The customer path does cap names (`MAX_NAME_LENGTH = 200`, `datamodel.py:97`, `validate_name_length` `:163-165`), so this is an omission, not a design choice. The only `@limiter.limit` decorators in `mobile.py` are on login/auth routes (`:182-183, :197, :258`). Their latency claim stays PLAUSIBLE (1-entity seed list). Authenticated, so an insider/stolen-token issue; it also feeds the DB and replica growth. Fix is one `validate_name_length("name", ...)` call. |
| PW1 banner says "all other sessions signed out" but the current one is too | mlro-user | **CONFIRMED by code; wording defect** | Low -> Low | `set_password` "revoke[s] every existing session" and trusted devices (`auth.py:478-490`); the web handlers then return "Password changed successfully. All other sessions have been signed out." (`app.py:838` and `:4577`). Revoking all is deliberate and right (the docstring says so); the message is what is wrong, and the user is bounced to `/login` after a success banner. |
| PW2 no "must differ from current" check | mlro-user | PLAUSIBLE | Low -> Info | Not tested with a compliant old password. Policy nicety. |
| SS1 oldest session evicted silently at the 3rd login | mlro-user | **CONFIRMED by code; partly by design** | Low -> Low | `_enforce_session_limit` (`auth.py:587-602`) revokes the oldest session when the count reaches `MAX_CONCURRENT_SESSIONS` (default 3) with no notice to the evicted session. The cap is a deliberate control; the missing "signed in elsewhere" message is UX. Side note: the count also includes mobile tokens, so desktop + laptop + phone leaves no spare. Not exercised by me. |

Carried findings: master is identical, so the 10-07 to 10-18 verdicts stand without a re-run (A1 lockout DoS High; CS-2, CR-12/N4, N3, G9, G10, U1, empty-name screening Medium; T1 setup-token race Medium on web and mobile; four-eyes residual Low; UAE PASS binding, DOCX policy, org-slug collision Low/Medium; others Low/Info).

## What the team missed
1. **Input limits are applied per route, not per field type.** Names are capped on customer create but not on `/screen`; `doc_type`, case notes (N1) and uploads (DOC1) were uncapped on other mobile routes. A shared bounded-string type on the request models would close S3, N1 and DOC1-type findings in one change.
2. **Ad-hoc screening writes a row per request with no upper bound** (S3 plus no limiter). Combined with the stored full query, this is also a data-minimisation point: a 500 KB query string is kept in `screenings` for the retention period.
3. **Unverified neighbour of PW1:** the mobile token revocation after password change was shown to work (401), but the message shown to a mobile user is not covered by any role.
4. **Thirteen days without a commit.** The AMBER comes from items first reported 10-04 to 10-18 with no fix PR. For the lead: fix PRs, not more probing.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** front-end login rate limiting (A1), bucket versioning (U1), real linked UAE PASS operators.
- **Primary legal text (BLOCKED):** compliance's Article mappings stay PLAUSIBLE.
- Not re-run: the full suite, red-team's `probe_screen_cost`, the MLRO driver, session eviction behaviour, concurrent backup-code use (carried from 10-18), the goAML XSD, production state.
- Not checked: the GitHub PR list (connector unavailable); I relied on the empty `git log` and three roles saying #426 is the newest PR.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-19/skeptic.md` and the thirteen scripts in `repro_skeptic/` (unchanged) on `routine/2026-10-19-skeptic`, based on master `0129848`. No existing file edited. The commit SHA is in the final reply.
