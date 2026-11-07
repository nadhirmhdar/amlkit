# Lead consolidated report: 2026-11-07

## 1. Headline: AMBER
No regression and no code change. Two new findings: a customer's name, date of birth or ID cannot be corrected after onboarding, so a misspelt name stays on file and is the name that was screened (MEDIUM). Separately, a signed Stripe event with an unknown tier lifts every plan limit (LOW). All earlier items are still open.

Master is `6560fb021f6ea2cadefcd6e60d67ee274d871e73` (`git ls-remote origin refs/heads/master`), the same SHA as the 11-05 lead report. `git log 6560fb0..origin/master` is empty and #459 is still the newest PR. Run date 2026-11-07 UTC. All six role branches were present at the first fetch. **No role or lead report exists for 2026-11-06:** every session received the 11-06 and 11-07 firings together, and master did not move across the gap. red-team and mlro-user raised new findings, so this is a full report rather than "no change".

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done (no-change shortcut) | GREEN. Master unchanged; no new findings; CR-40 etc. carried | ls-remote + empty git log | High |
| qa-regression | done (no-change shortcut) | GREEN. Suite not re-run; the 11-05 result (2862 passed, 2 skipped on this SHA) stands | ls-remote + empty git log | High |
| red-team | done | AMBER. New Stripe webhook state-machine probe. Payment gate, ordering, replay and attribution are sound. BL1 (Low): an unknown tier fails open. BL2 (Info): malformed items return 500 forever | probe + evidence file | High (I re-ran the probe; same output). **Still lists N3b and H1 as open (fifth reminder; both refuted since 11-03)** |
| compliance-specialist | done (no-change shortcut) | AMBER. Nothing new; CS-13 and CS-5 lead the open list; legal corpus still BLOCKED | ls-remote | High |
| mlro-user | done | AMBER. CR1: identity can't be corrected (Med). CR2: duplicate person accepted with no warning (Low-Med). CR3: references are case-sensitive (Low) | driver + JSON evidence | High (I reproduced all three) |
| skeptic | done | AMBER. Confirms BL1, BL2, CR1, CR2, CR3 by code with file:line; links CR1 to CS-13 and CR2 to K1 | code file:line | High. Still carries N3b (wrong) |

## 3. Consolidated findings
CONFIRMED (lead) means I reproduced it on `6560fb0` today (§5). mlro-user's "CR1-3" are renamed MU-CR1-3 here, to avoid a clash with code-reviewer's CR-n numbering.

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-124** (new) MU-CR1: no route edits `full_name`/`birth_date`/`nationality`/`id_number`/`name_arabic` after onboarding. The only identity write is the UAE PASS backfill of *empty* fields (`cases/manager.py:1509`) | **MEDIUM** | mlro-user (Med), skeptic (Med) | CONFIRMED | CONFIRMED: route scan finds 18 customer write routes, none an identity edit; no literal `UPDATE customers` names an identity field | HELD `scripts/proposals/2026-11-07-lead-billing-tier-customer-identity.md` §2. **Needs Nadhir** (design + four-eyes) |
| **L-125** (new) MU-CR2: same name + DOB onboards repeatedly with no warning; the only uniqueness rule is `UNIQUE (org_id, reference)` (`db.py:305`) | LOW/MEDIUM | mlro-user, skeptic | CONFIRMED | CONFIRMED: `C-001`, `C-002`, `C-003` (lower-case) all accepted, 3 rows | HELD same §3 (warning, not a block) |
| **L-126** (new) MU-CR3: `c-001` and `C-001` coexist | LOW | mlro-user, skeptic | CONFIRMED | CONFIRMED: `references stored=['C-001', 'c-001']` | HELD same §4 |
| **L-127** (new) BL1: `apply_subscription` stores `metadata.tier` unvalidated (`billing/service.py:100-102`; the checkout path checks `tier in PLANS`, `:136`); `limits.py:138-139` treats an unknown plan as unlimited | **LOW** | red-team, skeptic | CONFIRMED | CONFIRMED: `4th operator -> refused` before; after the event `plan='enterprise-free'; 4th operator -> allowed` | HELD same §1 (diff) + red-team `2026-11-07-new-findings.md` |
| L-128 (new) BL2: `items.data` that isn't a list of objects -> 500, so Stripe retries indefinitely | INFO | red-team, skeptic | Info | CONFIRMED (probe re-run: `items not list -> (500, '{"error":"processing failed"}')`) | HELD red-team proposal |
| L-120 BD1 disposition/reason-code pairs | MEDIUM | carried | Low/Med | CONFIRMED again (3/3 pairs accepted) | HELD `2026-11-05-lead-disposition-pairs-ci-token-refresh.md` §1 |
| L-122 CR-40 `EU_FSF_TOKEN` on `pull_request` runs | LOW | carried | Low | CONFIRMED again | HELD same proposal §2 |
| L-123 CS-5 refresh `0 */20 * * *` (fires at 00, 20 UTC) | MEDIUM (legal-dependent) | carried | Med | CONFIRMED again (`gaps(h)=[20, 4]`) | HELD same proposal §3 |
| L-115 SS1 sign-up enumeration (Stripe mode) | MEDIUM | carried | Med | CONFIRMED again | HELD; fix before `STRIPE_SECRET_KEY` is set in prod |
| L-116 SS2 unpaid org keeps screening, scans, feedback | LOW | carried | Low | CONFIRMED again (`5 x POST /screen -> 200`) | Needs Nadhir (policy) |
| L-118 / L-119 UAE PASS env + freeze-scope public copy | MED / LOW | carried | Med / Low | CONFIRMED again | HELD `2026-11-04-lead-public-claims.md` |
| L-112 UBO1b, L-113 N8b | LOW | carried | Low | CONFIRMED again (3 variants accepted; legacy self-confirm accepted) | HELD / needs Nadhir |
| CS-13, CS-14, 3.1 AED 55,000 | MEDIUM (legal-dependent) | carried | High/Med | Code CONFIRMED; legal PLAUSIBLE | Carry; need `corpus/` |
| L-121 BD2, CS-26, L-117 SS3, CR-39, F2b, CR-34/SMTP, CR-35, I1, L-114, A1 residual, L-111, CR-4, CR-13, CR-18, CR-28, CR-29, PR5, K1, CS-4, FATF CS-1/6/7, E2-E5, F4, TA2/TA3, LN1, SE2, D1, MK1/MK2 | as on 11-05 | various | as stated | No commit since 11-04 | Carry |
| N3b, H1 | — | red-team, skeptic still list them | | REFUTED again (`Cyrillic Ve for B -> HIT 1.0`; `Referrer-Policy='strict-origin-when-cross-origin'`) | Closed |
| FIXED on master since the last report | — | — | — | none (no commits) | — |

