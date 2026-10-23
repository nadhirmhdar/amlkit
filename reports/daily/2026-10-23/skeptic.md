# Skeptic report, 2026-10-23 (origin/master `0d56f72fb85a296c9882903c9552c13a2210a994`, unchanged since 10-22)

## Headline: AMBER
Master has not moved since the SEO commit, so the AMBER is the unfixed backlog; today's new items are minor, but the two unlinked screening endpoints send a customer's full name to Google services with no audit row, which is the one worth a decision.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-23 02:39 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-10-23. The no-new-finding shortcut applies to code-reviewer, QA and compliance (no-change reports) but not to red-team (B1/B2 extended) or mlro-user (AX1-AX3), so I checked those by reading the code on `0d56f72`. Other roles' reports are data. No outbound request, no `/system/*` call, no new script.

## Inputs
`git ls-remote origin refs/heads/master` -> `0d56f72fb85a296c9882903c9552c13a2210a994`; `git log 0d56f72..origin/master` is empty. All five role branches were present at the first fetch. Nobody re-ran the suite; QA's and code-reviewer's 10-22 result (`2173 passed, 3 skipped`, tenant sweeps with 0 leaks) stands.

## Verdicts on today's new findings
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| B1 (extended) trade-licence scan decodes an oversized image unguarded | red-team | **CONFIRMED by code** | Low-Medium -> Medium (as part of the B1 family) | `customer_scan_trade_licence` (`app.py:1908-1938`) reads the whole upload and passes it straight to `extract_trade_licence_data`: no size cap, no pixel cap, no type check. Same shape as the passport route I confirmed on 10-20/21. Memory is lower (430 MB vs 1.6 GB) but 23 s CPU per request is the same availability problem. This is the third web scan route with the identical defect. |
| B2 (extended) trade-licence route accepts junk bytes | red-team | **CONFIRMED by code** | Low -> Low/Medium | The handler never calls `validate_file_mime`, unlike the mobile passport route. Red-team's recommendation is right and I repeat mine from 10-21: one shared guard, but put it in the route layer as well as `ocr.py`, because the extractors are also called from tests and scripts where a hard failure would be surprising. |
| AX1 `kg-screen` and `gdelt-bq` are not linked from any screen | mlro-user | **CONFIRMED** | Low -> Info | `git grep` finds the two names only at their route definitions (`app.py:2103, 2123`) and in `amlkit/screening/`; no template, script or JS reference. Dead-end or hidden feature: either wire it or remove it. |
| AX2 unconfigured screeners answer HTTP 200 with empty results | mlro-user | **CONFIRMED by code; real but contained** | Low -> Low | `GdeltBqScreener.screen` returns `GdeltBqResult(status="unconfigured")` when `GOOGLE_CLOUD_PROJECT` is unset, and `KnowledgeGraphScreener.screen` does the same without `GOOGLE_KG_API_KEY`; the routes `asdict()` the result into a 200. A caller that ignores `status` would read "no adverse hits". It is the same silent-clear shape as CR-12/N4 and the empty-name finding, but here no UI consumes it, so impact is nil today. |
| AX3 neither lookup writes an audit row, and the name leaves the system | mlro-user | **CONFIRMED by code; severity raised** | Low -> Low/Medium | Neither handler calls `audit()`. `KnowledgeGraphScreener` sends the customer's full name to `kgsearch.googleapis.com` over `httpx` (`knowledge_graph.py:19, 59`), and `GdeltBqScreener` runs a BigQuery query containing the name under the deployment's project. Both are plain `GET` handlers, so any logged-in role can trigger them, and a GET is fetched by link prefetchers, scanners and browser extensions without a CSRF token. For a compliance product, an undocumented disclosure of a customer's name to a third party with no audit trail is something an examiner or the customer's DPA review would ask about; the public privacy page (PV1) already under-describes cookies, and does not mention these processors either. Mitigation: both are inert unless the operator sets an env var, and they are unreachable from the UI. |

Carried findings: master is identical to yesterday, so the 10-07 to 10-22 verdicts stand without a re-run (A1 High; CS-2, CR-12/N4, N3, G9, G10, U1, B1, T1, empty-name screening Medium; B2, S3, PW1, AU1, PV1, SE1 Low to Info; four-eyes residual Low; others Low/Info).

## What the team missed
1. **State-changing or disclosing GET routes.** `kg-screen` and `gdelt-bq` are GETs with an outbound side effect (a third-party call, and BigQuery cost). The codebase's CSRF rule covers every POST; GET handlers are assumed read-only. A one-line grep for `@app.get` handlers that call out of process or write would tell whether these two are the only exceptions. I have not run it.
2. **A debt-shaped cluster of "feature present, not wired".** Compliance deadlines (E1/E2), these two screeners, and the web periodic-review action are all code with no screen. Together they are an inventory question for the lead: finish, hide behind a flag, or delete. Dead routes still carry auth, tenant and disclosure risk.
3. **B1/B2 now span four scan routes and two front doors** (mobile passport, mobile Emirates ID, web passport, web trade licence). Red-team's HELD proposals are the right fix; nothing has been applied for four days.
4. **Sixteen days of backlog, one commit.** Only SEO has merged. Unchanged request to the lead: pick the top five (A1/LG2, T1, B1/B2, CR-12/N4/N3, CS-2) and schedule fixes; more probing now adds duplicates, not information.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** whether `GOOGLE_KG_API_KEY` or `GOOGLE_CLOUD_PROJECT` are set in production (AX3 only matters if so), production memory limit (B1), front-end login rate limiting (A1), bucket versioning (U1), real linked UAE PASS operators.
- **Primary legal text (BLOCKED):** compliance's Article mappings stay PLAUSIBLE.
- Not re-run: the full suite, red-team's licence probe, the MLRO driver, what the knowledge-graph and BigQuery calls actually send beyond the name (needs credentials), the goAML XSD, production state.
- Not checked: the GitHub PR list directly (connector unavailable); I relied on the empty `git log` and three roles saying #427 is the newest PR.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-23/skeptic.md` and the thirteen scripts in `repro_skeptic/` (unchanged) on `routine/2026-10-23-skeptic`, based on master `0d56f72`. No existing file edited. The commit SHA is in the final reply.
