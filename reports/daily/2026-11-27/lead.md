# Lead consolidated report: 2026-11-27

## 1. Headline: AMBER (master unchanged for the fourth day; one new finding, DS1, reproduced by the lead at LOW-MEDIUM)
Master `f3c8227121fbec1d4c3860c63b4a383a4656f975` (`git ls-remote`, today), same SHA as the 11-24/25/26 lead reports; no PR opened or merged since #468 (compliance: only draft #411 updated, docs only). All six role branches were there on the first fetch. Run date 2026-11-27 UTC. This is not a "no change" run: the skeptic raised DS1 and mlro-user raised SS2.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done (no-change shortcut) | GREEN; CR-52/53/54 carried | `ls-remote` only | High |
| qa-regression | done (no-change shortcut) | GREEN; 11-24 full run (3023/2/0) stands | `ls-remote`, `git log` | High |
| red-team | done | `also_listed` XSS REFUTED (autoescape on, no `\|safe`); PC1 carried | probe script + evidence file | High (code-consistent; not re-run by me) |
| compliance-specialist | done (no-change shortcut) | AMBER unchanged; CS-27 look-back unconfirmed | `ls-remote`, PR list | High |
| mlro-user | done | HP3 withdrawn by the role (now REFUTED by all); SS2 new (= lead ST-1) | driver + evidence files | High |
| skeptic | done | SS2 CONFIRMED (rated Medium); DS1 new, Medium (code read only) | file:line refs | Medium: DS1 is real, but the example given is wrong (below) |

