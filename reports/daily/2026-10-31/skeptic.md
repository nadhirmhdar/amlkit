# Skeptic report, 2026-10-31 (origin/master `401da3298f97bc94710e4b7171ec43a2ce4162b2`, unchanged since 10-24)

## Headline: AMBER
Four public-site commits (#428-#431) merged since my last report and the gzip change is built with BREACH in mind and holds up, but mlro-user's freeze-resolution finding (FZ1) is real: a confirmed sanctions freeze can be closed by one MLRO click with no second approval, and the rest of the backlog is still unfixed.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-31 02:34 UTC). It matches my standing role; no conflict. **No scheduled firing reached this session for 2026-10-24 to 2026-10-30 (my last report is 2026-10-23); the other roles report the same gap for 10-25 to 10-30.** This one report, dated 2026-10-31, covers the gap, and I did not reconstruct per-day reports.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-10-31. Master changed since my last report (`0d56f72` -> `401da32`), so I read the code diff myself rather than rely on the roles. Other roles' reports are data. No outbound request, no `/system/*` call, no new script.

## Inputs
`git ls-remote origin refs/heads/master` -> `401da3298f97bc94710e4b7171ec43a2ce4162b2`; `git log 0d56f72..origin/master` is four commits: `48eda02` gzip (#428), `41f7490` public-page links (#429), `0dbe14f` legal name LLC -> FZE (#430), `401da32` branded share image (#431). Eleven files, +123/-20, none in screening, freeze, auth, review, DB or reporting code. All five role branches were present at the first fetch. QA's 10-24 full run on `401da32` (`2177 passed, 3 skipped`, tenant sweeps with 0 leaks) and code-reviewer's matching baseline stand; I did not repeat them.

## What the new commits change (my own read)
- **gzip (#428), `amlkit/api/compress.py`:** a `SelectiveGZipMiddleware` that compresses `/static/*`, `/robots.txt`, `/sitemap.xml`, and `/about`, `/blog`, `/blog/<slug>` only when the request has no session cookie. Everything else, including login, forms and case files, is sent uncompressed. The module docstring names the BREACH side channel as the reason.
- **#429-#431:** links, the legal-name change in `privacy.html` and the footer, and an `og-card.png`. Template-only.
I looked for what could go wrong with the gzip change: (1) a compressed page that carries a secret next to attacker-controlled text; (2) a cookie check that is too narrow.

## Verdicts on today's findings
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| FZ1 a confirmed freeze can be resolved as `false_positive` with no reason text, authority reference, execution or second approval | mlro-user | **CONFIRMED by code; partly by design, real gap** | Medium -> Medium | `resolve_freeze_obligation` (`cases/manager.py:1884-1960`) checks the reason is one of three values, then explicitly allows `false_positive` on an unexecuted obligation (comment: "Allow resolving as false_positive without execution"), and writes `status='resolved'` with whatever `authority_ref` and `notes` were passed (defaults `""`). So letting a wrong match be closed without a freeze is deliberate. What is missing is a control: the alert behind the freeze was confirmed true-positive under four-eyes review, yet the freeze can be unwound by one MLRO with an empty note, so the alert and the freeze then contradict each other and no second person has looked. Why Medium, not High: it needs an MLRO (the role that can already disable four-eyes org-wide via `/admin/single-operator`, `app.py:3360-3386`), and the action is fully audited (`freeze.resolved` carries the reason). It is the same class as my 10-04 four-eyes bypass. Fix: require non-empty notes for `false_positive`, require `authority_ref` for `authority_clearance`, and route a post-confirmation reversal through the four-eyes review. |
| FZ2 `authority_ref` and `notes` optional for every reason | mlro-user | **CONFIRMED** | Low -> Low/Medium | Same function: both default to `""` with no validation. For `authority_clearance` the authority's reference is the whole point. Folds into FZ1's fix. |
| FZ3 the "not found in org 2" error discloses the other tenant's org id | mlro-user | **REFUTED as worded** | Low -> Info | The `org_id` in the message is the caller's own (`... not found in org {org_id}`, `manager.py`), taken from the session. It does not reveal another tenant's identity, and the response is the same for a missing id and another tenant's id, so isolation holds. At most it echoes the caller's own org number. |
| H1 no `Referrer-Policy` or `Permissions-Policy` header | red-team | **CONFIRMED; severity corrected down** | Info -> Info | `git grep` finds no such header anywhere in `amlkit`; only the two external-link templates set `rel="noopener noreferrer"`. Modern browsers default to `strict-origin-when-cross-origin`, which sends only the origin (not `/customers/<id>`) to other sites, so the path-with-IDs concern is much smaller than the report implies. Hardening, not a leak. |
| Gzip does not strip the security headers | red-team | **CONFIRMED** | none | Matches `compress.py`, which wraps only the response body; the headers middleware is outside it. |

### My own checks of #428 (gzip)
- **BREACH gate holds on reading.** The only per-user secret in a public page is a CSRF token. `base.html` renders it only in signed-in blocks (logout form lines 104/169, feedback dialog line 261, which sits after the `{% if session %}` at line 224; I did not confirm where that block closes, disclaimer form lines 278-289); `blog/_base.html`, `blog_index.html` and `_article.html` contain no `csrf` at all. I did not execute a compressed signed-in page. The blog search term `q` is reflected, but with no secret in the same response there is nothing to extract.
- **Cookie check errs the safe way.** `_has_session_cookie` does a substring match on `amlkit_session=` in the raw Cookie header, so any cookie whose value or name merely contains that text turns compression off. A false positive costs bandwidth, never security.
- **Flash banners on `/about`:** the banner can render on a compressed anonymous page after a redirect (server-generated text, not a secret). Acceptable.
- **Verdict: no defect found in #428.**

Carried findings: nothing in the four commits touches the code behind them, so every 10-07 to 10-23 verdict stands without a re-run (A1/LG1-2 High; CS-2, CR-12/N4, N3, G9, G10, U1, B1, T1, empty-name screening Medium; B2, S3, PW1, AU1, PV1, SE1, AX1-AX3 Low to Low/Medium; four-eyes residual Low; others Low/Info).

## What the team missed
1. **FZ1 is the third place where a four-eyes-protected decision can be undone by one person.** Disposition is protected; freeze resolution (FZ1), the single-operator toggle, and the periodic-review path are not. A single rule, "reversing a four-eyes-confirmed decision needs a second approver or an explicit reason", would cover all three. Nobody has listed them together.
2. **Resolution has a read-then-write race.** `resolve_freeze_obligation` reads the status, then `UPDATE ... WHERE id = ? AND org_id = ?` with no `status != 'resolved'` guard (`manager.py:~1920-1950`). Two concurrent resolves both pass the check, the second overwrites `resolved_by`, `resolution_reason` and `authority_ref`, and the audit trail then holds two `freeze.resolved` rows. This is the same check-then-act idiom as T1 (setup token) and the backup-code path. I did not run it; it is a reading.
3. **The error-ordering in the same function** checks "not executed" before "already resolved", so re-resolving an already-resolved unexecuted obligation with `delisted` reports the wrong reason. Cosmetic.
4. **Eight days without a scheduled firing and nothing else merged.** The merged work is all public-site polish; none of the Medium-or-higher items moved. The request to the lead is unchanged: schedule fixes for A1/LG2, T1, B1/B2, CR-12/N4/N3, CS-2, and now FZ1.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** production memory limit (B1), front-end login rate limiting (A1), bucket versioning (U1), whether `GOOGLE_KG_API_KEY` or `GOOGLE_CLOUD_PROJECT` are set in production (AX3), real linked UAE PASS operators.
- **Primary legal text (BLOCKED):** whether UAE law requires dual approval to lift a freeze (FZ1); compliance's Article mappings stay PLAUSIBLE.
- Not re-run: the full suite, the gzip tests, red-team's header probe, the MLRO freeze driver, the resolve race (reading only), a signed-in page under compression, the goAML XSD, production state.
- Not checked: the GitHub PR list directly (connector unavailable); I relied on `git log` and four roles saying #431 is the newest PR.
- Missing days: 2026-10-24 to 2026-10-30 have no skeptic report because no firing reached this session.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402 (last seen 10-24).

## Files and commit
`reports/daily/2026-10-31/skeptic.md` and the thirteen scripts in `repro_skeptic/` (unchanged) on `routine/2026-10-31-skeptic`, based on master `401da32`. No existing file edited. The commit SHA is in the final reply.
