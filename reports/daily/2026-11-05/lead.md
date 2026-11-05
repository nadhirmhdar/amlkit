# Lead consolidated report: 2026-11-05

## 1. Headline: AMBER
No regression, but the alert-disposition check accepts contradictory decisions: a PEP match can be closed as "false positive / confirmed match" with no narrative and no second review. Since #459 the CI workflow also hands a secret to pull-request runs, and sanctions lists are refreshed only twice a day, 20 hours apart. All 11-04 items are still open.

Master is `6560fb021f6ea2cadefcd6e60d67ee274d871e73` (`git ls-remote origin refs/heads/master`), the same SHA as the 11-04 lead report. No commit since. The roles compared against `c5da8aa` (their own last SHA), so they all reviewed #459, which I had already covered on 11-04. Because they raised new findings, this is a full report rather than "no change". Run date 2026-11-05 UTC. All six branches were present at the first fetch.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | GREEN. #459 read in full; `test_workflow_env.py` 2 passed. New: CR-40, the EU token is exposed to same-repo PR runs (LOW) | diff + file reading; full suite not re-run (no app change) | High (I reproduced CR-40) |
| qa-regression | done | GREEN. Full suite `2862 passed, 2 skipped` (996 s, Py 3.13); ID sweep `HITS: []`; list sweep 0 leaks over 73 routes; flaky test 30/30 | pasted counts, exit codes | High |
| red-team | done | AMBER. CI1 (= CR-40). SS2 extended: unpaid orgs also get the OCR scan routes and `/feedback`; customer and operator creation correctly refused (402 / redirect) | probe script + evidence file | High (I re-ran the probe; same output). **Still lists N3b and H1 as open, which have been refuted since 11-03 (fourth reminder)** |
| compliance-specialist | done | AMBER. CS-5: refresh cron `0 */20 * * *` fires at 00:00 and 20:00 UTC only. CS-26 stale `eu.py` docstring. CS-13/14/24/3.1 open | workflow file:line; Articles unverified | High on the workflow; legal PLAUSIBLE |
| mlro-user | done | AMBER. BD1: false_positive + `confirmed_match` accepted (MEDIUM). BD2: "Dismissed 0 alert(s)." shown as success (LOW). Four-eyes on bulk sanctions dismissals holds | driver + JSON evidence | High (I reproduced BD1) |
| skeptic | done | AMBER. Confirms CR-40, SS2, BD1 (lowers it to Low/Med), BD2 (Info); CS-5 PLAUSIBLE. 4 scripts re-run, unchanged | code file:line + script exits | High; still carries N3b (wrong) |

