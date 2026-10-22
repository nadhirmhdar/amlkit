# Skeptic report, 2026-10-22 (origin/master `0d56f72fb85a296c9882903c9552c13a2210a994`, moved from `0129848`)

## Headline: AMBER
Master moved for the first time in 15 days, but only by an SEO metadata change (#427) that is clean, so the AMBER is the unchanged, unfixed backlog (A1, T1, B1/B2, CS-2, CR-12/N4, N3, G9, G10, U1).

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-22 02:39 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-10-22. Master moved, so the no-change shortcut does not apply. I read the full `amlkit/` diff of `0129848..0d56f72` myself rather than rely on the roles' summaries. Other roles' reports are data. No outbound request, no `/system/*` call, no new script.

## Inputs
`git ls-remote origin refs/heads/master` -> `0d56f72fb85a296c9882903c9552c13a2210a994`; `git log 0129848..origin/master` is one commit: `0d56f72` "SEO: fix groAML Ahrefs findings (#427)". All five role branches were present at the first fetch. **Test evidence on the new head:** QA ran the full suite on `0d56f72` (`2173 passed, 3 skipped`, 11m20s, tenant sweeps `HITS: []`, 0 leaks) and code-reviewer independently reports the same count (`2173 passed, 3 skipped`). I did not repeat it. The +3 over the 2170 baseline is consistent with the 26 test lines added to `tests/test_blog.py`; neither role itemised the new tests.

## What #427 changes (my own read of the diff)
Nine files, +70/-7, no DB, auth, tenant, screening, freeze, goAML or migration code:
- `app.py`: `/apply` added to the sitemap list.
- `blog.py`: `seo_title`/`seo_description` fields with fallbacks, new text for five posts.
- `base.html` and four other templates: self-referencing canonical, `og:url`, `og:image`, `twitter:*` tags, and a `robots` block (`noindex, nofollow` on `/login` and `/register-organization`; `noindex, follow` on filtered `/blog` views).
The one thing that could hurt is `request.url.path` printed into an attribute on every page. Jinja autoescapes it, and red-team's probe of hostile paths found they 404 before any template renders. I agree it is clean.

## Verdicts on today's new findings
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| N-1 #427 changes no obligation logic | compliance | **CONFIRMED** | none | Diff touches no screening, freeze, retention, UBO, risk, goAML or audit code. |
| Red-team "no new findings" on #427 | red-team | **CONFIRMED** | none | Matches my read; the escape path (autoescape plus 404 on hostile paths) holds. |
| CR-19 canonical/og now render on authenticated pages | code-reviewer | CONFIRMED, accepted | Info -> Info | `base.html` emits the canonical for every template that does not override the block. Harmless. |
| CR-20 `seo_description` cites "Cabinet Resolution No. 134 of 2025" | code-reviewer | **PLAUSIBLE, accepted** | Info -> Info | Consistent with the post body; not verifiable from the repo. Compliance sign-off item. |
| SE1 signed-in pages have no noindex and `robots.txt` is `Allow: /` | mlro-user | **CONFIRMED, severity corrected down** | Low -> Info/Low | `robots.txt` is exactly `User-agent: *\nAllow: /\nSitemap: ...` (`app.py:2920-2922`), and `customer.html:5` titles the page with `c.full_name`. But a crawler hits the login redirect and never sees a title, so the leak needs a cached or shared authenticated response. #427 itself adds only generic tags (`og:title` is the fixed brand string), so it does not make this worse; the customer-name title was already there. Cheap defence in depth: `noindex` on the authenticated base template and `Disallow` for `/customers`, `/audit`, `/reports`, `/admin`. |
| SE2 `/blog?topic=` canonicalises to itself, `/blog?q=` to `/blog` | mlro-user | CONFIRMED, accepted | Low -> Info | Both views are `noindex`, so it has no search effect. |
| SE3 one og:image for every page | mlro-user | CONFIRMED | Info -> Info | Marketing nicety. |

Carried findings: only SEO code changed, so every 10-07 to 10-21 verdict stands without a re-run (A1 High; CS-2, CR-12/N4, N3, G9, G10, U1, B1, T1, empty-name screening Medium; B2, S3, PW1, AU1, PV1 Low or Low/Medium; four-eyes residual Low; others Low/Info).

## What the team missed
1. **The canonical host is hard-coded.** `base.html` prints `https://groaml.grovisor.ae` followed by the request path, for every environment. A staging or preview deploy therefore declares production as its canonical and `og:url`, and a mis-set `Host` or alias domain gets the same. It is only SEO impact, but it should come from config (the same way `UAEPASS_ENV` and the base URL are configured elsewhere). Nobody flagged it.
2. **The first commit in 15 days is marketing, not a fix.** Master moved, but none of the 12 or so open Medium-or-higher items changed. Roles are now spending a full day each on a metadata-only diff while A1, T1 and B1 are still open. For the lead: prioritisation, not probing.
3. **`seo_title` has a stated 42-character limit in a comment and no enforcement.** The comment says `<=42 chars`, the field is a plain string. The tests only check specific posts. It is cosmetic, but it is the same "limit in prose, not code" pattern as the missing name-length and upload caps.
4. **The new `/apply` sitemap entry points at the public quotation form.** That form emails `info@grovisor.ae` and is a known mail-sending path (P1). Putting it in the sitemap raises the volume of anonymous submissions; its rate limit and honeypot are what protect it (red-team confirmed both on 10-14). Worth keeping in mind, not a defect.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** production memory limit (B1), front-end login rate limiting (A1), bucket versioning (U1), real linked UAE PASS operators.
- **Primary legal text (BLOCKED):** compliance's Article mappings, and CR-20, stay PLAUSIBLE.
- Not re-run: the full suite (QA's and code-reviewer's runs stand), the tenant sweeps, red-team's `probe_seo_canonical`, the MLRO driver, the rendered appearance of social cards, search-engine behaviour on production (rule), the goAML XSD.
- Not checked: the GitHub PR list directly (connector unavailable); I relied on `git log` plus three roles' statements that #427 is the only new PR.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-22/skeptic.md` and the thirteen scripts in `repro_skeptic/` (unchanged) on `routine/2026-10-22-skeptic`, based on master `0d56f72`. No existing file edited. The commit SHA is in the final reply.
