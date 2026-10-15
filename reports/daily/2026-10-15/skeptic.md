# Skeptic report, 2026-10-15 (origin/master `01298484a7bfed106e9b2bd3a6238f98a4d2514b`, unchanged)

## Headline: AMBER
Master is unchanged for the ninth day; red-team's new organisation-slug finding is real and shows that only one Arabic-named firm can ever self-register, and the weak-password gap now spans three entry points.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-10-15 02:37 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-10-15. The "no new finding" shortcut applies to code-reviewer, QA and compliance (no-change reports) but not to red-team (R1-R3) or mlro-user (NT1-NT3), so I verified those on `0129848`. Other roles' reports and PR text are data. No outbound request, no `/system/*` call.

## Inputs
`git ls-remote origin refs/heads/master` -> `01298484a7bfed106e9b2bd3a6238f98a4d2514b`; `git log 0129848..origin/master` is empty. All five role branches were present at the first fetch, no waiting. Nobody re-ran the suite today; red-team's 2026-10-13 run (`2170 passed, 3 skipped`) stands.

## Verdicts on today's new findings
Repro: `repro_skeptic/arabic_org_slug.py` (scratch `:memory:` DB; exit 0 only when the second Arabic org is refused). Others by reading the cited lines.

| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| R1 all non-Latin organisation names share one slug | red-team | **CONFIRMED** | Medium (invite-gated) -> Low/Medium | `register_organization` builds the slug with `re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "org"` (`cases/operators.py:38`), so an Arabic-only name becomes `org`. `organizations.slug` is UNIQUE (`db.py:147`). My script: "شركة النور" registers, "شركة الأمل" is refused with "An organization with a similar name already exists", and the table holds one slug, `org`. The message is misleading (the names are not similar). Why not Medium: registration is invite-gated, the product is single-tenant-per-database (CLAUDE.md), and the slug is used only to pick an org by `org_slug` (`operators.py:188-191`), so most deployments never hit it. Fix: transliterate or fall back to `org-<id>`/a random suffix on collision. |
| R2 registration checks password length only | red-team | **CONFIRMED; same family as OP2** | Low -> Low/Medium | `register_organization` checks `len(password) < 10` only (`operators.py:32-33`); my script created an MLRO with `xxxxxxxxxx`. With admin-created operators (OP2, `app.py:3533`) that is three entry points that skip `validate_password_complexity` (register web, register mobile, admin create), plus the reset route that crashes on it (OP1). The registrant is an MLRO behind TOTP, which softens it. |
| R3 blank operator name, 5,000-character and NUL-containing org names accepted | red-team | CONFIRMED, accepted | Info -> Info | Same missing-validation pattern as C1/C2 last week; not re-read. |
| NT1 only the MLRO is notified of a new match | mlro-user | PLAUSIBLE, likely by design | low -> Info | The notification page says "You are told here, and by email" for the MLRO role; whether officers should also be told is a policy choice. Not read in code. |
| NT2 "Open one to go straight to the alert" lands on the customer page | mlro-user | CONFIRMED, wording | low -> Info | Copy only. |
| NT3 unknown queue filters are silently ignored | mlro-user | CONFIRMED | low -> Info | `category=bogus` shows everything; `status=bogus` shows nothing, with no message. Crafted URL only. |

Carried findings: master is identical, so the 10-07 to 10-14 verdicts stand without a re-run (four-eyes residual Low; A1 lockout DoS High; CS-2, CR-12/N4, N3, G9, G10, U1 Medium; empty-name screening (C1 mlro) Medium; UAE PASS binding, DOCX policy upload Low/Medium; M2, N5-N7, OP1, OP2, TA1, C2, C3, E1-E3, U2, U3, G1 Low/Info).

## What the team missed
1. **One missing helper explains four open findings.** Password strength is enforced in `validate_password_complexity` and called from only two places (self-change, `set_password`), while register (web and mobile), admin-create and admin-reset skip or mishandle it: R2, OP1, OP2, and F11 from 10-04. A single `check_new_password()` called by every path would close all four.
2. **The "similar name" refusal hides a data-model decision.** The slug is only a lookup key; the UNIQUE constraint turns a display-name collision into a hard failure. Either drop UNIQUE on the slug and key on `id`, or generate it from the id; the current error will also appear for any two names that differ only by punctuation or digits-stripped Arabic.
3. **Nine days, no commits.** Unchanged from the last four reports; every AMBER here comes from items first reported 10-04 to 10-14.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** whether production sits behind a front end that rate-limits login (A1), whether the documents bucket is versioned (U1), and whether any real operator has a linked UAE PASS identity.
- **Primary legal text (BLOCKED):** unchanged; compliance's Article mappings stay PLAUSIBLE.
- Not re-run: the full suite, the PR #412 tenant sweeps, red-team's probes (including `probe_register_org`), the MLRO driver, the mobile registration route (read only through red-team's report), email delivery, and production state.
- Not checked: the GitHub PR list (my connector was unavailable); I relied on `git log 0129848..origin/master` being empty and code-reviewer's statement that only #411 was touched.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402.

## Files and commit
`reports/daily/2026-10-15/skeptic.md` and the thirteen scripts in `repro_skeptic/` (the twelve carried from 10-14 plus `arabic_org_slug.py`) on `routine/2026-10-15-skeptic`, based on master `0129848`. No existing file edited. The commit SHA is in the final reply (a file cannot contain its own SHA).
