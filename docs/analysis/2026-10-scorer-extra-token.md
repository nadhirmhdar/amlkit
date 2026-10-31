# Scorer sensitivity to one extra name token or one attribute mismatch (L-3)

Status: analysis only. `amlkit/match/scorer.py` and `DEFAULT_THRESHOLD` (0.85) are unchanged.
Scores below were produced by calling `score_entity()` on the listed name
`AHMED ABD AL-JALEEL AL-HASNAWI` (Person, country `ly`, born 1975-03-12, male) unless the row says otherwise.
"Name" is the name score before attribute adjustments; "Final" is after them.

## Before / after table

"Before" is the query as listed (exact). "After" is the same person with one change that a real
onboarding file commonly produces. Alert = final score >= 0.85.

| # | Change from the exact query | Name | Final | Alert | Mechanism |
|---|-----------------------------|------|-------|-------|-----------|
| 1 | none (control: exact name) | 1.000 | 1.000 | yes | exact canonical match short-circuits |
| 2 | +1 token in the middle (`Ahmed Mohammed Abd Al-Jaleel Al-Hasnawi`) | 0.767 | 0.767 | **no** | recall 0.767 (the extra token earns nothing), precision 1.0 |
| 3 | +1 token at the end (`... Al-Hasnawi Al-Baghdadi`) | 0.698 | 0.698 | **no** | family-name weight (1.3) lands on the extra token, so the real family name earns the normal 1.0 weight |
| 4 | +2 tokens | 0.566 | 0.566 | **no** | recall falls to 0.566 |
| 5 | -1 token (`Ahmed Al-Jaleel Al-Hasnawi`) | 0.604 | 0.604 | no | recall 0.697, precision 0.667 |
| 6 | listed name has +1 token (query `Mohammed Rashid Hassan` vs `MOHAMMED RASHID HASSAN AL-MAKTOUM`) | 0.900 | 0.900 | yes | recall 1.0, precision 0.75: the scorer tolerates a *listed* extra token but not a *query* extra token |
| 7 | exact name, country differs (`ae` vs `ly`) | 1.000 | 0.800 | **no** | -0.20 |
| 8 | exact name, DOB year differs | 1.000 | 0.850 | yes (at the line) | -0.15 |
| 9 | exact name, gender differs (typo in the file) | 1.000 | 0.800 | **no** | -0.20 |
| 10 | exact name, country and DOB day differ | 1.000 | 0.550 | **no** | -0.20 and -0.25 |
| 11 | #2 plus country mismatch | 0.767 | 0.567 | no | penalties stack on an already-low name score |
| 12 | #2 with DOB and country both matching the listing | 0.767 | 0.767 | **no** | agreeing attributes add nothing |

## What this shows

1. **A single extra query token is enough to lose a full listed name.** Every listed token is present
   (precision 1.0), yet the score falls from 1.00 to 0.77 (middle token) or 0.70 (trailing token).
   Middle names, a second family name, a "bin"/"ibn" chain and patronymics are routine in UAE
   onboarding files, so this is the common case, not an edge case.
2. **The scorer is asymmetric.** A query that is a subset of the listed name (row 6) scores 0.90 and
   alerts; the listed name as a subset of the query (rows 2-4) does not. The 0.40 precision weight was
   calibrated against the first direction (see the comment in `name_score`); the second direction has no
   corresponding relief.
3. **One wrong attribute is enough to drop a verbatim name** (rows 7, 9, 10). A country or gender field
   that is merely wrong in the customer file, rather than evidence of a different person, suppresses the
   alert with no indication in the queue that a 1.00 name match was discarded.
4. **Positive attributes never rescue.** Row 12: a matching DOB and country do not lift a 0.77 name
   score. Only an identifier match (`W_IDENTIFIER_MATCH = 0.95`) can, and customer files rarely carry
   one that is also on the list.
5. The 0.85 threshold sits within one penalty of the common cases: 1.00 - 0.15 = 0.85 (row 8) alerts, but
   1.00 - 0.20 = 0.80 (rows 7, 9) does not.

## Recommendation

Do not change a constant in isolation: each of the options below moves the false-positive rate that
`tests/test_matching.py` pins, and the golden set there is too small to calibrate a change. In order:

1. **Review band, no new alerts.** Record every candidate scoring 0.65-0.85 *with name_score >= 0.95
   before adjustments, or with all listed tokens present* on the screening row and show it as
   "possible match - below threshold" on the screening result and customer page. Nothing enters the
   alert queue and the FP rate is unchanged, but the silent-miss class in rows 2-4, 7, 9 becomes visible.
   This is additive and needs no calibration.
2. **Containment rule.** When every listed token is matched (precision 1.0) and the query has at most
   one unmatched token, floor the name score at about 0.88. Rows 2 and 3 would alert; a single-token query
   still cannot (its recall already caps it). Measure against the false-positive suite before adopting; the
   risk is long common-name chains such as `Mohammed Ali Hassan` matching a three-token listing.
3. **Cap the stacked attribute penalty, and treat a mismatch as a downgrade flag rather than a
   suppressor** when the name score is >= 0.95: keep the alert but show "country differs" prominently.
   Whether that increases analyst workload acceptably needs a week of production counts (alerts that
   would have been raised by name alone).
4. **Positive attributes**: add a small credit (for example +0.05 each for matching DOB year and country)
   only after (1) has produced data on how often those occur alongside a name score of 0.7-0.85.

Needs a product decision from the owner: which of 1-3 to adopt, and the acceptable increase in
reviewable alerts per 1,000 customers. Option 1 is safe to implement first.
