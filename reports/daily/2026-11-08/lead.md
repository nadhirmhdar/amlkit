# Lead consolidated report: 2026-11-08

## 1. Headline: AMBER (improving)
Three merged PRs (#460-#462) fixed six open items: BD1, BD2, CR-40, sign-up enumeration by content (SS1), the 20-hour refresh gap (in the repo) and both public-copy overstatements. The suite is green at 2945 passed. Nothing new is above LOW. The open MEDIUMs are a feature gap (MU-CR1), the UAE PASS sandbox residual (CS-24) and the legal items, which still have no `corpus/`.

Master is `9219e2623b3a3ba7e73a20e44c703ab80df7e900` (`git ls-remote origin refs/heads/master`). Previous lead SHA was `6560fb0`. `git log 6560fb0..origin/master` shows #460 `fab52e2`, #461 `bbc035d` and #462 `9219e26`, all merged 2026-11-07. Run date 2026-11-08 UTC. All six role branches were present at the first fetch.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | AMBER. Full suite 2945 passed / 2 skipped. CR-40 fixed. CR-41 timing oracle (10 vs 114 ms), CR-42 mail flooding, CR-43 load from the 4-hourly rescreen not measured | suite + probe numbers | High (I reproduced CR-41) |
| qa-regression | done | GREEN. 2945 passed / 2 skipped (exit 0). Tenant sweeps 0 leaks, identical to before. HEAD middleware probe clean (token pages return 405 to HEAD) | pasted pytest line + sweep output | High |
| red-team | done | GREEN. SS1 and CI1 fixed, SS2 mostly fixed. New: SS1b timing (12 vs 76 ms), SS3b no mail cooldown, SS4 duplicate org names (Info), K2 (Info). All 40 reason-code combinations behave | probes + evidence files | High (I re-ran the timing myself). **Still lists N3b and H1 as open (sixth reminder; both refuted)** |
| compliance-specialist | done | AMBER. CS-5 fixed in the repo (deploy unverified), CS-25 closed, CS-24 partly closed. CS-13, CS-14 and 3.1 open. Suite 2945 passed. Legal corpus still BLOCKED | diff reading, suite | High on code; legal PLAUSIBLE |
| mlro-user | done | GREEN. All 38 earlier modes pass. BD1, BD2, MK1 and MK2 fixed. SU1 (Info): the invite path still says "already exists". CR1-3 unchanged | driver + JSON evidence | High |
| skeptic | done | GREEN. Confirms SS1b/CR-41 and SS3b/CR-42 (Low), CS-24 residual (Medium), CS-5 fixed but "invisible to CI". Of 14 scripts, 11 exit 1 (fixed) and 3 are by design | file:line + re-runs | High. Still carries N3b (wrong) |

## 3. Consolidated findings
CONFIRMED (lead) means I reproduced it today on `9219e26` with `repro_lead/checks_2026_11_08.py` or the earlier lead scripts (§5).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-129** (new) SS1b = CR-41: open sign-up timing oracle. Existing email returns at `cases/operators.py:120`, before `hash_password` (`:143`) | **LOW** | red-team, code-reviewer | CONFIRMED Low | **CONFIRMED**: median 71.6 ms (new) vs 12.2 ms (existing), pages identical after masking | HELD `scripts/proposals/2026-11-08-lead-signup-timing-uaepass-env-scheduler.md` §1 (diff + test). Fix before Stripe go-live |
| **L-130** (new) SS3b = CR-42: no per-address cooldown on the sign-up notice mail | LOW | red-team, code-reviewer | CONFIRMED Low | **CONFIRMED**: 12 sign-ups gave 12 notices to one address | HELD same §2 |
| **L-131** (new id; residual of L-118/CS-24) sandbox UAE PASS verifications look real: no `environment` column (`db.py:959-973`); button gated on `load_config() is not None` (`api/helpers.py:134`) | **MEDIUM** | compliance, skeptic | CONFIRMED Med | **CONFIRMED** (static) | HELD same §3 |
| **L-132** (new) CS-5 deploy: scheduler step `continue-on-error` (`source-canary.yml:570`); the `describe` at `:574` only checks that the job exists, nothing reads the schedule back | LOW (operational) | skeptic, compliance | Low pending live check | **CONFIRMED** | HELD same §4; **Nadhir: run `gcloud scheduler jobs describe amlkit-sanctions-refresh`** |
| L-133 INFO-8 "every 20h" / "> 20h" leftovers (`grant_scheduler_iam.sh:36`, `queries.py:1461,1502`) | INFO | compliance | — | CONFIRMED (grep) | HELD same §5 |
| SS4 duplicate org name allowed in open sign-up | INFO | red-team | Info, by design | Agree, by design | Carry, no action |
| K2 TA/adverse-media dispositions have no reason codes | INFO | red-team | Info, documented | Agree | Carry |
| SU1 invite path says "already exists" | INFO | mlro-user | by design | Agree. Needs a CLAUDE.md line (skeptic point 2) | Nadhir: keep or retire the invite door |
| CR-43 6x/day `rescreen_all` load not measured | INFO | code-reviewer | — | PLAUSIBLE (no measurement) | Carry; QA/code-reviewer to measure |
| L-124 MU-CR1 identity can't be corrected | MEDIUM | carried | Med | CONFIRMED again (`CR1 reproduces=True`) | HELD `2026-11-07-lead-billing-tier-customer-identity.md` §2; needs Nadhir |
| L-125 / L-126 MU-CR2 duplicate person / MU-CR3 case-sensitive refs | LOW-MED / LOW | carried | CONFIRMED | CONFIRMED again (3 rows; `['C-001','c-001']`) | HELD same §3-4 |
| L-127 BL1 unknown tier fails open | LOW | carried | Low | CONFIRMED again (`4th operator -> allowed`) | HELD same §1 |
| L-128 BL2 malformed items return 500 | INFO | carried | Info | Unchanged (red-team re-ran the probe: same) | HELD red-team proposal |
| L-116 SS2 unpaid org: `/screen` and `/feedback` stay open; scans return 402 | LOW | carried | product decision | Scans FIXED (red-team evidence: 3 scan routes 402). `/screen` 200 is a policy call | Nadhir (policy) |
| L-112 UBO1b, L-113 N8b | LOW | carried | Low | CONFIRMED again (3 suffix variants accepted; self-confirm accepted) | HELD / needs Nadhir |
| CS-13, CS-14, 3.1 AED 55,000 | MEDIUM (legal-dependent) | compliance | High/Med | Code CONFIRMED; legal PLAUSIBLE | Carry; need `corpus/` |
| L-117 SS3, CR-39, F2b, CR-34/SMTP, CR-35, I1, L-114, A1 residual, L-111, CR-4, CR-13, CR-18, CR-28, CR-29, PR5, K1, CS-4, FATF CS-1/6/7, E2-E5, F4, TA2/TA3, LN1, SE2, D1, CS-26 | as on 11-07 | various | as stated | Not touched by #460-#462 | Carry |
| N3b, H1 | — | red-team, skeptic still list them | | REFUTED again (`Cyrillic Ve for B -> HIT 1.0`; `Referrer-Policy='strict-origin-when-cross-origin'`) | Closed |
| **FIXED on master** | | | | | |
| L-120 BD1 disposition/reason-code pairs | — | — | agree | `BD1 reproduces=False (0/3 contradictory pairs accepted)` | **FIXED by PR #461** |
| L-121 BD2 empty bulk dismissal looked like success | — | — | agree | mlro-user retest (not re-run by me) | **FIXED by PR #461** |
| L-123 CS-5 20-hour refresh | — | — | agree | `schedule(s)=['0 */4 * * *']; gaps(h)=[4,4,4,4,4,4]` | **FIXED in repo by PR #461**; deploy unverified (L-132) |
| L-122 CR-40 EU token on PR runs | — | — | agree | `source-canary.yml:82,258` now `github.event_name != 'pull_request' && secrets.EU_FSF_TOKEN \|\| ''`. (My 11-05 script still prints True because it looks for a job-level `if:`. That heuristic is stale, not the code) | **FIXED by PR #462** |
| L-115 SS1 sign-up enumeration (content) | — | — | agree | `SS1 ... known email -> generic; known org name -> generic; reproduces=False` | **FIXED by PR #462**; timing residual L-129 |
| L-118 / L-119 public UAE PASS + freeze-scope copy (MK1/MK2, CS-25) | — | — | agree | `_uaepass_live()` (`public.py:39-44`); `landing.html:53` names UNSC + UAE Local Terrorist lists | **FIXED by PR #462**; in-product residual L-131 |

**Severity adjudication**
- L-129: code-reviewer and red-team both say LOW, the skeptic agrees, and so do I. It undoes part of the #462 content fix and must land before `STRIPE_SECRET_KEY` is set in production. It is not MEDIUM because it needs many timed requests at 5/min/IP and production SMTP adds noise. Two roles measured different gaps (64 vs 104 ms) on different machines. I measured 59 ms. The gap is real; its size depends on the machine.
- L-131: compliance and the skeptic say MEDIUM. I agree. An operator on a sandbox deployment can file a "verification" that an inspector would read as a CDD check, and production currently runs against staging (#378).
- L-132: the skeptic downgraded CS-5 to LOW pending a live check. I keep the code item closed and open L-132 as the operational residual, because the repo cannot show the job's state.
- Duplicates merged: SS1b=CR-41, SS3b=CR-42, CS-5 deploy=skeptic point 3. No severity disagreements today.

## 4. Combined assessment
1. No regression: three independent full-suite runs on `9219e26` each report 2945 passed, 2 skipped, and the tenant sweeps are unchanged.
2. The WP-29/WP-30 fix wave closed six lead items. Every role's retest agrees.
3. The open-sign-up residuals (L-129, L-130) are small. Fix them before Stripe goes live.
4. The open MEDIUMs are now a feature (MU-CR1), one schema/UI addition (L-131) and the legal questions (CS-13/14/3.1). None is a regression.
5. The one fact no session can check: whether production's refresh job is actually on `0 */4 * * *`.

## 5. Corrections I made
- **Owed from 11-07 "Next run":** re-ran `checks_2026_11_07.py`, `_05`, `_04` and `_03` on `9219e26` (copied into `repro_lead/` from their lead branches, run, then removed and not re-committed). Scratch venv, Python 3.11.18, `requirements.txt` + `requirements-dev.txt`, `PYTHONPATH=.`:
  ```
  BL1  reproduces=True  CR1 reproduces=True  CR2 reproduces=True  CR3 reproduces=True
  4/4 reproduce   exit=0                                  (checks_2026_11_07.py)
  BD1  reproduces=False (0/3 contradictory pairs accepted)
  CR40 reproduces=True   <- stale heuristic, see L-122 row; code is fixed
  CS5  refresh schedule(s)=['0 */4 * * *']; fires at UTC hours [0, 4, 8, 12, 16, 20]; gaps(h)=[4, 4, 4, 4, 4, 4]
  CS5  reproduces=False
  1/3 reproduce   exit=0                                  (checks_2026_11_05.py)
  SS1  first signup ok=True; known email -> generic; unknown email -> Check your email; known org name -> generic
  SS1  reproduces=False
  then AttributeError at line 71 (exit=1): #462 no longer shows the verify link on screen,
  so the SS2 half of the script can't log in. SS2 is covered by red-team's
  probe_unpaid_gate_on_9219e26.txt instead       (checks_2026_11_04.py)
  UBO1b reproduces=True (3 suffix variants accepted); N8b reproduces=True
  N3b true homoglyph: Cyrillic Ve for B -> HIT 1.0; H1 Referrer-Policy='strict-origin-when-cross-origin'
  2/2 reproduce   exit=0                                  (checks_2026_11_03.py)
  ```
- **Created `repro_lead/checks_2026_11_08.py`** (temp DB, dummy Stripe key, mail send counted in-process, no network). Output on `9219e26`:
  ```
  SS1b  12 pairs: median new-email 71.6 ms vs existing-email 12.2 ms; pages identical after masking=True
  SS1b  reproduces=True
  SS3b  existing-account notices sent to victim@alpha.ae over 12 sign-ups: 12
  SS3b  reproduces=True
  CS24  uaepass_verifications columns=[..., 'user_type', 'verified_at', 'verified_by']; env column=False
  CS24  in-product button gate: uaepass_enabled = uaepass.load_config() is not None
  CS24  reproduces=True
  CS5d  refresh step continue-on-error=True; any 'scheduler jobs describe' read-back=False
  CS5d  reproduces=True
  4/4 reproduce
  exit=0
  ```
  (The first draft of the CS5d check counted the existence-only `describe` at `:574` as a read-back. I tightened it to require `--format ... schedule` before relying on it.)
- **Created `scripts/proposals/2026-11-08-lead-signup-timing-uaepass-env-scheduler.md`** (HELD). It has diffs for L-129 (hash before the branch, plus a test), L-130 (a 1-hour per-address cooldown via `audit_log`), L-131 (an `environment` column and a sandbox badge), L-132 (a read-back step that warns) and INFO-8. Not applied, because each touches business logic, schema or the deploy workflow (rule 3).
- No tests added to `tests/`, because each would fail on master. No existing file edited. The secret scan of the new files is clean. The commit SHA is in the final reply.
- I did not re-run the full suite, because three roles ran it independently with the same result. I did not re-run the mlro-user driver.

## 6. Decisions needed from Nadhir
1. **Production check (one command):** confirm `amlkit-sanctions-refresh` shows `0 */4 * * *`. If not, the CS-5 fix is not live. Approve the L-132 read-back step.
2. **Before Stripe go-live:** approve L-129 (hash before the branch; optionally move mail to a background task) and L-130 (per-address cooldown).
3. **L-131:** approve recording the UAE PASS environment on each verification and badging sandbox rows on the case file, or hiding the CDD button outside production.
4. **SU1 / skeptic point 2:** keep the invite-gated sign-up door (which still says "already exists" to code holders), or retire it once Stripe is on. Record the answer in CLAUDE.md.
5. **L-116:** may an unpaid org keep using ad-hoc `/screen` and `/feedback`? (Scans are now refused.)
6. Carried from 11-07: MU-CR1 design and four-eyes, MU-CR2/CR3, BL1 tier validation and the unknown-plan default, the L-113 production backfill, L-112, CS-13/CS-14/3.1 (need `corpus/`), F2b, production SMTP, L-111, CR-29, PR5, K1, CR-4/#417, the FATF snapshot, the `github-advanced-security` 402 quota.

## 7. Next run: carried over
- From the repo root with `PYTHONPATH=.`, re-run `repro_lead/checks_2026_11_08.py` (this branch), `checks_2026_11_07.py` and `checks_2026_11_03.py` (from their lead branches). Exit 1 means every item in that script is fixed. Retire `checks_2026_11_04.py` and `_05.py`: their items are fixed and their CR40/SS2 heuristics are stale.
- Owed by the lead: none.
- For the roles: red-team and skeptic, drop N3b/H1 (sixth reminder). Code-reviewer or QA, measure CR-43 (`rescreen_all` six times a day on the single writer). mlro-user, the Stripe-mode sign-up walk, plus duplicate and case checks through mobile onboarding. Compliance, whether a customer-data correction (MU-CR1) needs second-person approval, once `corpus/` exists.
- Landing order: L-129 + L-130 (before Stripe), L-132 + the production check, L-131, L-124 MU-CR1 (after the design decision), L-127 BL1, L-125/L-126, L-113 (ops), L-116 policy, L-112, CS-13 (after the legal answer), L-117, L-111, F2b, INFO-8.
