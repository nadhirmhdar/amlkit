# HELD: transaction-monitoring evasions and edge cases
Status: HELD (screening/kyt.py, cases/manager.py, api/app.py). Evidence: probe_kyt.txt, probe_cache.txt.

K1 Out-of-order entry: `evaluate_transaction` only reads `occurred_at <= current` (kyt.py:216). 54,999 on day 5 then day 0 -> no alert; in order -> alert. Fix: query `occurred_at BETWEEN t-W AND t+W` (exclude self).
K2 `amount_aed` overrides `amount` even when currency=AED (manager.py:737, route app.py:2330): 100,000 AED with amount_aed=1 -> no rule. Fix: when currency is AED, ignore or require equality; reject amount_aed <= 0.
K3 `amount` = nan/inf/1e30 raise InvalidOperation/OverflowError; route catches only ValueError/PermissionError -> HTTP 500. Fix: `math.isfinite` check in `record_transaction`.
K4 Config cache keyed `(id(conn), org_id)` (kyt.py:96): CPython reuses `id()` of a closed connection, so a fresh connection returned the old threshold in 200/200 trials for up to 300 s. Fix: drop the cache, or key on `PRAGMA data_version` / `org_settings.updated_at`.
K5 `save_rule_config` accepts NaN (stored as NULL, silently reverts to default); alert threshold (`/admin/threshold`) has no floor. Fix: `math.isfinite`; floor (e.g. 0.70) or four-eyes on lowering.
K6 Design gaps (policy decision, not bugs): wires/cheques never aggregate (5 x 54,999 wire/day = no alert until velocity > 5); 7-day window only; no cross-customer aggregation by ID number or counterparty.
