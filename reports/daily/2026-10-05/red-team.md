# Red-team report, 2026-10-05 (origin/master `448a19ba978ef5c97ee3e955ecad5638c8a94e1e`)

## Headline: AMBER
No new High finding and still no cross-tenant path; every 2026-10-04 finding still reproduces on the new master, and the new alert-paging code adds one low-severity crash.

## Instructions I ran under
- Role (Nadhir's standing instructions): "Adversarial Red Team Operator (Agent 4)": probe AMLKit as a malicious actor (Arabic name matching, structuring, tenant isolation, UBO cycles, inputs that cause silent misses or crashes). Terse, evidence-first.
- Powers: read the repo, run code locally, commit and push to a branch. Never master. Local test data only: no production access, no `/system/*`, no secrets, additive-only (no application code edited; fixes only as proposals).
- This run: fired by the scheduled routine "groAML daily: red-team" (the stored prompt, which matches my standing role). Scope: code changed since my previous report first, then one area my previous report listed as not checked. Report goes to this file on `routine/2026-10-05-red-team` and to my final reply. Nothing in the routine conflicted with my standing instructions.
- Assumptions: master is `git ls-remote origin refs/heads/master` at run start; probes ran against scratch DBs seeded by PR #412's `repro/make_seed.py`.

## What I did
1. `git ls-remote` -> master `448a19b`; previous report base was `fc80e9f`. Three PRs merged since: #401 (diagram scroll, cookie notice), #402 (mobile alert paging), #406 (sign-in page). `git diff --stat fc80e9f origin/master` touches only `mobile.py`, `queries.py`, static JS/CSS, three templates, tests. No change under `names/`, `match/`, `screening/`, `cases/`, or `api/app.py`.
2. Probed the changed code: `GET /api/v1/alerts` `limit`/`offset`, `dashboard(alerts_sort_by)`, `alert_queue(offset)` (`probe_mobile_authz.py` section 1).
3. Not-checked area from last report: `/api/v1` bearer routes. Ran a no-token / MFA-locked MLRO / officer / MLRO matrix over every non-network route (`probe_mobile_authz.py` section 2) and the threshold endpoint (`probe_mobile_threshold.py`).
4. Re-ran the 2026-10-04 probes on `448a19b` to see what persists.
5. Read open PR #417 (not merged) statically: `background_submit` middleware and `bg-submit.js`.
Evidence: `reports/daily/2026-10-05/evidence/*_on_448a19b.txt`.

## Findings
| Id | Sev | Status | Summary |
|----|-----|--------|---------|
| N1 | Low | CONFIRMED | `GET /api/v1/alerts?offset=99999999999999999999` raises `OverflowError: Python int too large to convert to SQLite INTEGER` (unhandled, HTTP 500). `limit` is clamped to 1..200 and negative `offset` to 0, but there is no upper clamp on `offset` (`mobile.py` `api_alerts`, new in #402). Evidence: `probe_mobile_authz_on_448a19b.txt`. Fix: clamp `offset` (e.g. `min(offset, 2**62)`) or return 400. |
| N2 | Low | PLAUSIBLE | `POST /api/v1/admin/threshold {"threshold": 0.0}` is accepted and stored (`probe_mobile_threshold_on_448a19b.txt`), but readers use `org_alert_threshold(...) or DEFAULT_THRESHOLD` (e.g. `app.py:2286`, `mobile.py:526`), so 0.0 silently becomes 0.85. I did not run the screening end to end. `1.0` and `0.99` are accepted (no floor), same as the web route (F14 last report). NaN/Infinity/-1/1.5 are rejected (400). |
| P1 | n/a | CONFIRMED, still present on `448a19b` | All 2026-10-04 findings F1-F14 are unchanged: no relevant file changed (above), and re-runs match: four-eyes rename bypass (`proposer now confirms own proposal ... false_positive`), `/admin/org-profile` changes state with no/bad CSRF, extra-token and country-mismatch screening misses, 24.99%/nominee/director never rescreened, out-of-order and `amount_aed=1` KYT evasion, `1e30`/`inf` amounts crash. Evidence: `probe_csrf_session_on_448a19b.txt`, `probe_e2e2_on_448a19b.txt`, `probe_ubo_on_448a19b.txt`, `probe_kyt_on_448a19b.txt`. Corroborated independently by PR #414 (MLRO-user, same four-eyes bypass). Held proposals are in `scripts/proposals/` (branch `routine/2026-10-04-red-team`). |
| R1 | n/a | REFUTED | `/api/v1` is reachable without a token: 0 of 41 routes. |
| R2 | n/a | REFUTED | An MFA-locked MLRO bearer token reaches any `/api/v1` route: 0 of 41 (all 403 `mfa_required`). |
| R3 | n/a | REFUTED | Officer reaches MLRO-only API routes: `GET /audit`, `GET /admin`, `POST /admin/threshold`, `POST /admin/operators`, `.../reset-password`, `.../deactivate`, `GET /audit/export` all return 403 for an officer. Matches the web gating. `/admin/refresh` and `/reports/{id}/submit` call `_require_mlro` (read in `mobile.py:1525-1527, 1648-1650`; not run because they touch the network). |
| R4 | n/a | REFUTED | Alert paging leaks across tenants: org B sees 2 alerts, no `ALPHA` marker in the payload, `total` equals the DB count for org B. `status` SQL-injection string returns `total: 0`. |
| R5 | n/a | REFUTED (static, unmerged) | PR #417 `background_submit`: needs the custom `X-Background-Submit` header (not sendable cross-origin without CORS, none configured), redirect targets come from `back()` which rejects non-`/` and `//` paths (`app.py:339`). No finding. Not run. |

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails on every push with a 402 quota error (account-level); needs quota restored or the check made non-required. SendMessage to dreamon was unreachable last run; not retried.
- Not checked: `Secure` cookie flag (local HTTP), MFA lockout/backup-code logic, UAE PASS flow (needs sandbox network), file-upload content handling, rate limiter (disabled locally), `/admin/refresh` and adverse-media run routes (network), the new `signin-strands.js` canvas code beyond the CSP test already in the suite, production behaviour.
- Full pytest suite not run (about 10 minutes; the merged PRs list passing runs in their descriptions).

## Files created
`repro_redteam/probe_mobile_authz.py`, `repro_redteam/probe_mobile_threshold.py`, `reports/daily/2026-10-05/red-team.md`, `reports/daily/2026-10-05/evidence/*.txt`. The earlier probes and proposals are carried over unchanged from the 2026-10-04 branch. No application code edited.

## Addendum (04:41 UTC, manual re-fire; master `28e4b51`)
Master moved from `448a19b` to `28e4b51` with one merge, #416 (four blog posts, `web/blog.py`, templates, tests; no change to auth, screening, KYT or tenant code). I did not repeat the full job. One quick probe of the new public, unauthenticated `/blog` surface (`repro_redteam/probe_blog_public.py`, evidence `evidence/probe_blog_public_on_28e4b51.txt`): REFUTED for all of these: slug and topic path traversal or odd input (all 404; `/blog/..` is normalised client-side to a redirect), reflected `q` (HTML-escaped, `{{7*7}}` not evaluated), regex-style or max-length `q` (0.01 s), inline scripts in the five posts (0), JSON-LD that does not parse (all parse), `target=_blank` links without `rel=noopener` (0), `http://` links (0), non-GET methods (405). CSP and `X-Content-Type-Options`/`X-Frame-Options` are present; `Referrer-Policy` is not set on `/blog` pages (INFO, not a vulnerability). All findings in the 2026-10-05 report above still stand; nothing else was changed or checked.
