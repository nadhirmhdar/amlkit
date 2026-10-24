# Compliance specialist — daily report 2026-10-24

**Instructions I ran under.** Standing role from Nadhir: Regulatory Compliance Specialist for Law 10/2025, Cabinet Resolution 134/2025, Cabinet Decision 109/2023 and Cabinet Resolution 74/2020, citation-grounded, additive only, no production access, no `/system/*` calls, no secrets. This run's routine prompt: review changes since the previous report against UAE AML/CFT obligations, then one previously not-checked item; push the report to `routine/<DATE>-compliance-specialist`, never master. The no-change shortcut did not apply because master moved. No message from dreamon arrived. `corpus/` and `citation_register.json` do not exist in the repo, so every Article is unverified (PLAUSIBLE). Not legal advice.

**Headline: AMBER (unchanged).** Four new commits on master (public-site, compression and legal-name changes) touch no AML/CFT logic, the full suite passes on them, and every open finding from 2026-10-07 and 2026-10-22 stands.

## What I did, with evidence

- `git ls-remote origin refs/heads/master` at 01:16 UTC on 2026-10-24: `401da3298f97bc94710e4b7171ec43a2ce4162b2` (`401da32`). Previous report SHA was `0d56f72fb85a296c9882903c9552c13a2210a994`.
- `git log 0d56f72..origin/master`: four commits, all merged 2026-10-23: `48eda02` #428 gzip, `41f7490` #429 public-page links, `0dbe14f` #430 legal name, `401da32` #431 share image. 11 files, +123/-20. I read the whole non-test diff.
- No screening, freeze, retention, UBO, risk, goAML, review, KYT or audit code is touched. `goaml.py`, `cases/*`, `match/*`, `mail.py`, `ingest/*` are identical to `0d56f72`, so the code findings below are unchanged by diff.
- PR list sorted by update time: #428 to #431 are the only PRs merged since #427; draft #411 (docs audit) was updated again at 01:01 UTC and not reviewed.
- **Full test suite on `401da32`** (detached worktree, scratch venv): **2177 passed, 3 skipped in 875 s, exit 0.** This closes the "full suite on `0d56f72` not run" item from the last two reports and supersedes the older `2170 passed, 3 skipped` (that was `0129848`).

## Not-checked item taken this run

The full test suite on the post-`0129848` master (see above): passes. That also covers the two commits after `0d56f72`.

## Review of the four commits

- **#428 selective gzip (`amlkit/api/compress.py`, registered in `app.py`).** New ASGI middleware compresses only `/static/*`, `/robots.txt`, `/sitemap.xml`, and `/about`, `/blog`, `/blog/<slug>` when the request carries no session cookie. Reason given is BREACH. I checked it: every `csrf_token` field in `base.html` (lines 105, 170, 262, 284) sits inside a `{% if session %}` block, and the blog and about templates contain no `csrf_token`, flash or `set_cookie`. So an anonymous public response carries no per-user secret, and a request with a session cookie is never compressed. Login, forms, case files and downloads are unchanged. No confidentiality regression for customer or case data found. Residual: the gate keys on the session-cookie name only; a future public page that embeds a token for anonymous users would need to be kept out of `_PUBLIC_PAGES`. INFO.
- **#429 public-page links.** The header logo links `/about` when signed out (root 303-redirects to login); the UAE PASS link gets `rel="nofollow"`. No effect on the UAE PASS flow or its state/cookie checks.
- **#430 legal name LLC to FZE.** Footer, about, login, privacy page, blog templates and JSON-LD author/publisher now say "Grovisor Business Consultants FZE". `git grep` on `origin/master` (excluding `reports/` and `docs/reviews/`) finds no remaining "Business Consultants LLC", so the rename is complete in the repo. Whether FZE is the correct licensed name cannot be verified from the repo (it needs the trade licence); I did not touch it. The goAML reporting-entity reference is a per-organisation setting and is not affected.
- **#431 share image.** Adds `static/img/og-card.png` and points og/twitter image tags at it. No compliance relevance.

## Findings

| ID | Severity | Status | Finding |
|---|---|---|---|
| N-2 | none | REFUTED | #428 to #431 change no obligation logic (screening, freeze, retention, UBO, PF, goAML, MLRO liability) and cause no test failure. Regression risk to the six mandatory rules from these commits: none found. |
| CS-18 | INFO | PLAUSIBLE | The gzip allow-list in `compress.py` depends on public pages carrying no token for anonymous users and on the session cookie name. Safe on `401da32`; worth a regression test (an anonymous `/about`, `/blog` and `/blog/<slug>` response containing no `csrf_token`) so a later template change cannot reintroduce BREACH exposure on a page that also carries case data. Relates to customer confidentiality and tipping-off (Law 10/2025 Art 20 context, unverified). |
| CS-2 (carry) | HIGH | PLAUSIBLE (legal scope); CONFIRMED (code behaviour) | Unchanged: the product still opens `pending_execution` freeze obligations for OFAC/EU confirmed matches and `amlkit/mail.py:292-296` still tells the MLRO to freeze and file a CNMR, while the public guide says those lists are not CNMR/PNMR matters. Basis: Res 74/2020 Art 15, Law 10/2025 Art 17 (unverified). |
| CS-17 (carry) | INFO | PLAUSIBLE | `canonical` and `og:url` still derive from `request.url.path` on pages that do not override the block, including authenticated ones. |

All other findings in the 2026-10-22 and 2026-10-07 reports stand unchanged, including CS-13 (24-hour clock keyed to disposition, not designation), CS-14 to CS-16, the FATF items CS-1/CS-6/CS-7, CS-3 to CS-5, 3.1 (configurable cash threshold, Res 134/2025 Art 21), 4.2 and 5.x (UBO tiers, Dec 109/2023). Retention (5 vs 8 years; Law 10/2025 Art 25, Res 134/2025 Art 24) is unresolved without `corpus/`.

## BLOCKED / not checked

- **Primary legal text: BLOCKED**, unchanged. Three official hosts (`rulebook.centralbank.ae`, `uaelegislation.gov.ae`, `fatf-gafi.org`) refused this environment's egress on 2026-10-06; not retried or bypassed. To unblock: provide the official PDFs of the four instruments as `corpus/` plus `citation_register.json`.
- Correctness of the legal name "FZE" against the trade licence: not checkable from the repo.
- Draft #411 content: not reviewed.
- Production: not checked.

## Files and commit

`reports/daily/2026-10-24/compliance-specialist.md` on `routine/2026-10-24-compliance-specialist`, created from `origin/master` `401da32`. The commit SHA is in the final reply (a commit cannot name its own SHA).
