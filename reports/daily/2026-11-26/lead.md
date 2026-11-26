# Lead consolidated report: 2026-11-26

## 1. Headline: AMBER (master unchanged for the third day; one new LOW-MEDIUM gap found and reproduced by the lead, ST-1)
Master `f3c8227121fbec1d4c3860c63b4a383a4656f975` (`git ls-remote`, today), same SHA as the 11-24 and 11-25 lead reports; no PR opened or merged since #468 (roles: only draft #411 updated, docs only). All six role branches present on the first fetch. Run date 2026-11-26 UTC. Not a "no change" run: mlro-user raised HP5, and the lead probed the skeptic's first untested item (ad-hoc `/screen` on stale lists) and reproduced a gap.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done (no-change shortcut) | GREEN; CR-52/53/54 carried | `ls-remote` only | High |
| qa-regression | done (no-change shortcut) | GREEN; 11-24 full run (3023/2/0) stands | `ls-remote`, `git log` | High |
| red-team | done | Full suite 2,999 passed / 2 skipped / 0 failed with `test_entrypoint.py` ignored; one entrypoint failure is sandbox `rm`; PC1 mobile parity by reading | evidence files on branch | High (matches CR 11-24 count; not re-run by me) |
| compliance-specialist | done (no-change shortcut) | AMBER unchanged; CS-27 look-back unconfirmed | `ls-remote`, PR list | High |
| mlro-user | done | HP4 REFUTED by controlled re-run (stale lists refuse onboarding); HP5 new, low; HP3 carried as PLAUSIBLE | driver log `log_stale26.json` | High for HP4/HP5; HP3 carry is wrong (below) |
| skeptic | done | RED carried; HP5 CONFIRMED Low; HP3 REFUTED again; lists untested probes | file:line refs | High (I checked HP5 citations) |

