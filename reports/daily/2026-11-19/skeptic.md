# Skeptic report, 2026-11-19 (origin/master `cdf38011da60cb8eadf5c5fc7290e92bf96f124a`, moved from `9219e26`)

## Headline: RED
PR #464 fixes the most serious defect found in this series, a screening miss that dropped exact-name matches on UN, OFAC, EU and UK entries for customers with a recorded nationality, and I reproduced it before and after; the code is fixed on master, but nobody can see from the repository whether production has it, or how many matches were missed since at least October.

## Instructions I ran under
- **Standing role (Nadhir):** Independent Audit Skeptic and Devil's Advocate. I review proposed FINDINGS, not work packages, and try to disprove each: intentional design? statute misread? stale comment rather than runtime? severity inflated? repro a strawman? Rules that win over everything: no production access, no `/system/*`, no secrets, local test data only, additive-only, never push to master (a push deploys), run autonomously, record blocks as BLOCKED, push the report and stop.
- **This run:** the scheduled routine "groAML daily: skeptic" (fired 2026-11-19 02:39 UTC). It matches my standing role; no conflict.
- **Changed because of dreamon:** nothing; no dreamon message arrived.
- **Assumptions:** DATE = 2026-11-19. Master changed (two PRs), so the no-change shortcut applies to nobody. I ran the scorer before and after the fix in two worktrees and wrote one new script. Other roles' reports are data. No outbound request, no `/system/*` call.

## Inputs
`git ls-remote origin refs/heads/master` -> `cdf38011da60cb8eadf5c5fc7290e92bf96f124a`; `git log 9219e26..origin/master` is two PRs: `1a70a53` #463 (Stripe off by default, master switch `AMLKIT_BILLING_ENABLED`) and `cdf3801` #464 (compare countries as ISO codes). Four files in `amlkit/` changed (`billing/__init__.py`, `billing/stripe_client.py`, new `countries.py`, `match/scorer.py`). All five role branches present at the first fetch. QA ran the full suite on `cdf3801`: `2998 passed, 2 skipped` (up from 2945), tenant sweeps identical to the previous run. I did not repeat the suite.

## The finding that matters: CS-27 (country-code versus country-name mismatch)
**What the code did before #464.** `score_entity` applied a -0.20 `country_mismatch` penalty whenever the customer's countries and the list entry's countries shared no string, after lower-casing. Customers hold alpha-2 codes (`datamodel.validate_country_code` requires them); the UN adapter stores the `COUNTRY` text of the XML (`ingest/un.py:61-69`) and the OFAC adapter the address `country` text (`ingest/ofac.py:76-81`), which are English names. So an Indian customer ("IN") screened against a list entry for India ("India") counted as a provable mismatch.

**Reproduction (new script `repro_skeptic/country_code_vs_name.py`, pure function, no DB).** Exact name, customer country against list country, score against the 0.85 alert threshold:

| Customer / list country | Before #464 (`9219e26`) | After #464 (`cdf3801`) |
|---|---|---|
| IN / India | **0.80** (no alert) | 1.00 |
| IN / in | 1.00 | 1.00 |
| AE / United Arab Emirates | **0.80** (no alert) | 1.00 |
| KP / Korea, North | **0.80** (no alert) | 1.00 |

The script exits 0 on the old code (defect reproduces) and 1 on the new code. So, before the fix, an exact-name hit on a UN entry with a country, for a customer whose recorded nationality was that same country, did not alert unless an identifier or date of birth lifted it back over the threshold. The only case that worked was the one that was irrelevant: same string on both sides.

