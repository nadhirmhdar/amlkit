# Red-team report 2026-11-19 -- origin/master `cdf3801` (changed since 2026-11-18: PRs #463 and #464 merged)

## Headline: GREEN
Both changes hold up: the billing master switch keeps every Stripe surface off and sign-up invite-gated by default, and the new country comparison removes a real false-negative without opening a new evasion; I found one low-severity ambiguity and one pre-existing crash that real data should not reach.

## Instructions I ran under
- Role: red-team operator (Agent 4), local scratch data only; no production, no `/system/*`, no secrets; never master; additive-only (fixes as HELD proposals).
- Routine "groAML daily: red-team": master changed (`9219e26` -> `cdf3801`, PRs #463 billing off by default, #464 country compare as ISO codes), so I probed the changed code first. No conflict with my standing instructions.
- Assumptions: pure-function scoring plus an in-process `TestClient` on a scratch database; Stripe keys set to dummy values and never contacted; severities are my judgement. Full test suite not run.

## What I did
Read the 4-file app diff (`billing/__init__.py`, `billing/stripe_client.py`, new `countries.py`, `match/scorer.py`). `repro_redteam/probe_country_compare.py`: crash test over 529 odd input pairs, 19 scored cases with an exact name match (so only the country term moves), and a check that no alias in the 250-code table collides. `repro_redteam/probe_billing_switch.py`: 13 spellings of `AMLKIT_BILLING_ENABLED` with the Stripe keys present. Evidence: `reports/daily/2026-11-19/evidence/probe_{country_compare,billing_switch}_on_cdf3801.txt`.

## Findings
| Id | Sev | Status | Summary |
|---|---|---|---|
| CT1 | Low | CONFIRMED | The bare alias `Korea` resolves to South Korea (`KR`). A North Korean customer (`KP`) screened against a list entry whose country is just `Korea` is therefore treated as a provable mismatch and loses 0.20: an exact name match scores 0.80, below the 0.85 alert threshold. The UN and OFAC lists write `Korea, North` (that case alerts, 1.00), so this only matters for a source that uses the bare word. Drop the bare `Korea` alias or make it resolve to "cannot tell". |
| CT2 | Info | CONFIRMED | `_countries_contradict` calls `.strip()` on every value, so a non-string country in a list record (a number, tuple or set) raises `AttributeError` (262 of 529 odd combinations). The old code had the same call, and the sources I know write strings, so I could not reach it with real data; a type guard (`isinstance(c, str)`) would make an odd record skip the penalty instead of failing the screening. |

## Refuted / clean
- Country fix works: customer `IN` vs list `India` now alerts at 1.00 (it was dropped to 0.80); `RU` vs `Russian Federation`, `AE` vs `United Arab Emirates`, `IR`, `SY`, `MM`/`Burma`, `KP` vs `Korea, North`, `GE` vs `Georgia` all alert at 1.00.
- A true mismatch is still penalised (`IN` vs `Pakistan` 0.80), so the F2b policy behaviour is unchanged.
- Failing toward the alert: an unresolvable value on either side (`Hindustan`, `Bharat`, a customer typo, an invalid code `ZZ`, an empty customer country, a joined string such as `Pakistan, India`) applies no penalty and alerts at 1.00. A listing with both countries also alerts.
- No alias collides across country codes (368 aliases, 250 codes); the lookup is accent- and case-insensitive.
- Billing switch (#463): with the Stripe keys present, the flags unset, empty, `0`, `false`, `no`, `off`, `maybe` and `2` all leave billing off: `/billing` and the webhook return 404, the sign-up form shows the invite field and refuses a registration without the code. Flags `1`, `true`, `YES`, ` on ` and `On` switch it on (open sign-up works, `/billing` redirects to login, webhook 400 for an unsigned call). `/pricing` stays public in both states, as designed. The self-serve findings from 2026-11-04 to 2026-11-09 (SS1b, SS2b, SS3b/SS5, SS4) now apply only once the switch is turned on.

## Earlier findings still open (unchanged)
N3c, TD1, TD2, LM1, N3b, GV1, SS1b, SS2b, SS3b/SS5, SS4 (dormant while billing is off), BL1, BL2, F2b, N8b, K1, K2, I1, H1, D1, A1 residual. See `reports/daily/2026-11-18/red-team.md` and `2026-11-16`.

## BLOCKED / not checked
- BLOCKED: `github-advanced-security` 402 quota error on push (last seen 2026-10-24; not re-tested).
- Excluded by design: `/system/*`, production, real UAE PASS and Stripe endpoints.
- Not checked: the full test suite on `cdf3801`; the country field coming from the real CIA/Wikidata/UN/OFAC/UK/EU feeds (I used the names the code comments list, not live data); the effect on the false-positive rate against a real list; the real Checkout round trip; GCS runtime; the live UAE PASS sandbox.

## Files and commit
`repro_redteam/probe_country_compare.py`, `repro_redteam/probe_billing_switch.py`, `reports/daily/2026-11-19/` (this file + evidence). Branch `routine/2026-11-19-red-team`. No application code edited, no new proposal file (CT1/CT2 are described above).
