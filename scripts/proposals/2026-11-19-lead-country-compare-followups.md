# HELD: follow-ups to #464 (country comparison) — L-163 CT1/CT2/CS-27d, L-164 rescreen nationalities

Status: **HELD for human review** (touches `amlkit/countries.py`, `amlkit/match/scorer.py`,
`amlkit/match/engine.py`; the lead routine is additive-only). Master `cdf3801`.
Repro: `repro_lead/checks_2026_11_19.py`, `repro_lead/probe_dual_nat_rescreen_2026_11_19.py`.

## L-163a CT1 — ambiguous bare names resolve to one country (LOW)
`countries.py:60` maps bare `Korea` -> `KR`; `:36` bare `Congo` -> `CG`; `:96` bare
`Virgin Islands` -> `VI`. A list entry writing only the bare word is then a "provable"
mismatch for a `KP` / `CD` / `VG` customer: exact name scores 0.80 < 0.85, no alert
(output in the lead report). Fix: make these resolve to "cannot tell".

```diff
--- a/amlkit/countries.py
+++ b/amlkit/countries.py
@@
-    "CG": "Congo|Republic of the Congo|Congo, Republic of the|Congo (Brazzaville)|Congo, Rep.",
+    "CG": "Republic of the Congo|Congo, Republic of the|Congo (Brazzaville)|Congo, Rep.",
@@
-    "KR": "South Korea|Korea, South|Korea, Republic of|Republic of Korea|Korea (South)|Korea",
+    "KR": "South Korea|Korea, South|Korea, Republic of|Republic of Korea|Korea (South)",
@@
-    "VI": "U.S. Virgin Islands|Virgin Islands, U.S.|US Virgin Islands|Virgin Islands",
+    "VI": "U.S. Virgin Islands|Virgin Islands, U.S.|US Virgin Islands",
```
Test (add to `tests/test_country_matching.py`):
```python
@pytest.mark.parametrize("bare", ["Korea", "Congo", "Virgin Islands"])
def test_ambiguous_bare_country_names_do_not_resolve(bare):
    assert to_alpha2(bare) is None

@pytest.mark.parametrize("cust,listed", [("KP", "Korea"), ("CD", "Congo"), ("VG", "Virgin Islands")])
def test_ambiguous_bare_name_never_drops_exact_match(cust, listed):
    r = score_entity("Amit Kumar Shah", ["Amit Kumar Shah"], query_countries=[cust], cand_countries=[listed])
    assert r.score >= 0.85
```

## L-163b CT2 — non-string country raises (INFO)
`scorer._countries_contradict` calls `.strip()` on every value; an int in a record raises
`AttributeError` and fails the whole screening. Guard:
```diff
-    q_raw = {c.strip().lower() for c in query_countries if c and c.strip()}
-    c_raw = {c.strip().lower() for c in cand_countries if c and c.strip()}
+    query_countries = [c for c in query_countries if isinstance(c, str) and c.strip()]
+    cand_countries = [c for c in cand_countries if isinstance(c, str) and c.strip()]
+    q_raw = {c.strip().lower() for c in query_countries}
+    c_raw = {c.strip().lower() for c in cand_countries}
```
(A list with only non-strings then behaves as "no country": no penalty, the safe side.)

## L-163c CS-27d — UN parenthetical long forms unresolved (LOW)
`to_alpha2("Iran (Islamic Republic of)")`, `"Venezuela (Bolivarian Republic of)"`,
`"Bolivia (Plurinational State of)"` -> `None` (checked today). Safe direction (no penalty)
but the feature adds no evidence. Option: in `to_alpha2`, on a miss retry with a trailing
`" (...)"` stripped, *only* when the stripped stem resolves. Prefer the UAE-adapter approach
long-term (store alpha-2 alongside the name in `ingest/un.py`, `ofac.py`, `eu.py`, `uk.py`).

## L-164 — `rescreen_all` ignores `customers.nationalities` (MEDIUM, new)
`engine.py:522-535` selects `nationality` only and calls `screen(country=row["nationality"])`;
`cases/manager.py` onboarding calls `screen(countries=nationalities or [nationality])`.
A dual national (IN + PK) matching a listed person whose country is `Pakistan`:
onboarding alerts 1.0; the list-update re-screen scores 0.80 and raises nothing
(`probe_dual_nat_rescreen_2026_11_19.py`; control with PK only alerts). So a listing that
first appears at a refresh is missed for a dual national whose *second* nationality is the
listed one. Before #464 this was hidden because name-vs-code was always a mismatch.

```diff
--- a/amlkit/match/engine.py
+++ b/amlkit/match/engine.py
@@ def rescreen_all(
     for row in conn.execute(
-        "SELECT id, full_name, name_arabic, nationality, birth_date, gender"
+        "SELECT id, full_name, name_arabic, nationality, nationalities, birth_date, gender"
         " FROM customers WHERE status='active' AND org_id=?",
         (org_id,),
     ).fetchall():
         names = [n for n in (row["full_name"], row["name_arabic"]) if n and n.strip()]
+        try:
+            nats = [n for n in json.loads(row["nationalities"] or "[]") if n]
+        except (TypeError, ValueError):
+            nats = []
+        if row["nationality"] and row["nationality"] not in nats:
+            nats.insert(0, row["nationality"])
@@
             res = screen(
                 conn, nm, org_id=org_id, trigger="list_update", threshold=threshold,
-                country=row["nationality"], birth_date=row["birth_date"],
+                countries=nats or None, birth_date=row["birth_date"],
```
Test: `tests/test_rescreen.py` — onboard IN+PK, clear alerts in a fresh DB copy (or seed the
entity after onboarding), `rescreen_all` -> one alert. Also check other `screen()` callers that
re-screen a customer (periodic review, mobile rescreen, `cases/manager.py` edits) pass
`nationalities` the same way: `grep -n "country=row\[\"nationality\"\]\|country=cust" amlkit/`.

## L-165 — no scorer version on screening rows (needs decision; skeptic's point 3)
Nothing marks which scorer produced a "clear" `screenings` row, so the CS-27 exposure window
cannot be listed from data. Proposal: additive nullable `screenings.scorer_version TEXT`
(`_MIGRATIONS`), set from a `SCORER_VERSION = "2026-11-18-iso-country"` constant in
`match/scorer.py` at insert. Owner decision because it is a schema change.
