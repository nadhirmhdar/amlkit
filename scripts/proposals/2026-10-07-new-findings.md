# HELD: findings from the 2026-10-07 run (not applied; additive-only)
Evidence: reports/daily/2026-10-07/evidence/*_on_0129848.txt

## N8 Legacy pending proposals stay rename-bypassable (db.py `alert_reviews.operator_id`)
#426 stores `operator_id` on new proposals and compares ids when both sides carry one, else falls back to names. Every `pending_review` row created before the deploy has `operator_id = NULL`, so the rename bypass still works for those until they are resolved (probe_csrf_session section 1: seeded proposal without id -> `('BRAVO-officer','propose'), ('Renamed Officer','confirm')`; section 1b: route-created proposal -> refused).
Because `operators` is UNIQUE (org_id, name), a one-time backfill is exact for rows whose proposer has not been renamed since:
```sql
UPDATE alert_reviews SET operator_id = (
  SELECT o.id FROM operators o JOIN alerts a ON a.org_id = o.org_id
  WHERE a.id = alert_reviews.alert_id AND o.name = alert_reviews.operator)
WHERE operator_id IS NULL AND action = 'propose';
```
(run once in `_initialise`, idempotent; leave rows it cannot match as NULL).

## M2 TOTP code replay (auth.py `mfa_verify`)
`totp.verify(code, valid_window=1)` keeps no record of the last accepted time step, so one code works for several sessions within about 90 seconds (probe_mfa section 2: two separate locked sessions both verified with the same code). Proposal: store `last_used_step` on `mfa_secrets` (additive column) and reject any step <= it; use `totp.timecode(now)` to compute the matched step.

## INFO items (no action proposed)
- Lockout is per operator: a password-holder who misses 5 codes locks the real MLRO's MFA for 15 minutes (probe_mfa section 4). Inherent trade-off.
- `purge_expired` purges a closed customer whose `exit_date` is NULL on `retention_until` alone (`_inside_policy_window` returns False without an anchor). `close_relationship` always sets `exit_date`, so no current path produces that row (probe_retention_purge).
- `alert_queue` (#421) reads every matching alert of the org per call: 0.66 s per call and 1.3 s per dashboard at 50,000 open alerts (probe_alert_queue_scale). Each alert needs a real list hit, so it is bounded in practice.
