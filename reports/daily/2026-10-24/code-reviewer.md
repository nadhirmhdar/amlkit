# code-reviewer daily report, 2026-10-24

**Instructions I ran under:** scheduled routine "groAML daily: code-reviewer" (fired 2026-10-24 00:45 UTC). Review current origin/master, the changes since the SHA in my previous report, and PRs opened or updated since. Standing rules: no production access, no `/system/*` calls, no secrets, local test data only, never push to master, stop after delivering.

**Headline: GREEN.** origin/master moved from `0d56f72fb85a296c9882903c9552c13a2210a994` to `401da3298f97bc94710e4b7171ec43a2ce4162b2` by four public-site commits (#428-#431); I found no defect, including in the new selective gzip middleware.

**What I did (evidence):**
- `git ls-remote origin refs/heads/master` returned `401da32…`; `git log 0d56f72..origin/master` lists #428 gzip, #429 public-page links, #430 legal name FZE, #431 share image. All four were merged by the owner.
- Read the full diff (11 files, +123/-20). No DB, auth, tenant-isolation, migration or concurrency code is touched.
- **New code, `amlkit/api/compress.py` (#428), checked against the BREACH risk it exists to avoid:**
  - Compression applies only to `/static/*`, `/robots.txt`, `/sitemap.xml`, and `/about`, `/blog`, `/blog/*` when the request has no `amlkit_session` cookie.
  - Probe with `TestClient`, throwaway DB: anonymous `/about`, `/blog`, `/blog?q=…` and a blog post contain no `csrf_token` field. `/about` sets the `amlkit_csrf` cookie, but its value is not in the body.
  - `/login`, `/privacy`, `/apply` and any request carrying a session cookie stay uncompressed.
  - A `Range` request on `/static/img/og-card.png` returned a correct `206` with a correct `Content-Range`, uncompressed.
  - `og-card.png` is served unencoded, so there is no double compression.
- Tests: `tests/test_blog.py` 36 passed. Full suite on `401da32` (Linux, `.venv`): **2177 passed, 3 skipped**, 14 min 8 s (previous baseline 2173 passed, 3 skipped).

**Findings:**
- CR-21 (INFO, CONFIRMED): the new `test_public_pages_do_not_link_to_the_redirecting_root` ends with `assert A in html or "uaepass/start" not in html`, so the `rel="nofollow"` check on the UAE PASS link passes even if the attribute is removed. Test hygiene only.
- CR-22 (INFO, CONFIRMED): `twitter:card` is still `summary` while the new `og-card.png` is 1200x630. `summary_large_image` would use the full card; the image is small-card cropped today. SEO polish, not a defect.
- CR-23 (INFO, CONFIRMED): the cookie check in `compress.py` is a substring match on `amlkit_session=`, so a cookie like `x_amlkit_session=` also disables compression. This fails safe (less compression, never more), so no action is needed.
- CR-19/20 (INFO) from 2026-10-22 are unchanged.
- Carried findings, unchanged: CR-12 (MEDIUM, open), CR-4 (MEDIUM, open in unmerged #417), CR-13/14/18 (LOW), CR-1b (LOW residual), CR-2/3/5/17. Tables are in the 2026-10-06 and 2026-10-07 reports.

**BLOCKED / not checked:** nothing blocked. CI status for `401da32` was not looked up (standing rule: no CI re-checks). Rendered pages were checked via `TestClient` output and templates, not in a browser. The legal-name change (FZE vs LLC) is a factual claim about the entity that I can't verify from this repo.

**Files / commits:** `reports/daily/2026-10-24/code-reviewer.md`; commit SHA in the final reply.
