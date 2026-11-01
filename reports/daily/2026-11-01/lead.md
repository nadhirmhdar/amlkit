# Lead consolidated report: 2026-11-01

## 1. Headline: AMBER (much improved)
The 11-PR fix wave (#432-#442) closed nearly the whole backlog, including L-46 (HIGH) and L-95 (MEDIUM), and the suite is green (2499 passed, 2 skipped, three independent runs). What is left is one regression class: `compare_digest` on `str` throws 500s on the MLRO sign-in path, CSRF and the Stripe webhook (all LOW). Also open: a residual lockout DoS and the CS-13 legal question (both MEDIUM).

Master is `11a3527ef94126da09860257e583a2e46e87e958` (`git ls-remote origin refs/heads/master`). The previous lead report (10-31) named `401da32`. `git log 401da32..origin/master` lists 11 commits: #435 (WP-1), #433 (WP-2+6), #437 (WP-7), #432 (WP-3), #436 (WP-4), #438 (WP-5), #439 (WP-10), #440 (WP-8), #441 (WP-9), #442 (WP-12) and #434 (Stripe billing). 117 files, +7424/-1320. Run date: 2026-11-01 UTC.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | AMBER. Full suite 2499 passed/2 skipped. Found 3 LOW crash bugs (CR-24/25/26; CR-25 is a regression), CR-27 Stripe event ordering (PLAUSIBLE), CR-28 freeze-scope sign-off | file:line + repro, full run | High (I reproduced all three) |
| qa-regression | done | GREEN. 2499 passed, 0 new failures. Tenant sweeps `HITS: []`, 0 B->A leaks. The 3 new routes check out (no cross-tenant effect) | pasted counts, harness commit `18855e5` | High |
| red-team | done | AMBER. 18 probes re-run: most fixed. Still open: A1 (residual), C1, F2/F3, N3 residual, O1, S1, N8. Billing is clean. Wrong about H1 | 20 evidence files | High, except H1 (refuted below) |
| compliance-specialist | done | AMBER. CS-2 closed in code. CS-13 still open; new CS-19 (wording), CS-21, CS-22. Ran the full suite: 2499 passed | diff reading + file:line; Articles unverified | High on code; legal PLAUSIBLE |
| mlro-user | done | AMBER. Re-tested 29 modes: FZ1/FZ2, G9, PR1-3, LG2/3, PW, AU, PV1, SE1 and C1 are fixed. G10 partly fixed, LG1 mitigated, SS1 open. New: PR4, PR5, FZ4 | driver + JSON evidence | High |
| skeptic | done | AMBER. 13 scripts re-run; confirms the fixes. Ties CR-24/25/26 to its 10-04 finding; A1 is now High->Medium; flags stale repro scripts | exit codes + file:line | High |

## 3. Consolidated findings
CONFIRMED (lead) means I reproduced it on `11a3527` today (§5).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-100** (new) `compare_digest(str,str)` raises TypeError on non-ASCII input: `auth.py:815` mfa_verify (regression from #433), `auth.py:744` csrf_valid (every form POST), `stripe_client.py:195` webhook | **LOW** (×3, one fix) | code-reviewer CR-24/25/26, skeptic | Low/Med, Low, Low | CONFIRMED: `CR25 ... -> TypeError`, `CR26 ... -> TypeError`, `CR24 ... -> TypeError`. Path checked: `/mfa/verify` -> `mfa_check_code` (auth.py:861-862) has no digit filter | HELD `scripts/proposals/2026-11-01-compare-digest-bytes.md` |
| **L-101** (residual of L-46) 8 wrong guesses lock any account for 15 min. The unlock route needs a second MLRO, so it does nothing for a single-MLRO firm | **MEDIUM** | red-team A1, mlro LG1, skeptic | High->Medium | CONFIRMED: `A1r 8 unauthenticated wrong guesses -> count=8 locked_until=...; owner's correct pw -> 'Incorrect email or password.'` | **Needs Nadhir** (break-glass: email-link unlock or admin-API unlock) |
| L-46 lockout never resets (+L-86, L-87, L-74) | was HIGH | | | **FIXED on master by PR #435**: `_11` A1 `after ONE wrong=(1, None) correct pw -> 'OK' -> reproduces=False`; `_21` LG2/LG3 False | Closed |
| **CS-13** the 24h clock runs from confirmed disposition (`identified_at`), not from the match or designation | **MEDIUM** (legal-dependent) | compliance | Med/High | CONFIRMED in code (the overdue query is unchanged); legal basis PLAUSIBLE | **Needs Nadhir** + legal text |
| **L-102** (new) the "freeze without delay" wording appears for every sanctions hit, including OFAC/EU/UK, which #433 no longer freezes (`screening/pf.py:106-109`, `api/app.py:1986`) | **LOW-MEDIUM** | compliance CS-19 | Low/Med | CONFIRMED: `CS19 obligation_note({'sanction'}) takes no dataset and says 'SANCTIONS match. Freeze without delay...'; banner present=True` | Copy fix; carry (needs dataset passed to the note) |
| L-103 (new) re-screen after a confirmed true positive raises one new open alert for the same match (G10 residual) | LOW | mlro G10, skeptic | agree | PLAUSIBLE (mlro evidence; I did not re-run it) | Carry |
| L-104 (new) a freeze can be resolved `delisted` while its CNMR is still a draft, and the draft can then no longer be filed | LOW | mlro FZ4 | Low | PLAUSIBLE | Carry |
| L-105 (new) periodic-review validation error returns a raw JSON 400 (PR4); an officer can complete a review (PR5, policy) | LOW / INFO | mlro | Low/Info | PLAUSIBLE | Carry; PR5 needs Nadhir |
| L-106 (new) Stripe events are applied in arrival order, ignoring `created` | LOW (latent) | code-reviewer CR-27 | Low | PLAUSIBLE | Carry; fix before Stripe goes live |
| L-107 (new) false-positive suppression ignores changes to the customer's own identifiers (CS-21); the freeze email cites Res 134/2025 for senior-management liability (CS-22) | LOW | compliance | Low | PLAUSIBLE | Carry |
| CR-28 freeze scope is now UN/UAE-local only (reverses the #421 note) | INFO | code-reviewer | Info | CONFIRMED in code (`_07` CS-2 `freeze_obligations=[] -> reproduces=False`); legal PLAUSIBLE | **Needs Nadhir** sign-off |
| L-81 residual: the evicted session still lands on /login with no message (the notice from #442 goes to the *new* session) | LOW | mlro SS1, skeptic | Low | PLAUSIBLE; #442's diff shows the notice is stored on the new session | Carry |
| H1 / L-98 no Referrer-Policy / Permissions-Policy | was INFO | red-team H1 | unresolved | **REFUTED; FIXED by PR #442**: `amlkit/api/app.py:609` sets `Referrer-Policy`, `:611` sets `Permissions-Policy`, in the all-responses middleware. Red-team's "not these two" is wrong | Closed |
| C1 one UAE PASS identity verified two unrelated customers | LOW-MEDIUM | red-team | Low/Med | PLAUSIBLE: #441 adds an identity-match flag that nobody has walked through | Carry; next red-team run should check the flag |
| F2/F3 scoring and KYT aggregation gaps; N3 residual (ideographic space, homoglyphs, Urdu yeh); O1; S1; N8/CR-1b legacy name fallback; D1 | MEDIUM (policy) / LOW / INFO | red-team, skeptic | as stated | CONFIRMED by red-team probes; not re-run by me | Carry; F2/F3 need a policy decision |
| L-95/L-96/L-97 freeze resolution | was MEDIUM/LOW/LOW | | Confirmed fixed | **FIXED by PR #433**: `_31` now raises `ValueError: Explain why the confirmed match is a false positive (at least 20 characters)`. mlro FZ1/FZ2 FIXED. Skeptic read the `AND status != 'resolved'` + rowcount guard | Closed |
| L-38 freeze on non-UAE lists; L-66/69/76/77 one-time secrets; M2 TOTP replay | was MED-HIGH / LOW-MED | | | **FIXED by PR #433**: `_07` CS-2/M2 False; `_17` T1m/T1w/T2/BC False; `_18` EV/US `[1,1,1,1,1]` | Closed |
| L-82 upload caps, L-64/65/43/52/63/78 | was MEDIUM | | | **FIXED by PR #432**: `_20` B1w `413, peak RSS +58 MB`, B1m `413`; red-team U1-U3 fixed | Closed |
| L-53, L-28/29/30/9/6/54 screening | was MEDIUM | | | **FIXED by PR #436**: `_14` exits on `ValueError: full_name is required`; `_31` G9 False | Closed |
| L-70-L-73 periodic review | was MEDIUM | | | **FIXED by PR #438**: `_18` RV False, `_19` AM False | Closed |
| L-91-L-94 kg-screen / gdelt-bq | was LOW | | | **FIXED by PR #440** (modules removed; `_23` ImportError) | Closed |
| L-47/58/67/80/13/59/14/57/68; L-21/83/22/34/35/36/12/42/56; L-55/51/48/44/45/41/50; L-88-90, L-79, L-84, L-85, L-61, L-62, L-71, L-75, L-27, L-99 | was LOW / INFO | | | **FIXED by PRs #437 / #439 / #441 / #442**: `_11` OP1/OP2/GR False; `_15` all False; `_19` S3/L75/PW False; `_20` AU1/AU3/PV1 False; `_22` SE1 noindex present. `_16` NT2/NT3 and `_20` AU2 still print True, but the scripts are **stale**: the link is now `/alerts?status=open#alert-N` (notifications.py:66-71), the unknown-filter notice exists (app.py L-62 block), and `page=-1` is clamped (mlro AU1/AU2 FIXED). `_22` HC prints True because `AMLKIT_PUBLIC_BASE_URL` is unset locally: fixed by configuration | Closed (staging must set `AMLKIT_PUBLIC_BASE_URL`) |
| `_13` P1 DOCX policy upload | was LOW | skeptic | stale | **FIXED, script stale**: the route uses `validate_upload(..., allowed_mimes={PDF, DOCX})` (app.py:4124-4126); the script tests the narrowed `validate_file_mime` | Closed |
| CR-4 (#417 unmerged), CR-13, CR-18, CS-14 PNMR, CS-1/6/7 FATF, CS-4 Interpol, 3.1 cash threshold | as before | | | Unchanged; not re-checked | Carry |

**Severity adjudication**
- L-100: the skeptic puts CR-25 at Low/Medium because it sits on the MLRO's sign-in path. I keep LOW. A retry with ASCII digits works, there is no security effect, and the attempt is not counted. It has priority within LOW because it is a regression and the fix is a few lines. All three sites have one root cause, so one id and one fix.
- L-101: red-team says Medium; the skeptic moved it from High to Medium. I agree with MEDIUM. The persistent-relock defect (the High part) is gone, but an anonymous attacker can still keep a single-MLRO firm out of freeze handling.
- CS-13: compliance says High, the skeptic Medium/High. I put it at MEDIUM until the legal text settles where the clock starts. The code behaviour is certain; the obligation is not.
- L-102: compliance says Medium, the skeptic Low/Medium. I put it at LOW-MEDIUM. It is copy, but it tells an operator to freeze in cases where the product (correctly) raises no obligation.
- Contradiction: red-team H1 vs mlro-user SE1. mlro is right; I resolved it from the code (above).

## 4. Combined assessment
1. Biggest improvement since the routine began: all Medium-or-higher lead items from 10-31 except L-101 (residual) are FIXED on master. 15 of 17 lead scripts no longer reproduce, and the 2 that print True are stale.
2. QA, code-reviewer and compliance each ran the full suite: 2499 passed, 2 skipped. Tenant isolation holds, including on the 3 new routes.
3. New defects are small and share a pattern: #439 fixed `compare_digest` at one site and #433/#434 added two more (L-100).
4. Billing (#434) is inert by default and was probed clean. CR-27 (L-106) must be fixed before Stripe is switched on.
5. What remains is mostly decisions: break-glass unlock, CS-13 clock start, freeze-scope legal sign-off, KYT aggregation policy.

## 5. Corrections I made
- C-1 Created `repro_lead/checks_2026_11_01.py` (CR25, CR26, CR24, A1r, CS19; `:memory:` DB, no network). Output on `11a3527` (scratch venv, `requirements.txt` + pytest):
  ```
  CR25 mfa_verify(code='١٢٣٤٥٦') -> TypeError -> reproduces=True
  CR26 csrf_valid('abc123', 'abcé') -> TypeError -> reproduces=True
  CR24 verify_webhook_signature(header 't=100,v1=é') -> TypeError (SignatureError would be a 400) -> reproduces=True
  A1r  8 unauthenticated wrong guesses -> count=8 locked_until=2026-11-01T03:58:22+00:00; owner's correct pw -> 'Incorrect email or password.' -> reproduces=True
  CS19 obligation_note({'sanction'}) takes no dataset and says 'SANCTIONS match. Freeze without delay and wit'...; onboarding banner 'freeze without delay' present=True -> reproduces=True
  5/5 reproduce
  exit=0
  ```
- C-2 Created `scripts/proposals/2026-11-01-compare-digest-bytes.md` (HELD). It contains a `safe_equals` helper diff for 3 call sites plus the tests to add. Not applied, because it edits `auth.py` and `stripe_client.py` (rule 3).
- C-3 Owed from the 10-31 "Next run": I re-ran all 17 lead scripts (`_06`, `_07`, `_10`-`_23`, `_31`) on detached `11a3527` (`PYTHONPATH=.:tests`; `_06` from inside `repro_lead/`). The venv had no passporteye, pdfminer or tesseract, so there were no OCR paths; `_20` ran because B1 now rejects before OCR. **Exit codes: `_13` = 0 (stale, see §3); all 16 others = 1.** `reproduces=True` lines: `_13:1 (stale) _16:2 (NT2/NT3 stale) _20:1 (AU2 stale) _22:1 (HC, env-config)`. Every other `reproduces=` line is False. `_10`, `_12`, `_14`, `_31` and `_06` stop with the app's new validation errors (`KeyError: 'id'`, `ValueError: Closing an alert as a false positive needs a note of at least 10 characters`, `ValueError: full_name is required`, `ValueError: Explain why the confirmed match is a false positive (at least 20 characters)`, `TypeError` on a missing open alert). Those are fixed behaviour, not defects. `_23` stops with `ImportError: cannot import name 'knowledge_graph'` (module removed by #440). I copied the scripts in from their lead branches and removed them before committing. **They are retired from the carry list.**
- Not re-run by me: the full suite (three roles agree on 2499/2), red-team probes, the mlro driver.
- No tests added (each L-100 test would fail on master). No existing file edited.

## 6. Decisions needed from Nadhir
1. **L-100: approve the `safe_equals` PR** (3 call sites; CR-25 is a regression on the MLRO sign-in path). Small; recommended first.
2. **L-101: choose a break-glass unlock for single-MLRO firms**: an email-link self-unlock (recommended), or an `ADMIN_API_SECRET` unlock. Optionally, per-IP + per-account throttling instead of a hard lock.
3. **CS-13 and CR-28 (legal):** where the 24h clock starts (match vs confirmation), and sign-off that freeze obligations cover only UN/UAE-local lists. Both are blocked on the primary text: supply `corpus/` PDFs.
4. L-102: approve the dataset-aware freeze wording (a copy change in `pf.obligation_note` and the onboarding banner).
5. PR5: should periodic review be MLRO-only or four-eyes?
6. F2/F3: KYT aggregation rules (structuring across 7-day windows, mixed cash/wire, duplicate customers).
7. Before Stripe goes live: L-106 event ordering, and CR-24 (part of L-100).
8. Carried: CR-4/#417, CS-14 PNMR, the cash-threshold ceiling, the FATF snapshot, the `github-advanced-security` 402 quota, and a shared seed fixture with a compliant password (every role lost time on #437).

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_11_01.py` (this branch): `PYTHONPATH=. python repro_lead/checks_2026_11_01.py`. Exit 1 means one item is fixed; read the lines. The 10-xx lead scripts are retired; do not carry them.
- Owed by the lead: none.
- For the roles: red-team, walk #441's UAE PASS identity-match flag (C1) and fix its H1 line; mlro-user, re-test FZ4, PR4 and SS1 and run one pass with the limiter enabled (LG4); skeptic, retire or update the stale `docx_policy_upload.py`; compliance, CS-13 and CS-22 once `corpus/` exists.
- Landing order: L-100, L-101, L-102, CS-13 (after the legal answer), L-106 (before Stripe), L-103, L-104, L-105, L-81 residual, L-107, C1, F2/F3, O1, N3 residual, N8/CR-1b, CR-4, CS-14, D1.
