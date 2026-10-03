# amlkit Continuous-Improvement Kanban

Board consumed by the continuous-improvement tick. The tick picks the **top
item of `## Backlog`** as `next_item`, completes one additive cycle on
`gstack-work-branch`, then moves it to `## Done` with the commit SHA.

Seeded 2026-10-02 from the live open GitHub issue set (triage-summary and
recurring health-check issues excluded). Items are ordered high → low priority.
Scope rule: additive-only. Items that require editing existing route/DB/business
logic must be written up under `scripts/proposals/<item>.md` and left HELD, not
force-completed.

## Backlog

- [ ] #79 (high) retention_until migration: additive backfill script/migration for rows stored under the old 5-year rule
- [ ] #261 (medium) goAML serialize_goaml_xml institution-name coverage test (Originating/Beneficiary Bank from tx data)
- [ ] #267 (medium) record-retention/purge logic: regression tests pinning correct purge contract
- [ ] #253 (medium) UBO ownership-percentage validation/computation regression tests
- [ ] #313 (medium) Correct retention-period UI copy (10yr = firm policy, not CR 134/2025) — additive template/string change
- [ ] #73 (low) Move business logic out of api/app.py — analysis + proposal only (touches existing routes → HELD by scope rule)
- [ ] #40 (low) Refresh error handling hardening — scope TBD, likely proposal

## Held (needs human review — out of additive scope)

- [ ] #85 (critical) Register EU FSF token / set AMLKIT_EU_FSF_TOKEN — ops/secret action, not a code change this loop can make
- [ ] #84 (medium) Merge #83 + set AMLKIT_REGISTRATION_INVITE_CODE in Cloud Run — ops/deploy action
- [ ] #252 (medium) health-check re-flags #85 with no escalation — depends on #85 resolution

## In Progress

_(none)_

## Done

- [x] #268 (high) goAML org/transaction data is tenant-sourced (tests/test_goaml_tenant_data.py, 5 tests) — __SHA__ — 2026-10-03
- [x] #266 (high) Tenant-isolation regression suite (tests/test_tenant_isolation.py, 16 tests) — 400c5e0 — 2026-10-03
- [x] Bootstrap this Kanban board so the improvement loop has a real backlog to consume — 2026-10-02
