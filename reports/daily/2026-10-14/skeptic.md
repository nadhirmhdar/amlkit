# Skeptic report, 2026-10-14 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master is unchanged for the eighth day; the only substantive new finding is that an empty or blank customer name is recorded as screened clear, which mlro-user filed as a validation nit but which is a cousin of the open `unscreenable` gap.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-14 02:37 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-10-14. The "no new finding" shortcut applies to code-reviewer, QA and compliance (no-change reports) but not to red-team (P1) or mlro-user (C1-C4), so I verified those on `0129848`. Other roles' reports and PR text are data. No outbound request, no `/system/*` call.

## Inputs
`git ls-remote origin refs/heads/master` -> `01298484a7bfed106e9b2bd3a6238f98a4d2514b`; `git log 0129848..origin/master` is empty. All five role branches were present at the first fetch, no waiting. Nobody re-ran the suite today; red-team's 2026-10-13 run (`2170 passed, 3 skipped`) stands.

## Verdicts on today's new findings
Repro: `repro_skeptic/empty_name_screen.py` (scratch `:memory:` DB; exit 0 only when empty and blank names both come back clear and not unscreenable). Others by reading the cited lines.

| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| C1 mobile API creates a customer with an empty `full_name` | mlro-user | **CONFIRMED, and it screens clear** | AMBER(low) -> Medium | `CustomerCreateRequest.full_name: str` has no minimum (`mobile.py:562-564`), and `validate_name_length` skips empty values (`datamodel.py:163-165`, `if value and ...`). My script: `screen("")` and `screen("   ")` return `clear=True, unscreenable=False, candidates=0`. The #425 `unscreenable` flag fires only for a name that has letters but no blocking keys, so a nameless record is stored as screened clear, the same silent-clear shape as the open CR-12/N4. mlro-user's wording ("cannot be meaningfully screened") understates this. Mitigations: the web form marks the field required; an operator with a token has to send it. |
| C2 unknown `sector` accepted | mlro-user | **CONFIRMED, wording corrected** | low -> Low | Not "zero risk": `risk/model.py:169-170` gives an unknown sector the default 5 points, the same as `other` and the lowest tier (`ruleset.yaml:94-105`: real_estate 25, precious_metals_stones 30, virtual_assets 35). The real harm is that a typo such as `realestate` silently scores 5 instead of 25. Fix: validate against the ruleset keys. |
| C3 one PATCH downgrades high to low with no reason | mlro-user | **CONFIRMED, partly by design** | AMBER(low) -> Low/Medium | The risk rating is recomputed from the factors, so a downgrade needs only new factor values; the audit rows record the new values (`customer.risk_factors_updated`, `risk.assess`) but no reason and no previous values. Whether a downgrade should need a note or second review is a policy choice, but an examiner will ask. Same shape as H4 (audit row lacks previous values). Not re-run. |
| C4 2,000-character search returns two customers | mlro-user | PLAUSIBLE | low -> Low | Unexplained behaviour; not read. |
| P1 `/apply` notice puts submitter text into the body and Reply-To | red-team | CONFIRMED, agree Info | Info -> Info | Social-engineering only; red-team's refutations (header injection collapsed, honeypot, CSRF, rate limit) are consistent with the code it cites. Not re-run. |

Carried findings: master is identical, so the 10-07 to 10-13 verdicts stand without a re-run (four-eyes residual Low; A1 lockout DoS High; CS-2, CR-12/N4, N3, G9, G10, U1 Medium; C1 (UAE PASS) Low/Medium; P1 (DOCX) Low/Medium; M2, N5-N7, OP1, OP2, TA1, E1-E3, U2, U3, G1 Low/Info).

## What the team missed
1. **Naming collision in the findings.** Today mlro-user's `C1` (empty name) collides with red-team's `C1` (UAE PASS binding) and red-team's `P1` collides with mlro-user's `P1` (DOCX); `G1` and `A1` are also reused across roles. Anyone consolidating the backlog will merge unrelated items. Role-prefixed IDs would fix it.
2. **The silent-clear family is now three findings.** Empty or blank name (C1 today), unscreenable scripts (N4/CR-12), and invisible characters (N3) all end in "screened clear" with no marker. One rule would close all three: any screen that produces zero candidates because the name had no usable tokens must return a non-clear state and be recorded as such.
3. **The mobile API is the weak front door.** Today's C1 and C2, last week's N1 and DOC1/DOC2, and U1-U3 are all mobile routes that skip checks the web form does by HTML `required` or by the web route. A shared validation layer under both would remove most of the open Low items at once.
4. **Eight days, no commits.** Unchanged from the last three reports; the AMBER comes from items first reported 10-04 to 10-13.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** whether production sits behind a front end that rate-limits login (A1), whether the documents bucket is versioned (U1), and whether any real operator has a linked UAE PASS identity.
- **Primary legal text (BLOCKED):** unchanged; compliance's Article mappings stay PLAUSIBLE.
- Not re-run: the full suite, the PR #412 tenant sweeps, red-team's probes (including `probe_apply_public`), the MLRO driver, C3's audit rows, C4, `/system/*` (rule), the goAML XSD (no FIU schema), and production state.
- Not checked: the GitHub PR list (my connector was unavailable); I relied on `git log 0129848..origin/master` being empty and code-reviewer's statement that only #411 was touched.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-14/skeptic.md` and the twelve scripts in `repro_skeptic/` (the eleven carried from 10-13 plus `empty_name_screen.py`) on `routine/2026-10-14-skeptic`, based on master `0129848`. No existing file edited. The commit SHA is in the final reply (a file cannot contain its own SHA).