## 3. Consolidated findings
CONFIRMED (lead) means I reproduced it on `6560fb0` today (§5).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-120** (new) BD1: `_validate` (`cases/review.py:244-262`) never checks that the reason code fits the disposition | **MEDIUM** | mlro-user (Med), skeptic (Low/Med) | CONFIRMED | CONFIRMED: `role.pep false_positive + confirmed_match narrative=False -> accepted, awaiting_second_review=False`; `true_positive + different_dob -> accepted`; on a sanctions alert it goes to `pending_review` (four-eyes sees it) | HELD `scripts/proposals/2026-11-05-lead-disposition-pairs-ci-token-refresh.md` §1 |
| L-121 (new) BD2: bulk dismiss shows "Dismissed 0 alert(s)." as success | INFO | mlro-user (Low) | Info | PLAUSIBLE (mlro-user evidence; not re-run) | Optional, in the same proposal §1 |
| **L-122** (new) CR-40/CI1: `source-canary.yml` runs on `pull_request` (:33); `sources` (:61) and `heartbeat` (:237) have no job `if:`, and their steps get `secrets.EU_FSF_TOKEN` (:81, :257) | **LOW** | code-reviewer, red-team, skeptic | Low | CONFIRMED: `workflow triggers on pull_request=True; jobs with EU_FSF_TOKEN and no job-level if: ['sources', 'heartbeat']` | HELD same proposal §2 |
| **L-123** (new) CS-5: sanctions refresh `--schedule "0 */20 * * *"` (:579, :591) fires at 00:00 and 20:00 UTC; the 24 h staleness alarm never fires on the 20 h gap; comments (`match/engine.py:368`, workflow :544) say "every 20 hours" | **MEDIUM** (legal-dependent) | compliance (Med), skeptic (PLAUSIBLE) | Med | CONFIRMED in the workflow: `fires at UTC hours [0, 20]; gaps(h)=[20, 4]`. Production scheduler state BLOCKED (no gcloud, by rule) | HELD same proposal §3 (`0 */4 * * *`) |
| L-116 SS2, now extended: an unpaid org also gets web + mobile passport and trade-licence OCR scans and `/feedback` | LOW | red-team (Low-Med), skeptic (Low), code-reviewer | Low | CONFIRMED (red-team probe re-run): scans `-> 200`, `/feedback -> 200`, `/screen -> 200`; customers `402`/`303`, 0 stored | HELD red-team `2026-11-04-new-findings.md`. **Needs Nadhir** (policy) |
| CS-26 stale `ingest/eu.py:8` docstring ("works out of the box"; the code raises without a token, :37) | INFO | compliance | — | CONFIRMED (grep) | Carry; fix it with the next `eu.py` touch |
| L-115 SS1 sign-up enumeration (Stripe mode) | MEDIUM | carried | Medium | CONFIRMED again (`known email -> already exists ... known org name -> similar name already exists`) | HELD; fix before `STRIPE_SECRET_KEY` is set in production |
| L-118 / L-119 UAE PASS and freeze-scope public copy | MEDIUM / LOW | carried | Med / Low | CONFIRMED again (`landing mentions 'sandbox'=False`; `is_uae_freeze_list('us_ofac_sdn')=False`) | HELD `2026-11-04-lead-public-claims.md` |
| L-112 UBO1b, L-113 N8b | LOW | carried | Low | CONFIRMED again (3 suffix variants accepted; legacy self-confirm accepted) | HELD / needs Nadhir |
| N3b, H1 | — | red-team, skeptic still list them | | REFUTED again (`Cyrillic Ve for B -> HIT 1.0`; `Referrer-Policy='strict-origin-when-cross-origin'`) | Closed |
| CS-13 (24 h clock from `identified_at`), CS-14 PNMR, 3.1 AED 55,000 | MEDIUM (legal-dependent) | compliance (CS-13 HIGH) | High/Med | CONFIRMED in code; legal PLAUSIBLE | Carry; need `corpus/` |
| L-117 SS3, CR-39, F2b, CR-34/SMTP, CR-35, I1, L-114, A1 residual, L-111, CR-4, CR-13, CR-18, CR-28, CR-29, PR5, K1, CS-4, FATF CS-1/6/7, E2-E5, F4, TA2/TA3, LN1, SE2, D1 | as on 11-04 | various | as stated | No commit since 11-04 | Carry |
| FIXED on master since the last report | — | — | — | none (no commits) | — |

**Severity adjudication**
- BD1: mlro-user says Medium; the skeptic says Low/Medium because "no control is bypassed, the data is wrong". I set **MEDIUM**. On a PEP alert the stored, acted-on status says *cleared* while the stored reason says *confirmed*. No narrative or second reviewer is required, so a supervisor cannot tell which one the officer meant, and EDD keys off the status. The sanctions path is covered by four-eyes (reproduced), which keeps this below HIGH. The fix is a small table.
- CR-40: all three roles say Low. I agree: the token reads a public feed, and fork PRs get no secrets. The pattern still matters because automated sessions push branches here every day.
- CS-5 and CS-13: I keep both at **MEDIUM**, read together as the skeptic suggests. Ingest lag (up to 20 h) plus the disposition time can exceed 24 h even when everything works. Whether that is a breach depends on when the clock starts (legal text not available). Compliance's HIGH for CS-13 still comes with no new evidence.
- SS2 extended: red-team says Low-Med, the skeptic Low. I keep **LOW**. Scans cost CPU but are limited to 10/min per operator. This is the same product decision as yesterday.
- Duplicates: CI1 = CR-40. Contradictions: none new. red-team and the skeptic still carry the refuted N3b/H1.

## 4. Combined assessment
1. No regression: QA's full run gives 2862 passed, 2 skipped on `6560fb0`; tenant sweeps are byte-identical to 11-04.
2. Nothing has landed since 11-04, so every HELD item (SS1, the public-copy fixes, UBO1b, N8b) still reproduces.
3. New and worth fixing: BD1 (a contradictory disposition record) and CS-5 (the refresh cadence vs the 24 h obligation). Both fixes are small.
4. CR-40 is a hygiene fix to the workflow and is worth adding to the workflow test.
5. The binding constraints are still Nadhir's decisions and the missing legal corpus, not engineering.

