# Lead consolidated report: 2026-11-04

## 1. Headline: AMBER
Nothing regressed and the suite is green, but self-serve sign-up (#457) has two reproduced gaps that go live as soon as `STRIPE_SECRET_KEY` is set: the open form reveals which emails and firm names already have accounts (SS1), and unpaid orgs get unlimited stored screenings (SS2). The public pages also promise more than the product does (UAE PASS, freeze scope).

Master is `6560fb021f6ea2cadefcd6e60d67ee274d871e73` (`git ls-remote origin refs/heads/master`). The previous lead report named `938050f`. `git log 938050f..6560fb0`: `c2191e5` #457 (WP-26 public site, self-serve sign-up), `c5da8aa` #458 (WP-27 Stripe go-live wiring), `6560fb0` #459 (CI only: EU FSF token for the source-canary checks, +6 workflow lines, +22 test lines). All six roles reviewed `c5da8aa`. #459 landed after them; I checked it (§5). Run date 2026-11-04 UTC. All six role branches were present at the first fetch.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | GREEN. 2860 passed/2 skipped (Py 3.13). Ran the sign-up probe with a dummy key. CR-37 (free screening while unpaid), CR-38 (sign-up sends mail), CR-39 (keys in plain env vars), all INFO | full run + probe | High |
| qa-regression | done | GREEN. 2860/2 in 21 min. ID sweep `HITS: []`; list sweep over 73 routes, 0 B->A leaks; flaky test 30/30 | pasted counts, exit codes | High |
| red-team | done | AMBER. SS1 enumeration (Med), SS2 free screening (Low-Med), SS3 mail to any address (Low). HELD proposal | probe + evidence file | High on SS1/SS2 (I reproduced both). **Still lists N3b and H1 as open, which were refuted on 11-03; the probe was not fixed** |
| compliance-specialist | done | AMBER. Public-copy review: CS-24 UAE PASS claim (Med), CS-25 freeze scope (Low). N-7: MFA still forced. 2860/2 (Py 3.11). CS-13/CS-14/3.1 open | file:line + full run; Articles unverified | High on code; legal PLAUSIBLE |
| mlro-user | done | AMBER. All 34 driver modes exit 0. MK1 UAE PASS claim, MK2 freeze scope, MK3 no prices. Stripe mode not exercised | driver + evidence files | High |
| skeptic | done | AMBER. 14 scripts unchanged on Py 3.13. SS1 Medium, SS2 Low, MK1 Medium, MK2 Low. Adds the org-name leak and the web/mobile sign-up mismatch | code file:line + script exits | High; carries N3b as open (wrong) |

## 3. Consolidated findings
CONFIRMED (lead) means I reproduced it on `6560fb0` today with `repro_lead/checks_2026_11_04.py` or `checks_2026_11_03.py` (§5).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-115** (new) SS1: open sign-up says "An account with that email already exists" (`cases/operators.py:112`, shown by `routers/auth.py:347-351`) and "An organization with a similar name already exists" (`:47/53/94`). Stripe mode only | **MEDIUM** while Stripe is on; INFO in invite mode | red-team, skeptic | Medium | CONFIRMED: `known email -> already exists; unknown email -> Check your email; known org name -> similar name already exists` | HELD in red-team `scripts/proposals/2026-11-04-new-findings.md` (+ lead note on org name in `scripts/proposals/2026-11-04-lead-public-claims.md`). **Fix before setting `STRIPE_SECRET_KEY` in production** |
| **L-116** (new) SS2/CR-37: a `pending_payment` org can screen and store results | **LOW** | red-team, code-reviewer, skeptic (compliance: by design) | Low | CONFIRMED: `5 x POST /screen -> [200,200,200,200,200]; screenings rows 0 -> 5; retention_until=2036-11-04` | HELD (red-team proposal). **Needs Nadhir**: free taste or cap |
| L-117 (new) SS3/CR-38: verification mail to any address with a chosen name; 5/min/IP only; no cleanup of abandoned sign-ups | LOW | red-team, code-reviewer, skeptic | Low | PLAUSIBLE (red-team probe output; I did not re-run it) | HELD (red-team proposal) |
| **L-118** (new) MK1/CS-24: landing (`landing.html:45`) and `/aml-law` (`aml_law.html:26`) advertise UAE PASS verification; production uses the sandbox (CLAUDE.md, `uaepass.py:16`); rows do not record the environment | **MEDIUM** (copy); LOW (missing column) | mlro-user, compliance, skeptic | Medium | CONFIRMED: copy present, no "sandbox" on the page, `uaepass_verifications` has no environment column. Production env BLOCKED (secrets) | HELD `scripts/proposals/2026-11-04-lead-public-claims.md` §2-3 |
| **L-119** (new) MK2/CS-25: public copy says every confirmed sanctions match creates a freeze obligation (`landing.html:53`, `aml_law.html:30`) | LOW | mlro-user, compliance, skeptic | Low | CONFIRMED: phrases present; `is_uae_freeze_list('us_ofac_sdn')=False` | HELD same proposal §1 |
| CR-39 Stripe keys in plain Cloud Run env vars | INFO | code-reviewer | Info | CONFIRMED (`source-canary.yml:527`) | Carry; same pattern as SMTP |
| Web sign-up open, mobile `/api/v1/auth/register-organization` still invite-gated | INFO | skeptic, code-reviewer | — | CONFIRMED by CLAUDE.md, which says this is intended | Closed as documented design |
| L-112 UBO1b dotted / no-suffix / other-suffix self-owner accepted | LOW | (carried) | Low | CONFIRMED again: 3 of 5 variants `-> accepted` | HELD `2026-11-03-lead-ubo1b-legal-suffix.md`; needs Nadhir |
| L-113 N8b legacy NULL-operator proposal self-confirm | LOW (ops) | (carried) | Low | CONFIRMED again: `confirm by op 1 -> accepted` | Needs Nadhir: run the backfill on production |
| N3b, H1 | — | red-team, skeptic still list them | | **REFUTED again** on `6560fb0`: `Cyrillic Ve for B -> HIT 1.0`, `Latin control AL-BAFI -> MISS 0`; `Referrer-Policy='strict-origin-when-cross-origin'` | Closed. Red-team and skeptic should drop them |
| CS-13 24h clock from `identified_at` | MEDIUM (legal-dependent) | compliance (says HIGH) | High | CONFIRMED in code; legal PLAUSIBLE | Kept at MEDIUM: no Article verified until `corpus/` exists. Needs Nadhir + legal text |
| CS-14 PNMR, 3.1 AED 55,000 configurable | MEDIUM (legal-dependent) | compliance | Med | CONFIRMED in code | Carry |
| F2b, CR-34/SMTP, CR-35, I1, L-114, A1 residual, L-111, CR-4, CR-13, CR-18, CR-28, CR-29, PR5, K1, CS-4, FATF CS-1/6/7, E2-E5, F4, TA2/TA3, LN1, SE2, D1 | as on 11-03 | various | as stated | No commit in #457-#459 touches them (`git diff 938050f..6560fb0 --stat`: billing, auth/public routers, operators, templates, workflow) | Carry |

**Severity adjudication**
- SS1: red-team and skeptic both say Medium; code-reviewer did not flag it. I agree on **MEDIUM**, conditional on Stripe mode. Login was hardened against exactly this (LG2, dummy-hash timing), and for a compliance vendor "firm X uses groAML" is client-confidential. It is inert today only if `STRIPE_SECRET_KEY` is empty in production, which I cannot see.
- SS2: red-team says Low-Med, code-reviewer INFO, compliance "by design". I put it at **LOW**. The only cost is storage and free use, and 10/min per IP limits it. Whether to allow it is a product decision.
- MK1/CS-24: compliance and skeptic say Medium, mlro-user Low-Med. **MEDIUM for the copy**: a public CDD claim that cannot be used on real customers. The missing environment column is **LOW**, because `match_status` (`cases/manager.py:1383`) already flags a sandbox identity that does not match the file.
- CS-13: compliance raised it to HIGH today with no new evidence. I keep **MEDIUM** until the legal text is supplied.
- Duplicates: SS2 = CR-37; SS3 = CR-38; MK1 = CS-24; MK2 = CS-25. Contradiction: compliance N-7 calls free screening a positive design point; red-team calls it a gap (resolved as a product decision above).

## 4. Combined assessment
1. No regression: three independent full runs give 2860 passed, 2 skipped on two interpreters (3.11, 3.13); tenant sweeps clean over 73 routes.
2. #459 is CI-only; its test and the WP-26/27 tests pass on `6560fb0` (`102 passed`).
3. The Stripe go-live is the risk: SS1 should be fixed before the key is set in production, and SS2's policy should be decided.
4. Public copy now needs auditing like code: two claims (UAE PASS, freeze scope) are not backed by the product.
5. Older open items are unchanged and are mostly waiting on Nadhir's decisions or the legal corpus.

## 5. Corrections I made
- Owed from the 11-03 "Next run": re-run `repro_lead/checks_2026_11_03.py` on `6560fb0` (copied from `routine/2026-11-03-lead`, not re-committed). Scratch venv, Python 3.11.18, `requirements.txt` + `requirements-dev.txt`. Log lines removed from the output:
  ```
  UBO1b owner 'GULF HOLDINGS L.L.C.'   canonical_key='c glf hldngs l l'     -> accepted
  UBO1b owner 'Gulf Holdings'          canonical_key='glf hldngs'           -> accepted
  UBO1b owner 'Gulf Holdings FZE'      canonical_key='fz glf hldngs'        -> accepted
  UBO1b reproduces=True (3 suffix variants accepted)
  N8b   propose by op 1; proposal operator_id set NULL; confirm by op 1 -> accepted (proposer confirmed own legacy proposal) -> reproduces=True
  N3b   red-team probe: Cyrillic Ve for W -> MISS 0
  N3b   Latin control:   AL-BAFI        -> MISS 0
  N3b   true homoglyph:  Cyrillic Ve for B -> HIT 1.0
  H1    GET /login Referrer-Policy='strict-origin-when-cross-origin' Permissions-Policy='camera=(), microphone=(), geolocation=()'
  2/2 reproduce
  exit=0
  ```
- Created `repro_lead/checks_2026_11_04.py`. It uses a temporary-file DB, the test seed helpers, a dummy Stripe key and the in-process TestClient; Stripe is never contacted. Output on `6560fb0`:
  ```
  SS1  first signup ok=True; known email -> already exists; unknown email -> Check your email; known org name -> similar name already exists
  SS1  reproduces=True
  SS2  org plan=none status=pending_payment; 5 x POST /screen -> [200, 200, 200, 200, 200]; screenings rows 0 -> 5; retention_until=2036-11-04
  SS2  reproduces=True
  MK2  landing says 'Confirmed sanctions matches create freeze obligations': True; aml_law says 'Freeze obligations created from confirmed matches': True; is_uae_freeze_list('us_ofac_sdn')=False
  CS24 uaepass_verifications columns=[... 'user_type', 'verified_at', 'verified_by', 'match_status', 'match_detail']; environment column present=False; landing mentions 'sandbox'=False
  2/2 reproduce
  exit=0
  ```
- Created `scripts/proposals/2026-11-04-lead-public-claims.md` (HELD). It holds the copy diffs for freeze scope and UAE PASS, an additive `environment` column, and tests. Not applied, because it edits existing templates and `db.py` (rule 3). SS1-SS3 code fixes are in red-team's HELD proposal and are not duplicated.
- #459 check: `pytest tests/test_workflow_env.py tests/test_public_site.py tests/test_billing.py` on `6560fb0` -> `102 passed, 1 warning in 71.88s`. Full suite not re-run by me (three roles: 2860/2 on `c5da8aa`; #459 changes no app code).
- No tests added: tests for SS1 or SS2 would fail on master. No existing file edited. OCR not exercised (no tesseract).
- Commit SHA: given in the final reply.

## 6. Decisions needed from Nadhir
1. **Before Stripe go-live (L-115):** approve the SS1 fix (generic "check your email" answer for existing emails and firm names), or keep `STRIPE_SECRET_KEY` empty in production until it lands. Confirm whether the key is set now.
2. **L-116 SS2:** let unpaid orgs screen for free, cap them (for example 20 a day), or stop storing their screenings until payment.
3. **L-118 / L-119 copy:** approve the HELD copy changes. Also confirm whether `UAEPASS_ENV` is `production` with real credentials. If it is not, remove or qualify the UAE PASS claim.
4. Carried: L-113 production backfill; L-112 UBO1b policy (warn or refuse); CS-13/CS-14/3.1 need `corpus/`; F2b; production SMTP; L-111 required CI check; CR-29, PR5, K1, CR-4/#417, the FATF snapshot, the `github-advanced-security` 402 quota.

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_11_04.py` (exit 1 = SS1 and SS2 fixed) and `checks_2026_11_03.py` from `routine/2026-11-03-lead` (exit 1 = UBO1b and N8b fixed). Run both from the repo root with `PYTHONPATH=.`.
- Owed by the lead: none.
- For the roles: red-team, fix `probe_unicode_bypass.py:23` and drop N3b/H1 (third reminder); skeptic, drop N3b from the carried list; mlro-user, run a Stripe-mode pass with a dummy key (sign-up -> pending -> refusals); compliance, add the public-claims check to the standing review; QA, add a route-count floor to `repro/sweep.py`, which reads mobile routes by regex.
- Landing order: L-115 (before Stripe go-live), L-118/L-119 copy, L-113 (ops), L-116 policy, L-112, CS-13 (after the legal answer), L-117, L-111, F2b.
