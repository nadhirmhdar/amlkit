# Lead consolidated report: 2026-11-25

## 1. Headline: AMBER (master unchanged; no new defect from the roles; the lead's owed-optional F-2 is now reproduced, LOW)
Master `f3c8227121fbec1d4c3860c63b4a383a4656f975` (`git ls-remote`, today), same SHA as the 2026-11-24 lead report; `git log f3c8227..origin/master` empty. No PR opened or merged since #468; roles report only draft #411 updated (docs/agent reports, no code). All six role branches present on the first fetch. Run date 2026-11-25 UTC. Not a pure "no change" run because mlro-user and red-team raised new (minor) items.

## 2. Per role
| Role | Job | One-line result | Evidence quality | My confidence |
|---|---|---|---|---|
| code-reviewer | done (no-change shortcut) | GREEN, nothing new; CR-52/53/54 carried | `ls-remote` only | High |
| qa-regression | done (no-change shortcut) | GREEN; last full run 3023/2/0 on this SHA stands | `ls-remote`, `git log` | High |
| red-team | done | Trial expiry enforced at 7-day grace (REFUTED as problem); unparseable/NULL `trial_ends_at` fails open (info, by design) | script + evidence on branch | High (consistent with documented rule; not re-run by me) |
| compliance-specialist | done (no-change shortcut) | AMBER unchanged; CS-27 look-back still unconfirmed | `ls-remote`, PR list | High |
| mlro-user | done | Stale-list banners consistent (HP1 ok); HP2 low; HP3 PLAUSIBLE low-med; HP4 not determined | driver logs | Medium: HP3/HP4 explained by code (below) |
| skeptic | done | RED carried; HP3 REFUTED, HP4 explained (fail-closed onboarding), HP2 seed artefact | file:line refs | High (I checked each citation) |

