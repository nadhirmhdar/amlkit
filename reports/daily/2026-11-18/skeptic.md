# Skeptic report, 2026-11-18 (origin/master `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, unchanged since 11-08)

## Headline: AMBER
Master has not moved in eleven days; the two new findings are small and both check out against the code: the alert screen shows only the listed person's date of birth and countries and never the customer's own, and a hung Graphviz process has no timeout.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-11-18 02:39 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-11-18. The no-new-finding shortcut applies to code-reviewer, QA and compliance (no-change reports), but not to red-team (GV1) or mlro-user (EX1-EX3), so I read the code behind those. Other roles' reports are data. No outbound request, no `/system/*` call, no new script; I did not re-run my scripts because no code changed since 11-17.

## Inputs
`git ls-remote origin refs/heads/master` -> `9219e2623b3a3ba7e73a20e44c703ab80df7e900`; `git log 9219e26..origin/master` is empty; highest PR is #462. All five role branches present at the first fetch. The last full-suite result stands (`2945 passed, 2 skipped`, four independent runs).

## Verdicts
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| EX1 the alert queue and panel show the listed person's date of birth and countries but not the customer's | mlro-user | **CONFIRMED by code** | Low-Medium -> Medium | The queue query selects `e.countries` and `e.birth_date` from the entity, and only `c.id`, `c.reference` and `c.full_name` from the customer (`queries.py:~504-508`). The template renders `a.birth_date` and `a.countries` next to the dataset (`alerts.html:80-81`, `:140`), which are the listed person's. So the operator sees one side of the comparison that clears most false positives and has to open the customer page for the other. Medium rather than Low-Medium because the cost is not only time: the decision control (four-eyes, reason codes) assumes the reviewer has compared the facts, and this layout makes it easy to dismiss on the name alone. The fix is two columns in the query and two template lines. |
| EX2 matching-engine terms in the reason text ("recall", "precision 0.667", phonetic keys) | mlro-user | **CONFIRMED** | Low -> Low | The scorer's docstrings use recall and precision (`match/scorer.py:40-41, 120-123, 176`) and the reason text reuses the vocabulary. A sentence such as "2 of 3 name parts matched" is a template change, not a scoring change. |
| EX3 the detail panel repeats less than the queue row | mlro-user | CONFIRMED (their run) | Low -> Low | Not re-read in the template; consistent with EX1's layout. |
| GV1 `dot.pipe()` has no timeout | red-team | **CONFIRMED by code** | Low -> Low | `cases/diagram.py:110` and `:156` call `dot.pipe().decode("utf-8")` with no timeout argument and no surrounding wait. Red-team's stub that hangs held the request for 30 seconds (the server's own limit). The real `dot` did not hang even with 200 owners and 10 levels (0.43 s), so exposure needs a broken installation. Realistic fix: pass a timeout and treat expiry as "diagram unavailable", as the missing-Graphviz path already does. |
| Good practice: legal action text per list, exact-match explanation, no alert for mismatched DOB and nationality | mlro-user | **AGREE, REFUTED as defects** | none | The legal action wording matches the `sanctions_scope` rule fixed on 11-01 and 11-02. |

Carried findings: no code changed, so every 11-17 verdict stands (QU1 silent 200-alert cap, QU2/QU3, TD1, TX1-TX3, TD2, CL1/CL2, N3c, NM1/NM2, SO1, RL1-RL3, MA1/LM1, RP1 and the gender rewrite, SS1b, SS3b/SS5, SS4, RT1-RT3, K2, CS-24 residual, CS-5, CS-13, CS-14, 3.1, BL1, BL2, N3b, F2b, N8b, K1, I1/H1/D1, A1 residual, CR1-CR3, UBO1b).

## What the team missed
1. **EX1 sits next to the mismatch rule nobody has tested.** The scorer applies a -0.20 penalty for a country mismatch (F2b) and the product raises no alert for a mismatched DOB and nationality, as mlro-user observes. Together: the system uses the customer's facts to suppress alerts, and the screen that explains an alert hides those facts. The operator cannot tell why an alert did or did not appear. A "why this alert, why this score" panel with both sides' facts would answer EX1, F2b and N3c together.
2. **Another cap without a notice, in a different place.** GV1 is a missing timeout, QU1 a missing paging notice. Both are the same omission as the 10-20 findings: a limit exists elsewhere in the system and is not applied at one call site.
3. **The reports are converging.** Red-team's last five days (Arabic letters, UBO diagram, Graphviz, four-eyes parity, SQL triage) and mlro-user's (queue, closure, transactions, operator admin) are producing Low items with occasional Medium, and the Medium list is long and old. A one-line status table at the top of each report (open, fixed, new since last time) would make the daily output self-summarising and let the loop stop re-describing carried items.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** whether the production image's Graphviz is current and where it is installed; who holds the admin API secret; production SMTP; `UAEPASS_ENV`; Stripe configuration; the sanctions-refresh schedule; front-end login rate limiting; bucket versioning; whether the legacy-proposal scripts have been run on production.
- **Primary legal text (BLOCKED):** whether operators are required to compare the customer's identifiers with the list entry before dismissal (EX1); CL1, CS-13, CS-14, RT1, the AED 55,000 threshold.
- Not re-run: the full suite and tenant sweeps, my fifteen scripts (no code change), mlro-user's explanation-text driver, red-team's `probe_graphviz_failure`, EX3 against the template, the diagram path with a hung `dot`.
- Not checked: the GitHub PR list directly (connector unavailable); I relied on `git log` and the roles' statements.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402 (last seen 10-24).

## Files and commit
`reports/daily/2026-11-18/skeptic.md` and the fifteen scripts in `repro_skeptic/` (unchanged) on `routine/2026-11-18-skeptic`, based on master `9219e26`. No existing application file edited. The commit SHA is in the final reply.
