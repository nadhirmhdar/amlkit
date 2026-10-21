# Skeptic report, 2026-10-21 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master is unchanged for the fifteenth day; red-team's follow-up shows B1 (image decompression) is on every scan route and that the web scan route skips the file-type check entirely, and mlro-user's "new" login-lockout finding is my 10-11 A1 re-found, with a genuine enumeration side effect I had only half-noted.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-21 02:39 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-10-21. The no-new-finding shortcut applies to code-reviewer, QA and compliance (no-change reports) but not to red-team (B1 extended, B2) or mlro-user (LG1-LG4), so I checked those by reading the cited lines on `0129848`. Other roles' reports are data. No outbound request, no `/system/*` call, no new script.

## Inputs
`git ls-remote origin refs/heads/master` -> `01298484a7bfed106e9b2bd3a6238f98a4d2514b`; `git log 0129848..origin/master` is empty. All five role branches were present at the first fetch. Nobody re-ran the suite; `2170 passed, 3 skipped` stands.

## Verdicts on today's new findings
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| B1 (extended) image bomb on every scan route | red-team | **CONFIRMED by code; extends my 10-20 verdict** | Medium -> Medium | The web `customer_scan_passport` (`app.py:1878-1905`) reads the whole upload and hands it to `extract_passport_data` with no size, pixel or type check, exactly like the mobile route, and the Emirates ID and trade-licence variants follow the same shape. Still no `MAX_IMAGE_PIXELS` anywhere in `amlkit`. Production OOM remains PLAUSIBLE (unknown memory limit and instance count). One shared upload guard would close every scan route. |
| B2 web passport scan accepts arbitrary bytes | red-team | **CONFIRMED by code** | Low -> Low/Medium | The web handler (`app.py:1878-1905`) never calls `validate_file_mime`; the mobile twin does (`mobile.py:~675-688`). So the two front doors disagree on the same operation, which is the recurring inconsistent-validation shape (U2, DOCX, S3). Severity: authenticated, and the bytes only reach Pillow/OCR, but it removes the one cheap gate that might have rejected a non-image before decode. Note it also widens B1: a non-image payload with an image header avoids nothing, but junk reaches the decoders. |
| LG1 anyone knowing an email can lock the account | mlro-user | **CONFIRMED; duplicate of A1 (my 10-11 finding, High)** | Medium -> High | `MAX_FAILED_LOGINS = 8`, `LOCKOUT_MINUTES = 15` (`auth.py:71-72`), and `failed_login_count` is not reset at expiry (my `lockout_persistence.py`, 10-11), so one wrong attempt per 15 minutes keeps the account locked, not just "repeat when it expires". mlro-user's rating of Medium understates it for the same reason I raised it to High: the locked role can be the sole MLRO who executes freezes inside a 24-hour clock. |
| LG2 lock message enumerates real accounts | mlro-user | **CONFIRMED by code; a point I had missed** | Low -> Low | `login()` hashes a dummy value for unknown emails to defeat timing (`auth.py:~366-372`), which shows enumeration resistance was a design goal; but only a real row can reach the "Account locked ... Try again after HH:MM UTC" branch (`:376-382`). So after 8-9 attempts the response differs between real and unknown addresses, and it also names the exact time to attack again. Fix is in the same change as A1: neutral message, or the same message for both. |
| LG3 empty password -> raw 422 | mlro-user | CONFIRMED, accepted | Low -> Info | Cosmetic. |
| LG4 declared rate limits did not return 429 | mlro-user | **PLAUSIBLE, not a defect on this evidence** | unverified -> unverified | The test client shares one address and most likely runs with the limiter disabled or keyed away from the test traffic; I did not check. It cannot support or rebut A1 either way. It does mean no one has ever verified the limiter fires on `/login`. Worth a single targeted test, not a finding. |

Carried findings: master is identical, so the 10-07 to 10-20 verdicts stand without a re-run (A1 High; CS-2, CR-12/N4, N3, G9, G10, U1, empty-name screening, B1 Medium; T1 setup-token race Medium; S3, PW1, AU1 (my 10-07 item), PV1 Low; four-eyes residual Low; others Low/Info).

## What the team missed
1. **A1 fix should be one change with LG2.** The lock counter reset, the neutral message and the unlock path interact; fixing one alone leaves the others. I listed this on 10-12; three roles have now re-found parts of it separately.
2. **The scan routes are the one place where web and mobile diverge on validation in a way that matters for availability** (B2 plus B1). A single upload-validation function shared by `app.py` and `mobile.py` is the repeated recommendation: it would close B1, B2, S3-adjacent limits, U2, U3 and DOCX in one place.
3. **Nobody has tested that the rate limiter fires.** LG4 is a gap in the test suite, not in the roles: no test asserts a 429 on `/login`.
4. **Fifteen days without a commit.** Three days in a row now produce a new availability or lockout issue on top of a stable, unfixed backlog.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** production memory limit and instance count (B1), front-end login rate limiting (A1), bucket versioning (U1), real linked UAE PASS operators.
- **Primary legal text (BLOCKED):** compliance's Article mappings stay PLAUSIBLE.
- Not re-run: the full suite, red-team's `probe_scan_variants` (large images risk exhausting this sandbox), the MLRO driver, whether the limiter is enabled under the test client (LG4), the goAML XSD, production state.
- Not checked: the GitHub PR list (connector unavailable); I relied on the empty `git log` and three roles saying #426 is the newest PR.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-21/skeptic.md` and the thirteen scripts in `repro_skeptic/` (unchanged) on `routine/2026-10-21-skeptic`, based on master `0129848`. No existing file edited. The commit SHA is in the final reply.