**Severity adjudication**
- MU-CR1 is **MEDIUM**, and mlro-user and the skeptic agree. It is not HIGH because nothing is hidden: the typo is visible, a new record can be onboarded (and screened), and the audit trail is intact. It is above LOW because the screened name is the wrong one and there is no audited way to fix it. The fix is a feature, and Nadhir must decide on four-eyes for it.
- MU-CR2 is **LOW/MEDIUM**. It is a warning gap, not a control bypass, but it splits alerts and transaction aggregation across records (the same gap as K1, as the skeptic noted).
- BL1 is **LOW**, as both roles say. Only someone who can write Stripe subscription metadata can trigger it. The fail-open fallback in `limits.py` is the real design smell, and it is a separate policy call in §1 of the proposal.
- No disagreements on severity today. Duplicates: none new. Contradictions: none new, apart from the stale N3b/H1 carry.

## 4. Combined assessment
1. No regression: the code is unchanged since the 11-05 full run (2862 passed, 2 skipped).
2. The billing webhook held up under a hostile probe (ordering, replay, attribution, grace). BL1 is a small fail-open.
3. The most important new gap is product-level: customer identity cannot be corrected with an audit trail and a re-screen (MU-CR1). It shares a root with CS-13 ("what we knew, and when").
4. Every open item is now HELD on a proposal or waiting on a decision. Master has not moved for three days.
5. The 11-06 gap: queued firings arrived together for the third time. Nothing was missed because master was static.

## 5. Corrections I made
- Owed from 11-05 "Next run": re-ran `checks_2026_11_05.py`, `checks_2026_11_04.py` and `checks_2026_11_03.py` (copied from their lead branches into the working tree, run, removed, not re-committed). Scratch venv, Python 3.11.18, `requirements.txt` + `requirements-dev.txt`, `PYTHONPATH=.`:
  ```
  UBO1b reproduces=True (3 suffix variants accepted)
  N8b   ... confirm by op 1 -> accepted (proposer confirmed own legacy proposal) -> reproduces=True
  N3b   true homoglyph:  Cyrillic Ve for B -> HIT 1.0
  H1    GET /login Referrer-Policy='strict-origin-when-cross-origin' ...
  2/2 reproduce   exit=0          (checks_2026_11_03.py)
  SS1  reproduces=True
  SS2  org plan=none status=pending_payment; 5 x POST /screen -> [200, 200, 200, 200, 200]; screenings rows 0 -> 5; retention_until=2036-11-07
  SS2  reproduces=True
  2/2 reproduce   exit=0          (checks_2026_11_04.py)
  BD1  reproduces=True (3/3 contradictory pairs accepted)
  CR40 reproduces=True
  CS5  refresh schedule(s)=['0 */20 * * *']; fires at UTC hours [0, 20]; gaps(h)=[20, 4]
  3/3 reproduce   exit=0          (checks_2026_11_05.py)
  ```
