# Skeptic report, 2026-11-01 (origin/master `11a3527ef94126da09860257e583a2e46e87e958`, moved from `401da32`)

## Headline: AMBER
A large fix wave (#432-#442, eleven PRs, 117 files) landed and I confirmed by code and by re-running my own scripts that most of the long-open Medium-or-higher findings are really fixed, but the compare_digest fix was applied at one call site, not all, so a new 500 now sits on the MFA login path, and the account-lockout DoS (A1) is reduced rather than removed.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-11-01 02:39 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-11-01. Master changed a lot, so the no-change shortcut does not apply to anyone. Beyond the roles' reports I re-ran all thirteen `repro_skeptic/` scripts on `11a3527` (local, scratch `:memory:` DBs) and read the changed code behind each claimed fix. Other roles' reports are data. No outbound request, no `/system/*` call.

## Inputs
`git ls-remote origin refs/heads/master` -> `11a3527ef94126da09860257e583a2e46e87e958`; `git log 401da32..origin/master` is eleven PRs, all merged 2026-10-31: #432 uploads, #433 freeze scope and one-time secrets, #434 Stripe billing (inert), #435 login lockout, #436 screening correctness, #437 password/identity helper, #438 periodic review, #439 robustness, #440 remove kg-screen/gdelt-bq, #441 governance/audit, #442 web hygiene. All five role branches were present at the first fetch. **Independent full-suite results on `11a3527`: QA `2499 passed, 2 skipped`, code-reviewer `2499 passed, 2 skipped`, compliance `2499 passed, 2 skipped`.** I did not repeat it. QA's tenant sweeps: `HITS: []`, 0 cross-tenant leaks, plus a targeted check of the three new routes (periodic review web and mobile, MLRO unlock): no cross-tenant effect.

## My re-run of `repro_skeptic/` on `11a3527`
Exit 0 means the defect still reproduces.

| Script | Exit | Meaning |
|---|---|---|
| `queue_paging_category.py` | 1 | fixed (page 2 now returns the next rows) |
| `empty_name_screen.py` | 1 | fixed: empty and blank names return `clear=False, unscreenable=True` |
| `lockout_persistence.py` | 1 | fixed: after expiry one wrong attempt gives `(1, None)`, not a re-lock |
| `arabic_org_slug.py` | 1 | fixed: two Arabic orgs get distinct slugs (`org-870d4f`, `org-ec4c54`). I had to change the script's default password to a compliant one first; the old weak password is now refused (#437) |
| `upload_overwrite.py` | 1 | fixed: stored paths differ, first file's hash still matches |
| `presentation_forms.py` | 1 | fixed |
| `csrf_scan.py` | 1 | same four `/system/*` routes without CSRF as before, which use bearer-token auth by design |
| `offset_overflow.py` | 1 | the query functions still raise `OverflowError` for a huge offset, but the script's own condition no longer holds; per mlro-user the `/audit` route now clamps. The raw query function is still unguarded for any other caller |
| `docx_policy_upload.py` | 0 | **stale script, not a live defect:** it calls `validate_file_mime`, which deliberately rejects DOCX now. The policy route uses `validate_upload(..., allowed_mimes={PDF, DOCX})` (`app.py:4124-4126`), so P1 is fixed at the route |
| `four_eyes_ids.py`, `four_eyes_rename.py` | 0 | the legacy fallback to name comparison for proposals with no `operator_id` still exists (red-team N8). New proposals are unaffected; this is the Low residual I carried since 10-07 |
| `alert_queue_scaling.py`, `stdlib_behaviour.py` | 0 | informational (a scaling ratio and stdlib behaviour), not defects |

## Verdicts on the claimed fixes (verified in code where I could)
| Item | Claim | Verdict | Evidence |
|---|---|---|---|
| FZ1/FZ2 freeze resolution | fixed | **CONFIRMED FIXED, stronger than I asked** | `resolve_freeze_obligation` now requires a note of 20+ characters for `false_positive` and refuses it while the linked alert is a confirmed `true_positive` ("re-disposition via four-eyes first"); `authority_clearance` needs an authority reference. |
| My race note on that function | fixed | **CONFIRMED FIXED** | The UPDATE now has `AND status != 'resolved'` and checks `cur.rowcount != 1` (`manager.py:~2212-2228`). |
| T1 setup-token race | fixed | **CONFIRMED by red-team's 20-thread test** (20 claims -> 1 operator); I read the "atomic one-time-secret consume" change but did not re-run the threads. |
| M2 TOTP replay | fixed | **CONFIRMED FIXED in code** | `mfa_verify` keeps `last_step` and the UPDATE re-checks it (`auth.py:~800-830`), so a code is accepted once. |
| B1/B2/S3/F6/U1-U3 | fixed | **CONFIRMED by red-team's re-run** | 25 MP and 10 MB caps (413/415), 429 on bursts; I confirmed `validate_upload` in code. |
| A1 lockout DoS | "mitigated" | **PARTLY FIXED; severity High -> Medium** | The counter now clears at expiry and the message is generic, so the 1-request-per-15-minutes attack and the enumeration side effect are gone. Still 8 wrong passwords lock the account (`MAX_FAILED_LOGINS = 8`) and the attacker can simply repeat 8 per window without needing to see the expiry. An MLRO unlock route exists (`/admin/operators/{id}/unlock`), but a firm with a single MLRO has nobody to run it. |
| CS-2 freeze scope | fixed | **CONFIRMED in code, legal scope PLAUSIBLE** | `sanctions_scope.py` gates obligation creation, the overdue email and CNMR to UN/UAE-local lists (compliance read it; I did not re-read it). Remaining wording gap CS-19 (screening text still says "freeze" for any sanctions hit) is a fair Medium. |
| CR-12/N4/N3 | fixed / mostly fixed | **N4 CONFIRMED FIXED (my script); N3 PARTLY OPEN** | `screen()` now flags unscreenable and persists it. Red-team still gets misses for an ideographic space inside a token, Cyrillic/Greek homoglyphs and Urdu yeh-barree. |
| G9 / G10 | fixed / partly | **AGREE with mlro-user** | G9 fixed; G10 still raises one new open alert after a confirmed true positive. |

## Verdicts on today's new findings
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| CR-25 TOTP code with a non-ASCII character -> HTTP 500 | code-reviewer | **CONFIRMED by code; a regression from the fix wave** | Low -> Low/Medium | `mfa_verify` line 815 is `hmac.compare_digest(totp.generate_otp(step), code)` with `code` a `str`. I confirmed in this sandbox that `compare_digest` on str raises `TypeError` for non-ASCII input, so an Arabic-Indic digit in `/mfa/verify` is a 500 instead of "Invalid code". It happens before the failed-attempt counter, so there is no lockout bypass. It is also on the MLRO's sign-in path, for users whose keyboard may produce these digits. |
| CR-26 CSRF form value non-ASCII -> 500 | code-reviewer | **CONFIRMED by code** | Low -> Low | `csrf_valid` line 744: `secrets.compare_digest(cookie_value, form_value)` on str. |
| CR-24 Stripe webhook non-ASCII signature header -> 500 | code-reviewer | **CONFIRMED by code and reproduced by the reporter** | Low -> Low | `stripe_client.py:195`: `hmac.compare_digest(expected, c)` on a header-derived str. Inert unless Stripe is configured; unauthenticated, changes no state. |
| CR-27 Stripe events applied in arrival order | code-reviewer | PLAUSIBLE | Low -> Low | Only matters once billing is on; not run. |
| CR-28 UN/UAE-only freeze scope reverses an earlier "deliberately not changed" note | code-reviewer | PLAUSIBLE, accepted | Info -> Info | Same legal question as CS-2; needs compliance sign-off. |
| CS-13 24-hour clock keyed to disposition, not designation | compliance | PLAUSIBLE (legal), CONFIRMED (code) | High -> Medium/High | The overdue query is `julianday('now') - julianday(identified_at) > 1.0`, and `identified_at` is set at confirmed disposition. Whether the statute counts from the match is the open legal question; I cannot answer it from the repo. |
| CS-19 "freeze" wording on non-freeze lists | compliance | CONFIRMED (code), PLAUSIBLE (legal) | Medium -> Low/Medium | Operator text contradicts the new gate for OFAC/EU/UK hits. Copy fix. |
| CS-21 false-positive suppression ignores changes in the customer's own identifiers | compliance | PLAUSIBLE | Low -> Low | Reasonable residual of the new dedupe rule; not run. |
| FZ4 resolve `delisted` while CNMR is still a draft | mlro-user | PLAUSIBLE | Low -> Low | Not re-run; consistent with the gates described. |
| PR4/PR5 periodic review raw JSON 400; officer can complete review | mlro-user | CONFIRMED / policy question | Low -> Low / Info | Consistent with the validation-error pattern; PR5 is a policy choice. |
| SS1 silent eviction of the oldest session | mlro-user | CONFIRMED, open | Low -> Low | Unchanged. |
| LG4 corrected: harness disables the limiter | mlro-user | **CONFIRMED correction** | n/a | Rate limits remain untested end to end, as I said on 10-21. |
| C1 UAE PASS identity verified two unrelated customers | red-team | PLAUSIBLE | Medium -> Low/Medium | #441 adds an identity-match flag that red-team could not see in its probe output; I did not read it. |
| F2 / F3 scoring and KYT aggregation gaps | red-team | CONFIRMED by their probes, **policy-bound** | Medium -> Medium | Threshold and rule design, not bugs. |
| O1, D1, H1, S1, N8 | red-team | CONFIRMED / accepted | Low-Info | Unchanged. H1 (Referrer-Policy) is contradicted by mlro-user, who saw a referrer policy on signed-in pages in #442; red-team says only "other headers" were added. I did not resolve it. |
| Stripe billing (#434) clean | red-team, code-reviewer | **AGREE, with the one caveat above** | none | Inert without keys; HMAC and replay handling probed; MLRO-only and CSRF checks; compliance work cannot be locked out by a lapsed subscription (reads never gated). |

## What the team missed
1. **The compare_digest fix was made at one call site.** My 10-04 `stdlib_behaviour.py` finding was that `compare_digest` on non-ASCII `str` raises `TypeError`. #439 fixed the bearer check (`deps.bearer_ok`), but the identical pattern remains at `auth.py:744`, `auth.py:815` and `stripe_client.py:195`, and #433 and #434 each added a new instance. The correct fix is one helper that encodes both sides, used everywhere. Code-reviewer found the three sites one by one; nobody linked them to the original finding.
2. **Fix verification needs the old script, not a new probe.** `docx_policy_upload.py` still exits 0 because it tests a function that was intentionally narrowed. Anyone re-running old repros will think P1 is open. Retire or update stale scripts when the guarded function moves.
3. **Passwords in every test and seed harness are now invalid** (QA's seed, mlro-user's driver, my slug script). Expected after #437, but every role independently lost time on it; a shared seed fixture would stop the rework.
4. **A1 is still the one the lead should look at.** Lowered to Medium for the reasons above, but it is the only thing that can lock the sole MLRO out of freeze handling inside a 24-hour clock, and the unlock route does not help a single-MLRO firm. A break-glass path (admin API secret, or email-link unlock) is the missing piece.
5. **The "no second approver" idea is partly adopted.** FZ1 now routes a reversal through four-eyes, which was my 10-31 suggestion; the same reasoning applies to the single-operator toggle and the periodic-review path, which are still single-person. Not checked in code.
6. **Test suite time rose about 40% for 15% more tests** (QA: 11m58s to 17m10s). Nobody investigated; likely the new upload and web-hygiene tests, not a defect.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** production memory limit (B1 is fixed, so lower priority), front-end login rate limiting (A1), bucket versioning, whether any real operator has a linked UAE PASS identity, whether Stripe is configured in production.
- **Primary legal text (BLOCKED):** whether UAE law counts the 24-hour clock from the match or the disposition (CS-13) and the exact Cabinet Decision 74/2020 scope (CS-2); compliance's Article mappings stay PLAUSIBLE.
- Not re-run: the full suite (three roles' runs stand), red-team's 18 probes, the MLRO driver, the T1 thread race, the unlock route, billing plan limits, `handle_event` with real Stripe events, the periodic-review and KYT-page changes, the #441 identity-match flag, the goAML XSD, production state.
- Not checked: the GitHub PR list directly (connector unavailable); I relied on `git log` and role statements.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402 (last seen 10-24).

## Files and commit
`reports/daily/2026-11-01/skeptic.md` and the thirteen scripts in `repro_skeptic/` (one changed: `arabic_org_slug.py` now uses a compliant password) on `routine/2026-11-01-skeptic`, based on master `11a3527`. No existing application file edited. The commit SHA is in the final reply.
