# groAML monitoring (Cloud Monitoring / Cloud Logging)

Idempotent `gcloud` scripts for the owner to run; nothing here is applied by CI.
Re-running any script updates the existing resource instead of duplicating it.

## Run

```bash
export PROJECT=<gcp-project-id>        # required; no project is hard-coded
export REGION=<cloud-run-region>       # default me-central1 (only informational)
# optional: SERVICE (amlkit), HOST (groaml.grovisor.ae),
#           ALERT_EMAIL (info@grovisor.ae), NOTIFICATION_CHANNEL (existing channel resource name)
bash scripts/monitoring/apply-all.sh
```

Needs `gcloud` authenticated with Monitoring Editor + Logs Configuration Writer.
Without `NOTIFICATION_CHANNEL`, an email channel for `ALERT_EMAIL` is found or created.
The `gcloud monitoring uptime|policies|dashboards|channels` surfaces are used as
documented; if your gcloud is old, use `gcloud alpha monitoring ...` (same flags).

## What gets created

| Script | Resource |
|---|---|
| `01-uptime-check.sh` | HTTPS uptime check `groAML /health` on `https://$HOST/health` (1 min) |
| `02-log-metrics.sh` | `amlkit_freeze_overdue` (hourly freeze-check runs with `overdue_count > 0`), `amlkit_5xx` (Cloud Run request logs, status >= 500) |
| `03-alert-policies.sh` | 5xx rate > 1% over 10 min; overdue freezes > 0; uptime failure; litestream sync failure |
| `04-dashboard.sh` | Dashboard from `dashboard.json`: request rate, latency p95, 5xx, instance count, overdue freezes |

## Log sources in the app

- `amlkit/ops.py` logs one line per `/system/check-freeze-obligations` run:
  message `freeze_obligation_check overdue_count=N org_count=M`, JSON fields `overdue_count`, `org_count`.
- One line per `/system/refresh` run: message `sanctions_refresh ...`, fields `duration_seconds`,
  `dataset_counts` (per dataset), `failure_count`, `mandatory_failure_count`, `new_alerts`.
- `amlkit/replication.py` warns `replica sync (<reason>) failed|timed out|errored`; the sync-failure
  policy matches those (the benign "skipped" warning is excluded).

## Notes

- The freeze-overdue policy evaluates hourly (the Scheduler job's cadence) and auto-closes after 2 h;
  it re-fires every hour while an obligation stays overdue.
- The 5xx policy uses the built-in `run.googleapis.com/request_count` ratio so it is a true rate;
  `amlkit_5xx` feeds the dashboard and ad-hoc log queries.
- Service is pinned to one instance (`--max-instances 1`), so "instance count" going to 0 or 2 is itself notable.
- `/admin/ops` in the app shows the same state per MLRO (datasets, replica, queues, build SHA).