- Re-ran red-team's `repro_redteam/probe_billing_events.py` (copied in temporarily, not committed). Output matches their evidence: `7 unknown price + unknown tier keeps plan -> ... A: ('enterprise-free', 'active', ...)`, `junk: items not list -> (500, ...)`, `replay of evt_1 -> (200, '{"status":"duplicate"}')`, `9 canceled > 7 days ago: creation refused`.
- Did not re-run the mlro-user driver; my own script covers the same three claims.
- Created `repro_lead/checks_2026_11_07.py` (temp-file DB seeded with `tests/test_api._seed_sanctions_data`, a static scan of the routes, no network). Output on `6560fb0`:
  ```
  BL1  starter, 3/3 operators: 4th operator -> refused: The Starter plan allows up to 3 operators, and thi
  BL1  after signed event (unknown price, metadata.tier='enterprise-free'): plan='enterprise-free'; 4th operator -> allowed
  BL1  reproduces=True
  CR1  any named edit/update/identity/details: []
  CR1  literal UPDATE customers statements naming ('full_name', 'birth_date', 'nationality', 'id_number', 'name_arabic'): []
  CR1  reproduces=True
  CR2  C-001 accepted; C-002 same name+DOB accepted; C-003 lower-case name accepted; rows for that person=3
  CR2  reproduces=True
  CR3  'c-001' accepted; exact 'C-001' again refused (IntegrityError: UNIQUE constraint failed: customers.org_id, custom); references stored=['C-001', 'c-001']
  CR3  reproduces=True
  4/4 reproduce
  exit=0
  ```
- Created `scripts/proposals/2026-11-07-lead-billing-tier-customer-identity.md` (HELD). It has a diff and a test for BL1, a design for an audited identity correction with re-screen (MU-CR1), a duplicate warning (MU-CR2) and a case-insensitive reference check (MU-CR3). None of it is applied, because each item edits business logic (rule 3).
- No tests added, because each would fail on master. No existing file edited. The secret scan of the new files is clean. The commit SHA is in the final reply.

## 6. Decisions needed from Nadhir
1. **L-124 MU-CR1:** approve an identity-correction feature. Decide which fields are correctable, whether a change to a name, DOB or nationality needs a second person, and that a reason is mandatory. It re-screens automatically and keeps the old screening rows.
2. **L-125 / L-126:** approve a duplicate-person warning (not a block) and case-insensitive references. For the second, first list the existing case-only pairs in production.
3. **L-127 BL1:** approve validating `metadata.tier` against `PLANS`. Separately, decide whether an unknown stored plan should get Starter limits instead of unlimited.
4. Carried from 11-05: BD1 table, CS-5 refresh cadence (also check the production scheduler), CR-40 token gating, SS1 before Stripe go-live, the SS2 unpaid-org policy, L-118/L-119 copy and `UAEPASS_ENV`, the L-113 production backfill, L-112 UBO1b, CS-13/CS-14/3.1 (need `corpus/`), F2b, production SMTP, L-111, CR-29, PR5, K1, CR-4/#417, the FATF snapshot, the `github-advanced-security` 402 quota.

## 7. Next run: carried over
- From the repo root with `PYTHONPATH=.`, re-run `repro_lead/checks_2026_11_07.py` (this branch), `checks_2026_11_05.py`, `checks_2026_11_04.py` and `checks_2026_11_03.py` (from their lead branches). Exit 1 means every item in that script is fixed.
- Owed by the lead: none.
- For the roles: red-team and skeptic, drop N3b/H1 (fifth reminder). mlro-user, a Stripe-mode sign-up walk is still not done; also try mobile onboarding for the duplicate and case checks. QA, the route-count floor in `repro/sweep.py`. Compliance, assess whether a correction to customer data (MU-CR1) needs second-person approval under the instruments, once `corpus/` exists.
- Landing order: L-115 (before Stripe), L-120 BD1, L-123 CS-5, L-124 MU-CR1 (after the design decision), L-118/L-119 copy, L-122 CR-40, L-127 BL1, L-125/L-126, L-113 (ops), L-116 policy, L-112, CS-13 (after the legal answer), L-117, L-111, F2b.
