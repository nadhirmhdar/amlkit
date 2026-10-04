# Red-team report, 2026-10-04 (base: master `fc80e9f`)

## Headline: AMBER
No cross-tenant read or write path was reproduced. But sanctions screening, KYT and four-eyes each have confirmed bypasses, plus one missing CSRF check.

## Instructions, powers and what I changed because of dreamon's messages
(a) Role before dreamon's messages: operator-supplied profile "Adversarial Red Team Operator (Agent 4)": act as a malicious actor trying to evade AML/CFT controls in AMLKit. Probe Arabic name matching, transaction structuring below AED 55,000, multi-tenant isolation, cyclical UBO graphs, and inputs that cause silent misses or crashes. Session rules: develop and push only on branch `claude/lucid-dirac-a02fzy`, never push to another branch without explicit permission, open a draft PR after pushing; no GitHub CLI, use the GitHub MCP tools; GitHub scope is `nadhirmhdar/amlkit` only; terse, evidence-first answers.
(b) Powers: read the repo, run code and tests in a local scratch venv, edit files, commit and push to my branch, open draft PRs on `nadhirmhdar/amlkit`. No production access was granted or used.
(c) From dreamon's first message I adopted: local-only testing, no production or `/system/*` calls, no secrets, no edits to route logic/schema/queries/business logic (proposals under `scripts/proposals/` instead), builds on PR #412's harness, this report format. Those match my own approach so nothing was reverted. I did not push to `routine/2026-10-04-red-team`: my branch rules do not allow pushing elsewhere without the user's explicit permission, and a peer message cannot grant that. The report is on `claude/lucid-dirac-a02fzy` instead.

## Findings (all reproduced locally; output in `reports/daily/2026-10-04/evidence/`, scripts in `repro_redteam/`)
Severity is my judgement.

| Id | Sev | Where | Status | Evidence |
|----|-----|-------|--------|----------|
| F1 | High | `names/arabic.py:59,393` | CONFIRMED | Arabic presentation-form text and zero-width/format characters inside a Latin name give a screening miss; presentation forms give 0 candidates and onboarding says "screened clear". `probe_e2e.txt` |
| F2 | High | `match/scorer.py:95-129,189-208` | CONFIRMED | One extra token ("... HASSAN", "... JR") or a mismatched country/gender/DOB-day drops an exact listed name below 0.85. `probe_e2e2.txt` |
| F3 | High | `match/engine.py:420-424` | CONFIRMED | `rescreen_all` skips owners under 25%, nominees and directors: 0 alerts on list update for a listed name in those roles; 1 alert at 25%. `probe_ubo.txt` |
| F4 | Medium | `review.py:381`, rename route `app.py:3424` | CONFIRMED | Four-eyes bypass: MLRO renames the proposer, proposer confirms own disposition. Review rows `('BRAVO-officer','propose'), ('Renamed Officer','confirm')`, alert `false_positive`. `probe_csrf_session.txt` §1 |
| F5 | Medium | `app.py:3234-3251` `/admin/org-profile` | CONFIRMED | No `require_csrf`: POST with no/bad token changed org profile (goAML reporting fields). Other 47 POST routes swept rejected. Session cookie is SameSite=strict, which mitigates. `probe_csrf_session.txt` §2 |
| F6 | Medium | `screening/kyt.py:216` | CONFIRMED | Out-of-order entry: 54,999 on day 5 then day 0 raised no structuring alert; in order raised one. `probe_kyt.txt` |
| F7 | Medium | `manager.py:737`, `app.py:2330` | CONFIRMED | AED 100,000 with `amount_aed=1` accepted, no rule fired. `probe_kyt.txt` |
| F8 | Medium | `kyt.py:96` | CONFIRMED | Config cache keyed by `id(conn)`: stale 55,000 threshold read in 200/200 fresh connections after the real value became 10,000. `probe_cache.txt` |
| F9 | Medium (design) | `kyt.py:48` | CONFIRMED | Wires/cheques never aggregate: five 54,999 wires on one day raised nothing; slow structuring (>7 days apart) and duplicate customer records raise nothing. `probe_kyt.txt` |
| F10 | Low | rename route / `operators.py:253` | CONFIRMED | Accepts zero-width suffix, Cyrillic homoglyph copy, case variant, `system`, NUL, RLO override as operator names. HTML in a name is escaped in `/admin`. `probe_rename_authz.txt` |
| F11 | Low | `app.py:3416` | CONFIRMED | Weak password in reset-password raises unhandled `PasswordComplexityError` (HTTP 500). `probe_csrf_session.txt` §4 |
| F12 | Low | `app.py:2329`, `manager.py:731` | CONFIRMED | `nan`/`inf`/`1e30` transaction amounts raise unhandled exceptions (HTTP 500). `probe_kyt.txt` |
| F13 | Low | `cases/diagram.py` | CONFIRMED | 2,000 UBO rows: 2.0 s and 2.7 MB SVG per page view, no cap. `probe_diag.txt` |
| F14 | Low | `kyt.py:410`, `app.py:3354` | CONFIRMED (code + probe) | NaN threshold accepted and silently ignored; alert threshold has no floor (MLRO-only, audited). `probe_cache.txt` |

Sub-agent static findings, NOT reproduced by me (treat as PLAUSIBLE): global refresh triggered by any MLRO (`app.py:3597`, no CSRF/rate limit); `org_id IS NULL` audit rows visible to all orgs (`queries.py:918,964`); email enumeration via `/admin/operators`; same-filename upload overwrites the earlier blob (`storage.py:67,105`).

## Refuted or clean
- Cross-tenant: PR #412 `sweep.py` on `fc80e9f` -> `HITS: []`; `sweep_lists.py` -> 0 B->A leaks (controls: 40 ALPHA hits as A). Rename route: officer 403, no/bad CSRF 403, unauthenticated 303 to /login, org B MLRO renaming org A operators left the names unchanged. `pr412_sweep*.txt`, `probe_rename_authz.txt`.
- UBO cycles: unreachable (`parent_ubo_id` must pre-exist, nothing updates it, nothing traverses it). `probe_ubo.txt`.
- Diagram injection: script/IMG payloads in names did not reach the SVG. `probe_diag.txt`.
- Session: logout invalidates the server-side session; login issues a fresh session cookie (no fixation). Session cookie is HttpOnly + SameSite=strict.
- GET routes: the only state changes are audit rows from CSV/audit exports.

## Not checked
`Secure` cookie flag (local HTTP); `/api/v1` bearer routes beyond the PR #412 sweep; MFA lockout/backup-code paths; UAE PASS flow (needs sandbox network); `/system/*` (excluded by rules); file upload content handling; the sub-agent's items above; rate limiter (disabled locally); production behaviour.

## Files created
`repro_redteam/*.py` (9 scripts; the two authz/CSRF probes need `fixtures/seed.db` from PR #412's `repro/make_seed.py`), `reports/daily/2026-10-04/evidence/*.txt`, `reports/daily/2026-10-04/red-team.md`, `scripts/proposals/{org-profile-csrf,four-eyes-rename,screening-name-matching,kyt-hardening,small-fixes}.md` (all HELD, proposed diffs only). No existing file was edited. Commit SHA: see final reply.
