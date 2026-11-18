# HELD: DOB penalty inversion (L-158) and one-sided alert facts (L-159 EX1/EX3)

Status: HELD for human review (scorer weights and route/query/template logic; the lead may not edit them).
Master: `9219e2623b3a3ba7e73a20e44c703ab80df7e900`. Repro: `repro_lead/checks_2026_11_18.py` (DOB1, EX1, EX3, GV1) and `repro_lead/probe_dob_onboard_2026_11_18.py`.

## L-158 DOB1: a near-miss date of birth is punished harder than a wrong year

`amlkit/match/scorer.py:29-30`:

```python
P_DOB_DAY_MISMATCH = -0.25
P_DOB_YEAR_MISMATCH = -0.15
```

`scorer.py:272-277` checks the year first and only reaches the day check (`elif`) when the years agree. So:

| customer DOB vs listed 1975-03-12 (exact name, same nationality) | adjustment | score | alert (threshold 0.85) |
|---|---|---|---|
| 1975-03-13 (one day off) | dob_day_mismatch -0.25 | 0.75 | **no** |
| 1975-12-03 (DD/MM swap) | dob_day_mismatch -0.25 | 0.75 | **no** |
| 1975-12-31 | dob_day_mismatch -0.25 | 0.75 | **no** |
| 1976-03-12 (one year off) | dob_year_mismatch -0.15 | 0.85 | yes |
| 1981-01-02 (six years off) | dob_year_mismatch -0.15 | 0.85 | yes |

The closer the DOB, the lower the score. The two most common data-entry faults on a correct identity (DD/MM swap, off-by-one day from a Hijri/Gregorian conversion or time zone) fall in the suppressed band. On a UAE Local Terrorist List entry that suppresses the freeze trigger with no alert and no trace on the queue.

Proposed diff (one of two options; Nadhir chooses):

Option A (minimal, restores ordering):
```diff
-P_DOB_DAY_MISMATCH = -0.25
-P_DOB_YEAR_MISMATCH = -0.15
+P_DOB_DAY_MISMATCH = -0.10   # same year, different day: weakest contradiction (typos, DD/MM swaps)
+P_DOB_YEAR_MISMATCH = -0.15
```
With this an exact-name match with a same-year DOB scores 0.90 (alert), a different year 0.85 (alert, as today).

Option B (Option A plus a floor): never let contradicting-feature adjustments take an exact canonical-name match (`name_score == 1.0`) on a mandatory dataset below `DEFAULT_THRESHOLD`; the adjustments stay in `score_detail` so the reviewer sees them. Wider effect: also reverses the country-mismatch suppression (F2b, `1975-03-12 IN -> NO ALERT` in the probe), so it needs a false-positive estimate on real data first.

Also treat a DD/MM swap (`q[5:7]==c[8:10] and q[8:10]==c[5:7]`) as no contradiction.

Tests to add (`tests/test_scorer_dob.py`):
1. `score_entity(N, [N], query_birth_date="1975-03-13", cand_birth_date="1975-03-12").score >= 0.85`.
2. Same with `"1975-12-03"` (swap) `>= 0.85`.
3. Monotonic: score for a one-day difference `>=` score for a one-year difference.
4. `grep -rln "dob_day_mismatch\|P_DOB" tests` finds no test pinning the weights today, so none is expected to break; run the full suite anyway (other calibration tests may pin exact scores).

Severity: MEDIUM (lead). False negative on an exact name; not HIGH only because a matching ID number still overrides (`W_IDENTIFIER_MATCH`) and the fixture is synthetic, not production data.

## L-159 EX1 + EX3: the alert shows only the listed person's facts

`queries.py:504-508` selects `e.birth_date`, `e.countries` from the entity but only `c.id, c.reference, c.full_name` from the customer; `alerts.html:80-81, 140-141` render the listed DOB/countries. `_alert_panel.html:17-32` renders neither side's DOB/countries nor the reason text.

Proposed diff:
```diff
# queries.py alert_queue select
-               c.id AS customer_id, c.reference, c.full_name AS customer_name,
+               c.id AS customer_id, c.reference, c.full_name AS customer_name,
+               c.birth_date AS customer_birth_date, c.nationality AS customer_nationality,
```
```diff
# alerts.html (both row variants) and _alert_panel.html
+  {% if a.customer_birth_date or a.customer_nationality %}
+  <div class="muted small">Customer: {% if a.customer_birth_date %}DOB {{ a.customer_birth_date }}{% endif %}
+    {% if a.customer_nationality %} · {{ a.customer_nationality|upper }}{% endif %}</div>
+  {% endif %}
```
Panel: add Listed DOB / countries rows and the `score_detail` explanation macro used by the queue row. Mobile `/api/v1/alerts` gains the two fields automatically (same query).
Test: onboard an alerting customer with DOB 1981-01-02 / LY; assert both `1981-01-02` and `1975-03-12` appear on `/alerts` and on `/alerts/{id}/panel`.

## GV1 (red-team): see `scripts/proposals/2026-11-18-new-findings.md` on `routine/2026-11-18-red-team`. Lead agrees on the fix's intent, with a correction: the installed `graphviz` 0.21 `Digraph.pipe()` has **no** `timeout` parameter (checked: `inspect.signature` shows format/renderer/formatter/neato_no_op/quiet/engine/encoding only). Replace both `dot.pipe()` calls with `subprocess.run(["dot", "-Tsvg"], input=dot.source.encode(), capture_output=True, timeout=10, check=True).stdout.decode()` inside the existing `except Exception` (which already catches `TimeoutExpired`), so expiry yields "diagram unavailable". Also note: a `dot` that exits 0 with empty output currently returns `""`, not `None` (lead check GV1).