## 3. Consolidated findings
| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-178 ST-1** ad-hoc `/screen` (web + mobile) runs on stale lists and returns an unlabelled CLEAR, while onboarding fails closed | **LOW-MEDIUM** | lead (from skeptic's untested list) | (listed as untested) | **CONFIRMED (lead)**: `st1_adhoc_screen_on_stale_lists_2026_11_26.py` exit 0; no freshness check in `engine.py:255`, `routers/screening.py:59-113`, `mobile.py:556`; nothing in `screen.html` | HELD `scripts/proposals/2026-11-26-lead-adhoc-screen-stale-notice.md`; **Nadhir: label vs block** |
| **L-179 HP5** refusal text "Admin → Refresh sources" vs button "Refresh sanctions lists now" | LOW (wording) | mlro-user | CONFIRMED Low | **CONFIRMED**: `manager.py:363` vs `admin.html:235`, `dashboard.html:23`; no test references the old string (`grep -rn "Refresh sources" tests/` empty) | HELD, same proposal file (one-line diff) |
| HP4 stale lists → 0 alerts | none | mlro-user | REFUTED | **REFUTED** (role's own controlled re-run + `manager.py:360-364`) | Closed |
| HP3 no overdue-review indicator | none | mlro-user (carried as PLAUSIBLE) | REFUTED | **REFUTED** (closed 11-25: `dashboard.html:215-230`, `customer.html:153`) | Closed; mlro-user's carry is stale, not a disagreement on facts |
| `test_entrypoint.py` failure (`rm: command not found`) | none (env) | red-team, CR, QA, compliance | environmental | PLAUSIBLE env; QA says it passes with `PATH=/usr/local/bin:/usr/bin:/bin` | Note; unverified on clean runner/CI |
| PC1/PC1b mobile parity | carried | red-team | agree | PLAUSIBLE→consistent (reading only) | HELD 11-20 proposal |
| L-177 F-2 onboard commit-before-screen | LOW | compliance (#411) | — | **CONFIRMED**, re-run today exit 0 | HELD 11-25 proposal |
| L-176 F-1 disposition race | LOW-MEDIUM | compliance | Low-Med | **CONFIRMED**, re-run today exit 0 | HELD 11-24 proposal |
| L-166 DB1 / CS-28 / CR-48 | MEDIUM-HIGH | 5 roles | High | CONFIRMED 11-24 (no code change) | HELD 11-20 §1; **Nadhir** |
| L-163 CS-27 look-back | HIGH (operational) | compliance, skeptic | carried | post-deploy re-screen **unconfirmed** | **Nadhir** |
| L-174, L-175, L-172/L-171, L-170, L-168, L-167, CS-30, L-164, L-162, L-159, L-161, L-156, L-173, L-169 | as 11-24 | | | CONFIRMED 11-24; not re-run (master unchanged) | HELD as 11-24 |
| CR-52/53/54, CS-31, SL2, RT trial fail-open INFO, CR-50/51 and older carried set | as 11-25 | | | unchanged | carry |

**Adjudication.** ST-1 LOW-MEDIUM, not Medium: the stale data is not deleted (a name already on the old list still hits), lists refresh every 4h, and the dashboard 24-hour banner (`dashboard.html:9-25`) warns every signed-in operator; but the result page itself, and the mobile JSON, say CLEAR with no caveat, which is the screen an officer acts on for a walk-in. It is inconsistent with the deliberate fail-closed rule at onboarding. HP5 LOW, agree with skeptic and mlro-user. No factual contradictions between roles; the only divergence is mlro-user carrying HP3 after two refutations (code evidence wins). Duplicates: HP5 raised by mlro-user and confirmed by skeptic (one item).

## 4. Combined assessment
1. No application change for three days; full suite green on this SHA (two independent runs: QA 3023/2/0, red-team 2999/2/0 minus entrypoint).
2. One new confirmed gap (ST-1) found by probing untested ground, as the skeptic suggested; HELD with a small label fix.
3. F-1 and F-2 still reproduce on master.
4. All Medium-or-above items remain HELD; none moved.
5. Decisions, not discovery, remain the bottleneck.

## 5. Corrections I made
Scratch venv (Python 3.11.18, `requirements.txt` only; OCR not exercised), `PYTHONPATH=.`, branch app code identical to master. No existing file edited; no `/system/*` call; no network beyond git and pip.
- Owed from 11-25: none.
- New `repro_lead/st1_adhoc_screen_on_stale_lists_2026_11_26.py`, exit 0:
  ```
  ST1 datasets_fresh after backdating to 2026-01-01: False
  ST1 onboard on stale lists: refused (Cannot onboard: no fresh mandatory sanctions dataset available. Ask an MLRO to run Admin → Refresh sources)
  ST1 ad-hoc screen on stale lists: CLEAR  'Zainab Omar Khalid' - 0 candidates, no hits >= 0.85
  ST1 ScreeningResult fields=[...'unscreenable'] stale/fresh flag present=False
  ST1 static checks: {'web /screen checks freshness': False, 'mobile /screen checks freshness': False, 'screen.html mentions freshness': False}
  ```
  The same run also shows HP5's string verbatim.
- New `scripts/proposals/2026-11-26-lead-adhoc-screen-stale-notice.md` (HELD): label diff for web + mobile, test sketch, HP5 one-line diff.
- Re-ran `f1_disposition_race_2026_11_24.py` and `f2_onboard_commit_before_screen_2026_11_25.py`: both exit 0, output identical to prior runs.
- Evidence: `reports/daily/2026-11-26/evidence/lead_checks_2026_11_26_on_f3c8227.txt`. Commit SHA: in the final reply.

## 6. Decisions needed from Nadhir
1. **CS-27 look-back (urgent, carried):** confirm a refresh + `rescreen_all` ran after 2026-11-18 14:36 UTC, review its alerts (UN first), record the window (from at least 2026-10-04).
2. **Exact-name floor (L-166 + L-170):** Option B recommended, DB2 in the same PR.
3. **Delisting (L-171/172/174/175):** as 11-25.
4. **F-1 guard:** approve the two-line status guard.
5. **F-2:** approve `onboarding_incomplete` marking (or the single-transaction rewrite).
6. **ST-1 (new):** label stale ad-hoc results (recommended) or refuse like onboarding; HP5 wording fix can ride along.
7. Carried: CR-53, PEP fold (L-168 + PC1 + CS-30), EDD (L-169), EV1+EV4, CR-45, L-156 + L-162, L-159, L-149, L-152, L-154, L-145/L-146, runbook, correct-and-refile, L-135, L-132/L-131, corpus, goAML XSD (+EV2), `github-advanced-security` 402.

## 7. Next run: carried over
- Owed by the lead: none.
- Still untested by anyone (skeptic's list): re-screen of existing customers on stale lists (`rescreen_all`), mobile onboarding on stale lists (code path `mobile.py:667` catches `StaleDatasetsError`, not exercised), F-1 with two real writers.
- Re-run the carried lead scripts plus `f1_`, `f2_`, `st1_` if master moves in screening/review/freeze/onboarding code.
- Landing order: CS-27 follow-ups (L-164 + CT1 + CT2) with L-166/L-170 + DB2; L-168 + CR-49; delisting set with F-1; L-169; then F-2, ST-1 + HP5, EV1+EV4, CR-52 and the rest.
