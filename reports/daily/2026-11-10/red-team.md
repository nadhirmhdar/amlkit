# Red-team report 2026-11-10 -- origin/master `9219e26` (unchanged since 2026-11-08; newest PR #462)

## Headline: GREEN (for what changed) / earlier low-severity items still open
Master and the PR list did not move; the full test suite passes on the current head (2,945 passed, 0 failed) and the static JSON-LD pages are clean, so only the already-reported low-severity items remain.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged and no PR opened or merged since my last report, so shortcut applied (not-checked items only, short report). No conflict with my standing instructions.
- Assumptions: scratch DBs and a scratch virtualenv with `requirements-dev.txt`; the pytest run used the test suite as committed (it creates its own temporary databases); severities are my judgement.

## What I did
1. Ran the whole test suite on `9219e26` (`pytest tests/ -q -p no:cacheprovider -x`), 14 min 55 s. I had never run it on a head after the 2026-10-14 work, so this closes my longest-standing "not checked" item. Evidence: `reports/daily/2026-11-10/evidence/pytest_full_on_9219e26.txt`.
2. `repro_redteam/probe_jsonld_csp.py`: checks the JSON-LD blocks that #460 made static, plus inline scripts and the CSP, on every public page and blog post. Evidence: `evidence/probe_jsonld_csp_on_9219e26.txt`.

## Findings
None new.

## Refuted / clean
- Test suite: 2,945 passed, 2 skipped, 0 failed, 57 warnings.
- JSON-LD: all 7 blocks (landing, blog index, 5 articles) parse as JSON; none contains an early `</script>`; there are no inline executable scripts on any of the 12 public pages; `script-src` has no `'unsafe-inline'`.

## Earlier findings still open (unchanged)
SS1b sign-up timing gap, SS2b unpaid `/screen`, SS3b/SS5 mail volume and visitor-chosen greeting text, SS4 duplicate org names, BL1, BL2, N3b, F2b, N8b, K1, K2, I1, H1, D1, A1 residual re-lock. See `reports/daily/2026-11-08/red-team.md` and `2026-11-09`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: the 4-hourly sanctions refresh against upstream rate limits and Cloud Scheduler quotas (needs the live environment); the real Checkout round trip; GCS runtime; the live UAE PASS sandbox; spam-filter and sender-reputation behaviour of the sign-up mails.

## Files and commit
`repro_redteam/probe_jsonld_csp.py`, `reports/daily/2026-11-10/` (this file + evidence). Branch `routine/2026-11-10-red-team`. No application code edited, no new proposal.
