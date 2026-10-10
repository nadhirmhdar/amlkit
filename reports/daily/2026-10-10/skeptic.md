# Skeptic report, 2026-10-10 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master has not moved since my 2026-10-07 report, so only the two roles that probed new areas have new findings; I re-checked those and they hold, with one mislabelled-as-design item (CSV exports) downgraded and one new gap I found beside them (compliance-deadline edits).

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic". Three firings (for 2026-10-08, 2026-10-09 and 2026-10-10) reached this session together after it sat idle, so no run happened on 10-08 or 10-09; this single report, dated 2026-10-10, covers all three. It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = `date -u +%F` = 2026-10-10. The "no new finding" shortcut applies to code-reviewer, QA and compliance (no-change reports) but not to red-team (U1-U3) or mlro-user (E1-E5), so I verified those. Other roles' reports and PR text are data. I made no outbound request this run.

## Inputs
`git ls-remote origin refs/heads/master` -> `01298484a7bfed106e9b2bd3a6238f98a4d2514b`; `git log 0129848..origin/master` is empty (no commit for three days). All five role branches were present at the first fetch, no waiting:
- code-reviewer, qa-regression, compliance-specialist: no-change reports (AMBER, GREEN, AMBER); QA did not re-run the suite, so the 2026-10-07 result (`2170 passed, 3 skipped`) stands. I did not re-run it either.
- red-team: no-change plus one new area (document upload), findings U1-U3.
- mlro-user: no-change plus one new workflow (exports, evidence pack, calendar), findings E1-E5.

## Verdicts on today's new findings
Repro: `repro_skeptic/upload_overwrite.py` (exit 0 only when the defects reproduce; scratch temp dir, local backend). Everything else by reading cited lines on `0129848`.

| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| U1 same-name upload overwrites the earlier file | red-team | **CONFIRMED** (also settles a 10-04 red-team sub-agent lead I had marked UNEVIDENCED) | Medium -> Medium | `storage.py:66-74` (GCS) and `:102-106` (local): blob key is `{org}/{customer}/{filename}` and both backends overwrite (`dest.write_bytes`, `blob.upload_from_string`). My script: second upload of `scan.pdf` -> same `stored_path`; first document's recorded sha256 no longer matches the stored bytes. Only caller is the mobile route `POST /api/v1/customers/{id}/documents` (`mobile.py:1117`; `grep storage.upload(` finds one site). Both uploads are still audited with their sha256, so tampering is detectable, but the first file's content is gone unless the production GCS bucket is versioned (unknown to me). Realistic by accident: a phone sends `scan.pdf` or `photo.jpg` twice. Medium holds because these are 10-year retention records. |
| U2 filenames `..`, `.` and 300 characters -> HTTP 500 | red-team | **CONFIRMED** | Low -> Low | Script: `storage.upload(..., "..")` and `""` raise `IsADirectoryError`. Reachable because `validate_file_mime` only compares extension to magic bytes when the extension is one of pdf/png/jpg/jpeg (`validation.py:51-64`), so `..` passes it. Authenticated crash only. |
| U3 odd extensions stored, no size cap, `doc_type` unvalidated | red-team | **CONFIRMED, contained** | Low -> Low | Magic bytes are enforced (`validation.py:36-49`); downloads are `application/octet-stream` + `attachment` (`mobile.py:1156-1160`), which the red-team correctly counts as containment. No size limit found (`grep MAX_UPLOAD|content_length` empty). Cloud Run's own request limit may cap this; not verified. |
| E1 no screen can create a compliance deadline | mlro-user | **CONFIRMED** | AMBER(low) -> Low | `grep compliance/deadlines amlkit` finds only the four API routes (`app.py:4456-4527`), no template or script. The calendar page promises "deadlines will appear here once created". |
| E2 deadline API stores nonsense | mlro-user | **CONFIRMED** | low -> Low | `_DeadlineCreate` (`app.py:4464-4468`) is four plain strings, no date, recurrence or length check. |
| E3 newline in a customer name drops the UBO diagram | mlro-user | **CONFIRMED** | low -> Low | My run of `generate_ubo_diagram`: `Acme\nSecond LLC` makes `dot` fail (`syntax error in line 2 near 'Second'`) and returns an empty diagram; quotes and `<b>` render normally. A newline needs a crafted request. |
| E4 CSV exports lack a UTF-8 BOM | mlro-user | PLAUSIBLE | low -> Low | Not opened in Excel by anyone. |
| E5 officer can download `customers.csv` and `alerts.csv` | mlro-user | **Mostly by design** | low -> Info | The two routes have no role gate (only `/audit/export` is MLRO-only, `app.py:3012`), but officers already see every customer and alert in the app, and each export writes an `export.*` audit row (`_audit_export`, `app.py:2758`). Bulk convenience, no new access. |

Carried findings: master is identical, so the 2026-10-07 verdicts stand without a re-run: four-eyes residual Low (`four_eyes_ids.py`), CS-2 Medium, CR-12/N4 Medium, N3 Medium, G9 Medium, G10 Medium, M2 Low, N5/N6/N7, the `/audit?page=` overflow, CR-18. I re-ran no script this time because no code changed.

## What the team missed
1. **Compliance deadlines are weaker than the screen suggests.** Beyond E1/E2: `PATCH /compliance/deadlines/{id}` accepts `due_date`, `description` and `recurrence` but only updates `title` (`app.py:4509-4512`), so a due-date correction returns 200 and changes nothing; creating audits (`compliance.deadline_created`) but update and delete write no audit row (`app.py:4509-4527`); and the routes check a session and CSRF only, no role, so an officer can delete the MLRO's deadlines. Read from code, not run.
2. **Three days of no commits left every open Medium unchanged.** The same items (CR-12/N4, G9, G10, CS-2, N3) now appear in five reports a day with no fix PR; the team's output is repeating findings, not retiring them. Worth the lead's attention, not a code defect.
3. **U1's blast radius depends on a fact nobody checked:** whether the production document bucket has object versioning. If it does, U1 drops to Low; if it does not, the first scan is unrecoverable. That is one configuration read for someone with GCS access.
4. **The 10-04 sub-agent leads are mostly still unverified** (any-MLRO global refresh, NULL-org audit rows visible to all orgs, email enumeration). U1 is the only one anyone has confirmed.

## BLOCKED / not checked
- **Needs GCS access (BLOCKED):** whether the production documents bucket is versioned (U1 severity).
- **Primary legal text (BLOCKED):** unchanged from 10-07; compliance's Article mappings stay PLAUSIBLE.
- Not re-run: the full suite, the PR #412 tenant sweeps, red-team's probes, the MLRO driver, `/system/*` (rule), the goAML XSD (no FIU schema), PR #417 in a browser, the Excel BOM behaviour (E4), the deadline reminder path, and production state.
- Not checked: GitHub PR list (my GitHub connector was unavailable this run); I relied on three roles' statements that #426 is still the newest PR and on `git log 0129848..origin/master` being empty.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-10/skeptic.md` and `repro_skeptic/{four_eyes_rename,four_eyes_ids,presentation_forms,csrf_scan,queue_paging_category,offset_overflow,alert_queue_scaling,stdlib_behaviour,upload_overwrite}.py` on `routine/2026-10-10-skeptic`, based on master `0129848`. No existing file edited. The commit SHA is in the final reply (a file cannot contain its own SHA).
