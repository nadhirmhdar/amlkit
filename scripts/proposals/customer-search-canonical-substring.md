# L-56: customer search returns unrelated customers for repeated-letter or very short queries (HELD)

Status: HELD for human review (changes query logic in `amlkit/queries.py`). Severity: LOW.
Raised by mlro-user (C4, 2026-10-14); root-caused by the lead 2026-10-15 on master `0129848`.

## What happens
`search_customers()` (`amlkit/queries.py:724-767`) ORs four clauses. The fourth is
`AND` over `c.canonical_key LIKE '%<token>%'` for each `canonical_tokens(query)`.
Canonicalisation collapses repeated letters and drops vowels, so:

- `canonical_tokens('a' * 2000) == ['a']` and `canonical_tokens('aa') == ['a']`
- `'%a%'` matches every canonical key containing an `a` (`ahmed`, `fatima`).

Repro (`repro_lead/checks_2026_10_15.py`, exit 0):
```
L-56 search 'a'*2000 -> ['Q-001', 'Q-002']; search 'aa' -> ['Q-001', 'Q-002'] -> reproduces=True
```
Nothing truncates the query; the earlier guess that truncation was involved is wrong.
Impact: search UI only (screening uses `blocking_keys`, not this function). No cross-tenant
effect (`c.org_id = ?` is kept). An MLRO who searches for a name and sees unrelated
customers is mildly misled; an empty result would be more accurate.

## Proposed diff (not applied)
Drop canonical tokens shorter than 2 characters (they match almost every key) and cap
the query at 200 characters, as `/screen` does (`app.py:1675`). Keep the substring match:

```diff
-    tokens = canonical_tokens(query)
+    tokens = [t for t in canonical_tokens(query[:200]) if len(t) >= 2]
```

The lead checked this filter against the repro keys (simulated in Python, not applied):
`'a'*2000 -> []`, `'aa' -> []`, `'jaleel' -> Q-001`, `'Ahmad Jalil' -> Q-001`,
`'احمد عبد الجليل' -> Q-001`, `'Fatima' -> Q-002`.
A token-boundary (prefix) match was also tried and **rejected**: `Abd Al-Jaleel`
canonicalises to the single token `abdljl`, so a prefix match on `jl` loses the
`'Ahmad Jalil'` transliteration hit. The docstring's "prefix match" wording should be
corrected to "substring match" in the same change.

Test to add with the fix: search `'a'*2000` and `'aa'` over the four repro customers
returns `[]`; `'jaleel'`, `'Ahmad Jalil'` and the Arabic variants in the mlro-user
2026-10-14 driver still return Q-001.
