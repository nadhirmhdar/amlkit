# Red-team report 2026-11-15 -- origin/master `9219e26` (unchanged since 2026-11-08; newest PR #462)

## Headline: GREEN (for this area) / earlier items still open
Master and the PR list did not move; a property fuzz of the Arabic/Latin name pipeline found no crash and no out-of-range score, and all 13 Arabic spellings of the patronymic and "Al" particles still reach the alert threshold against the Latin listing.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master unchanged and no PR opened or merged since my last report, so shortcut applied (one area, short report). No conflict with my standing instructions.
- Assumptions: pure-function tests of `names.arabic` and `match.scorer` (no database); fuzz uses `hypothesis` with 4,000 generated pairs per property, including lone surrogates, combining-mark storms and bidi controls; severities are my judgement.

## What I did
Name matching is the first of my standing areas, and I had only tested hand-picked spellings. `repro_redteam/fuzz_names.py`: five properties over 4,000 random pairs each, plus a 400,000-character input. `repro_redteam/probe_arabic_particles.py`: 13 Arabic-script variants of "Mohammed bin Salman Al Saud" (bin, ibn with two hamza forms, vowel marks, spaced and fused "Al", missing particles, a "walad" form, a full ancestry chain, short and variant Latin spellings) scored against three Latin listings. I also read `screening/kyt.py` to close yesterday's question about the loose direction string: only the structuring rule groups by direction; velocity does not. Evidence: `reports/daily/2026-11-15/evidence/{fuzz_names,probe_arabic_particles}_on_9219e26.txt`.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| NM1 | Info | CONFIRMED | `canonical_tokens` is not idempotent: `'0B'` gives `['b']` but a second pass on that result gives `[]` (a lone Latin `b` is treated as the "bin" abbreviation). Canonicalisation is applied once to raw names on both sides, so no mismatch results today; it would matter if a canonical form were ever stored and re-canonicalised. |
| NM2 | Info | CONFIRMED | Names made only of particles canonicalise to nothing and are flagged "unscreenable" (`bin`, `ibn`, `al`, `abu`, `de`, `van`, `Al Bin`). That is the intended handling, listed here so reviewers know that an `Abu`-only record needs manual review. Short Latin tokens such as `the` also fold to a single Greek letter (`θ`), so very short tokens can collide with each other. |

## Refuted / clean
- No exception on any input in 4,000 cases per property (includes lone surrogates and bidi controls); score always within [0, 1] and never NaN; identical names always score 1.0; the score is deliberately recall-weighted, so it is not symmetric (e.g. `A` vs `A:0B` 0.80 vs 0.43), which is by design.
- A 400,000-character input canonicalises and scores in 0.8 seconds, so there is no algorithmic blow-up in this layer.
- All 13 Arabic variants alert (scores 0.87 to 1.00 against the 0.85 threshold): `بن`, `ابن` and `إبن` (the last two keep an extra `abn` token and still score 0.97), vowel-marked `بنْ`/`بِن`, spaced and fused `ال`, no particle, no `Al`, `ولد`, the full ancestry chain, a short Latin form (0.87, lowest) and a variant Latin spelling.
- KYT: velocity and large-cash rules do not use the transaction direction, so the spelling gap reported as TD1 on 2026-11-14 affects only the structuring rule.

## Earlier findings still open (unchanged)
TD1 (direction spelling defeats structuring), TD2, LM1, SS1b, SS2b, SS3b/SS5, SS4, BL1, BL2, N3b, F2b, N8b, K1, K2, I1, H1, D1, A1 residual. See `reports/daily/2026-11-14/red-team.md` and `2026-11-12`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: matching against a full sanctions list (the seed has one entry, so latency and false-positive rates at scale are untested); fuzzing the Latin transliteration rules against Persian/Urdu letter variants beyond the earlier hand-picked cases; the real Checkout round trip; GCS runtime; the live UAE PASS sandbox.

## Files and commit
`repro_redteam/fuzz_names.py`, `repro_redteam/probe_arabic_particles.py`, `reports/daily/2026-11-15/` (this file + evidence). Branch `routine/2026-11-15-red-team`. No application code edited, no new proposal.
