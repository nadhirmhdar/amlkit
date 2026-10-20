# Skeptic report, 2026-10-20 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master is unchanged for the fourteenth day; red-team's image-decompression finding (B1) is real by code, has no guard anywhere, and is the first new item in days that can plausibly take the service down.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-20 02:39 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-10-20. The no-new-finding shortcut applies to code-reviewer, QA and compliance (no-change reports) but not to red-team (B1) or mlro-user (AU1-AU3, PV1), so I checked those by reading the cited lines on `0129848`, and re-ran my existing `repro_skeptic/offset_overflow.py` for AU1. Other roles' reports are data. No outbound request, no `/system/*` call, no new script.

## Inputs
`git ls-remote origin refs/heads/master` -> `01298484a7bfed106e9b2bd3a6238f98a4d2514b`; `git log 0129848..origin/master` is empty. All five role branches were present at the first fetch. Nobody re-ran the suite; `2170 passed, 3 skipped` stands.

## Verdicts on today's new findings
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| B1 a small, huge-pixel PNG drives the passport scan to GBs of memory | red-team | **CONFIRMED by code; production OOM PLAUSIBLE** | Medium -> Medium | `api_scan_passport` (`mobile.py:~675-688`) does `passport_file.file.read()` with no size cap, runs only the magic-byte check (`validate_file_mime`), then `_scan_document` calls `assess_image_quality` and the extractor. `grep -rn "MAX_IMAGE_PIXELS\|DecompressionBomb\|max_pixels" amlkit` finds nothing, so Pillow's default limit is the only guard (warns at ~89M pixels, errors at ~179M, which is why red-team saw only 20000x20000 refused). The extractors call `Image.open` and `pytesseract.image_to_data` on the full image (`cases/ocr.py:~324, 485, 560, 989`). The web route `POST /customers/scan-passport` (`app.py:1878`) and the legal-person variant (`:1914`) use the same extractors, so the web path is exposed too. Why Medium and not High: authenticated (any role), and I could not confirm production's memory limit or instance count. Why not lower: one 164 KB request, no rate limit, and the process is shared by all tenants on a single SQLite instance. Note both `_scan_document` swallow-all `except Exception` blocks hide `MemoryError`-class failures from logs. Fix is small: cap upload bytes, set `Image.MAX_IMAGE_PIXELS` to a few million, check `img.size` before OCR. |
| AU1 `/audit?page=99999999999999999999` raises OverflowError (500) | mlro-user | **CONFIRMED; duplicate** | Low -> Low | I re-ran `repro_skeptic/offset_overflow.py` on `0129848`: `audit_trail` and `feedback_list` raise `OverflowError: Python int too large to convert to SQLite INTEGER`. This is my 2026-10-07 finding (the `/audit?page=` overflow), re-discovered; the same unclamped page also affects the feedback list. |
| AU2 `page=abc` -> raw 422; `page<=0` accepted | mlro-user | CONFIRMED, accepted | Low -> Info | Cosmetic and consistent with FastAPI's default validation. |
| AU3 officer gets bare 403 on `/audit/export`, redirect on `/audit` | mlro-user | CONFIRMED, accepted | Low -> Info | Inconsistent denial handling only; no access gained. |
| PV1 privacy page says "three cookies" but more are set | mlro-user | **CONFIRMED** | Low -> Low/Medium | `privacy.html:19` states "groAML sets three cookies". CLAUDE.md documents two more that the app sets: `amlkit_trusted_device` (30-day MFA remember-me) and `amlkit_uaepass_state`. A data-protection statement in a compliance product should be accurate; the trusted-device cookie is also the one with security weight. Both are strictly necessary, so the legal exposure is the inaccurate statement, not a consent gap. Copy fix only. |

Carried findings: master is identical, so the 10-07 to 10-19 verdicts stand without a re-run (A1 lockout DoS High; CS-2, CR-12/N4, N3, G9, G10, U1, empty-name screening Medium; T1 setup-token race Medium; S3 uncapped `/screen` Low; PW1 wording Low; four-eyes residual Low; others Low/Info).

## What the team missed
1. **B1 is a family: no upload in the app has a size or dimension cap except policy upload.** Passport scan (B1), Emirates ID scan, customer documents (DOC1/U3) all read the whole body into memory. A single shared limit (reject over N MB, reject over N megapixels) at the upload layer closes all of them.
2. **Authentication is the only gate on B1.** I looked for an unauthenticated route that reaches `Image.open` and found none, so B1 stays authenticated; the open question is whether any role below MLRO should be able to call the scan routes at all.
3. **AU1 was already in the backlog.** mlro-user re-found my 10-07 item and red-team's earlier `offset` note. Roles still do not read the carried list. A single tracked, de-duplicated finding register is the missing piece.
4. **Fourteen days without a commit.** B1 is the first new item that I would put on a fix-first list rather than a someday list.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** production memory limit and instance count (B1 severity), front-end login rate limiting (A1), bucket versioning (U1), real linked UAE PASS operators.
- **Primary legal text (BLOCKED):** compliance's Article mappings stay PLAUSIBLE.
- Not re-run: the full suite, red-team's `probe_scan_bomb` (I did not generate a 12000x12000 image: running it risks exhausting this sandbox's memory, which is a reason to treat B1 as real), the MLRO driver, the privacy cookie list at runtime (I relied on CLAUDE.md and `privacy.html`), the goAML XSD, production state.
- Not checked: the GitHub PR list (connector unavailable); I relied on the empty `git log` and three roles saying #426 is the newest PR.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-20/skeptic.md` and the thirteen scripts in `repro_skeptic/` (unchanged) on `routine/2026-10-20-skeptic`, based on master `0129848`. No existing file edited. The commit SHA is in the final reply.