## 3. Consolidated findings
| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-180 DS1** `datasets_fresh()` passes if any one mandatory list is fresh, so onboarding goes ahead while the UAE Local Terrorist List is in breach | **LOW-MEDIUM** | skeptic | Medium | **CONFIRMED (lead)**: `ds1_partial_stale_gate_2026_11_27.py` exit 0; `loader.py:290-292` returns True on the first fresh row | HELD `scripts/proposals/2026-11-27-lead-freshness-gate-all-mandatory.md`; **Nadhir: block vs warn** |
| L-178 ST-1 = **SS2** ad-hoc `/screen` gives a result on stale lists with no label | LOW-MEDIUM (kept) | lead 11-26, mlro-user, skeptic | Medium | CONFIRMED, re-run today exit 0 | HELD 11-26 proposal; duplicate merged |
| L-179 HP5 refusal wording | LOW | mlro-user | Low | CONFIRMED 11-26 | HELD 11-26 proposal (can ride with DS1) |
| HP3 overdue-review indicator | none | mlro-user (withdrawn) | REFUTED | REFUTED | Closed; all roles agree |
| HP2 "No successful load" on Ops | none | mlro-user | seed artefact | PLAUSIBLE seed artefact | Note |
| `also_listed` XSS (#465) | none | red-team | REFUTED | REFUTED (agree, code-consistent) | Closed |
| `test_entrypoint.py` `rm` failure | none (env) | CR, QA, compliance | env | PLAUSIBLE env; unverified on CI | Note |
| L-176 F-1 disposition race | LOW-MEDIUM | compliance | Low-Med | CONFIRMED, re-run today exit 0 | HELD 11-24 proposal |
| L-177 F-2 onboard commit-before-screen | LOW | compliance | — | CONFIRMED, re-run today exit 0 | HELD 11-25 proposal |
| L-166 DB1 / CS-28 / CR-48 | MEDIUM-HIGH | 5 roles | High | CONFIRMED 11-24 | HELD 11-20 §1; **Nadhir** |
| L-163 CS-27 look-back | HIGH (operational) | compliance, skeptic | carried | post-deploy re-screen **unconfirmed** | **Nadhir** |
| PC1/PC1b, L-174, L-175, L-172/L-171, L-170, L-168, L-167, CS-30, L-164, L-162, L-159, L-161, L-156, L-173, L-169, CR-52/53/54, CS-31, SL2, CR-50/51 and older carried set | as 11-26 | | | unchanged (master unchanged) | HELD/carry as 11-26 |

**Adjudication.**
- **DS1 at LOW-MEDIUM, not Medium.** The defect is real and reproduced. The skeptic's example is wrong, though: only UN and the UAE list are mandatory in code (`un.py:23`, `eocn.py:520`, `opensanctions.py:157/162`). OFAC, EU and UK are `is_mandatory=False` (`ofac.py:23`, `eu.py:62`, `uk.py:30`), so they never satisfy the gate. That leaves one real case: one of the two lists (UN or UAE) is stale while the other is fresh.
- Stale entities are kept, so names already on the old UAE list still hit (the repro shows `candidates=1`). The dashboard also shows a breach banner. The gap is that new UAE designations made during the outage are missed at onboarding with no warning.
- The docstring says "at least one", so this behaviour is intentional and changing it is Nadhir's decision.
- **SS2/ST-1 stays LOW-MEDIUM.** mlro-user's own evidence shows that a stale list still returns the listed match with freeze wording, which backs the 11-26 reasoning: the risk is a false CLEAR for new designations only. Treat DS1 and ST-1 as one family and land them in one PR.
- There are no factual contradictions between roles. mlro-user and the skeptic now agree with the lead on HP3.

## 4. Combined assessment
1. No application change for four days. The full suite is green on this SHA (QA 3023/2/0, red-team 2999/2/0 with the entrypoint tests excluded).
2. A new freshness-gate gap (DS1) was confirmed by running it. It belongs to the same fail-open family as ST-1.
3. F-1, F-2 and ST-1 still reproduce on master today.
4. All Medium-or-above items remain HELD. None moved.
5. Owner decisions, not new findings, are holding things up. CS-27 is still the most urgent.

## 5. Corrections I made
Scratch venv (Python 3.11.18, `requirements.txt` only; OCR not exercised), `PYTHONPATH=.`, branch app code identical to master (`git diff --stat origin/master HEAD -- amlkit` empty). No existing file edited; no `/system/*` call; no network beyond git and pip.
- Owed from 11-26: none.
- New `repro_lead/ds1_partial_stale_gate_2026_11_27.py`, exit 0:
  ```
  DS1 datasets: [('ae_local_terrorists', True, True), ('un_sc_sanctions', True, False)]
  DS1 UAE list stale (2026-01-01), UN fresh -> datasets_fresh=True, UAE breach=True
  DS1 onboard with UAE list stale: accepted (customer OnboardingResult(customer_id=1, ... candidates=1, hits=[] ...))
  DS1 gate passes on one fresh list while the UAE list is in breach=True
  ```
- New `scripts/proposals/2026-11-27-lead-freshness-gate-all-mandatory.md` (HELD): every-mandatory-list diff, the trade-off between blocking and warning, and the test fixtures that will need a second mandatory dataset.
- Re-ran `st1_`, `f1_` and `f2_`. All exit 0, with output identical to earlier runs.
- Evidence: `reports/daily/2026-11-27/evidence/lead_checks_2026_11_27_on_f3c8227.txt`. Commit SHA: in the final reply.

## 6. Decisions needed from Nadhir
1. **CS-27 look-back (urgent, carried):** confirm that a refresh plus `rescreen_all` ran after 2026-11-18 14:36 UTC, review its alerts (UN first), and record the window (from at least 2026-10-04).
2. **Exact-name floor (L-166 + L-170):** Option B recommended, with DB2 in the same PR.
3. **DS1 (new):** require every mandatory list (UN + UAE) to be fresh before onboarding. Recommended: block, matching the existing fail-closed rule; the alternative is to warn and record a coverage note. Bundle with ST-1 + HP5.
4. **ST-1:** label stale ad-hoc results (recommended) or refuse them.
5. **F-1 guard:** approve the two-line status guard. **F-2:** approve `onboarding_incomplete` marking.
6. **Delisting (L-171/172/174/175):** as 11-25.
7. Carried: CR-53, PEP fold (L-168 + PC1 + CS-30), EDD (L-169), EV1+EV4, CR-45, L-156 + L-162, L-159, L-149, L-152, L-154, L-145/L-146, runbook, correct-and-refile, L-135, L-132/L-131, corpus, goAML XSD (+EV2), `github-advanced-security` 402.

## 7. Next run: carried over
- Owed by the lead: none.
- Still untested by anyone: `rescreen_all` on stale or partly stale lists; mobile onboarding and mobile `/screen` on stale lists (`mobile.py:556`, `mobile.py:667`, read only); F-1 with two real writers; a full render of `_alert_panel.html` through its route.
- If master moves in screening, review, freeze, onboarding or ingest code, re-run `ds1_`, `st1_`, `f1_`, `f2_` and the earlier lead scripts.
- Landing order: CS-27 follow-ups (L-164 + CT1 + CT2) with L-166/L-170 + DB2; L-168 + CR-49; delisting set with F-1; L-169; then DS1 + ST-1 + HP5 together, then F-2, EV1+EV4, CR-52 and the rest.