## 5. Corrections I made
- Owed from 11-04 "Next run": re-ran `repro_lead/checks_2026_11_04.py` and `checks_2026_11_03.py` (copied from their lead branches, not re-committed) on `6560fb0`. Scratch venv, Python 3.11.18, `requirements.txt` + `requirements-dev.txt`, `PYTHONPATH=.`:
  ```
  UBO1b reproduces=True (3 suffix variants accepted)
  N8b   ... confirm by op 1 -> accepted (proposer confirmed own legacy proposal) -> reproduces=True
  N3b   true homoglyph:  Cyrillic Ve for B -> HIT 1.0
  H1    GET /login Referrer-Policy='strict-origin-when-cross-origin' ...
  2/2 reproduce   exit=0          (checks_2026_11_03.py)
  SS1  reproduces=True
  SS2  org plan=none status=pending_payment; 5 x POST /screen -> [200, 200, 200, 200, 200]; screenings rows 0 -> 5; retention_until=2036-11-05
  SS2  reproduces=True
  2/2 reproduce   exit=0          (checks_2026_11_04.py)
  ```
- Re-ran red-team's `repro_redteam/probe_unpaid_gate.py` (not committed): output matches their evidence (customers `402`/`303`, 0 stored; scans, `/screen` and `/feedback` `200`). passporteye was installed, so the OCR routes ran.
- Created `repro_lead/checks_2026_11_05.py` (in-memory DB plus a read of the workflow file; no network). Output on `6560fb0`:
  ```
  BD1  role.pep  false_positive  + confirmed_match  narrative=False -> accepted -> alerts.status='false_positive' awaiting_second_review=False
  BD1  role.pep  true_positive   + different_dob    narrative=True  -> accepted -> alerts.status='true_positive' awaiting_second_review=False
  BD1  sanction  false_positive  + confirmed_match  narrative=False -> accepted -> alerts.status='pending_review' awaiting_second_review=True
  BD1  reproduces=True (3/3 contradictory pairs accepted)
  CR40 workflow triggers on pull_request=True; jobs with EU_FSF_TOKEN and no job-level if: ['sources', 'heartbeat']
  CR40 reproduces=True
  CS5  refresh schedule(s)=['0 */20 * * *']; fires at UTC hours [0, 20]; gaps(h)=[20, 4]
  CS5  reproduces=True
  3/3 reproduce
  exit=0
  ```
- Created `scripts/proposals/2026-11-05-lead-disposition-pairs-ci-token-refresh.md` (HELD). It has proposed diffs for BD1 (an allowed-pairs table in `review.py`), CR-40 (gate the token on `event_name`) and CS-5 (`0 */4 * * *`), plus tests. Not applied: each one edits existing logic or the deploy workflow (rule 3), and a workflow change on master would deploy.
- No tests added: a test for BD1, CR-40 or CS-5 would fail on master. No existing file edited. Secret scan of both new files: clean. The commit SHA is in the final reply.

## 6. Decisions needed from Nadhir
1. **L-120 BD1:** approve the reason-code/disposition table. Decide whether `insufficient_data` may close an alert as false positive.
2. **L-123 CS-5:** approve a 4-hourly (or 6-hourly) sanctions refresh; check refresh run time first. Confirm the production scheduler matches the workflow (`gcloud scheduler jobs describe amlkit-sanctions-refresh`; the routine cannot run it).
3. **L-122 CR-40:** approve gating `EU_FSF_TOKEN` off `pull_request` runs.
4. Carried from 11-04: L-115 SS1 before Stripe go-live (is `STRIPE_SECRET_KEY` set in production?); L-116 unpaid-org policy (now covers scans and feedback too); L-118/L-119 copy and `UAEPASS_ENV`; L-113 production backfill; L-112 UBO1b policy; CS-13/CS-14/3.1 need `corpus/`; F2b; production SMTP; L-111; CR-29, PR5, K1, CR-4/#417, the FATF snapshot, the `github-advanced-security` 402 quota.

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_11_05.py` (exit 1 = BD1, CR-40 and CS-5 all fixed), `checks_2026_11_04.py` (from `routine/2026-11-04-lead`) and `checks_2026_11_03.py` (from `routine/2026-11-03-lead`), from the repo root with `PYTHONPATH=.`.
- Owed by the lead: none.
- For the roles: red-team and skeptic, drop N3b/H1 (fourth reminder). mlro-user, a Stripe-mode pass is still not done. QA, the route-count floor in `repro/sweep.py`. Compliance, read CS-5 and CS-13 as one time budget.
- Landing order: L-115 (before Stripe), L-120 BD1, L-123 CS-5, L-118/L-119 copy, L-122 CR-40, L-113 (ops), L-116 policy, L-112, CS-13 (after the legal answer), L-117, L-111, F2b.