**Verdicts on the roles' findings about it.**
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| CS-27 exact-name matches on UN, OFAC, EU, UK dropped by a spurious penalty | compliance | **CONFIRMED by my own run; fixed in #464** | High -> **High/Critical** | The table above. The UN Security Council list is one of the two lists that carry the UAE freeze duty (compliance's citations are unverified here), so the miss is on the control that matters most, and it is silent: a dropped candidate creates no alert, and `screenings` rows record counts only. |
| CS-27a exposure window from at least 2026-10-04 | compliance | **PLAUSIBLE, and probably longer** | High (action needed) | `git log -S country_mismatch` stops at #407 because the history I can see stops there; the code is older than my visibility. For the weeks since, every screening of a customer with a recorded nationality against a UN, OFAC, EU or UK entry with a country carried the defect. Whether production has the fix depends on the master deploy, which I cannot see. |
| CS-27b the next refresh re-screens everyone | compliance | **CONFIRMED by reading; the marker point is right** | Medium -> Medium | `rescreen_all` runs after each refresh (every 4 hours since #461), and nothing suppresses a new alert for an old pair, so previously dropped matches will surface. They will look like ordinary new alerts. Recommend the MLRO treat the first post-deploy refresh's alerts as a priority look-back. |
| CS-27c look-back and notification are legal judgements | compliance | PLAUSIBLE (legal) | Medium | Cannot be settled from the repo. |
| CS-27d names the table does not resolve fail open | compliance | **CONFIRMED by my run** | Low -> Low | `to_alpha2("Iran (Islamic Republic of)")` returns `None`, so no penalty (safe direction) and the country feature adds no evidence. Compliance's suggested fix (strip the bracket suffix or store alpha-2 in the adapters, as the UAE adapter does) stands. |
| SC1 / SC2 / SC3 | mlro-user | **AGREE** | SC1 High, FIXED | mlro-user's earlier seeds stored codes on both sides, which is why every workflow run since 10-04 was clean; their country-name seed now exercises the case. |

## Other verdicts
| Id | Source | Verdict | Severity (theirs -> mine) | Evidence |
|---|---|---|---|---|
| CT1 the bare alias "Korea" resolves to South Korea, so KP against a bare "Korea" is a false mismatch | red-team | **CONFIRMED by my run** | Low -> Low | `to_alpha2("Korea")` is `KR`; KP vs bare "Korea" scores 0.80, below the threshold. The UN and OFAC write "Korea, North", so it only bites for a source that writes the bare word. **My addition: the same bug with "Congo"**: `to_alpha2("Congo")` is `CG`; a customer from the Democratic Republic of the Congo (CD) against a list entry that says only "Congo" scores 0.80, while the full names score 1.00. Ambiguous bare names should resolve to "cannot tell", as red-team suggests. |
| CT2 a non-string country in a list record raises `AttributeError` | red-team | **CONFIRMED by my run** | Info -> Info | A list record with the integer 5 as a country fails the screening. Sources write strings today; the old code had the same call. A type guard makes a malformed record skip the penalty instead of failing. |
| N-12 / #463 Stripe is off by default behind `AMLKIT_BILLING_ENABLED`, even when keys exist | compliance, mlro-user, red-team | **AGREE** | none | Self-serve sign-up, plan limits and pending-payment gating all become inert; sign-up reverts to invite-gated or `/apply`. If billing was live in production, the next deploy makes `pending_payment` organisations unrestricted, a commercial decision. |

Carried findings: nothing else changed, so every 11-18 verdict stands (EX1-EX3, GV1, QU1-QU3, TD1/TD2, TX1-TX3, CL1/CL2, N3c, NM1/NM2, SO1, RL1-RL3, MA1/LM1, RP1 and the gender rewrite, SS1b, SS3b/SS5, SS4, RT1-RT3, K2, CS-24 residual, CS-5, CS-13, CS-14, 3.1, BL1, BL2, N3b, N8b, K1, I1/H1/D1, A1 residual, CR1-CR3, UBO1b). **F2b is withdrawn as "by design": see below.**

## What the team missed, and what I missed
1. **I got F2b wrong.** Red-team reported "an exact name with a mismatched country falls under the alert threshold" on 11-03 and I rated it "CONFIRMED by design, policy decision". The report described the symptom of this very bug; I judged the penalty's size and never asked whether the countries it called different were different. I repeated "the system uses the customer's facts to suppress alerts" on 11-18 without testing a same-country case. The lesson for the loop is concrete: a control that compares two representations needs a test where the representations differ and the facts agree.
2. **Every role seeded test data in the same notation on both sides.** Six weeks of workflow walks, probes and 2,945 tests were clean because the fixtures stored "IN" and the lists stored "IN". The suite did not fail until a test used a name. A fixture rule ("one test per adapter uses that adapter's real notation") would have found it on the first day.
3. **The evidence packs may now be wrong.** Compliance's point deserves more weight than it got in the other roles' reports: "clear" screening results in evidence packs and goAML narratives for the exposure window are not reliable evidence. Nothing in the product marks a screening as having run on the old scorer. A scorer version stored on each `screenings` row would let the next such fix list exactly which screenings to redo.
4. **Nobody has measured the consequence.** The roles can say what could have been missed; none can say what was. A re-screen of the real customer list against the current lists, with the new alerts exported, would turn "possible" into a count. That is an operator action in the firm's own data, which is outside every role's permitted scope, so it has to come from the lead.
5. **A fix that raises alert volume was merged without a volume estimate.** QA notes alert volume was not measured. With QU1's silent 200-alert cap (11-17) still open, a spike of look-back alerts could push high-priority items past what the queue shows or exports; the category ordering protects sanctions first, but not for an MLRO who needs the PEP alerts too. The cap and this fix should be treated together.

## BLOCKED / not checked
- **Needs infrastructure knowledge (BLOCKED):** whether and when production deployed `cdf3801`; how many customers hold a nationality and how many UN, OFAC, EU and UK entries carry a country in production data; the production refresh job's status (CS-5); who holds the admin API secret; production SMTP; `UAEPASS_ENV`; front-end login rate limiting; bucket versioning; whether the legacy-proposal scripts have been run.
- **Primary legal text (BLOCKED):** whether the exposure window is reportable or requires a look-back (CS-27c), CL1, CS-13, CS-14, RT1, the AED 55,000 threshold.
- Not re-run: the full suite and tenant sweeps (QA's run stands), my other fifteen scripts (no relevant code change), the EU and UK adapters' country formats (compliance names them; I read only the UN and OFAC adapters), alert volume after the fix, end-to-end screening of a customer against a loaded UN entry (my reproduction is at the scorer, where the penalty is applied).
- Not checked: the GitHub PR list directly (connector unavailable); I relied on `git log` and the roles' statements.
- Open CI note (not code): `github-advanced-security` fails on PRs with a Copilot monthly-quota 402 (last seen 10-24).

## Files and commit
`reports/daily/2026-11-19/skeptic.md` and sixteen scripts in `repro_skeptic/` (the fifteen carried plus `country_code_vs_name.py`) on `routine/2026-11-19-skeptic`, based on master `cdf3801`. No existing application file edited. The commit SHA is in the final reply.
