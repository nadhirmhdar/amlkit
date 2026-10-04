# 2026-10-04 — groaml.grovisor.ae down: cold start outgrew the startup probe, replica head unrestorable

**Status:** fix in PR #396; production needs a replica reseed (owner action, below).
**Impact:** every request to groaml.grovisor.ae (and the raw Cloud Run URL) hung and
then failed with 503 (after ~260s) or 429 from Cloud Run's front end from roughly
20:30 UTC on 3 Oct. grovisor.ae, grotax.grovisor.ae and `/api/lead` were unaffected.

## Timeline (UTC, 3–4 Oct)

| when | what |
|---|---|
| 00:00:01 | litestream took its daily full snapshot (L9, 25.3 MB, TXID 1–0x225d) |
| 00:00–19:45 | ~2,400 **level-0** LTX files written, one per small write every 15–35 s; no compacted level appears in any restore plan |
| 12:21 | daily backup-verify: restore **562 s** (133 s on 30 Sep, 109 s on 1 Oct, 308 s on 2 Oct), integrity ok |
| 19:25–19:30 | deploy (manual re-run) booted in 108 s |
| 20:00:02 | Cloud Scheduler `/system/refresh` fired; recorded as failed (status 13) |
| 20:01–20:06 | deploy of #390 booted in 101 s while the refresh was still writing on the previous instance (two litestream writers on one replica, the overlap the deploy comments warn about) |
| 20:15–20:18 | last files on the replica: the refresh's bulk writes (7.5 MB + 6.9 MB), TXID 0x2bcc–0x2bdb |
| ~20:30 → | instance idled out (`--min-instances 0`); every later request needed a cold start |
| 02:00 (4 Oct) | cold start = restore ~2,400 files + integrity check + schema init; killed by the default 240 s TCP startup probe; requests 503/429 |
| 02:13–02:22 | deploy of #391: `Container failed to become healthy. Startup probes timed out after 4m` |
| 02:10–02:20 | on-demand restore of the replica head: `decode database: decode page 14267: copy page 14269 header: nonsequential page numbers in snapshot transaction: 14266,14269` |
| 02:25–02:39 | restore to `-timestamp 2026-10-03T19:50:00Z` (lands on TXID 0x2bcb, 19:45:43): **succeeds** in 766 s |
| 02:41–02:45 | `-timestamp 2026-10-03T20:30:00Z` and `23:59:30Z`: `timestamp does not exist` (no files after 20:18:33) |

## Two causes

1. **Cold-start time.** A restore downloads the newest snapshot and replays every LTX
   file after it. With one L0 file per write and nothing compacting them, a day is
   ~2,400 objects to fetch; the daily snapshot resets the chain at 00:00 UTC, so the
   restore is slowest just before midnight. Cloud Run gives a container 240 s by
   default; once the replay crossed that, every cold start was killed mid-restore.
   `--min-instances 0` made a cold start the normal path for the first request after
   any idle period.
2. **Replica head corrupt.** The 20:00 refresh on the old instance overlapped the
   20:01–20:06 rollout of the new one. Two `litestream replicate` processes wrote the
   same replica; the head (0x2bcc–0x2bdb) no longer decodes. A restore to 0x2bcb
   (19:45:43) is clean.

## Fix (PR #396)

- `litestream.yml`: `snapshot: {interval: 4h, retention: 24h}` caps the replay at 4 h.
- Deploy: `--min-instances 1` (a process stays up to snapshot; operators never hit the
  restore path), `--startup-probe` 600 s (Cloud Run maximum), `--cpu-boost`.
- `entrypoint.sh`: `-parallelism 16`, logs the restore time, warns above 120 s.
- `backup-verify`: prints the restore plan, fails at 300 s / warns at 150 s, and takes
  an optional `restore_point` (timestamp or TXID) for `workflow_dispatch`.

## Correction (added after PR #396)

