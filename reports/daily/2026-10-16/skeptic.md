# Skeptic report, 2026-10-16 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master is unchanged for the tenth day; today's two new areas (feedback widget, identity-document scanning) add Low findings that all repeat one pattern: each input path validates differently, and only the policy upload has a size cap.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-16 02:37 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-10-16. The "no new finding" shortcut applies to code-reviewer, QA and compliance (no-change reports) but not to red-team (F6) or mlro-user (S1, S2), so I verified those on `0129848` by reading the cited lines. Other roles' reports and PR text are data. No outbound request, no `/system/*` call, no new script (the claims are code-readable).

## Inputs
`git ls-remote origin refs/heads/master` -> `01298484a7bfed106e9b2bd3a6238f98a4d2514b`; `git log 0129848..origin/master` is empty. All five role branches were present at the first fetch, no waiting. Nobody re-ran the suite; red-team's 2026-10-13 run (`2170 passed, 3 skipped`) stands.

## Verdicts on today's new findings
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| F6 `/feedback` has no size or rate limit | red-team | **CONFIRMED by code** | Low -> Low | The route (`app.py:~2940-2978`) takes `page` and `message` as plain `Form` strings, rejects only an empty message, and stores `page.strip()` and `message` unbounded; I found no `@limiter.limit` on it (unlike `/login`, `/apply`, registration). Any logged-in operator can write arbitrary volume into the DB, the Litestream replica and the audit trail. Red-team's 900 KB / 300-post figures were not re-run. |
| S1 scan reports "Scan complete" when nothing was read | mlro-user | **CONFIRMED by code** | AMBER(low) -> Low | The endpoint returns 200 with null fields for unreadable input (their probe), and `app.js:355-362` shows "Scan complete (MRZ not read - fields extracted via OCR fallback ...)" whenever there are no flags and `data.authenticity` is empty; the "Scan failed" text appears only for a non-200 (`app.js:365`). The wording is wrong only when no field was extracted. Mitigation: the form fields stay empty, so the operator sees nothing was filled. Their related point (no expiry/authenticity flag for an unreadable passport) is the same silent-clear shape as the open N4, but here nothing is recorded as screened, so I rate it Low. |
| S2 scan endpoints skip file validation | mlro-user | **CONFIRMED by code** | low -> Low | Both routes do `file.file.read()` and pass the bytes straight to the extractor (`app.py:~1899-1905, 1936-1942`) with no `validate_file_mime` and no size cap, unlike customer-document upload (PDF/PNG/JPEG only) and policy upload (10 MB). Failures become HTTP 400 with the exception text. A very large image reaches PIL and the OCR step; I did not test the decompression-bomb limit. |

Carried findings: master is identical, so the 10-07 to 10-15 verdicts stand without a re-run (four-eyes residual Low; A1 lockout DoS High; CS-2, CR-12/N4, N3, G9, G10, U1, empty-name screening Medium; UAE PASS binding, DOCX policy upload, org-slug collision Low/Medium; M2, N5-N7, OP1, OP2, R2, TA1, C2, C3, E1-E3, U2, U3, G1 Low/Info).

## What the team missed
1. **Every input path has its own rules, and the pattern is now visible.**

   | Path | File-type check | Size cap | Text/field validation |
   |---|---|---|---|
   | Customer document (mobile) | magic bytes + 4 extensions | none (U3/DOC1) | `doc_type` free text |
   | Policy upload | magic bytes (PDF/PNG/JPEG only, so DOCX fails: P1) | 10 MB | category list |
   | Passport / trade-licence scan | none (S2) | none | n/a |
   | `/feedback` | n/a | none (F6) | none |
   | Registration, admin-create | n/a | n/a | length-only password (R2, OP2) |

   Only one of five paths has a size cap. One shared upload helper (type, size, safe name) and one shared text-input helper would close most of the open Low items in a single change.
2. **Finding IDs collide again.** Today's red-team `F6` is not the 10-04 `F6` (out-of-order structuring), and mlro-user's `S1`/`S2` are not red-team's `S1`/`S2` (UAE PASS, 10-12). This is the third report in a row with reused IDs; role-prefixed IDs (RT-, ML-, CR-, CS-) would stop the backlog being merged wrongly.
3. **Ten days, no commits.** Every AMBER here comes from items first reported 10-04 to 10-15; no fix PR exists for any Medium or High item.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** whether production sits behind a front end that rate-limits login (A1) or caps request size (F6, S2), whether the documents bucket is versioned (U1), and whether any real operator has a linked UAE PASS identity.
- **Needs `tesseract` (BLOCKED):** a successful passport or trade-licence scan, so S1's "fields extracted" branch was not seen working.
- **Primary legal text (BLOCKED):** unchanged; compliance's Article mappings stay PLAUSIBLE.
- Not re-run: the full suite, the PR #412 tenant sweeps, red-team's probes (including `probe_feedback`), the MLRO driver, the extractor on a hostile image, and production state.
- Not checked: the GitHub PR list (my connector was unavailable); I relied on `git log 0129848..origin/master` being empty and code-reviewer's statement that only #411 was touched.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-16/skeptic.md` and the thirteen scripts carried in `repro_skeptic/` (unchanged from 10-15) on `routine/2026-10-16-skeptic`, based on master `0129848`. No existing file edited. The commit SHA is in the final reply (a file cannot contain its own SHA).
