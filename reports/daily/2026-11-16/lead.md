# Lead consolidated report: 2026-11-16

## 1. Headline: AMBER (code unchanged nine days; six new findings from 11-14 to 11-16, two of them MEDIUM controls defeated by input spelling)
Master is `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, same SHA as the 11-08 to 11-13 lead reports (`git ls-remote` today; newest PR still #462). Run date 2026-11-16 UTC. All six role branches present at first fetch. **No lead report exists for 11-14 or 11-15** (no `routine/2026-11-1{4,5}-lead` branch), so this report also adjudicates the 11-14/11-15 role findings. New and reproduced by the lead today: CL1, CL2, TD1, TX1, TX2, N3c. All 21 carried defect checks still reproduce.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done | GREEN, no change. CR-41/CR-42 carried | ls-remote SHA, PR ref | High |
| qa-regression | done | GREEN, no change; suite not re-run (2945 passed, 2 skipped on `9219e26`) | ls-remote, empty `git log` | High |
| red-team | done | AMBER. N3c: 11/86 one-letter Arabic-script variants score < 0.85 | probe script + evidence file (read; one case re-run) | High for Urdu heh, medium for the rest (4 hand-picked names; two "misses" are misspellings, not script variants) |
| compliance-specialist | done | AMBER, no change. CS-13, CS-14 stand; corpus BLOCKED | ls-remote, PR list | High |
| mlro-user | done | AMBER. CL1 (Med), CL2 (Low) closure with open TFS work | driver + JSON log | High (reproduced by lead) |
| skeptic | done | AMBER. Adjudicates TD1, TX1-3, TD2, CL1/2, N3c, NM1/2 (covers 11-14..16; says it missed 11-14/15) | file:line + new `urdu_heh.py` | High, one overstatement (below) |

## 3. Consolidated findings
CONFIRMED (lead) = reproduced today on `9219e26` by `repro_lead/checks_2026_11_16.py` (output in §5).

| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-149 CL1** (new): `close_relationship` (`cases/manager.py:784-822`) closes a customer with an open sanctions alert or an `executed_pending_report` freeze; no check, web and mobile | **MED** | mlro-user, skeptic | CONFIRMED, Med | **CONFIRMED** (both cases closed) | HELD `scripts/proposals/2026-11-16-lead-lifecycle-and-input-normalisation.md` §1; override policy needs Nadhir |
| **L-150 CL2** (new): closed customer's alerts stay `open` | LOW | mlro-user, skeptic | CONFIRMED, Low | **CONFIRMED** | Same proposal §1 |
| **L-151 TD1** (new): `direction` free text (`routers/alerts.py:54`, `mobile.py:1052`); structuring groups by exact string (`screening/kyt.py:226-230`) | **MED** | red-team (11-14), skeptic | CONFIRMED, Med | **CONFIRMED** (in/in/in → structuring; in/IN/" in" → none) | HELD same proposal §2 |
| **L-152 TX1** (new): operator-typed `amount_aed` only range-checked (`manager.py:1072-1089`); USD 100,000 as AED 1 → 0 flags | LOW-MED | mlro-user (11-14), skeptic | CONFIRMED, Med | **CONFIRMED** | HELD §3; FX policy needs Nadhir |
| **L-153 TX2/TX3** (new): currency code unvalidated (`XXX` stored); TX3 lower case is normalised (`manager.py:1080` `.upper()`) | LOW | mlro-user, skeptic | CONFIRMED / PLAUSIBLE | **TX2 CONFIRMED; TX3 REFUTED by code** | HELD §3 |
| **L-154 N3c** (new): Urdu heh U+06C1 (and Sindhi/Kurdish kaf, reh, lam) not folded (`names/arabic.py:44-60`) | **MED** (Urdu heh) | red-team, skeptic | CONFIRMED, Med | **CONFIRMED** (`خالد بن هاشم القحطاني` 1.00 → 0.60) | HELD §4 |
| L-155 TD2 (new): free-text fields uncapped, control/RTL characters stored | LOW | red-team (11-14), skeptic | CONFIRMED, Low | PLAUSIBLE (not re-run by lead) | Carry; same class as CR-29 |
| NM1, NM2 (new, 11-15) | INFO | red-team, skeptic | Info, by design | Accepted, no action | Close |
| L-145..L-148 SO1, RL1, RL2/RL2d, RL3 | MED / LOW-MED / LOW-MED / LOW | carried | CONFIRMED | CONFIRMED (`checks_13` 5/5) | HELD 11-13 |
| L-138 MA1 | MED | carried | | CONFIRMED (`checks_10`) | HELD 11-10 |
| L-140 RP1, L-141 gender rewrite | MED / MED | carried | | CONFIRMED (`checks_11` 2/2) | HELD 11-11 |
| L-134 SS5; L-135 RT1; L-136 RT2 | LOW / MED / LOW | carried | | CONFIRMED (`checks_09` 3/3) | HELD 11-09 |
| L-129/130 SS1b/SS3b; L-131 CS24; L-132 CS5d | LOW / LOW / MED / LOW | carried | | CONFIRMED (`checks_08` 4/4) | HELD 11-08 |
| L-124/125/126 CR1-3; L-127 BL1 | MED / LOW-MED / LOW / LOW | carried | | CONFIRMED (`checks_07` 4/4) | HELD 11-07 |
| L-112 UBO1b, L-113 N8b | LOW | carried | | CONFIRMED (`checks_03` 2/2) | HELD |
| L-143 amount cap, L-144, L-142 RP2, L-139 MA2, L-137, L-133, SS4, K2, SU1, CR-41, CR-42, CR-43, L-128, L-116, CS-13, CS-14, and the rest of the 11-13 carry list | as 11-13 | various | as stated | No code change | Carry |
| N3b, H1 | — | red-team, skeptic still list | | REFUTED 11-08 | Closed |
| FIXED on master since 11-13 | — | | | None (master unchanged) | — |

**Severity adjudication**
- **N3c, MEDIUM (skeptic) vs Low-Medium (red-team): MEDIUM for Urdu heh only.** It is the default heh on Urdu keyboards, it is a sanctions miss (0.60 vs 0.85), and the fix is a one-line fold. The other letters stay LOW until measured. **Skeptic overstated its core case:** `عبدالله` with Urdu heh does get a different key (`abdl`), but still scores 0.88 against "Abdullah" and would alert; the miss shows on multi-token names (red-team's case, reproduced). `پ ژ ڤ` are different sounds; folding them needs a false-positive run first.
- **TD1, MEDIUM (agree).** The web form uses a `<select>` (`customer.html:345`), so a web user cannot mis-spell it; but a mobile/integration client sending `IN` alongside web `in` silently splits every structuring group. Silent control failure across surfaces outweighs the UI mitigation.
- **TX1: LOW-MED, below both roles' Medium.** An insider who wants to evade can simply not record the transaction, so the evasion scenario adds little; the real risk is a wrong AED figure by mistake, which a plausibility warning fixes. Design (no FX source) is deliberate and documented in the docstring.
- **CL1, MEDIUM (agree).** Mitigated: `purge_expired()` already skips customers with open alerts or unresolved freezes, so nothing is deleted. Not HIGH: closure does not cancel the alert or the freeze. Rises if the corpus shows exit during an open TFS obligation is itself a breach.
- Duplicates/contradictions: TX1 and TD1 both weaken the structuring rule (skeptic's point, adopted). TX3 REFUTED by code (upper-cased before storage). Skeptic notes it missed 11-14/15; no lead ran those days either, so 11-14 findings were unadjudicated for two days.

## 4. Combined assessment
1. Ninth day on the same SHA; no regression; 21/21 carried checks and 6/6 new checks reproduce.
2. New cluster: inputs that feed controls are not normalised (direction, AED equivalent, currency, Arabic letter forms); one boundary-normalisation pass fixes TD1, TX2, N3c.
3. CL1 joins MA1/SO1 as a lifecycle action with no precondition tied to open obligations.
4. Open MEDIUMs now 12: L-149, L-151, L-154, L-145, L-138, L-140, L-141, L-135, L-124, L-131, plus RL1/TX1 at LOW-MED. All have HELD proposals.
5. Still unverifiable here: live refresh schedule, legal corpus, goAML XSD, production FX policy, production `AMLKIT_SINGLE_OPERATOR_MODE`.

## 5. Corrections I made
- **Owed from 11-13 "Next run":** none owed by the lead. Re-ran the carried checks (copied from lead branches into `repro_lead/`; scratch venv, Python 3.11.18, `requirements.txt` + `requirements-dev.txt`, `PYTHONPATH=.`, OCR not exercised):
  ```
  checks_2026_11_13 exit=0  5/5 reproduce (SO1, RL1, RL2, RL2d, RL3)
  checks_2026_11_11 exit=0  2/2 reproduce (RP1, RP1g)
  checks_2026_11_10 exit=0  1/1 reproduce (MA1)
  checks_2026_11_09 exit=0  3/3 reproduce (SS5, RT1, RT2)
  checks_2026_11_08 exit=0  4/4 reproduce (SS1b, SS3b, CS24, CS5d)
  checks_2026_11_07 exit=0  4/4 reproduce (BL1, CR1, CR2, CR3)
  checks_2026_11_03 exit=0  2/2 reproduce (UBO1b, N8b)
  ```
  The carried scripts were not re-committed (already on their own lead branches).
- **Created `repro_lead/checks_2026_11_16.py`** (exit 0 while any reproduces):
  ```
  CL1  open sanctions alerts=1 closed_with_open_alert=True; closed_with_executed_unreported_freeze=True
  CL2  alert still open after closure=True
  TD1  structuring with in/in/in=True; with in/IN/' in'=False
  TX1  USD 100,000 cash recorded as AED 1 accepted; flags=0
  TX2  currency 'XXX' accepted, stored as 'XXX'
  N3c  canonical_key std='abdullah' urdu_heh='abdl'; name_score vs 'Abdullah' std=1.00 urdu_heh=0.88 (still >=0.85)
  N3c  'خالد بن هاشم القحطاني' vs Latin listing: standard=1.00 urdu_heh=0.60
  6/6 reproduce
  exit=0
  ```
  (The freeze case inserts the `freeze_obligations` row by SQL rather than walking the UI; mlro-user's `close16` walk covered the UI path.)
- **Created `scripts/proposals/2026-11-16-lead-lifecycle-and-input-normalisation.md`** (HELD: business logic, rule 3): closure preconditions with audited MLRO override, `direction` closed set + data fix, ISO 4217 + FX plausibility flag, six unambiguous letter folds.
- Code read on `9219e26`: `cases/manager.py:784-822, 1035-1089`, `screening/kyt.py:215-240`, `names/arabic.py:40-60`, `routers/alerts.py:54`, `mobile.py:1051-1067`, `customer.html:345`. No existing file edited. Not re-run: full suite (no code change), red-team's full 86-variant probe (one case re-run), TD2.

## 6. Decisions needed from Nadhir
1. **Closure with open TFS work (L-149):** hard block, or block with an MLRO override (reason + audit)? Should open transaction (KYT) alerts block too?
2. **FX plausibility (L-152):** refuse, or raise an `fx_implausible` alert, when the typed AED rate is far from a reference? Static indicative table or org-maintained rates?
3. **Letter folds (L-154):** land the six unambiguous folds now; `پ ژ ڤ` only after a false-positive run?
4. **Fix wave:** master frozen since 11-07 and the Medium list is growing. Suggested order: L-151 + L-154 (small, low risk), then operator-admin wave L-138 + L-145..L-148, then L-149/L-150, then L-141 + L-140 + L-143.
5. Carried: single-operator rule (L-145), role change (L-146), no-MLRO recovery runbook, correct-and-refile, pre-Stripe batch L-129 + L-130 + L-134, L-135 scope, production scheduler check / L-132, L-131, corpus, goAML XSD, `github-advanced-security` 402 quota.

## 7. Next run: carried over
- From the repo root with `PYTHONPATH=.`, re-run `checks_2026_11_16.py`, `_13`, `_11`, `_10`, `_09`, `_08`, `_07`, `_03` from their lead branches (copy into `repro_lead/` first). Exit 1 means every item in that script is fixed.
- Owed by the lead: re-run red-team's `probe_arabic_letter_variants.py` in full and, if cheap, a TD2 check (1 MB note, RTL override) to move L-155 to CONFIRMED.
- For the roles (suggestions only): red-team, measure false positives of folding `پ ژ ڤ` against a full list; skeptic, an "every free input that feeds a rule" inventory; red-team and skeptic, drop N3b/H1.
- Landing order: L-151 + L-154, L-138 + L-145..L-148, L-149/L-150, L-141 + L-140 + L-143, L-152/L-153, then the 11-13 order (L-129 + L-130 + L-134, L-136, L-132, L-131, L-135, L-124, L-127, L-125/L-126, L-113, L-116, L-112, CS-13, L-117, L-111, F2b, INFO-8).
