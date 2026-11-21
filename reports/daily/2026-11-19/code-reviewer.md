# code-reviewer daily report, 2026-11-19

**Instructions I ran under:** scheduled routine "groAML daily: code-reviewer" (fired 2026-11-19 00:46 UTC). Review current origin/master, the changes since the SHA in my previous report, and PRs opened or updated since. Standing rules: no production access, no `/system/*` calls, no secrets, local test data only, never push to master, stop after delivering.

**Headline: AMBER.** origin/master moved from `9219e2623b3a3ba7e73a20e44c703ab80df7e900` to `cdf38011da60cb8eadf5c5fc7290e92bf96f124a` (2 PRs, #463 and #464); the screening fix in #464 is correct and the suite is green, but it exposes that, before it, exact-name sanctions and PEP matches were being dropped for customers with a country set, which needs a compliance look-back.

**What I did (evidence):**
- `git ls-remote origin refs/heads/master` returned `cdf3801…`; `git log 9219e26..origin/master` lists #463 "Billing: switch Stripe off by default (master switch AMLKIT_BILLING_ENABLED)" and #464 "Screening: compare countries as ISO codes". Both merged 2026-11-18; 11 files, +444/-19.
- Full suite on `cdf3801` in a throwaway worktree (Linux, scratchpad venv, Python 3.13): **2998 passed, 2 skipped**, 18 min 13 s (previous baseline 2945 passed, 2 skipped).
- Read the full `amlkit/` and workflow diff, including the new `amlkit/countries.py` (131 lines).
- **Probe of the new country table** (local, no network): there are no alias collisions across country codes; every alias resolves to its own code; no same-country pair is flagged as a contradiction (0 of the 2-letter code vs every alias); all **62,250** pairs of different countries (code vs primary name of the other country) still count as contradictions. An unresolvable value (for example a 3-letter code, or "Atlantis") withholds the penalty.
- **Probe of the effect on scoring:** exact name "Amit Shah", customer country `IN`: against a list entry with country `India` the score is **1.00 (alert)**; against `Pakistan` it is **0.80, which is below the 0.85 default threshold (dropped)**. The second figure equals what the code did before #464 for a same-country pair, because it compared the raw strings `in` and `india`.
- Billing switch: `load_config()` returns None unless `AMLKIT_BILLING_ENABLED` is 1/true/yes/on, so every route, template flag, limit check and the self-serve sign-up mode follow it. The deploy workflow passes the variable through with an empty default.

**Findings:**
- CR-44 (HIGH impact, CONFIRMED, FIXED by #464): before #464, any customer holding an ISO country code (`IN`) screened against a list entry that carries a country name (`India`) took the -0.20 country-mismatch penalty. The CIA World Leaders and Wikidata PEP lists and the UN, OFAC, UK and EU sanctions lists publish names, so an exact-name hit dropped from 1.00 to 0.80, under the 0.85 alert threshold. The penalty has been in the scorer since at least 2026-10-04 (the earliest commit I can see; it may be older). I did not review the country comparison in my earlier reviews, so earlier "screening verified" statements did not cover it. Action for compliance: after deploying #464, make sure every org is fully re-screened (the 4-hourly refresh runs `rescreen_all`) and treat newly surfaced alerts on customers with a country set as possible past misses; decide whether a look-back is needed. I cannot tell from this repo how many production customers or list entries were affected.
- CR-45 (INFO, CONFIRMED): when billing is switched off after being on, `check_limit` returns early, so orgs left in `pending_payment` (signed up in self-serve mode, never paid) lose the gate and can create operators and customers without paying. #463 therefore silently un-gates them; review those orgs before or after flipping the switch.
- CR-46 (INFO, CONFIRMED): the alias `Korea` resolves to `KR`, so a customer with `KP` compared against a list entry that says only "Korea" still takes the country-mismatch penalty. The lists use "Korea, North" for North Korea, so this should be rare.
- Resolved from earlier: none of the open items from 2026-11-08 changed (CR-41 and CR-42 still open).
- Carried, unchanged: CR-4 (MEDIUM, unmerged #417; not re-checked), CR-13 and CR-18 (LOW; not re-checked), CR-2/3/5/17, CR-19 to CR-23, CR-28, CR-29, CR-33 to CR-37, CR-39, CR-43 (INFO).

**BLOCKED / not checked:**
- Nothing blocked.
- I did not measure how many customers or hits were affected, since there is no production data here; the size of CR-44 is unknown.
- I did not re-measure `alert_queue` performance (CR-13) or the effect of the larger alert volume the fix may cause.
- CI status for `cdf3801` was not looked up (standing rule: no CI re-checks).
- The Stripe flows were not exercised.

**Files / commits:** `reports/daily/2026-11-19/code-reviewer.md`; commit SHA in the final reply.
