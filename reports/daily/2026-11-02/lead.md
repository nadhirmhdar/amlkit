# Lead consolidated report: 2026-11-02

## 1. Headline: GREEN (lowest open severity since the routine began)
The second fix wave (#443-#451) closed every open lead item from 11-01 except CS-13 (legal) and the policy carries. Three roles each ran the full suite (2651 passed, 2 skipped) and QA's tenant sweeps found no leaks. The new defects are all LOW or LOW-MEDIUM: UBO structure validation (U4 recursion crash and UBO1 self-ownership) and one wording residual (CS-23).

Master is `e8ddf262a73c1f0fda99a174871d879e35fcbbcf` (`git ls-remote origin refs/heads/master`). The previous lead report named `11a3527`. `git log 11a3527..origin/master` lists 9 commits: #446 (WP-13), #443 (WP-14), #445 (WP-15), #444 (WP-16), #447 (WP-17), #448 (WP-20), #449 (WP-21), #450 (WP-19) and #451 (test fix). 79 files, +4326/-218. Run date: 2026-11-02 UTC. All six role branches were present at the first fetch.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | GREEN. 2651 passed/2 skipped. CR-24/25/26/27 fixed (re-probed). Four new INFO items: CR-29 standing-record semantics, CR-30 unlock via GET plus timing, CR-31 `hypothesis` in prod requirements, CR-32 `/admin/ops` infra detail | full run + probes + diff reading | High (CR-24/25/26 and CR-31 re-checked by me) |
| qa-regression | done | GREEN. 2651 passed, 0 new failures. Sweeps `HITS: []`, 68 routes, 0 B->A leaks. New-route check `FINDINGS: none` | pasted counts and exit codes | High |
| red-team | done | AMBER. #443 self-unlock is clean (concurrency, scope and token probing all tested). New U4: a deep ownership chain causes RecursionError. A1 residual is now Low. Still lists H1 as open | 2 probes + evidence files | High on U4 (I reproduced it); H1 wrong again |
| compliance-specialist | done | AMBER. CS-19, CS-21 and CS-22 closed in code. New CS-23 (wording residual). CS-13 and CS-14 still open. Retention and UBO items narrowed. Ran the full suite: 2651/2 | diff reading + file:line; Articles unverified | High on code; legal PLAUSIBLE |
| mlro-user | done | AMBER. Re-ran 31 modes, all exit 0. Self-unlock, SS1, PR4, G10 and FZ4 are fixed. New UBO1 (self-owner accepted); UL1 (no unlock mail without SMTP) | driver + JSON logs | High (UBO1 reproduced by me) |
| skeptic | done | AMBER. Confirms U4 (lowers it to Low), UBO1 and A1 (Low). Links UBO1 and U4. Flags the #451 master-red process gap and the unresolved H1 | exit codes + file:line | High; one overreach (cycle-entry claim, refuted below) |

## 3. Consolidated findings
CONFIRMED (lead) means I reproduced it on `e8ddf26` today (§5).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-108** (new) UBO structure is not validated. U4: `_identified_ownership.eff()` (`cases/manager.py:668-677`) recurses per level with no depth bound, so `ownership_state()` raises RecursionError at depth 1100 (900 works), which breaks risk reassessment and mobile `/risk` for that customer. UBO1: `add_ubo` (`cases/manager.py:528`) accepts the customer as its own owner | **LOW-MEDIUM** (UBO1) / **LOW** (U4); one fix | red-team U4, mlro-user UBO1, skeptic | U4 Med->Low; UBO1 Low/Med | CONFIRMED: `UBO1 ... -> accepted`, `U4 depth 900: ownership_state -> single_layer_foreign`, `U4 depth 1100: ownership_state -> RecursionError` | HELD `scripts/proposals/2026-11-02-lead-ubo-structure-and-cs23.md` §1 |
| **L-109** (new; residual of L-102) the terrorism/proliferation freeze wording is returned before the dataset check in `obligation_note` (`screening/pf.py:95-108`), so OFAC SDGT-only hits still say "Freeze without delay" | **LOW** | compliance CS-23, skeptic | Low | CONFIRMED: `is_uae_freeze_list('us_ofac_sdn')=False; obligation_note({'terrorism'}, 'us_ofac_sdn') = 'TERRORISM FINANCING match. Freeze without delay...'` | HELD, same proposal §2; wording needs sign-off |
| **CS-13** the 24h clock runs from `identified_at` (confirmed disposition). `/admin/ops` (#450) inherits the same clock | **MEDIUM** (legal-dependent) | compliance | Med/High | CONFIRMED in code (compliance read `queries.ops_org_figures`); legal PLAUSIBLE | **Needs Nadhir** + legal text |
| L-110 (new) `hypothesis` (test-only) is in the production `requirements.txt` | INFO (cost: every role's first suite run failed at collection) | code-reviewer CR-31, qa, compliance, skeptic | Info | CONFIRMED: `requirements.txt` line `33: hypothesis>=6.100` | Small fix: move it to a dev requirements file. Owner decision (build config) |
| L-111 (new) #447 merged with a failing test; #451 is titled "(master red)" | INFO (process) | skeptic | n/a | PLAUSIBLE: commit message `tests: fix retention finalise test after #447 (master red) (#451)`; I did not read CI history | Needs Nadhir: required status check on master |
| CR-29 decided alerts are now a standing record (re-alert only on `list_updated` or `subject_changed`). A change to a UBO's own identifiers does not re-alert | INFO | code-reviewer, compliance | agree | CONFIRMED in code by two roles | **Needs Nadhir** compliance sign-off |
| UL1 no SMTP means no unlock mail (audit `delivery: not_configured`) | LOW | mlro-user | Low | PLAUSIBLE. My run printed the link to the console when SMTP was unset, which does not help an operator in production | Needs Nadhir: confirm production `AMLKIT_SMTP_HOST` is set |
| A1 / L-101 residual: an attacker can re-lock after every self-unlock | LOW | red-team, skeptic | Low | CONFIRMED: `A1r 8 unauthenticated wrong guesses -> count=8 locked_until=...`, and the unlock link was issued in the same run | L-101 **FIXED by PR #443** (break-glass works, per mlro and red-team). Residual: carry (optional per-IP throttle) |
| CR-30 unlock is a GET that changes state (scanner prefetch) plus possible enumeration timing; CR-32 `/admin/ops` shows replica status to any org's MLRO | INFO | code-reviewer, red-team | Info | CR-30 GET CONFIRMED by red-team; timing and CR-32 PLAUSIBLE | Carry |
| H1 Referrer-Policy / Permissions-Policy | closed | red-team (still lists it as open) | "unresolved" | **REFUTED again**: `amlkit/api/app.py:611` `Referrer-Policy`, `:613` `Permissions-Policy` on `e8ddf26`. The skeptic's "no one has done it for two days" is wrong: I settled it on 11-01 from the same lines | Closed. Red-team should drop H1 |
| Skeptic: "nothing stops a cycle or loop being entered through the UI" | n/a | skeptic | — | **REFUTED**: `add_ubo` requires the parent to exist before the child is inserted, and `grep -rn "UPDATE ubo_links" amlkit` is empty, so `parent_ubo_id` is never re-pointed. Only depth and self-reference are reachable | Recorded in the proposal |
| L-100 compare_digest TypeErrors (CR-24/25/26) | was LOW | | | **FIXED by PR #446**: `CR25 ... -> False`, `CR26 ... -> False`, `CR24 ... -> SignatureError ... reproduces=False` | Closed |
| L-102 freeze wording for non-UAE sanctions (generic case) | was LOW-MED | | | **FIXED by PR #446**: `CS19 ... onboarding banner 'freeze without delay' present=False -> reproduces=False`. The terrorism/proliferation residual is now L-109 | Closed |
| L-103 (G10), L-104 (FZ4), L-107 (CS-21, CS-22) | was LOW | | | **FIXED by PR #445** (mlro re-test, compliance diff reading) | Closed |
| L-105 PR4 raw JSON 400; L-81 residual SS1; L-106 Stripe ordering | was LOW | | | **FIXED by PR #446** (mlro re-test; code-reviewer read `billing_last_event_created`) | Closed |
| PR5 officer can complete a periodic review | INFO (policy) | mlro | Info | unchanged | Needs Nadhir (carried) |
| CR-28 freeze scope is UN/UAE-local only | INFO | | | unchanged | Needs Nadhir legal sign-off (carried) |
| Retention 4.1/4.2; UBO 5.x | was MEDIUM | compliance | — | Narrowed by #444 and #447. The 10-year policy exceeds both candidate statutory figures | Carry at LOW until `corpus/` exists |
| C1, F2/F3, N3 residual, O1, S1, N8/CR-1b, D1, CR-4 (#417), CR-13, CR-18, CS-14 PNMR, CS-4, FATF CS-1/6/7, 3.1 cash threshold, E2-E5, F4, TA2/TA3, high-risk-country free text | as before | various | as stated | Not touched by #443-#451 (per the roles); not re-run by me | Carry |

**Severity adjudication**
- U4: red-team says Medium, the skeptic Low. I put it at **LOW**. It takes more than 900 deliberately added chain levels, the damage is limited to one customer's risk reassessment, and there is no cross-tenant effect or data loss. It shares one fix with UBO1, so it goes in with that.
- UBO1: mlro says low-medium, the skeptic Low/Medium. I agree on **LOW-MEDIUM**. It is reachable through normal UI data entry (a typo or a misunderstanding), it inflates the disclosed ownership, and an examiner would flag it.
- CS-23 (L-109): **LOW**. Same contradiction as L-102, on a narrower set (OFAC/EU/UK terrorism or PF programmes). Over-freezing advice is the safe direction of error.
- A1 residual: red-team Low, skeptic Medium->Low. I agree on **LOW**.
- Contradiction: red-team H1 vs code. Resolved from `app.py:611/613` (above).

## 4. Combined assessment
1. Every lead item rated LOW or higher on 11-01 is FIXED on master except CS-13, which is blocked on the legal text. Yesterday's lead script: 1/5 reproduce, and that one is the by-design lock, which now mails an unlock link.
2. Three independent full runs: 2651 passed, 2 skipped (+152 tests). Tenant isolation holds on 68 routes plus the new unlock and ops routes.
3. The new defects come from one gap: #447 added percentage validation to `add_ubo` but no structure validation. One small HELD change fixes both.
4. Process: #451 shows a merge went in red (L-111), and the test-only `hypothesis` dependency cost every role a failed first run (L-110).
5. What remains is mostly decisions: CS-13, CR-28, CR-29, PR5, KYT policy (F2/F3), and production SMTP for self-unlock.

## 5. Corrections I made
- C-1 Owed from the 11-01 "Next run": re-ran `repro_lead/checks_2026_11_01.py` (copied in from `routine/2026-11-01-lead`, not committed) on detached `e8ddf26`. Scratch venv from `requirements.txt` + pytest. Output:
  ```
  CR25 mfa_verify(code='١٢٣٤٥٦') -> False -> reproduces=False
  CR26 csrf_valid('abc123', 'abcé') -> False -> reproduces=False
  CR24 verify_webhook_signature(header 't=100,v1=é') -> SignatureError (SignatureError would be a 400) -> reproduces=False
  amlkit: no SMTP configured (AMLKIT_SMTP_HOST unset) -- printing the account unlock link for mlro@t.test instead of emailing it.
  A1r  8 unauthenticated wrong guesses -> count=8 locked_until=2026-11-02T03:58:53+00:00; owner's correct pw -> 'Incorrect email or password.' -> reproduces=True
  CS19 obligation_note({'sanction'}) takes no dataset and says 'SANCTIONS match. Freeze without delay and wit'...; onboarding banner 'freeze without delay' present=False -> reproduces=False
  1/5 reproduce
  exit=1
  ```
  A1r=True is the intended lock; the break-glass link appears in the same output. The CS19 label text is stale: the function now takes a dataset. **This script is retired.**
- C-2 Created `repro_lead/checks_2026_11_02.py` (UBO1, U4, CS23, CR31; `:memory:` DB, no network). Output on `e8ddf26`:
  ```
  UBO1 add_ubo(customer 'Gulf Holdings LLC' as its own 30% owner) -> accepted -> reproduces=True
  U4   depth 900: ownership_state -> single_layer_foreign
  U4   depth 1100: ownership_state -> RecursionError
  U4   reproduces=True (recursionlimit 1000)
  CS23 is_uae_freeze_list('us_ofac_sdn')=False; obligation_note({'terrorism'}, 'us_ofac_sdn') = 'TERRORISM FINANCING match. Freeze without delay and without '... -> reproduces=True
  CR31 requirements.txt hypothesis line -> 33: hypothesis>=6.100 -> reproduces=True
  4/4 reproduce
  exit=0
  ```
- C-3 Created `scripts/proposals/2026-11-02-lead-ubo-structure-and-cs23.md` (HELD). It holds the diff sketch for: a self-owner guard and a `MAX_UBO_CHAIN_DEPTH` check in `add_ubo`, an iterative `eff()`, and a dataset-first `obligation_note`, plus the tests to add. Not applied because it edits `cases/manager.py` and `screening/pf.py` (rule 3).
- Not re-run by me: the full suite (three roles agree on 2651/2), the red-team probes (`fixtures/` from #412 needed), the mlro driver, the skeptic scripts. No OCR paths were exercised (the venv has no tesseract).
- No tests added: each L-108/L-109 test would fail on master. No existing file edited.
- Commit SHA: given in the final reply. A file cannot name its own commit.

## 6. Decisions needed from Nadhir
1. **L-108 + L-109: approve one small PR** from the HELD proposal (UBO self-owner and depth guard, an iterative look-through walk, dataset-first terrorism/PF wording). Recommended next.
2. **CS-13 and CR-28 (legal):** where the 24h clock starts, and sign-off that freeze applies only to UN/UAE-local lists. Blocked until `corpus/` PDFs are supplied.
3. **CR-29:** sign off on decided alerts being a standing record, and on a UBO identifier change not re-alerting.
4. **UL1:** confirm production has `AMLKIT_SMTP_HOST` set. Without it, self-unlock (#443) only prints to the container log.
5. **L-111:** make the CI test job a required status check on master, so a red PR cannot merge.
6. **L-110:** move `hypothesis` to a dev requirements file.
7. Carried: PR5 (who may complete a periodic review), F2/F3 KYT aggregation policy, CR-4/#417, CS-14 PNMR, the cash-threshold ceiling, the FATF snapshot, the `github-advanced-security` 402 quota.

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_11_02.py` (this branch): `PYTHONPATH=. python repro_lead/checks_2026_11_02.py`. Exit 1 means one item is fixed; read the lines. `checks_2026_11_01.py` is retired.
- Owed by the lead: none.
- For the roles: red-team, drop H1 (`app.py:611/613`) and walk #441's UAE PASS identity-match flag (C1, now two runs overdue); mlro-user, one pass with the limiter enabled (LG4); compliance, CS-13 and the retention figures once `corpus/` exists; skeptic, retire `docx_policy_upload.py`.
- Landing order: L-108/L-109, CS-13 (after the legal answer), L-110, L-111, A1 residual throttle, CR-30, C1, F2/F3, O1, N3 residual, N8/CR-1b, CR-4, CS-14, D1.
