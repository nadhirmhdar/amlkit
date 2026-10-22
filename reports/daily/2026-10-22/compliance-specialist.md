# Compliance specialist — daily report 2026-10-22

**Instructions I ran under.** Standing role from Nadhir: Regulatory Compliance Specialist for Law 10/2025, Cabinet Resolution 134/2025, Cabinet Decision 109/2023 and Cabinet Resolution 74/2020, citation-grounded, additive only, no production access, no `/system/*` calls, no secrets. This run's routine prompt: review changes since the previous report against UAE AML/CFT obligations, then one previously not-checked item; push the report to `routine/<DATE>-compliance-specialist`, never master. The no-change shortcut did not apply because master moved. No message from dreamon arrived. `corpus/` and `citation_register.json` do not exist in the repo, so every Article is unverified (PLAUSIBLE). Not legal advice.

**Headline: AMBER (unchanged).** One new commit on master (SEO metadata only) introduces no AML/CFT regression, and every open finding from 2026-10-07 stands.

## What I did, with evidence

- `git ls-remote origin refs/heads/master` at 01:16 UTC on 2026-10-22: `0d56f72fb85a296c9882903c9552c13a2210a994` (`0d56f72`). Previous report SHA was `01298484a7bfed106e9b2bd3a6238f98a4d2514b` (`0129848`).
- `git log 0129848..origin/master`: one commit, `0d56f72` "SEO: fix groAML Ahrefs findings" (PR #427, merged 2026-10-21 04:19 UTC). 9 files, +70/-7: `amlkit/api/app.py` (sitemap adds `/apply`), `amlkit/web/blog.py` (`seo_title`/`seo_description` fields on the five posts), `base.html`, `blog/_article.html`, `blog_index.html`, `about.html`, `login.html`, `register_organization.html`, `tests/test_blog.py`. I read the whole non-test diff.
- No screening, freeze, retention, UBO, risk-model, goAML, review or audit code is touched. `amlkit/reporting/goaml.py`, `amlkit/cases/*`, `amlkit/match/*`, `amlkit/mail.py`, `amlkit/ingest/*` are identical to `0129848`, so the code findings below are unchanged by diff.
- PR list sorted by update time: #427 is the only PR opened or merged since #426; draft #411 (docs audit) was updated again at 01:02 UTC and was not reviewed.
- Tests: ran `tests/test_blog.py` and `tests/test_p54_alert_queue_sort.py` on a detached worktree of `0d56f72` with the scratch venv: **35 passed**. The PR notes the full suite was not run locally and I did not run it (about 11 minutes), so the earlier `2170 passed, 3 skipped` result is for `0129848` and does not cover `0d56f72`.

## Not-checked item taken this run

Whether the public 24-hour-rule guide, whose metadata this commit edits, still matches the EOCN list scope and the CNMR/PNMR rules. Source: EOCN guidance page `uaeiec.gov.ae/en-us/un-page`, fetched 2026-10-06 and held in my scratchpad; the official legal text itself is still BLOCKED.

- `blog/uae-sanctions-screening-24-hour-rule.html` says only the UAE Local Terrorist List and the UN Consolidated List carry the 24-hour duty (line 25), that OFAC/EU/UK hits are not CNMR/PNMR (lines 34-35, 79, 87, 204), CNMR/PNMR within five business days, and the five-year look-back. That matches the EOCN guidance as I read it on 2026-10-06. The new `seo_title` ("UAE 24-Hour Freezing Rule for DNFBPs") and `seo_description` (which lists trigger the freeze, first-day actions, goAML, inspection proof) make no claim beyond the body. No Article numbers appear in the new metadata. Result: consistent with EOCN guidance; legal basis PLAUSIBLE (Law 10/2025 Art 17, Res 74/2020 Art 15, Res 134/2025 Art 32 are the cited anchors, unverified).
- The risk-assessment description now names "Cabinet Resolution No. 134 of 2025" and the regulatory-updates description names "Federal Decree-Law No. 10 of 2025 and its Executive Regulations". Both are consistent with the instruments named in the standing brief. Unverified against primary text.

## Findings

| ID | Severity | Status | Finding |
|---|---|---|---|
| N-1 | none | REFUTED | #427 changes no obligation logic (screening, freeze, retention, UBO, PF, goAML, MLRO liability). Regression risk to the six mandatory rules from this commit: none found. |
| CS-2 (update) | HIGH | PLAUSIBLE (legal scope), CONFIRMED (code behaviour, not touched by #427) | The public guide, now with fresh SEO metadata, tells customers that OFAC/EU/UK hits are not CNMR/PNMR and not subject to the 24-hour freeze. The product still opens `pending_execution` freeze obligations for OFAC/EU confirmed matches and `amlkit/mail.py:292-296` still tells the MLRO to freeze and file a CNMR. The product contradicts its own published guidance, so the gap is more visible than before. Open since 2026-10-06; legal basis Res 74/2020 Art 15, Law 10/2025 Art 17 (unverified). |
| CS-17 | INFO | PLAUSIBLE | `base.html` now emits `canonical` and `og:url` as `https://groaml.grovisor.ae{{ request.url.path }}` for every page that does not override the block, which includes authenticated pages such as `/customers/{id}`. This goes only to the logged-in operator's browser, so no third-party disclosure is evident, and I did not render an authenticated page to confirm. Flagged only because it puts customer record ids in canonical/social tags, which is worth keeping out of any future share or preview feature (tipping-off and confidentiality, Law 10/2025 Art 20 and Art 17 context, unverified). |

All other findings in the 2026-10-07 report stand unchanged: CS-13 (24-hour clock keyed to disposition rather than designation), CS-14, CS-15, CS-16, the FATF items CS-1/CS-6/CS-7, CS-3, CS-4, CS-5, 3.1 (configurable cash threshold, Res 134/2025 Art 21), 4.2 and 5.x (UBO tiers, Dec 109/2023). Retention: #422 removed the statutory figure from code and copy and set a 10-year firm plan; whether the statutory minimum is 5 or 8 years is still unresolved without `corpus/` (Law 10/2025 Art 25, Res 134/2025 Art 24, unverified).

## BLOCKED / not checked

- **Primary legal text: BLOCKED**, unchanged. Three official hosts (`rulebook.centralbank.ae`, `uaelegislation.gov.ae`, `fatf-gafi.org`) refused this environment's egress on 2026-10-06; not retried or bypassed. To unblock: provide the official PDFs of the four instruments as `corpus/` plus `citation_register.json`.
- Full test suite on `0d56f72`: not run (only the two targeted files above).
- Draft #411 content: not reviewed.
- Production: not checked.

## Files and commit

`reports/daily/2026-10-22/compliance-specialist.md` on `routine/2026-10-22-compliance-specialist`, created from `origin/master` `0d56f72`. The commit SHA is in the final reply (a commit cannot name its own SHA).
