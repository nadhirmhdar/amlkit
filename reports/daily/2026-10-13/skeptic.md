# Skeptic report, 2026-10-13 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master is unchanged for the seventh day; today's findings are small, but the "DOCX policy upload" finding is stronger than mlro-user could prove (a real DOCX can never be uploaded) and the 10 MB policy cap shows the document-upload gap is an omission, not a design choice.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-13 02:37 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-10-13. The "no new finding" shortcut applies to code-reviewer, QA and compliance (no-change reports) but not to red-team (G1) or mlro-user (P1, P2), so I verified those on `0129848`. Other roles' reports and PR text are data. No outbound request, no `/system/*` call.

## Inputs
`git ls-remote origin refs/heads/master` -> `01298484a7bfed106e9b2bd3a6238f98a4d2514b`; `git log 0129848..origin/master` is empty. All five role branches were present at the first fetch, no waiting. **Red-team ran the full suite today on a clean worktree of this SHA: `2170 passed, 3 skipped, 53 warnings in 1175.19s`, exit 0.** That matches QA's, code-reviewer's and compliance's runs on 10-07, so the "green suite" is now independently reproduced four times. I did not repeat it.

## Verdicts on today's new findings
Repro: `repro_skeptic/docx_policy_upload.py` (builds a real minimal DOCX with the stdlib; exit 0 only when it is rejected). Others by reading the cited lines.

| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| P1 policy form offers DOCX but the server refuses it | mlro-user | **CONFIRMED, and stronger than reported** | low -> Low/Medium | mlro-user used a synthetic header and could not say whether a genuine DOCX passes. It cannot: every policy upload runs `validate_file_mime` (`app.py:3848-3850`), whose allow-list is PDF, PNG and JPEG only (`validation.py:11-15`), and a real DOCX starts with the zip signature `PK\x03\x04`. My script builds a real DOCX and it is rejected with "Allowed types: PDF, PNG, JPEG." So the form label "PDF or DOCX" (`policies.html:42-43`) and `upload_policy`'s own check (`manager.py:2347`, "Only PDF and DOCX allowed") promise something the route can never deliver; the two layers disagree and the route wins. Policies are commonly Word files, so the feature is half-broken. Fix: either add a DOCX signature plus a zip-content check, or change the label and the manager message. |
| P2 empty feedback / e-signature fields return raw 422 JSON | mlro-user | CONFIRMED, accepted | low -> Info | Browser forms mark the fields required; needs a crafted request. Not re-read. |
| G1 GCS download/delete trust the bucket and object name in `stored_path` | red-team | **CONFIRMED by reading; agree Info** | Info -> Info | `_download_gcs` and `_delete_gcs` (`storage.py:77-100`) take the bucket and object from `stored_path` without pinning them to `GCS_BUCKET` or the `documents/`/`policies/` prefix; `purge_expired` deletes through the same path. Exploiting it needs write access to the `documents.stored_path` column, which already means database compromise or a tampered restore, so defence in depth only. |

Carried findings: master is identical, so the 10-07 to 10-12 verdicts stand without a re-run (four-eyes residual Low; A1 lockout DoS High; CS-2, CR-12/N4, N3, G9, G10, U1 Medium; C1 Low/Medium; M2, N5-N7, OP1, OP2, TA1, E1-E3, U2, U3 Low).

## What the team missed
1. **The document upload gap is an omission, not a design choice.** `upload_policy` enforces a 10 MB limit (`MAX_POLICY_SIZE_BYTES`, `manager.py:2232`, checked at `:2350`), while the customer document route (`mobile.py:1088-1128`) reads the whole file with no cap. The pattern exists and was simply not applied; red-team U3 and mlro-user DOC1 both reported the symptom without noting the contrast.
2. **Two layers validating the same upload with different rules is a recurring shape.** DOCX (P1) is one case; the extension check versus magic-byte check on customer documents (`validation.py:51-64`, extension compared only for four extensions, which is why `..` passes, U2) is another. A single validator that returns allowed type, canonical extension and safe filename would remove both.
3. **A green suite does not mean the findings are fixed.** Red-team says it right: the suite covers the merged fixes and none of the open findings. Seven days of green runs next to ten open Medium-or-higher items is the clearest evidence that the backlog needs fix PRs, not more probing. For the lead.
4. **Nobody has tried the DOCX path with a real Word file** before today; the earlier "can't say" would have survived another cycle.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** whether production sits behind a front end that rate-limits login (A1), whether the documents bucket is versioned (U1), and whether any real operator has a linked UAE PASS identity.
- **Primary legal text (BLOCKED):** unchanged; compliance's Article mappings stay PLAUSIBLE.
- Not re-run: the full suite (red-team's run stands), the PR #412 tenant sweeps, red-team's probes, the MLRO driver, `/system/*` (rule), the goAML XSD (no FIU schema), the GCS backend at runtime, and production state.
- Not checked: the GitHub PR list (my connector was unavailable); I relied on `git log 0129848..origin/master` being empty and code-reviewer's statement that only #411 was touched.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-13/skeptic.md` and the eleven scripts in `repro_skeptic/` (the ten carried from 10-12 plus `docx_policy_upload.py`) on `routine/2026-10-13-skeptic`, based on master `0129848`. No existing file edited. The commit SHA is in the final reply (a file cannot contain its own SHA).