The fix above, and the comments it put in `litestream.yml`, `scripts/entrypoint.sh`,
`source-canary.yml` and `CLAUDE.md`, said litestream only snapshots after
`snapshot.interval` of *continuous process uptime*, with no catch-up at startup.
That is wrong for the version in use (v0.5.16, unchanged in v0.5.17).
`Store.monitorCompactionLevel` in `store.go` starts each level's timer at 1 ns, so
the first attempt runs as soon as litestream starts, and then reschedules to the
next multiple of the interval on the UTC clock (`CompactionLevel.NextCompactionAt`
= `now.Truncate(interval) + interval`). `Store.CompactDB` takes a snapshot whenever
the newest one was created before the most recent grid boundary and the database
has moved past it. The timeline above agrees: the daily snapshot landed at
00:00:01 UTC. A local run of v0.5.17 logs `snapshot complete` about one second
after startup.

What still holds: at the 24h default a restore could replay up to a day of LTX files,
and 4h caps that. `--min-instances 1` is still what keeps operators off the restore
path. The reasoning that "a scaled-to-zero service never snapshots" does not hold,
and neither does the claim that the deploy needed a warm instance for snapshots to
fire. The deploy also runs with request-based CPU (no `--no-cpu-throttling`), so
litestream gets very little CPU between requests. Its 1 s replication loop and its
timers then run late, and WAL from the last request before an idle spell can sit
unreplicated. Since then, the app asks litestream to sync (`litestream sync -wait`
over the control socket, `amlkit/replication.py`, `AMLKIT_SYNC_REPLICA`) after the
sanctions refresh, report finalisation and freeze execution.

## Recovery runbook (owner)

The deploy can reseed the replica itself; no bucket write access outside the
service is needed (the Cloud Run runtime service account already replicates to
the bucket, while the GitHub Actions service accounts are read-only, which is
why `recovery-reseed.yml` has never completed).

1. Set repo variable `LITESTREAM_REPLICA_URL` to a **new** prefix, e.g.
   `gs://gen-lang-client-0153967509-aml-data/litestream-v3/amlkit.db`; keep
   `litestream-v2/` as evidence.
2. Run **Source canary** manually (Actions → Source canary → Run workflow, on
   `master`) with
   - `seed_from_url` = `gs://gen-lang-client-0153967509-aml-data/litestream-v2/amlkit.db`
   - `seed_txid` = `0000000000002bcb` (19:45:43 UTC, 3 Oct: the last point that
     restores cleanly; see the timeline).
   The container restores the source at that TXID, verifies it, and
   `litestream replicate` writes it to the new prefix. The deploy log shows
   `seed restore finished in …s` and `Seeded database verified`.
3. Confirm: `/health` answers, and a `backup-verify` run restores the new
   prefix with `integrity_check: ok`.
4. The next ordinary deploy (any push to master) drops the seed variables. Until
   then they are harmless: the entrypoint ignores them once the target has a
   replica.

What is lost: the 20:00 UTC automated sanctions refresh (list reload +
rescreen), which the next scheduled refresh recreates. No operator writes
happened after 19:45:43.

## Open follow-ups

- Why no L1–L3 compaction ever appears in the restore plan (litestream compacts L0
  every 30 s by default). Needs Cloud Run logs; candidates are CPU throttling between
  requests starving litestream's timers, or compaction errors against GCS. If it is
  throttling, `--no-cpu-throttling` fixes it at the cost of an always-allocated vCPU.
- What writes one page every 15–35 s around the clock (the 1,031-byte L0 files at
  00:00:02, 00:00:15, 00:00:33 …). Fewer writes means fewer files to replay.
- The deploy still overlaps two litestream writers for the length of a rollout; that
  needs a lease, or a pre-deploy drain of the old instance.
- Cloud Scheduler's `/system/refresh` at 20:00 UTC has been failing (status 13); with
  the service back it should be re-checked.