## 3. Consolidated findings
| id | Sev (lead) | Raised by | Skeptic | Lead verdict | Action |
|---|---|---|---|---|---|
| **L-177 F-2** onboard commits customer before screening; a fault after the commit leaves an active, unscreened, unrated customer whose reference cannot be retried | **LOW** | compliance (from #411) | — | **CONFIRMED (lead)**: `f2_onboard_commit_before_screen_2026_11_25.py` exit 0; commit at `manager.py:424`, `screen()` at `manager.py:460` | HELD `scripts/proposals/2026-11-25-lead-onboard-commit-before-screen.md` |
| HP4 0 alerts after aging lists | none | mlro-user | explained | **REFUTED as a defect**: `manager.py:360-363` raises `StaleDatasetsError` before any INSERT when `datasets_fresh` is false, so nothing was onboarded (intended fail-closed) | Close. mlro-user may re-run with fresh lists |
| HP3 no overdue-review indicator | none | mlro-user | REFUTED | **REFUTED by code**: `dashboard.html:215-230` "Due for periodic review" from `due_for_review` (`manager.py:1010-1028`, `next_review <= today`, active only); not rendered by me. Note: it reads the *latest* `risk_assessments` row, so a backdate on an older row would not show | Close |
| HP2 "No successful load recorded yet" beside aged datasets | none | mlro-user | seed artefact | Agree: `admin/ops.html:25` reads `system.last_refresh`, not dataset rows | Close |
| RT trial fail-open on unparseable/NULL `trial_ends_at` | INFO | red-team | agree | PLAUSIBLE (role evidence, matches CLAUDE.md "unknown period end fails open") | Note; optional hardening |
| L-176 F-1 disposition race | LOW-MEDIUM | compliance | Low-Med | **CONFIRMED (lead)**, re-run today exit 0 | HELD 11-24 proposal |
| L-166 DB1 / CS-28 / CR-48 | MEDIUM-HIGH | 5 roles | High | CONFIRMED 11-24 (no code change) | HELD 11-20 §1; **Nadhir's decision** |
| L-163 CS-27 look-back | HIGH (operational) | compliance, skeptic | carried | post-deploy re-screen **unconfirmed** | **Nadhir's decision** |
| L-174, L-175, L-172/L-171, L-170, L-168, L-167, CS-30, L-164, L-162, L-159, L-161, L-156, L-173, L-169 | as 11-24 | | | CONFIRMED 11-24; not re-run (master unchanged) | HELD as 11-24 |
| CR-52 / CR-53 / CR-54 / CS-31 / SL2 / red-team INFO / CR-50, CR-51 and the older carried set | as 11-24 | | | unchanged | carry |
| SL1 | LOW (latent) | mlro-user | REFUTED prod | REFUTED for production (11-24) | Note |
| L-158 DOB1 | — | | | FIXED by #466 | Closed |

**Adjudication.** F-2 LOW (not Low-Med): it needs an unexpected exception between two statements in one request; `busy_timeout=30000` makes lock faults rare; the screening gap closes at the next list refresh because `rescreen_all` selects every active customer (`engine.py:569-570`), but the missing risk rating never self-heals and the customer is invisible to `due_for_review`. HP3 and HP4 are closed on code evidence; I side with the skeptic. No contradictions on facts between roles today. Duplicates: F-2 = #411 finding 2.

## 4. Combined assessment
1. No application change for two days; full suite last green on this SHA (3023/2/0, QA 11-24).
2. Today's role findings are all minor or refuted; the one new confirmed item (F-2) is LOW and HELD.
3. F-1 still reproduces on master (exit 0).
4. All Medium-or-above screening/delisting items remain HELD awaiting decisions; nothing moved.
5. The risk is unchanged: decisions, not discovery, are the bottleneck.

## 5. Corrections I made
Scratch venv (Python 3.11.18, `requirements.txt` only; OCR not exercised), `PYTHONPATH=.`, branch app code identical to master (`git diff origin/master HEAD -- amlkit` empty). No existing file edited; no `/system/*` call; no network beyond git.
- **Owed-optional (11-24): verify F-2.** Done. New `repro_lead/f2_onboard_commit_before_screen_2026_11_25.py`, exit 0:
  ```
  F2  onboard raised: database is locked (simulated)
  F2  customer rows=[(1, 'active')] screenings=0 risk_assessments=0 alerts=0
  F2  retry with same reference: IntegrityError: UNIQUE constraint failed: customers.org_id, customers.reference
  F2  active customer left unscreened and unrated (UN-listed name)=True
  ```
  The fault is injected by wrapping `manager.screen` in-process (stand-in for any post-commit exception). Proposal + diff + test: `scripts/proposals/2026-11-25-lead-onboard-commit-before-screen.md` (HELD).
- Re-ran `f1_disposition_race_2026_11_24.py`: exit 0, identical output. Other carried scripts not re-run (master unchanged).
- Files created: the repro, the proposal, `reports/daily/2026-11-25/evidence/lead_checks_2026_11_25_on_f3c8227.txt`, this report. Commit SHA: in the final reply.

## 6. Decisions needed from Nadhir (unchanged except item 5)
1. **CS-27 look-back (urgent, carried):** confirm a refresh + `rescreen_all` ran after 2026-11-18 14:36 UTC, review its alerts (UN first), record the window (from at least 2026-10-04).
2. **Exact-name floor (L-166 + L-170):** Option B recommended, DB2 in the same PR.
3. **Delisting (L-171/172/174/175):** soft-delist; whether "delisted before execution" may close a freeze obligation; drop or fix the `delisted` option in the UI.
4. **F-1 guard:** approve the two-line status guard (11-24 proposal).
5. **F-2 (new, low):** approve marking a half-onboarded customer `onboarding_incomplete` (or prefer the single-transaction rewrite).
6. Carried: CR-53 granted trials, PEP fold (L-168 + PC1 + CS-30), EDD (L-169), EV1+EV4, CR-45, L-156 + L-162, L-159, L-149, L-152, L-154, L-145/L-146, runbook, correct-and-refile, L-135, L-132/L-131, corpus, goAML XSD (+EV2), `github-advanced-security` 402.

## 7. Next run: carried over
- Owed by the lead: none.
- Re-run the 11 carried lead scripts plus `f1_...` and `f2_...` if master moves in screening/review/freeze/onboarding code (run `ev1`, `checks_18`, `checks_17` from inside `repro_lead/`).
- Landing order unchanged: CS-27 follow-ups (L-164 + CT1 + CT2) with L-166/L-170 + DB2; then L-168 + CR-49; then delisting set with F-1; then L-169; then F-2, EV1+EV4, CR-52 and the rest.
