# Lead consolidated report: 2026-11-03

## 1. Headline: GREEN
The third fix wave (#452-#456) closed every code item from 11-02 (L-108, L-109, L-110, UL1, CR-30/32, C1, S1, O1, N3, F2, CR-1b). The 5,046-line `app.py` split (#456) was shown to be a pure move by four roles using different methods. Today's new defects are LOW. The open items are mostly decisions waiting on Nadhir or the legal text.

Master is `938050fda10fe248b2cc327ea5d0770b5cb08f01` (`git ls-remote origin refs/heads/master`). The previous lead report named `e8ddf26`. `git log e8ddf26..938050f` lists 5 commits: #454 (WP-23), #452 (WP-24), #453 (WP-25), #455 (WP-22) and #456 (WP-18). Run date: 2026-11-03 UTC. All six role branches were present at the first fetch.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | GREEN. 2810 passed/2 skipped. #456 checked by route fingerprint (0 changed fields), AST and decorators. CR-30/31/32 and CR-1b closed. New INFO: CR-33 (legacy proposal), CR-34 (no-SMTP lock message reveals that an account exists), CR-35, CR-36 | full run + 3 mechanical diffs | High |
| qa-regression | done | GREEN. 2810/2 in 24.5 min. Tenant sweeps `HITS: []`, 72 list routes, 0 B->A leaks. Fixed its sweep, which saw 1 route after the split | pasted counts, exit codes | High |
| red-team | done | GREEN. 23 probes re-run. U4, C1, S1, O1 and F2 fixed; A1 mitigated. New N3b, F2b, N8b and I1. H1 still listed as open | evidence files per probe | High on fixes. **N3b refuted** (§3). **H1 wrong for the third day** |
| compliance-specialist | done | AMBER. CS-23 closed. UBO structure guard confirmed. AST check: 157/162 functions identical, and the 5 that differ are the intended changes. CS-13, CS-14 and 3.1 open. 2810/2 | AST + file:line; Articles unverified | High on code; legal PLAUSIBLE |
| mlro-user | done | AMBER. All 33 driver modes exit 0. Targeted fixes work. New UBO1b (dotted-suffix self-owner accepted) | driver + JSON logs | High (I reproduced UBO1b) |
| skeptic | done | GREEN. Re-ran 14 scripts. UBO1b CONFIRMED and wider. Flags route-scanner silent passes after the split. Calls H1 unresolved | exit codes + file:line | High; took N3b at face value |

## 3. Consolidated findings
CONFIRMED (lead) means I reproduced it on `938050f` today with `repro_lead/checks_2026_11_03.py` (§5).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-112** (new) UBO1b: the self-owner guard is an exact match (`cases/manager.py:532-562`). "GULF HOLDINGS L.L.C.", "Gulf Holdings" and "Gulf Holdings FZE" are accepted as owners of "Gulf Holdings LLC" | **LOW** | mlro-user, skeptic | Low (broader) | CONFIRMED: 3 of 5 variants `-> accepted` | HELD `scripts/proposals/2026-11-03-lead-ubo1b-legal-suffix.md`. **Needs Nadhir**: refuse or warn (a real "X Ltd" can own "X LLC") |
| **L-113** (new) N8b/CR-33: a pending proposal with NULL `operator_id` (from before #426) can be confirmed by its own proposer (`cases/review.py:411-413`) | **LOW** (operational) | red-team, code-reviewer, compliance, skeptic | Low | CONFIRMED: `confirm by op 1 -> accepted (proposer confirmed own legacy proposal)` | **Needs Nadhir**: run `scripts/check_legacy_proposals.py`, then `backfill_proposal_operator.py`, on production. No code change |
| N3b "a Latin name with one Cyrillic consonant scores 0" | — | red-team | PLAUSIBLE Low/Med | **REFUTED (probe error)**. The probe puts Cyrillic В (which looks like B) in place of the **W** of "AL-WAFI", so it screens "AL-BAFI", a different name. Lead run: `Cyrillic Ve for W -> MISS 0`, `Latin control AL-BAFI -> MISS 0`, `Cyrillic Ve for B -> HIT 1.0`, `Cyrillic a, o -> HIT 1.0`. `В` is in the `_CONFUSABLES` table (`names/confusables.py:27`) | Closed. Red-team should fix line 23 of `probe_unicode_bypass.py` |
| H1 Referrer-Policy / Permissions-Policy | — | red-team | "unresolved" | **REFUTED at runtime**: `GET /login Referrer-Policy='strict-origin-when-cross-origin' Permissions-Policy='camera=(), microphone=(), geolocation=()'` (TestClient), from `amlkit/api/app.py:318/320` | Closed, permanently |
| F2b an exact name with a mismatched country falls below 0.85 (-0.20 penalty) | LOW (policy) | red-team | by design | CONFIRMED in red-team evidence: `MISS 0 ... exact name + country mismatch` | **Needs Nadhir/compliance**: should a country mismatch suppress an exact-name hit? |
| CR-34 without SMTP, the 8th failed login says the account is locked and the mail failed, which shows the account exists | INFO | code-reviewer | deliberate | PLAUSIBLE (code read by two roles) | Inert if production SMTP is set; same question as UL1 |
| CR-35 homoglyph folding of all-look-alike tokens; extra blocking keys | INFO | code-reviewer | Info | PLAUSIBLE, not measured | Carry (measure candidate counts) |
| I1 GET routes that write state (`/changelog` seen-marker, audit rows from exports) | INFO | red-team | by design | CONFIRMED by red-team | Carry, no action |
| L-114 (new, process) route-enumerating tools silently tested 0 routes after #456 (QA sweep, red-team CSRF probe, skeptic csrf_scan) | INFO | skeptic, qa, red-team | — | CONFIRMED from three reports; all three tools fixed today, and the skeptic's now fails below 20 routes | Recommend a route-count floor in every scanner |
| **CS-13** the 24h clock runs from `identified_at` (confirmed disposition) | **MEDIUM** (legal-dependent) | compliance | High | CONFIRMED in code; legal PLAUSIBLE | **Needs Nadhir** + legal text (carried) |
| CS-14 PNMR not supported (`SUPPORTED_REPORT_TYPES` = STR/SAR/FFR); 3.1 the AED 55,000 cash threshold is configurable per org | MEDIUM (legal-dependent) | compliance | Med | CONFIRMED in code (compliance) | Carry; needs `corpus/` |
| L-108 UBO self-owner (exact) + U4 recursion | was LOW-MED | | | **FIXED by PR #455**: `UBO1 ... -> ValueError: A customer cannot be recorded as its own beneficial owner`, `U4 reproduces=False` (the chain is refused at depth 10) | Closed |
| L-109 / CS-23 terrorism wording before dataset check | was LOW | | | **FIXED by PR #454**: `obligation_note({'terrorism'}, 'us_ofac_sdn') = 'Confirmed sanctions match on a non-UAE list - apply enhanced'...` | Closed |
| L-110 `hypothesis` in prod requirements | was INFO | | | **FIXED by PR #454**: `CR31 requirements.txt hypothesis line -> None`; it is now in `requirements-dev.txt:5` | Closed |
| UL1 no unlock mail without SMTP | was LOW | | | **FIXED by PR #453** (now tells the user the mail could not be sent; mlro re-test). Production SMTP is still unconfirmed | Closed (code); SMTP question carried |
| CR-30 unlock GET changes state; CR-32 replica detail on tenant ops page | was INFO | | | **FIXED by PR #454** (two-step unlock: mlro, red-team, compliance; derived replica state: code-reviewer) | Closed |
| C1 UAE PASS identity reuse; S1 SSO ignores password lock; N8/CR-1b four-eyes by name; O1 look-alike operator names | was MED/LOW | | | **FIXED by PR #453 / #454** (red-team probes; skeptic `four_eyes_rename` exit 1) | Closed. The residual is L-113 |
| N3 invisible/look-alike characters; F2 extra-token query | was MED | | | **FIXED by PR #452** (red-team probe: all HIT except the refuted N3b case; F2 `HIT 0.97`) | Closed |
| A1 residual: an attacker can re-lock after each self-unlock | LOW | red-team | Low | unchanged (mitigated by two-step unlock) | Carry (optional per-IP throttle) |
| L-111 #447 merged with a failing test | INFO (process) | | | No red merge seen in #452-#456 (not checked in CI) | Carry: required status check |
| CR-28, CR-29, PR5, K1 (F2/F3 KYT aggregation), CR-4 (#417), CR-13, CR-18, CS-4, FATF CS-1/6/7, retention figures, E2-E5, F4, TA2/TA3, LN1, SE2, D1, high-risk-country free text | as before | various | as stated | No commit in #452-#456 touches them (per the roles); not re-run by me | Carry |

**Severity adjudication**
- UBO1b: mlro-user says low; the skeptic says Low, with a wider scope. I put it at **LOW**. It cannot form a cycle or crash anything. The fix is not just mechanical, because a refusal on the base name alone would block legitimate same-name group structures, so it needs a policy choice.
- N3b: red-team says Low-Medium; the skeptic left it PLAUSIBLE Low/Medium. I **refute** it. The probe string is a different name, not a spoof. The Latin control misses the same way, and a real Cyrillic-for-Latin swap scores 1.0.
- N8b/CR-33: four roles agree on Low. It is operational, not code: the gap closes once the backfill script runs on production. **LOW**.
- Duplicates: N8b = CR-33 = compliance's four-eyes residual = the skeptic's `four_eyes_ids` line (one item, L-113). UL1 and CR-34 are one SMTP question.
- Contradiction: red-team H1 against the code and the runtime. Settled with live response headers (above).

## 4. Combined assessment
1. Every lead item rated LOW or higher on 11-02 is FIXED on master except CS-13, which is blocked on the legal text. The 11-02 lead script: 0/4 reproduce.
2. Three independent full runs: 2810 passed, 2 skipped (+159 tests). Tenant isolation holds over 72 list routes and the ID-route sweep.
3. The router split is a verified pure move (route fingerprints, AST, decorators, route/limit diffs: 4 roles).
4. Today's real defects: UBO1b (LOW, needs a policy choice) and the legacy-proposal backfill (LOW, operational). N3b and H1 are refuted.
5. Tooling risk: route-enumerating scanners passed silently on 0 routes after #456. All three have been fixed, but only the skeptic's has a floor.

## 5. Corrections I made
- C-1 (owed from 11-02 "Next run"): re-ran `repro_lead/checks_2026_11_02.py` on detached `938050f` (scratch venv from `requirements.txt` + `requirements-dev.txt`). The script was copied in from `routine/2026-11-02-lead` and placed in `repro_lead/` because it resolves `requirements.txt` relative to its own folder. Not committed again. Output:
  ```
  UBO1 add_ubo(customer 'Gulf Holdings LLC' as its own 30% owner) -> ValueError: A customer cannot be recorded as its own beneficial owner. Record the natural persons or other entities that own or control it. -> reproduces=False
  U4   reproduces=False (recursionlimit 1000)
  CS23 is_uae_freeze_list('us_ofac_sdn')=False; obligation_note({'terrorism'}, 'us_ofac_sdn') = 'Confirmed sanctions match on a non-UAE list - apply enhanced'... -> reproduces=False
  CR31 requirements.txt hypothesis line -> None -> reproduces=False
  0/4 reproduce
  exit=1
  ```
  U4 printed no depth line because `add_ubo` refused the chain before depth 900 (MAX_UBO_DEPTH = 10). **This script is retired.**
- C-2 Created `repro_lead/checks_2026_11_03.py`. It counts UBO1b and N8b, and prints N3b and H1 for information. It uses `:memory:` databases and the test seed helpers, with no network; the TestClient talks to `testserver` only. Output on `938050f`, with `screen()` log lines and JSON app logs removed:
  ```
  UBO1b owner 'Gulf Holdings LLC'      canonical_key='glf hldngs lc'        -> refused (A customer cannot be recorded as its own bene...)
  UBO1b owner 'GULF  holdings llc'     canonical_key='glf hldngs lc'        -> refused (A customer cannot be recorded as its own bene...)
  UBO1b owner 'GULF HOLDINGS L.L.C.'   canonical_key='c glf hldngs l l'     -> accepted
  UBO1b owner 'Gulf Holdings'          canonical_key='glf hldngs'           -> accepted
  UBO1b owner 'Gulf Holdings FZE'      canonical_key='fz glf hldngs'        -> accepted
  UBO1b reproduces=True (3 suffix variants accepted)
  N8b   propose by op 1; proposal operator_id set NULL; confirm by op 1 -> accepted (proposer confirmed own legacy proposal) -> reproduces=True
  N3b   red-team probe: Cyrillic Ve for W -> MISS 0
  N3b   Latin control:   AL-BAFI        -> MISS 0
  N3b   true homoglyph:  Cyrillic Ve for B -> HIT 1.0
  N3b   true homoglyph:  Cyrillic a, o    -> HIT 1.0
  H1    GET /login Referrer-Policy='strict-origin-when-cross-origin' Permissions-Policy='camera=(), microphone=(), geolocation=()'
  2/2 reproduce
  exit=0
  ```
- C-3 Created `scripts/proposals/2026-11-03-lead-ubo1b-legal-suffix.md` (HELD). It contains a legal-form split helper, a refuse-or-warn design choice and the tests to add. Not applied, because it edits `cases/manager.py` (rule 3).
- Not re-run by me: the full suite (three roles agree on 2810/2), the tenant sweeps, the red-team probes, the mlro driver. No OCR path was exercised (no tesseract).
- No tests added: a UBO1b or N8b test would fail on master. No existing file edited.
- Commit SHA: given in the final reply. A file cannot name its own commit.

## 6. Decisions needed from Nadhir
1. **L-113 (operational):** run `scripts/check_legacy_proposals.py` against production, and if it reports rows, run `scripts/backfill_proposal_operator.py`. Until then, four-eyes can be bypassed on pre-#426 pending proposals. Put it on the release checklist.
2. **L-112 UBO1b:** choose (a) warn only, (b) refuse same legal form and warn on a different form (recommended), or (c) refuse every base-name match. Then approve a small PR from the HELD proposal.
3. **CS-13 / CR-28 / CS-14 / 3.1 (legal):** blocked until the `corpus/` PDFs are supplied.
4. **F2b:** should a country mismatch be allowed to push an exact-name sanctions hit below the alert line?
5. **SMTP (UL1/CR-34):** confirm production has `AMLKIT_SMTP_HOST` set.
6. **L-111:** make the CI test job a required status check on master.
7. Carried: CR-29 standing-record sign-off, PR5, K1 KYT aggregation policy, CR-4/#417, the FATF snapshot, the `github-advanced-security` 402 quota.

## 7. Next run: carried over
- Re-run `repro_lead/checks_2026_11_03.py` (this branch): `PYTHONPATH=. python repro_lead/checks_2026_11_03.py`. Exit 1 means UBO1b or N8b is fixed (an N8b fix needs a code change; a production backfill does not change this script). `checks_2026_11_02.py` is retired.
- Owed by the lead: none.
- For the roles: red-team, fix `probe_unicode_bypass.py:23` (swap the B, not the W) and drop H1; QA and red-team, add a route-count floor to the sweeps; mlro-user, the UBO row cap and a limiter-enabled pass (LG4); compliance, CS-13 once `corpus/` exists; code-reviewer, measure candidate-count growth from #452 (CR-35).
- Landing order: L-113 (ops), L-112, CS-13 (after the legal answer), L-111, F2b, A1 residual throttle, K1, CR-4, CS-14, D1.
