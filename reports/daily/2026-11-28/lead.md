# Lead consolidated report: 2026-11-28

## 1. Headline: AMBER (master unchanged for the fifth day; no new defect, SS2/ST-1 now shown on mobile too)
Master `f3c8227121fbec1d4c3860c63b4a383a4656f975` (`git ls-remote`, today). This is the same SHA as the 11-24 to 11-27 lead reports. No PR has been opened or merged since #468; compliance reports that only draft #411 was updated (docs only). All six role branches were present on the first fetch. Run date 2026-11-28 UTC. This is not a "no change" run, because mlro-user ran a new mobile pass (MS1-MS3) and the skeptic added a repro.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done (no-change shortcut) | GREEN; CR-52/53/54 carried | `ls-remote` only | High |
| qa-regression | done (no-change shortcut) | GREEN; 11-24 full run (3023/2/0) stands | `ls-remote`, `git log` | High |
| red-team | done | `test_entrypoint.py` passes 24/24 with a real `rm` on PATH, so it is an environment artefact; PC1 carried | evidence file | High (consistent with the test's `shutil.which` stub-bin design) |
| compliance-specialist | done (no-change shortcut) | AMBER unchanged; CS-27 look-back still unconfirmed | `ls-remote`, PR list | High |
| mlro-user | done | Mobile onboarding fails closed (MS1, fine); mobile `/screen` has no staleness flag (SS2); MS2 and MS3 | driver + JSON evidence | High for SS2. MS2's main claim is wrong (see below) |
| skeptic | done | DS1 reproduced with a script; SS2-mobile CONFIRMED (Medium) | script + file:line | Medium: the DS1 repro forces OFAC to mandatory, which is not the production config |

## 3. Consolidated findings
| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| L-178 ST-1 = **SS2** (web **and mobile**) ad-hoc `/screen` returns a verdict on stale lists with no staleness field | LOW-MEDIUM (kept) | lead, mlro-user, skeptic | Medium | **CONFIRMED**: `st1_` exit 0 today; code read `mobile.py:558-578`, which has no freshness check and a response without a staleness key | HELD `scripts/proposals/2026-11-26-lead-adhoc-screen-stale-notice.md` (already includes the mobile diff, `lists_stale`) |
| L-180 DS1 freshness gate passes when any one mandatory list is fresh | LOW-MEDIUM (kept) | skeptic, lead | Medium | **CONFIRMED** by two independent repros (lead `ds1_` exit 0; skeptic `partial_stale_gate.py` exit 0) | HELD `2026-11-27-lead-freshness-gate-all-mandatory.md`; **Nadhir: block or warn** |
| MS3 `/api/v1/datasets` has `last_refresh` but no breach verdict | INFO | mlro-user | info | CONFIRMED (role evidence) | Would be covered by ST-1's `lists_stale`; no separate proposal |
| MS2 mobile refusal text points to "Admin → Refresh sources"; the role says mobile has no refresh action | LOW (wording only) | mlro-user | Low | **Partly REFUTED**: mobile has `POST /api/v1/admin/refresh` for MLROs (`mobile.py:1679-1687`), so the action exists. Only the web-UI wording is a nit | Fold into HP5 (L-179) |
| MS1 mobile onboarding on stale lists | none | mlro-user | REFUTED | REFUTED (503 fail-closed, same as web) | Closed |
| `test_entrypoint.py` `rm` failures | none (env) | CR, QA, compliance, red-team | env | **Closed as environment**: red-team 24/24 with `/usr/bin:/bin` first; QA gives the same workaround. Whether CI runs it is still unchecked | Note; red-team's test-hardening idea is optional |
| L-179 HP5 refusal wording | LOW | mlro-user | Low | CONFIRMED 11-26 | HELD 11-26 proposal (now also covers MS2) |
| L-176 F-1 disposition race | LOW-MEDIUM | compliance | Low-Med | CONFIRMED, `f1_` exit 0 today | HELD 11-24 proposal |
| L-177 F-2 onboard commit-before-screen | LOW | compliance | — | CONFIRMED, `f2_` exit 0 today | HELD 11-25 proposal |
| L-166 DB1 / CS-28 / CR-48 | MEDIUM-HIGH | 5 roles | High | CONFIRMED 11-24 | HELD 11-20 §1; **Nadhir** |
| L-163 CS-27 look-back | HIGH (operational) | compliance, skeptic | carried | post-deploy re-screen **unconfirmed** | **Nadhir** |
| PC1/PC1b, L-174, L-175, L-172/L-171, L-170, L-168, L-167, CS-30, L-164, L-162, L-159, L-161, L-156, L-173, L-169, CR-52/53/54, CS-31, SL2, CR-50/51, HP2 and the older carried set | as 11-27 | | | unchanged (master unchanged) | HELD/carry as 11-27 |

**Adjudication.**
- **DS1 stays LOW-MEDIUM, not Medium.**
  - The skeptic's script inserts `ofac_sdn` with `is_mandatory=1` directly. In code, OFAC is `is_mandatory=False` (`ofac.py:23`), as are EU and UK.
  - The realistic case is therefore still "UN fresh, UAE stale" or the reverse, which the lead's 11-27 repro covers.
  - The two repros agree on the mechanism (`loader.py:290-292` returns True on the first fresh row).
  - Stale entities are kept and the dashboard shows a breach, so the miss is limited to new designations made while the list is stale.
- **SS2 stays LOW-MEDIUM.**
  - Mobile adds a second surface but no new failure mode.
  - mlro-user's run shows a listed name still hits on stale lists (`clear:false`, 1 hit).
  - The risk is again a false CLEAR for new designations only.
  - The skeptic rates it Medium on the same facts. I keep Low-Medium because the existing names are still caught.
- **MS2 is downgraded.** The role says the device cannot follow the instruction, but MLROs can refresh from mobile at `/api/v1/admin/refresh`. The text is still web-specific.
- **One change covers DS1, ST-1/SS2 (web + mobile), MS3 and HP5/MS2.** The skeptic and I agree on this. It should land as one PR.

## 4. Combined assessment
1. There has been no application change for five days. The full suite is green on this SHA (QA 3023/2/0), and the entrypoint failures are now explained as an environment problem.
2. No new defect class was found today. Mobile mirrors the web: onboarding fails closed and ad-hoc screening is silent about stale lists.
3. DS1, ST-1, F-1 and F-2 all still reproduce on master (exit 0 today).
4. All Medium-or-above items remain HELD and none moved. Owner decisions are what is holding them up.
5. CS-27 is still the most urgent item.

## 5. Corrections I made
Scratch venv (Python 3.11.18, `requirements.txt` only; OCR not exercised), `PYTHONPATH=.`. Branch `routine/2026-11-28-lead` is built on `routine/2026-11-27-lead`, and its app code is identical to master (`git diff --stat origin/master HEAD -- amlkit` was empty). No existing file was edited, no `/system/*` endpoint was called, and there was no network traffic beyond git and pip.
- Owed from 11-27: none.
- Re-ran `ds1_`, `f1_`, `f2_` and `st1_`, plus the skeptic's `partial_stale_gate.py` from its branch. All five exit 0 (true exit codes recorded separately; the first pass's `exit=` lines were tail's and are marked as superseded in the evidence file):
  ```
  ds1_partial_stale_gate_2026_11_27.py exit=0
  f1_disposition_race_2026_11_24.py exit=0
  f2_onboard_commit_before_screen_2026_11_25.py exit=0
  st1_adhoc_screen_on_stale_lists_2026_11_26.py exit=0
  skeptic_psg.py exit=0      (datasets_fresh -> True with ae_local_terrorists + un_sc_consolidated stale)
  ```
- Checked MS2 by reading the code: `grep` on master shows `1679:@router.post("/admin/refresh")` in `mobile.py`.
- No new proposal was needed: the 11-26 ST-1 proposal already contains the mobile `lists_stale` diff.
- Evidence: `reports/daily/2026-11-28/evidence/lead_checks_2026_11_28_on_f3c8227.txt`. Commit SHA: in the final reply.

## 6. Decisions needed from Nadhir
1. **CS-27 look-back (urgent, carried):** confirm that a refresh plus `rescreen_all` ran after 2026-11-18 14:36 UTC, review its alerts (UN first), and record the window (from at least 2026-10-04).
2. **Exact-name floor (L-166 + L-170):** Option B is recommended, with DB2 in the same PR.
3. **Staleness bundle (DS1 + ST-1/SS2 web+mobile + MS3 + HP5/MS2):** For onboarding, I recommend blocking unless every mandatory list (UN + UAE) is fresh. For ad-hoc screening, I recommend labelling stale results rather than refusing them. All of it should land in one PR.
4. **F-1:** approve the two-line status guard. **F-2:** approve the `onboarding_incomplete` marking.
5. **Delisting (L-171/172/174/175):** as 11-25.
6. Carried: CR-53, PEP fold (L-168 + PC1 + CS-30), EDD (L-169), EV1+EV4, CR-45, L-156 + L-162, L-159, L-149, L-152, L-154, L-145/L-146, runbook, correct-and-refile, L-135, L-132/L-131, corpus, goAML XSD (+EV2), `github-advanced-security` 402.

## 7. Next run: carried over
- Owed by the lead: none.
- Still untested by anyone:
  - `rescreen_all` (and mobile alert rescreen) on stale or partly stale lists
  - F-1 with two real writers
  - a full render of `_alert_panel.html` through its route
  - whether CI runs `tests/test_entrypoint.py`
  - DS1 over HTTP rather than at function level
- If master moves in screening, review, freeze, onboarding or ingest code, re-run `ds1_`, `st1_`, `f1_`, `f2_` and the earlier lead scripts.
- Landing order (unchanged):
  1. CS-27 follow-ups (L-164 + CT1 + CT2) with L-166/L-170 + DB2
  2. L-168 + CR-49
  3. the delisting set with F-1
  4. L-169
  5. the staleness bundle (DS1 + ST-1 + HP5 + MS2/MS3)
  6. F-2, EV1+EV4, CR-52 and the rest
