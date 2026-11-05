# HELD (lead 2026-11-05): BD1 reason/disposition pairs, CR-40 CI token scope, CS-5 refresh cadence

Status: **HELD for Nadhir's review.** Each fix changes existing business logic or the deploy workflow, so rule 3 bars the routine from applying it.
Reproduced on master `6560fb0` by `repro_lead/checks_2026_11_05.py` (exit 0 = still present).

## 1. BD1: disposition and reason code are never checked against each other (`amlkit/cases/review.py:244-262`)

`_validate` checks that the status and the reason code are each valid on their own. It never checks that they agree.
Repro output:
```
BD1  role.pep  false_positive  + confirmed_match  narrative=False -> accepted -> alerts.status='false_positive' awaiting_second_review=False
BD1  role.pep  true_positive   + different_dob    narrative=True  -> accepted -> alerts.status='true_positive' awaiting_second_review=False
BD1  sanction  false_positive  + confirmed_match  narrative=False -> accepted -> alerts.status='pending_review' awaiting_second_review=True
```
For sanctions alerts the four-eyes reviewer sees the contradiction. Non-sanctions alerts (PEP) close at once. The record then says "false positive / Confirmed match to the listed party". The `alerts` status is the one the system acts on, so a confirmed PEP ends up stored as cleared.

Proposed diff (review.py):
```python
+# Which reason codes make sense for which disposition. 'escalated' and
+# 'open' accept any code; the narrative rules still apply.
+_ALLOWED_CODES = {
+    "false_positive": {"different_dob", "different_nationality", "name_coincidence",
+                       "different_entity_type", "other"},
+    "true_positive": {"confirmed_match", "other"},
+}
+
 def _validate(status: str, reason_code: str, narrative: str) -> None:
     ...
+    allowed = _ALLOWED_CODES.get(status)
+    if allowed is not None and reason_code not in allowed:
+        raise ReviewError(
+            f"reason code {REASON_CODES[reason_code]!r} does not fit a "
+            f"{status.replace('_', ' ')} decision"
+        )
```
`insufficient_data` is left out of `false_positive` on purpose, because its label says "kept open for enquiry". Product decision: confirm this, or allow it.
Check before landing: `grep -rn "reason_code=" tests/` for existing tests that use a mismatched pair (they would start failing). Also decide what the bulk-dismiss form (`bulk_dismiss_alerts`, :508) should offer. It should list only the false-positive codes.
Test to add: a parametrised test over every (status, code) pair that asserts it is accepted or raises `ReviewError`.
Historical rows: do not rewrite them. A read-only query can count them: `SELECT count(*) FROM alerts a JOIN alert_reviews r ... WHERE status='false_positive' AND reason_code='confirmed_match'`. Run it on a copy of production data, not live.

BD2 (bulk-dismiss "Dismissed 0 alert(s)." shown as success) is INFO. Optional: flash a warning when the count is 0.

## 2. CR-40 / CI1: `EU_FSF_TOKEN` reaches pull-request runs (`.github/workflows/source-canary.yml:33,61,81,237,257`)

The workflow triggers on `pull_request` (line 33). The `sources` (61) and `heartbeat` (237) jobs have no job-level `if:`, and since #459 their steps get `secrets.EU_FSF_TOKEN` (81, 257). A branch in this repository controls `scripts/heartbeat.py` and the inline Python, so it can read the token. This repository is pushed to every day by automated sessions.

Proposed diff (applied to both steps):
```yaml
         env:
-          AMLKIT_EU_FSF_TOKEN: ${{ secrets.EU_FSF_TOKEN }}
+          AMLKIT_EU_FSF_TOKEN: ${{ github.event_name != 'pull_request' && secrets.EU_FSF_TOKEN || '' }}
```
A PR run then exercises the EU adapter's "token not configured" path, which is optional (`is_mandatory=False`). Scheduled, push and dispatch runs keep full coverage.
Extend `tests/test_workflow_env.py` with an assertion that no `secrets.` expression appears in a job that runs on `pull_request` unless it is guarded by `event_name`.

## 3. CS-5: the sanctions refresh runs at 00:00 and 20:00 UTC only (`source-canary.yml:579,591`)

`--schedule "0 */20 * * *"` fires at hours 0 and 20. The gaps are 20 h and 4 h, not "every 20 h" as the repository comments say. The staleness alarm is 24 h (`datasets.max_age_hours`), so a 20 h gap never alerts.

Proposed diff (both the create and the update branch):
```diff
-              --schedule "0 */20 * * *" \
+              --schedule "0 */4 * * *" \
```
Minute 0 stays clear of the :15 freeze check, which keeps the separation the workflow comment asks for. Cost: six refreshes plus `rescreen_all` a day instead of two. Check the refresh duration and the single-writer lock first (`/system/refresh` logs). Correct the "every 20h" comments in `match/engine.py` and next to the freeze-check job at the same time.
The legal weight depends on CS-13: does the 24 h clock run from designation or from confirmation? It stays MEDIUM until `corpus/` exists.
