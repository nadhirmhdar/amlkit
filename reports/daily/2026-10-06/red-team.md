# Red-team report, 2026-10-06 (origin/master `b7eeb2f32c6f3eae4f29420477189aaf11ea1d02`)

## Headline: AMBER
Master fixed the Arabic presentation-form/zero-width screening miss and the CSRF gap, but I found four new Medium-or-higher issues: more invisible-character screening bypasses, an "unscreenable" flag that is not enforced downstream, a CR/LF reference that silences the hourly freeze alert, and goAML finalise accepting XML-illegal characters. No cross-tenant path.

## Instructions I ran under
- Role (Nadhir's standing instructions): "Adversarial Red Team Operator (Agent 4)": probe AMLKit as a malicious actor (Arabic name matching, structuring, tenant isolation, UBO cycles, inputs that cause silent misses or crashes). Terse, evidence-first.
- Powers: read the repo, run code locally, commit and push to a branch. Never master. Local test data only; no production access, no `/system/*` calls, no secrets; additive-only (no application code edited, fixes only as proposals).
- This run: fired by the scheduled routine "groAML daily: red-team". Scope: code changed since my previous report (master `28e4b51`), then one not-checked area. Nothing in the routine conflicted with my standing instructions.
- Assumptions: probes ran on scratch DBs seeded by PR #412's `repro/make_seed.py`; the one extra process I started (a throw-away local SMTP sink on 127.0.0.1:2525) was stopped afterwards; severities are my judgement. I did NOT call any `/system/*` endpoint (reviewed `system_check_freeze_obligations` by reading it only).

## What I did
1. `git ls-remote` -> master `b7eeb2f`; previous report base `28e4b51`. Seven PRs merged since: #403 (adverse-media list), #419 (hourly freeze check endpoint), #420 (blog text), #423 (Windows test fixes, UTC retention dates), #424 (goAML reference, CSRF on org-profile/logout, export validation), #425 (Unicode normalisation of names + "unscreenable" flag), #418 (cleanup policy doc).
2. Re-tested the two fixes and tried to bypass them (`probe_unicode_bypass.py`, `probe_csrf_session.py`, `probe_logout_goaml.py`).
3. Probed the new surfaces: freeze-overdue alert path (`probe_freeze_alert_subject.py`, `probe_reference_crlf_web.py`), goAML export (`probe_goaml_ctrlchars.py`).
4. Re-ran PR #412 `sweep.py` and `sweep_lists.py` on `b7eeb2f`, plus every earlier probe to see what persists.
Evidence: `reports/daily/2026-10-06/evidence/*_on_b7eeb2f.txt`.

## Findings (new this run)
| Id | Sev | Status | Summary |
|----|-----|--------|---------|
| N3 | High | CONFIRMED | #425 `clean_name_text` removes only Unicode category Cf. An exact listed name still scores 0 (MISS) with VS16 U+FE0F, combining grapheme joiner U+034F, C0/DEL controls, Braille blank U+2800 or private-use U+E000 inside a token (`names/arabic.py`, `probe_unicode_bypass_on_b7eeb2f.txt`). ZWSP, soft hyphen, BOM and Arabic presentation forms now HIT. |
| N4 | Medium | CONFIRMED | `unscreenable` is only surfaced on the /screen page and mobile /screen. `add_ubo` still says "Beneficial owner added and screened clear" (`app.py:2302`), `onboard()` proceeds, the persisted screening is `hits=0 candidates=0 datasets_used=[]` with no marker, and `rescreen_all` returns `screened=1 alerts=0` (`probe_unicode_bypass_on_b7eeb2f.txt`, "downstream" section). Cyrillic-only, Chinese-only and Persian-only names all land here. |
| N5 | Medium | CONFIRMED | A customer reference containing CR/LF (accepted by `POST /customers`, `probe_reference_crlf_web_on_b7eeb2f.txt`) makes `mail.send_freeze_obligation_alert` raise `ValueError` (Subject header, `mail.py:283-284`, outside its try/except), so the hourly overdue check fails for that whole org. With a local SMTP sink: control = 3 of 3 obligations alerted; attack = 1 of 3, `failures=['t: Header values may not contain linefeed or carriage return characters']` (`probe_freeze_alert_subject_on_b7eeb2f.txt`). Requires SMTP configured; header injection itself is blocked (no Bcc reached the sink). |
| N6 | Medium | CONFIRMED | #424's finalise validation accepts XML-illegal characters: reports with `\x0b`, `\x00`, U+FFFE or U+D800 in a name were saved, submitted (`status=submitted`) and `/reports/{id}/export` returned 200 with non-well-formed XML (`probe_goaml_ctrlchars_on_b7eeb2f.txt`). Markup, entities and a 1 MB value stay well-formed; no file disclosure. |
| N7 | Low | PLAUSIBLE | `system_refresh` and `system_check_freeze_obligations` compare the bearer with `secrets.compare_digest(str, str)`; a non-ASCII Authorization value raises `TypeError` (shown in isolation: "comparing strings with non-ASCII characters is not supported"), so an unauthenticated request probably gets a 500 instead of 401. Not exercised against the endpoints (rule: no `/system/*` calls). |

## Status of earlier findings on `b7eeb2f`
- FIXED: F5 (`/admin/org-profile` CSRF): 0 of 48 POST routes change state without a valid token (`probe_csrf_session_on_b7eeb2f.txt`). New logout behaviour is correct: no/bad token keeps the session (303 `/`), valid token ends it (`probe_logout_goaml_on_b7eeb2f.txt`).
- PARTLY FIXED: F1 (presentation forms and Cf characters fixed; see N3 for what remains).
- STILL PRESENT, unchanged: F2 extra-token padding and country/gender/DOB-mismatch misses (`probe_e2e2`), F3 `rescreen_all` skips 24.99%/nominee/director owners (`probe_ubo`), F4 four-eyes rename bypass (`probe_csrf_session` section 1: `BRAVO-officer propose` then `Renamed Officer confirm`), F6-F9 and F12 KYT items (`probe_kyt`, `probe_cache`: stale threshold 200/200), F10 look-alike operator names (`probe_rename_authz`), F11 weak password in reset-password returns 500, N1 `offset` overflow on `/api/v1/alerts` (`probe_mobile_authz`), N2 threshold 0.0. F13/F14 not re-run (code unchanged).

## Refuted / clean
- Cross-tenant: PR #412 sweeps on `b7eeb2f` -> `HITS: []`; lists sweep 66 routes, B->A leaks 0 (control as A: 41 routes contain the marker). The new `/adverse-media` list (#403) is covered by that sweep; `status` is whitelisted in the route.
- `/api/v1`: no unauthenticated route, none reachable with an MFA-locked MLRO token, officer refused on the 7 MLRO-only routes (`probe_mobile_authz_on_b7eeb2f.txt`).
- goAML export: markup/entity payloads and a 1 MB value stay well-formed; no external-entity file read.
- `/system/check-freeze-obligations` (static read): disabled (403) when `SCHEDULER_SECRET` unset, bearer compare, per-org failure isolation; the "mark after SENT" logic is sound apart from N5/N7.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` fails on every push with a 402 quota error (account-level). Needs quota restored or the check made non-required.
- Not exercised by design: all `/system/*` endpoints (rule), production.
- Not checked: `Secure` cookie flag (local HTTP), MFA lockout/backup codes, UAE PASS flow (needs network), file-upload content handling, rate limiter (disabled locally), the sign-in canvas JS beyond the CSP test, the full pytest suite (about 11 minutes).

## Files and commit
Created: `repro_redteam/probe_unicode_bypass.py`, `probe_freeze_alert_subject.py`, `probe_reference_crlf_web.py`, `probe_logout_goaml.py`, `probe_goaml_ctrlchars.py`; `reports/daily/2026-10-06/red-team.md` and `evidence/`; `scripts/proposals/2026-10-06-new-findings.md` (HELD diffs). Earlier probes and proposals carried over unchanged. No application code edited. Branch `routine/2026-10-06-red-team`; commit SHA in the final reply.
