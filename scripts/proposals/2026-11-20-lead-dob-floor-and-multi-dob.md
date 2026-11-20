# HELD: DOB penalty inversion (DB1/CS-28), one DOB per list entry (CR-49), PEP fold without identity (PC1)

Lead, 2026-11-20, master `bfb0253`. HELD for human review: every change below touches `match/scorer.py`,
`match/engine.py`, the ingest adapters or the schema, which the routine may not edit.
Repro: `repro_lead/checks_2026_11_20.py` (exit 0 while any item reproduces).

## 1. DB1 / CS-28: same-year DOB difference penalised harder than a wrong year

`amlkit/match/scorer.py:30-35,306-314`: `P_DOB_DAY_MISMATCH = -0.25` applies to a same-year date that
is not a "near miss" (#466 covers same-month and dd/mm swap only); `P_DOB_YEAR_MISMATCH = -0.15` applies to
any year difference. Exact name, listed 1975-03-04: month typo 1975-08-04 = 0.75 (silent); 1995-03-04 = 0.85 (alert).
A list-side `01-01` placeholder (common for "year known only") also hits -0.25 (red-team DB1).

Two options (owner picks):

**A. Minimal (numbers only).** Make the same-year penalty no harsher than the year penalty:

```diff
-P_DOB_DAY_MISMATCH = -0.25
+P_DOB_DAY_MISMATCH = -0.15   # never harsher than a wrong year (DB1/CS-28)
```

plus: treat a candidate DOB of `YYYY-01-01` as year-only (skip the day/month comparison).
Leaves every year-different case at exactly 0.85 = threshold (zero margin; any second penalty silences it).

**B. Floor for exact canonical names (skeptic's and lead's preference).** In `score_entity`, after summing
adjustments: if the name score is 1.0 (exact canonical equality) and no identifier contradicts, the DOB/gender/
country adjustments may lower the score but not below `DEFAULT_THRESHOLD`; record `exact_name_floor: true` in
the detail so the alert shows why it was kept.

```diff
     score = max(0.0, min(1.0, score))
+    if best_score >= 1.0 and score < DEFAULT_THRESHOLD:
+        features["exact_name_floor"] = round(DEFAULT_THRESHOLD - score, 4)
+        score = DEFAULT_THRESHOLD
     return ScoreResult(score=score, name_score=best_score, ...)
```

(Against `scorer.py:319-325` on `bfb0253`; an identifier *contradiction* is not modelled today, so no carve-out is needed yet.) Closes the whole class (CS-27-shape country
penalty, DB1, gender, F2b residual) instead of re-tuning each weight. Cost: more alerts on true mismatches
for exact common names; volume unknown without production data. Option B with a per-org threshold above 0.85
needs the floor to use the org threshold, which `score_entity` does not receive today; pass it from `screen()`.

Tests to add (a "must alert" corpus, skeptic's point 2): exact name × {month typo, month+day, 01-01 placeholder,
invalid month, year ±1, year ±20} × {country same, ISO vs name, missing}; each must alert.

## 2. CR-49: adapters store one birth date per entry

`ingest/un.py:71-74` (`ind.find` = first `INDIVIDUAL_DATE_OF_BIRTH`), `ofac.py:84-87` (first `dateOfBirthItem`),
`eu.py:162-165` (first `birthdate`); `uk.py:118-125` keeps the last. Lists commonly give alternates.
Effect (lead run): alternate DOB in the same year as the first → 0.75, silent; in another year → 0.85, zero margin.
Also UN `TYPE_OF_DATE=BETWEEN` (FROM_YEAR/TO_YEAR) yields `None` (no penalty, safe side).

Proposal: store all dates (additive column `entities.birth_dates TEXT` JSON, `_MIGRATIONS` entry; keep
`birth_date` = first for compatibility), and in `engine.screen` score against each and keep the best
(`min` penalty). Adapter change: collect every `DATE`/`YEAR` (UN), every `dateOfBirth` (OFAC), every
`calendarDate`/`year` (EU), every DOB (UK). Option B above also neutralises this for exact names.

## 3. PC1 / CR-47 / CS-29: PEP fold without an identity signal

`match/engine.py:216-246`: key = sorted canonical name tokens + countries do not contradict (`_countries_contradict`
is False when either side is empty). Two different PEPs "John Smith" (GB vs no country) → 1 hit labelled
"Same person also listed on". PEP-only; sanctions never fold (red-team, code-reviewer verified).

```diff
-                if (k.is_pep and not k.is_sanction and _pep_name_key(k.caption) == key
-                        and not _countries_contradict(...)):
+                if (k.is_pep and not k.is_sanction and _pep_name_key(k.caption) == key
+                        and not _countries_contradict(...)
+                        and not _dobs_contradict(birth_by_entity.get(k.entity_id),
+                                                 birth_by_entity.get(h.entity_id))):
```

and store caption, countries and birth date per `also_listed` item so the panel can show them
(template wording: "Possibly the same person, also listed on"). CS-30 (re-alert when the kept entity changes)
needs suppression keyed on the folded group; leave for a later PR.

## 4. DB2: no record of sub-threshold candidates

Store the top N (e.g. 5) candidates under threshold per screening with their adjustments (new table
`screening_candidates`, additive). Turns a CS-27/DB1-shape miss into something an examiner can query.
Pairs with L-165 (scorer version on `screenings`).
