# Red-team report 2026-11-16 -- origin/master `9219e26` (unchanged since 2026-11-08; newest PR #462)

## Headline: AMBER
Master and the PR list did not move; testing Persian, Urdu, Sindhi and Kurdish letter variants of Arabic names found that 11 of 86 one-letter spellings fall below the alert threshold, the most realistic being the Urdu heh (ہ).

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged and no PR opened or merged since my last report, so shortcut applied (one area, short report). No conflict with my standing instructions.
- Assumptions: pure-function scoring of `match.scorer.name_score` against Latin listings (no database); the four baseline names and their Latin spellings are my own choices, so the miss rate is indicative, not a measurement; severities are my judgement.

## What I did
Closed my "Persian/Urdu letter variants beyond hand-picked cases" item. `repro_redteam/probe_arabic_letter_variants.py` takes four Arabic names (3 two- or three-token names, one single-word name pair) and, for each, applies one substitution at a time from a list of 29 letter variants (Persian, Urdu, Sindhi, Kurdish, Pashto and hamza/maksura forms) plus 7 formatting variants (tatweel, shadda, a vowel mark, a trailing Eastern-Arabic digit, a zero-width joiner, NBSP separators, double spaces). 86 variants were scored against two Latin listings each; the baselines all score 1.00. Evidence: `reports/daily/2026-11-16/evidence/probe_arabic_letter_variants_on_9219e26.txt`.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| N3c | Low-Medium | CONFIRMED | 11 of 86 variants score 0.35 to 0.60, below the 0.85 threshold, so a query spelled that way would not alert against the Latin listing. Misses: Urdu heh `ہ` (for `ه`), Sindhi kaf `ڪ`, veh `ڤ` (for `ف`), Kurdish reh `ڕ` and lam `ڵ`, peh `پ` (for `ب`), zheh `ژ` (for `ز`); and, for the short name `فاطمة الزهراء`, also teh marbuta typed as teh and tah typed as teh. Short names fall hardest (0.35 to 0.45). The fold table in `names/arabic.py` already covers `ی ک ے ۓ ھ` and the hamza/alef forms. Urdu heh is the realistic one: it is the standard heh on Urdu keyboards. |

Proposal: `scripts/proposals/2026-11-16-new-findings.md` (HELD).

## Refuted / clean
- 75 of 86 variants alert (score at or above 0.85), including every hamza/alef/maksura form, Persian yeh and kaf, `ھ`, `گ` for `ق`, `چ` for `ج`, `ث`/`ذ`/`ض`/`ظ`/`غ` swaps, and all seven formatting variants (tatweel, shadda, vowel mark, trailing digit, zero-width joiner, NBSP, double space).
- Baselines score 1.00 for all four names.

## Earlier findings still open (unchanged)
TD1 (direction spelling defeats structuring), TD2, LM1, N3b Cyrillic homoglyph, SS1b, SS2b, SS3b/SS5, SS4, BL1, BL2, F2b, N8b, K1, K2, I1, H1, D1, A1 residual. See `reports/daily/2026-11-15/red-team.md` and `2026-11-14`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: the effect of folding the ambiguous letters (`پ ژ چ گ`) on false positives against a real list; multi-letter variants; matching against a full sanctions list; the real Checkout round trip; GCS runtime; the live UAE PASS sandbox.

## Files and commit
`repro_redteam/probe_arabic_letter_variants.py`, `scripts/proposals/2026-11-16-new-findings.md`, `reports/daily/2026-11-16/` (this file + evidence). Branch `routine/2026-11-16-red-team`. No application code edited.
