# Skeptic report, 2026-11-13 (origin/master `9219e2623b3a3ba7e73a20e44c703ab80df7e900`, unchanged since 11-08)

## Headline: AMBER
Master did not move; today's new findings are all in operator administration and are real: one MLRO can switch off the second-reviewer rule for the whole firm in one click, the web guard against removing the last MLRO tells the user to "promote another operator" when no promote control exists, and a reactivated operator gets their old password back.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-11-13 02:39 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-11-13. The no-new-finding shortcut applies to code-reviewer, QA, compliance and red-team (none new), but not to mlro-user (SO1, RL1-RL3), so I read the code behind those. Other roles' reports are data. No outbound request, no `/system/*` call, no new script; I did not re-run my fourteen scripts because no code changed since 11-08.

## Inputs
`git ls-remote origin refs/heads/master` -> `9219e2623b3a3ba7e73a20e44c703ab80df7e900`; `git log 9219e26..origin/master` is empty; highest PR is #462. All five role branches present at the first fetch. The last full-suite result stands (`2945 passed, 2 skipped`, four independent runs on this SHA).

## Verdicts
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| SO1 one MLRO can turn single-operator mode on for the whole organisation, even with other operators present | mlro-user | **CONFIRMED by code; long-known design, now shown to be unconstrained** | Medium -> Medium | `admin_set_single_operator` (`api/routers/admin.py:341-366`) checks only that the caller is an MLRO with a valid CSRF token, then `set_org_single_operator_mode`; it never counts active operators. `review.py:329-345` then records dismissals as `single_operator` and applies them with no second reviewer. I cited this exact route on 10-04 (as `app.py:3360-3386`) as the reason the four-eyes bypass was Medium rather than High: the control could already be disabled by the people it checks. Today's run shows it with an MLRO, an officer and a second MLRO present. What mitigates it: the change is audited (`org.single_operator_set`) and each affected dismissal carries the `single_operator` flag, so it is detectable after the fact. What does not: nothing stops it, and the page text says "genuinely one compliance officer" without enforcing it. A reasonable rule: allow "on" only when there is exactly one active operator, or require a second MLRO to confirm, and show the flag in the audit export. |
| RL1 an operator's role cannot be changed, yet the last-MLRO error says to promote another operator | mlro-user | **CONFIRMED by code** | Low-Medium -> Medium (with MA1) | The web guard says "Cannot deactivate the last active MLRO. Promote another operator to MLRO first." (`routers/admin.py:~552`); I confirmed on 11-12 that neither surface has a role-change route. So the advice is impossible to follow, and the only way to a second MLRO is creating a new account with a new email. This matters beyond wording: it raises the cost of ever getting to two MLROs, which is exactly what MA1's protection (and SO1's remedy) assume. |
| RL2 reactivating an operator restores their previous password | mlro-user | **CONFIRMED by code** | Low-Medium -> Low/Medium | The web reactivate handler I read on 11-12 (`routers/admin.py`, after `check_limit`) runs only `UPDATE operators SET is_active=1`. Deactivation revokes sessions but leaves the hash. An operator removed for cause regains access with the credential they already know, plus their stored MFA enrolment, unless the MLRO also resets the password. Fix: require a password reset (or force one at next login) on reactivation. |
| RL3 reactivating an already active operator says success and writes a duplicate audit row | mlro-user | **CONFIRMED by code** | Low -> Low | The handler has no `is_active` check before the update and the audit call. Cosmetic, but it pollutes the audit trail. |
| Web/mobile four-eyes parity | red-team | **AGREE, clean** | none | Red-team drove the screening-alert flow through both surfaces: same officer cannot confirm own proposal, MLRO confirm closes, repeat refused, confirm on an unproposed alert refused. Matches the operator-id rule fixed on 11-02. |
| Admin create and reset parity | red-team | **AGREE** | none | Matches my own read on 11-12. |

Carried findings: no code changed, so every 11-12 verdict stands (MA1/LM1, RP1 and the gender rewrite, SS3b/SS5, RT1-RT3, SS1b, SS4, K2, CS-24 residual, CS-5, CS-13, CS-14, 3.1, BL1, BL2, N3b, F2b, N8b, K1, I1/H1/D1, A1 residual, CR1-CR3, UBO1b).

## What the team missed
1. **Operator administration is a single design problem, not five findings.** MA1 (last MLRO deactivated on mobile), RL1 (no role change), RL2 (reactivation keeps credentials), SO1 (anyone can disable four-eyes) and the earlier "demote/promote impossible" all come from the same gap: the admin surface was built operator-by-operator and has no model of the organisation's required roles. A short spec ("always at least one active MLRO; going to two requires promotion; four-eyes off only with one active operator; reactivation resets credentials") would give the fix wave one target.
2. **SO1 is the answer to a question the team has been circling since 10-04.** Every four-eyes finding was rated down because single-operator mode exists; that is only a valid defence if the mode is hard to enter by mistake or malice. It is not. Either lower four-eyes severities permanently (accept the control is advisory) or constrain SO1.
3. **Reactivation plus MFA.** A reactivated MLRO keeps their MFA secret and their backup codes. Nobody has checked whether `forget-devices` or a backup-code reset is triggered on deactivation; if the trusted-device cookie survives, a removed operator's old device may skip MFA after reactivation. I did not test this.
4. **The daily loop has now probed web/mobile parity four days running** (admin deactivate, reset, create, four-eyes). The yield was one real drift. The remaining parity surface is customer-side routes (red-team listed it) and is probably low yield.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** whether the instance-level `AMLKIT_SINGLE_OPERATOR_MODE` is set in production and how it interacts with the per-organisation setting (mlro-user could not tell); who holds the admin API secret for the no-MLRO recovery; production SMTP; `UAEPASS_ENV`; Stripe configuration; front-end login rate limiting; bucket versioning; whether the legacy-proposal scripts have been run on production.
- **Primary legal text (BLOCKED):** whether four-eyes review is a regulatory requirement or a product choice (SO1's severity depends on it); whether an entity may lack an MLRO; RT1, CS-13, CS-14, the AED 55,000 threshold.
- Not re-run: the full suite and tenant sweeps, my fourteen scripts (no code change), mlro-user's `roles13` and `single13` drivers, reactivation with MFA and trusted devices (point 3), customer-side web/mobile parity.
- Not checked: the GitHub PR list directly (connector unavailable); I relied on `git log` and the roles' statements.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402 (last seen 10-24).

## Files and commit
`reports/daily/2026-11-13/skeptic.md` and the fourteen scripts in `repro_skeptic/` (unchanged) on `routine/2026-11-13-skeptic`, based on master `9219e26`. No existing application file edited. The commit SHA is in the final reply.
